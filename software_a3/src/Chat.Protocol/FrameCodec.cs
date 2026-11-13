using System.Buffers.Binary;
using System.Text.Encodings.Web;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Chat.Protocol;

public static class FrameCodec
{
    public const int HeaderBytes = 4;
    public const int MaxFrameBytes = 64 * 1024;
    private static readonly JsonSerializerOptions Options = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        PropertyNameCaseInsensitive = false,
        UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow,
        Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
        MaxDepth = 8
    };

    public static byte[] Encode(ChatMessage message)
    {
        MessageRules.Validate(message);
        byte[] body = JsonSerializer.SerializeToUtf8Bytes(message, Options);
        if (body.Length is <= 0 or > MaxFrameBytes)
            throw new ProtocolException("invalid_frame_length: JSON 帧体不得超过 64 KiB。");
        byte[] frame = new byte[HeaderBytes + body.Length];
        // 帧头 N 是整段 JSON 的长度，不是 ContentLength。
        BinaryPrimitives.WriteInt32BigEndian(frame.AsSpan(0, HeaderBytes), body.Length);
        body.CopyTo(frame.AsSpan(HeaderBytes));
        return frame;
    }

    public static async ValueTask<ChatMessage?> ReadAsync(Stream stream, CancellationToken cancellationToken = default)
    {
        byte[] header = new byte[HeaderBytes];
        // 首次读取为 0 表示两帧之间正常关闭；读到一部分后 EOF 则是截断。
        int first = await stream.ReadAsync(header.AsMemory(), cancellationToken).ConfigureAwait(false);
        if (first == 0) return null;
        try
        {
            await stream.ReadExactlyAsync(header.AsMemory(first), cancellationToken).ConfigureAwait(false);
        }
        catch (EndOfStreamException error)
        {
            throw new ProtocolException("truncated_header: 连接在帧头中途关闭。", error);
        }
        int length = BinaryPrimitives.ReadInt32BigEndian(header);
        if (length is <= 0 or > MaxFrameBytes)
            throw new ProtocolException("invalid_frame_length: 帧体长度必须在 1 到 65536 字节之间。");
        byte[] body = new byte[length];
        try
        {
            await stream.ReadExactlyAsync(body.AsMemory(), cancellationToken).ConfigureAwait(false);
        }
        catch (EndOfStreamException error)
        {
            throw new ProtocolException("truncated_body: 连接在帧体中途关闭。", error);
        }
        ChatMessage message;
        try
        {
            message = JsonSerializer.Deserialize<ChatMessage>(body, Options)
                ?? throw new ProtocolException("invalid_json: 帧体不能是 null。");
        }
        catch (JsonException error)
        {
            throw new ProtocolException("invalid_json: JSON / UTF-8 格式或必需字段无效。", error);
        }
        MessageRules.Validate(message);
        return message;
    }
}
