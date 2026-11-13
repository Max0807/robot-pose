using System.Net;
using System.Net.Sockets;
using Chat.Client;
using Chat.Protocol;
using Chat.Server;

namespace Chat.Tests;

internal static class NetworkTests
{
    private static ChatServer Start(TimeSpan? registrationTimeout = null)
    {
        var server = new ChatServer(IPAddress.Loopback, 0, registrationTimeout: registrationTimeout);
        server.Start();
        return server;
    }
    private static Task<ChatClient> Connect(ChatServer server, string name) => ChatClient.ConnectAsync("127.0.0.1", server.Port, name);
    private static async Task<ChatMessage> Read(ChatClient client)
    {
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5));
        return await client.ReceiveAsync(timeout.Token) ?? throw new IOException("意外 EOF");
    }
    private static async Task<ChatMessage?> ReadRaw(FramedConnection connection)
    {
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5));
        return await connection.ReceiveAsync(timeout.Token);
    }

    public static IEnumerable<TestCase> Cases()
    {
        yield return new("network.bidirectional_utf8_and_online_list", async () =>
        {
            await using var server = Start();
            await using var alice = await Connect(server, "Alice");
            await using var bob = await Connect(server, "Bob");
            string id = await alice.SendChatAsync("bOB", "你好 Bob 🙂\n第二行");
            ChatMessage message = await Read(bob);
            Check.Equal("Alice", message.Sender); Check.Equal("Bob", message.Receiver);
            Check.Equal(id, message.MessageId); Check.Equal("你好 Bob 🙂\n第二行", message.Content);
            Check.Equal(MessageTypes.Forwarded, (await Read(alice)).Type);
            string reply = await bob.SendChatAsync("Alice", "收到，双向通信正常");
            Check.Equal(reply, (await Read(alice)).MessageId);
            Check.Equal(MessageTypes.Forwarded, (await Read(bob)).Type);
            await alice.RequestUsersAsync();
            var users = await Read(alice);
            Check.Equal(MessageTypes.Users, users.Type); Check.Equal("Alice, Bob", users.Content);
        });
        yield return new("network.many_senders_one_recipient", async () =>
        {
            await using var server = Start();
            await using var alice = await Connect(server, "Alice");
            await using var bob = await Connect(server, "Bob");
            await using var carol = await Connect(server, "Carol");
            const int count = 40;
            Task<string[]> first = Task.WhenAll(Enumerable.Range(0, count).Select(index => alice.SendChatAsync("Bob", $"A消息{index}🙂")));
            Task<string[]> second = Task.WhenAll(Enumerable.Range(0, count).Select(index => carol.SendChatAsync("Bob", $"C消息{index}中文")));
            string[][] sent = await Task.WhenAll(first, second);
            var ids = sent.SelectMany(values => values).ToHashSet();
            for (int index = 0; index < 2 * count; index++)
            {
                var message = await Read(bob);
                Check.Equal(MessageTypes.Chat, message.Type); Check.True(ids.Remove(message.MessageId), "消息丢失、重复或编号错误");
            }
            Check.Equal(0, ids.Count);
            foreach (var sender in new[] { alice, carol })
                for (int index = 0; index < count; index++) Check.Equal(MessageTypes.Forwarded, (await Read(sender)).Type);
        });
        yield return new("network.duplicate_name_keeps_original_session", async () =>
        {
            await using var server = Start();
            await using var alice = await Connect(server, "Alice");
            await Check.ThrowsAsync<IOException>(async () => { await using var duplicate = await Connect(server, "aLiCe"); }, "name_in_use");
            await alice.RequestUsersAsync();
            Check.Equal("Alice", (await Read(alice)).Content);
            Check.Equal(1, server.OnlineUsers.Count);
        });
        yield return new("network.offline_error_does_not_disconnect_sender", async () =>
        {
            await using var server = Start();
            await using var alice = await Connect(server, "Alice");
            string id = await alice.SendChatAsync("Nobody", "在线吗");
            var error = await Read(alice);
            Check.Equal(MessageTypes.Error, error.Type); Check.Equal(id, error.MessageId);
            Check.True(error.Content.StartsWith("recipient_offline:", StringComparison.Ordinal));
            await alice.RequestUsersAsync();
            Check.Equal(MessageTypes.Users, (await Read(alice)).Type);
        });
        yield return new("network.registration_required_and_bound_sender", async () =>
        {
            await using var server = Start();
            using (var tcp = new TcpClient())
            {
                await tcp.ConnectAsync(IPAddress.Loopback, server.Port);
                await using var wire = new FramedConnection(tcp.GetStream());
                await wire.SendAsync(ChatMessage.Create(MessageTypes.Chat, "Imposter", "Bob", "未注册"));
                Check.True((await ReadRaw(wire))!.Content.StartsWith("registration_required:", StringComparison.Ordinal));
                Check.Equal<ChatMessage?>(null, await ReadRaw(wire));
            }
            using var raw = new TcpClient();
            await raw.ConnectAsync(IPAddress.Loopback, server.Port);
            await using var connection = new FramedConnection(raw.GetStream());
            await connection.SendAsync(ChatMessage.Create(MessageTypes.Register, "Alice", "server", ""));
            Check.Equal(MessageTypes.RegisterOk, (await ReadRaw(connection))!.Type);
            await using var bob = await Connect(server, "Bob");
            await connection.SendAsync(ChatMessage.Create(MessageTypes.Chat, "Carol", "Bob", "冒用发送者"));
            Check.True((await ReadRaw(connection))!.Content.StartsWith("sender_mismatch:", StringComparison.Ordinal));
            await connection.SendAsync(ChatMessage.Create(MessageTypes.Chat, "Alice", "Bob", "身份正确"));
            Check.Equal("身份正确", (await Read(bob)).Content);
        });
        yield return new("network.malformed_peer_isolated", async () =>
        {
            await using var server = Start();
            await using var alice = await Connect(server, "Alice");
            using var bad = new TcpClient();
            await bad.ConnectAsync(IPAddress.Loopback, server.Port);
            await bad.GetStream().WriteAsync(new byte[] { 0, 1, 0, 1 }); // 65537，大于帧长上限
            byte[] buffer = new byte[1];
            using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5));
            Check.Equal(0, await bad.GetStream().ReadAsync(buffer, timeout.Token));
            await alice.RequestUsersAsync();
            Check.Equal("Alice", (await Read(alice)).Content);
        });
        yield return new("network.registration_timeout_and_half_frame", async () =>
        {
            await using var server = Start(TimeSpan.FromMilliseconds(150));
            using var idle = new TcpClient();
            await idle.ConnectAsync(IPAddress.Loopback, server.Port);
            await idle.GetStream().WriteAsync(new byte[] { 0, 0 });
            byte[] buffer = new byte[1];
            using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5));
            Check.Equal(0, await idle.GetStream().ReadAsync(buffer, timeout.Token));
            await Check.EventuallyAsync(() => server.ConnectionCount == 0, "注册超时连接未清理");
        });
        yield return new("network.single_reader_and_cancelled_read", async () =>
        {
            await using var server = Start();
            using var tcp = new TcpClient();
            await tcp.ConnectAsync(IPAddress.Loopback, server.Port);
            await using var wire = new FramedConnection(tcp.GetStream());
            using var cancel = new CancellationTokenSource();
            Task<ChatMessage?> first = wire.ReceiveAsync(cancel.Token);
            await Check.ThrowsAsync<InvalidOperationException>(async () => await wire.ReceiveAsync());
            Check.True(!wire.IsClosed);
            cancel.Cancel();
            await Check.ThrowsAsync<OperationCanceledException>(async () => await first);
            Check.True(wire.IsClosed);
        });
        yield return new("network.disconnect_cleanup_and_reconnect", async () =>
        {
            await using var server = Start();
            var alice = await Connect(server, "Alice");
            alice.Dispose();
            await Check.EventuallyAsync(() => server.OnlineUsers.Count == 0, "断线用户名未清理");
            await using var replacement = await Connect(server, "Alice");
            await replacement.RequestUsersAsync();
            Check.Equal("Alice", (await Read(replacement)).Content);
            await replacement.QuitAsync();
            await Check.EventuallyAsync(() => server.ConnectionCount == 0, "退出连接未清理");
        });
        yield return new("network.server_shutdown_releases_all_connections", async () =>
        {
            await using var server = Start();
            await using var alice = await Connect(server, "Alice");
            using var unregistered = new TcpClient();
            await unregistered.ConnectAsync(IPAddress.Loopback, server.Port);
            await server.StopAsync().WaitAsync(TimeSpan.FromSeconds(5));
            Check.Equal(0, server.ConnectionCount);
            Check.Equal(0, server.OnlineUsers.Count);
            Check.Equal<ChatMessage?>(null, await alice.ReceiveAsync());
        });
    }
}
