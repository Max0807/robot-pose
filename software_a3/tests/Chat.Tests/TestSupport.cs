using System.Diagnostics;

namespace Chat.Tests;

internal sealed record TestCase(string Name, Func<Task> Run);

internal static class Check
{
    public static void True(bool condition, string message = "条件不成立")
    {
        if (!condition) throw new InvalidOperationException(message);
    }

    public static void Equal<T>(T expected, T actual)
    {
        if (!EqualityComparer<T>.Default.Equals(expected, actual))
            throw new InvalidOperationException($"期望 {expected}，实际 {actual}");
    }

    public static async Task<T> ThrowsAsync<T>(Func<Task> action, string? contains = null) where T : Exception
    {
        try { await action(); }
        catch (T error)
        {
            if (contains is not null) True(error.Message.Contains(contains, StringComparison.Ordinal), error.Message);
            return error;
        }
        throw new InvalidOperationException($"应当抛出 {typeof(T).Name}");
    }

    public static async Task EventuallyAsync(Func<bool> condition, string message)
    {
        var timer = Stopwatch.StartNew();
        while (!condition())
        {
            if (timer.Elapsed > TimeSpan.FromSeconds(5)) throw new TimeoutException(message);
            await Task.Delay(10);
        }
    }
}

// 与真实 TCP 的分包方式无关，确定性地模拟一次只能读到几个字节。
internal sealed class ChunkedReadStream(byte[] bytes, int chunkSize) : MemoryStream(bytes, false)
{
    public override ValueTask<int> ReadAsync(Memory<byte> buffer, CancellationToken cancellationToken = default) =>
        base.ReadAsync(buffer[..Math.Min(buffer.Length, chunkSize)], cancellationToken);
}

internal class RecordingStream : Stream
{
    private readonly MemoryStream _data = new();
    private int _writers;
    public bool Overlapped { get; private set; }
    public bool WasDisposed { get; private set; }
    public byte[] Bytes => _data.ToArray();
    public override bool CanRead => false;
    public override bool CanSeek => false;
    public override bool CanWrite => true;
    public override long Length => _data.Length;
    public override long Position { get => _data.Position; set => throw new NotSupportedException(); }
    public override void Flush() { }
    public override int Read(byte[] buffer, int offset, int count) => throw new NotSupportedException();
    public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
    public override void SetLength(long value) => throw new NotSupportedException();
    public override void Write(byte[] buffer, int offset, int count) => _data.Write(buffer, offset, count);
    public override async ValueTask WriteAsync(ReadOnlyMemory<byte> buffer, CancellationToken cancellationToken = default)
    {
        if (Interlocked.Increment(ref _writers) != 1) Overlapped = true;
        try { await Task.Delay(1, cancellationToken); _data.Write(buffer.Span); }
        finally { Interlocked.Decrement(ref _writers); }
    }
    protected override void Dispose(bool disposing) { WasDisposed = true; base.Dispose(disposing); }
}

internal sealed class BlockingWriteStream : RecordingStream
{
    public TaskCompletionSource Entered { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
    public TaskCompletionSource Release { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
    public override async ValueTask WriteAsync(ReadOnlyMemory<byte> buffer, CancellationToken cancellationToken = default)
    {
        Entered.TrySetResult();
        await Release.Task.WaitAsync(cancellationToken);
        await base.WriteAsync(buffer, cancellationToken);
    }
}

internal sealed class FailingWriteStream : RecordingStream
{
    public override ValueTask WriteAsync(ReadOnlyMemory<byte> buffer, CancellationToken cancellationToken = default)
    {
        Write(buffer.ToArray(), 0, Math.Min(2, buffer.Length));
        return ValueTask.FromException(new IOException("模拟帧只写入一部分"));
    }
}
