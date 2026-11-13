using System.Collections.Concurrent;
using System.Net;
using System.Net.Sockets;
using Chat.Protocol;

namespace Chat.Server;

public sealed class ChatServer : IAsyncDisposable
{
    private readonly TcpListener _listener;
    private readonly Action<string> _log;
    private readonly TimeSpan _registrationTimeout;
    private readonly TimeSpan _sendTimeout;
    private readonly CancellationTokenSource _shutdown = new();
    private readonly ConcurrentDictionary<string, ClientSession> _users = new(StringComparer.OrdinalIgnoreCase);
    private readonly ConcurrentDictionary<long, TcpClient> _connections = new();
    private readonly ConcurrentDictionary<long, Task> _handlers = new();
    private Task? _acceptLoop;
    private long _nextId;
    private int _started;

    public ChatServer(IPAddress address, int port, Action<string>? log = null,
        TimeSpan? registrationTimeout = null, TimeSpan? sendTimeout = null)
    {
        _listener = new TcpListener(address, port);
        _log = log ?? (_ => { });
        _registrationTimeout = registrationTimeout ?? TimeSpan.FromSeconds(10);
        _sendTimeout = sendTimeout ?? TimeSpan.FromSeconds(5);
    }

    public int Port => ((IPEndPoint)_listener.LocalEndpoint).Port;
    public IReadOnlyList<string> OnlineUsers => _users.Values.Where(session => session.IsReady)
        .Select(session => session.UserName).Order(StringComparer.OrdinalIgnoreCase).ToArray();
    public int ConnectionCount => _connections.Count;
    public Task Completion => _acceptLoop ?? Task.CompletedTask;

    public void Start()
    {
        if (Interlocked.Exchange(ref _started, 1) != 0) throw new InvalidOperationException("服务器已启动。");
        _listener.Start();
        _acceptLoop = AcceptLoopAsync();
    }

    private async Task AcceptLoopAsync()
    {
        try
        {
            while (!_shutdown.IsCancellationRequested)
            {
                TcpClient client = await _listener.AcceptTcpClientAsync(_shutdown.Token).ConfigureAwait(false);
                if (_shutdown.IsCancellationRequested) { client.Dispose(); break; }
                client.NoDelay = true; // 降低交互延迟；分帧仍由 FrameCodec 处理。
                long id = Interlocked.Increment(ref _nextId);
                _connections[id] = client;
                Task task = HandleClientAsync(id, client);
                _handlers[id] = task;
                _ = ObserveHandlerAsync(id, task);
            }
        }
        catch (OperationCanceledException) when (_shutdown.IsCancellationRequested) { }
        catch (SocketException) when (_shutdown.IsCancellationRequested) { }
        catch (ObjectDisposedException) when (_shutdown.IsCancellationRequested) { }
    }

    private async Task ObserveHandlerAsync(long id, Task task)
    {
        try { await task.ConfigureAwait(false); }
        catch (Exception error) { _log($"HANDLER_ERROR {error.GetType().Name}: {error.Message}"); }
        finally { _handlers.TryRemove(id, out _); }
    }

    private async Task HandleClientAsync(long id, TcpClient client)
    {
        await using var connection = new FramedConnection(client.GetStream());
        ClientSession? session = null;
        try
        {
            ChatMessage? registration;
            using (var deadline = CancellationTokenSource.CreateLinkedTokenSource(_shutdown.Token))
            {
                deadline.CancelAfter(_registrationTimeout);
                registration = await connection.ReceiveAsync(deadline.Token).ConfigureAwait(false);
            }
            if (registration is null) return;
            if (registration.Type != MessageTypes.Register ||
                !string.Equals(registration.Receiver, NameRules.Server, StringComparison.OrdinalIgnoreCase))
            {
                await ErrorAsync(connection, registration.Sender, registration.MessageId, "registration_required: 首条消息必须是 register。").ConfigureAwait(false);
                return;
            }
            if (!NameRules.IsUserName(registration.Sender))
            {
                await ErrorAsync(connection, registration.Sender, registration.MessageId, "invalid_name: server 为保留名称。").ConfigureAwait(false);
                return;
            }
            session = new ClientSession(registration.Sender, client, connection);
            if (!_users.TryAdd(session.UserName, session))
            {
                await ErrorAsync(connection, session.UserName, registration.MessageId, "name_in_use: 用户名已在线，大小写不区分。").ConfigureAwait(false);
                return;
            }
            await SendAsync(connection, ChatMessage.Create(MessageTypes.RegisterOk, NameRules.Server,
                session.UserName, "注册成功", registration.MessageId)).ConfigureAwait(false);
            session.MarkReady();
            _log($"ONLINE {session.UserName}");
            while (!_shutdown.IsCancellationRequested)
            {
                ChatMessage? message = await connection.ReceiveAsync(_shutdown.Token).ConfigureAwait(false);
                if (message is null) break;
                if (!string.Equals(message.Sender, session.UserName, StringComparison.OrdinalIgnoreCase))
                {
                    await ErrorAsync(connection, session.UserName, message.MessageId, "sender_mismatch: 发送方必须与注册连接一致。").ConfigureAwait(false);
                    continue;
                }
                if (message.Type == MessageTypes.Chat)
                {
                    await ForwardAsync(session, connection, message).ConfigureAwait(false);
                }
                else if (message.Type == MessageTypes.UsersRequest && IsForServer(message))
                {
                    await SendAsync(connection, ChatMessage.Create(MessageTypes.Users, NameRules.Server,
                        session.UserName, string.Join(", ", OnlineUsers), message.MessageId)).ConfigureAwait(false);
                }
                else if (message.Type == MessageTypes.Quit && IsForServer(message)) break;
                else
                {
                    await ErrorAsync(connection, session.UserName, message.MessageId, "invalid_operation: 当前消息类型或接收方不适用。").ConfigureAwait(false);
                }
            }
        }
        catch (OperationCanceledException) when (_shutdown.IsCancellationRequested) { }
        catch (OperationCanceledException) { _log($"TIMEOUT connection={id}"); }
        catch (ProtocolException error) { _log($"PROTOCOL_ERROR connection={id} {error.Message}"); }
        catch (IOException error) { _log($"IO_CLOSED connection={id} {error.Message}"); }
        catch (ObjectDisposedException) { }
        catch (SocketException error) { _log($"SOCKET_CLOSED connection={id} {error.SocketErrorCode}"); }
        finally
        {
            if (session is not null)
            {
                session.Dispose();
                // 比较值后原子删除，旧连接清理不会误删同名的新连接。
                if (_users.TryRemove(new KeyValuePair<string, ClientSession>(session.UserName, session)))
                    _log($"OFFLINE {session.UserName}");
            }
            _connections.TryRemove(id, out _);
            client.Dispose();
        }
    }

    private static bool IsForServer(ChatMessage message) =>
        string.Equals(message.Receiver, NameRules.Server, StringComparison.OrdinalIgnoreCase);

    private async Task ForwardAsync(ClientSession sender, FramedConnection connection, ChatMessage message)
    {
        if (!_users.TryGetValue(message.Receiver, out var recipient))
        {
            await ErrorAsync(connection, sender.UserName, message.MessageId, "recipient_offline: 接收方不在线。").ConfigureAwait(false);
            return;
        }
        try
        {
            using var deadline = CancellationTokenSource.CreateLinkedTokenSource(_shutdown.Token);
            deadline.CancelAfter(_sendTimeout);
            // 实际发送方由已注册连接确定，显示名字采用注册时的大小写。
            await recipient.SendAsync(message with { Sender = sender.UserName, Receiver = recipient.UserName }, deadline.Token).ConfigureAwait(false);
        }
        catch (Exception error) when (error is IOException or ObjectDisposedException or OperationCanceledException or SocketException)
        {
            recipient.Dispose();
            if (_users.TryRemove(new KeyValuePair<string, ClientSession>(recipient.UserName, recipient)))
                _log($"OFFLINE {recipient.UserName}");
            if (!_shutdown.IsCancellationRequested)
                await ErrorAsync(connection, sender.UserName, message.MessageId, "recipient_offline: 接收方已断开或发送超时。").ConfigureAwait(false);
            return;
        }
        await SendAsync(connection, ChatMessage.Create(MessageTypes.Forwarded, NameRules.Server,
            sender.UserName, recipient.UserName, message.MessageId)).ConfigureAwait(false);
        _log($"FORWARD {sender.UserName} -> {recipient.UserName} id={message.MessageId} bytes={message.ContentLength}");
    }

    private Task ErrorAsync(FramedConnection connection, string receiver, string id, string content) =>
        SendAsync(connection, ChatMessage.Create(MessageTypes.Error, NameRules.Server, receiver, content, id));

    private async Task SendAsync(FramedConnection connection, ChatMessage message)
    {
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(_shutdown.Token);
        deadline.CancelAfter(_sendTimeout);
        await connection.SendAsync(message, deadline.Token).ConfigureAwait(false);
    }

    public async Task StopAsync()
    {
        _shutdown.Cancel();
        _listener.Stop();
        foreach (var client in _connections.Values) client.Dispose();
        if (_acceptLoop is not null) await _acceptLoop.ConfigureAwait(false);
        foreach (var client in _connections.Values) client.Dispose();
        await Task.WhenAll(_handlers.Values).ConfigureAwait(false);
    }

    public async ValueTask DisposeAsync() => await StopAsync().ConfigureAwait(false);
}
