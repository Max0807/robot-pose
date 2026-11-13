using System.Net.Sockets;
using Chat.Protocol;

namespace Chat.Client;

public sealed class ChatClient : IDisposable, IAsyncDisposable
{
    private readonly TcpClient _client;
    private readonly FramedConnection _connection;
    private int _quitting;
    public string UserName { get; }
    public bool IsClosed => _connection.IsClosed;
    public bool IsQuitting => Volatile.Read(ref _quitting) != 0;

    private ChatClient(string userName, TcpClient client, FramedConnection connection)
    {
        UserName = userName;
        _client = client;
        _connection = connection;
    }

    public static async Task<ChatClient> ConnectAsync(string host, int port, string userName,
        CancellationToken cancellationToken = default)
    {
        if (!NameRules.IsUserName(userName))
            throw new ArgumentException("用户名须为 1-20 位英文字母 / 数字 / 下划线，以字母开头；server 为保留名称。");
        var client = new TcpClient { NoDelay = true };
        FramedConnection? connection = null;
        try
        {
            using var deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            deadline.CancelAfter(TimeSpan.FromSeconds(10));
            await client.ConnectAsync(host, port, deadline.Token).ConfigureAwait(false);
            connection = new FramedConnection(client.GetStream());
            ChatMessage registration = ChatMessage.Create(MessageTypes.Register, userName, NameRules.Server, "");
            await connection.SendAsync(registration, deadline.Token).ConfigureAwait(false);
            ChatMessage answer = await connection.ReceiveAsync(deadline.Token).ConfigureAwait(false)
                ?? throw new IOException("服务器在注册完成前关闭连接。");
            if (answer.Type == MessageTypes.Error) throw new IOException(answer.Content);
            if (answer.Type != MessageTypes.RegisterOk || answer.MessageId != registration.MessageId ||
                !string.Equals(answer.Sender, NameRules.Server, StringComparison.OrdinalIgnoreCase) ||
                !string.Equals(answer.Receiver, userName, StringComparison.OrdinalIgnoreCase))
                throw new ProtocolException("invalid_registration_reply: 注册响应不匹配。");
            return new ChatClient(answer.Receiver, client, connection);
        }
        catch
        {
            connection?.Dispose();
            client.Dispose();
            throw;
        }
    }

    public async Task<string> SendChatAsync(string receiver, string content, CancellationToken cancellationToken = default)
    {
        if (!NameRules.IsUserName(receiver)) throw new ArgumentException("接收方用户名格式无效。");
        if (string.IsNullOrWhiteSpace(content)) throw new ArgumentException("聊天内容不能为空。");
        ChatMessage message = ChatMessage.Create(MessageTypes.Chat, UserName, receiver, content);
        await _connection.SendAsync(message, cancellationToken).ConfigureAwait(false);
        return message.MessageId;
    }

    public Task RequestUsersAsync(CancellationToken cancellationToken = default) =>
        _connection.SendAsync(ChatMessage.Create(MessageTypes.UsersRequest, UserName, NameRules.Server, ""), cancellationToken);

    public async Task<ChatMessage?> ReceiveAsync(CancellationToken cancellationToken = default)
    {
        try
        {
            ChatMessage? message = await _connection.ReceiveAsync(cancellationToken).ConfigureAwait(false);
            if (message is null) { Dispose(); return null; }
            if (!string.Equals(message.Receiver, UserName, StringComparison.OrdinalIgnoreCase))
                throw new ProtocolException("wrong_receiver: 收到的消息不属于本用户。");
            bool isChat = message.Type == MessageTypes.Chat && NameRules.IsUserName(message.Sender);
            bool isServer = (message.Type is MessageTypes.Error or MessageTypes.Users or MessageTypes.Forwarded) &&
                string.Equals(message.Sender, NameRules.Server, StringComparison.OrdinalIgnoreCase);
            if (!isChat && !isServer) throw new ProtocolException("invalid_server_message: 服务器消息类型或身份无效。");
            return message;
        }
        catch { Dispose(); throw; }
    }

    public async Task QuitAsync(CancellationToken cancellationToken = default)
    {
        // 在关闭传输前标记主动退出，让并行接收循环识别正常的本地关闭。
        Interlocked.Exchange(ref _quitting, 1);
        try
        {
            if (!IsClosed)
                await _connection.SendAsync(ChatMessage.Create(MessageTypes.Quit, UserName, NameRules.Server, ""), cancellationToken).ConfigureAwait(false);
        }
        finally { Dispose(); }
    }

    public void Dispose() { _connection.Dispose(); _client.Dispose(); }
    public ValueTask DisposeAsync() { Dispose(); return ValueTask.CompletedTask; }
}
