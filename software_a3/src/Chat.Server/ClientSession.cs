using System.Net.Sockets;
using Chat.Protocol;

namespace Chat.Server;

public sealed class ClientSession(string userName, TcpClient client, FramedConnection connection) : IDisposable
{
    private readonly TaskCompletionSource<bool> _registration = new(TaskCreationOptions.RunContinuationsAsynchronously);
    private int _closed;
    public string UserName { get; } = userName;
    public bool IsReady => Volatile.Read(ref _closed) == 0 && _registration.Task.IsCompletedSuccessfully && _registration.Task.Result;

    public void MarkReady() => _registration.TrySetResult(true);

    public async Task SendAsync(ChatMessage message, CancellationToken cancellationToken)
    {
        // 名字先占位，但注册确认必须先于其他人发来的聊天消息写入。
        if (!await _registration.Task.WaitAsync(cancellationToken).ConfigureAwait(false) || !IsReady)
            throw new IOException("接收方连接已关闭。");
        await connection.SendAsync(message, cancellationToken).ConfigureAwait(false);
    }

    public void Dispose()
    {
        if (Interlocked.Exchange(ref _closed, 1) != 0) return;
        _registration.TrySetResult(false);
        connection.Dispose();
        client.Dispose();
    }
}
