namespace Chat.Protocol;

public sealed class FramedConnection(Stream stream) : IDisposable, IAsyncDisposable
{
    private readonly SemaphoreSlim _sendGate = new(1, 1);
    private int _closed;
    private int _reading;
    public bool IsClosed => Volatile.Read(ref _closed) != 0;

    public async Task SendAsync(ChatMessage message, CancellationToken cancellationToken = default)
    {
        byte[] frame = FrameCodec.Encode(message);
        // 等待锁被取消时尚未写入，不会破坏其他任务正在发送的帧。
        await _sendGate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            ObjectDisposedException.ThrowIf(IsClosed, this);
            try
            {
                // 锁覆盖整个帧：帧头和帧体不会与另一条消息交错。
                await stream.WriteAsync(frame.AsMemory(), cancellationToken).ConfigureAwait(false);
            }
            catch
            {
                // 写到一半失败 / 取消后，连接不能再用于发送下一帧。
                Dispose();
                throw;
            }
        }
        finally { _sendGate.Release(); }
    }

    public async Task<ChatMessage?> ReceiveAsync(CancellationToken cancellationToken = default)
    {
        ObjectDisposedException.ThrowIf(IsClosed, this);
        if (Interlocked.CompareExchange(ref _reading, 1, 0) != 0)
            throw new InvalidOperationException("一条连接只能有一个接收循环。");
        try
        {
            var message = await FrameCodec.ReadAsync(stream, cancellationToken).ConfigureAwait(false);
            if (message is null) Dispose();
            return message;
        }
        catch
        {
            Dispose();
            throw;
        }
        finally { Volatile.Write(ref _reading, 0); }
    }

    public void Dispose()
    {
        if (Interlocked.Exchange(ref _closed, 1) == 0) stream.Dispose();
        // 不在此处销毁 semaphore，仍在等待的发送任务会醒来并检查 IsClosed。
    }

    public ValueTask DisposeAsync() { Dispose(); return ValueTask.CompletedTask; }
}
