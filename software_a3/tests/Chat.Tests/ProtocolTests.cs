using System.Buffers.Binary;
using System.Text;
using Chat.Protocol;

namespace Chat.Tests;

internal static class ProtocolTests
{
    private static ChatMessage Sample(string content = "你好🙂\n with spaces") =>
        ChatMessage.Create(MessageTypes.Chat, "Alice", "Bob", content, "test-1");

    public static IEnumerable<TestCase> Cases()
    {
        yield return new("protocol.utf8_length_and_roundtrip", async () =>
        {
            ChatMessage original = Sample();
            Check.Equal(Encoding.UTF8.GetByteCount(original.Content), original.ContentLength);
            Check.True(original.ContentLength != original.Content.Length);
            byte[] frame = FrameCodec.Encode(original);
            Check.Equal(frame.Length - 4, BinaryPrimitives.ReadInt32BigEndian(frame));
            Check.True(frame.Length - 4 > original.ContentLength);
            using var stream = new MemoryStream(frame);
            Check.Equal(original, await FrameCodec.ReadAsync(stream));
            Check.Equal<ChatMessage?>(null, await FrameCodec.ReadAsync(stream));
        });
        foreach (int chunk in new[] { 1, 2, 3, 7 })
        {
            int size = chunk;
            yield return new($"protocol.fragmented_header_body_{size}", async () =>
            {
                using var stream = new ChunkedReadStream(FrameCodec.Encode(Sample()), size);
                Check.Equal(Sample(), await FrameCodec.ReadAsync(stream));
            });
        }
        yield return new("protocol.coalesced_frames", async () =>
        {
            var messages = Enumerable.Range(0, 30).Select(index => Sample($"消息 {index} 中文🙂")).ToArray();
            byte[] joined = messages.SelectMany(FrameCodec.Encode).ToArray();
            using var stream = new ChunkedReadStream(joined, 11);
            foreach (var message in messages) Check.Equal(message, await FrameCodec.ReadAsync(stream));
            Check.Equal<ChatMessage?>(null, await FrameCodec.ReadAsync(stream));
        });
        yield return new("protocol.clean_eof", async () =>
        {
            using var stream = new MemoryStream();
            Check.Equal<ChatMessage?>(null, await FrameCodec.ReadAsync(stream));
        });
        yield return new("protocol.truncated_header_and_body", async () =>
        {
            byte[] frame = FrameCodec.Encode(Sample());
            foreach (int length in new[] { 1, 2, 3, 4, frame.Length - 1 })
            {
                using var stream = new ChunkedReadStream(frame[..length], 1);
                await Check.ThrowsAsync<ProtocolException>(async () => await FrameCodec.ReadAsync(stream), "truncated_");
            }
        });
        yield return new("protocol.reject_invalid_frame_lengths", async () =>
        {
            foreach (int length in new[] { 0, -1, FrameCodec.MaxFrameBytes + 1, int.MaxValue })
            {
                byte[] header = new byte[4];
                BinaryPrimitives.WriteInt32BigEndian(header, length);
                using var stream = new MemoryStream(header);
                await Check.ThrowsAsync<ProtocolException>(async () => await FrameCodec.ReadAsync(stream), "invalid_frame_length");
            }
        });
        yield return new("protocol.reject_invalid_json_fields", async () =>
        {
            const string valid = "{\"type\":\"chat\",\"sender\":\"Alice\",\"receiver\":\"Bob\",\"contentLength\":6,\"content\":\"你好\",\"messageId\":\"x\"}";
            foreach (string body in new[] { "null", "{", "{}", valid.Replace("\"contentLength\":6", "\"contentLength\":2"),
                valid.Replace("\"chat\"", "\"unknown\""), valid.Replace("\"x\"}", "\"x\",\"extra\":true}"),
                valid.Replace("\"sender\":\"Alice\"", "\"sender\":null") })
            {
                using var stream = new MemoryStream(RawFrame(Encoding.UTF8.GetBytes(body)));
                await Check.ThrowsAsync<ProtocolException>(async () => await FrameCodec.ReadAsync(stream));
            }
            using var invalidUtf8 = new MemoryStream(RawFrame([0xff, 0xff]));
            await Check.ThrowsAsync<ProtocolException>(async () => await FrameCodec.ReadAsync(invalidUtf8));
        });
        yield return new("protocol.content_limit_and_unicode", async () =>
        {
            FrameCodec.Encode(Sample(new string('a', MessageRules.MaxContentBytes)));
            await Check.ThrowsAsync<ProtocolException>(() => Task.Run(() => FrameCodec.Encode(Sample(new string('a', MessageRules.MaxContentBytes + 1)))));
            await Check.ThrowsAsync<EncoderFallbackException>(() => Task.Run(() => Sample("\ud800")));
            Check.True(NameRules.IsUserName("Alice_1"));
            Check.True(!NameRules.IsUserName("SERVER") && !NameRules.IsUserName("1Alice") && !NameRules.IsUserName("张三"));
        });
        yield return new("connection.serialize_concurrent_writes", async () =>
        {
            using var stream = new RecordingStream();
            await using var connection = new FramedConnection(stream);
            ChatMessage[] messages = Enumerable.Range(0, 60).Select(index => Sample($"消息 {index}") with { MessageId = $"id-{index}" }).ToArray();
            await Task.WhenAll(messages.Select(message => connection.SendAsync(message)));
            Check.True(!stream.Overlapped, "出现并发写入");
            using var read = new MemoryStream(stream.Bytes);
            var ids = new HashSet<string>();
            for (int index = 0; index < messages.Length; index++) ids.Add((await FrameCodec.ReadAsync(read))!.MessageId);
            Check.Equal(messages.Length, ids.Count);
            Check.Equal<ChatMessage?>(null, await FrameCodec.ReadAsync(read));
        });
        yield return new("connection.partial_write_closes_transport", async () =>
        {
            using var stream = new FailingWriteStream();
            await using var connection = new FramedConnection(stream);
            await Check.ThrowsAsync<IOException>(() => connection.SendAsync(Sample()));
            Check.True(connection.IsClosed && stream.WasDisposed);
            await Check.ThrowsAsync<ObjectDisposedException>(() => connection.SendAsync(Sample()));
        });
        yield return new("connection.cancel_waiting_writer_preserves_transport", async () =>
        {
            using var stream = new BlockingWriteStream();
            await using var connection = new FramedConnection(stream);
            Task first = connection.SendAsync(Sample());
            await stream.Entered.Task;
            using var cancelled = new CancellationTokenSource();
            Task waiting = connection.SendAsync(Sample(), cancelled.Token);
            cancelled.Cancel();
            await Check.ThrowsAsync<OperationCanceledException>(() => waiting);
            Check.True(!connection.IsClosed);
            stream.Release.SetResult();
            await first;
            await connection.SendAsync(Sample("仍可使用"));
        });
        yield return new("connection.cancel_started_write_closes_transport", async () =>
        {
            using var stream = new BlockingWriteStream();
            await using var connection = new FramedConnection(stream);
            using var cancelled = new CancellationTokenSource();
            Task sending = connection.SendAsync(Sample(), cancelled.Token);
            await stream.Entered.Task;
            cancelled.Cancel();
            await Check.ThrowsAsync<OperationCanceledException>(() => sending);
            Check.True(connection.IsClosed && stream.WasDisposed);
        });
    }

    internal static byte[] RawFrame(byte[] body)
    {
        byte[] frame = new byte[4 + body.Length];
        BinaryPrimitives.WriteInt32BigEndian(frame, body.Length);
        body.CopyTo(frame, 4);
        return frame;
    }
}
