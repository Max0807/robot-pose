using System.Diagnostics;
using System.Text;
using System.Threading.Channels;

namespace Chat.Tests;

internal static class ProcessTests
{
    public static IEnumerable<TestCase> Cases(string outputDirectory)
    {
        yield return new("process.three_real_clients_and_server_shutdown", async () =>
        {
            string root = FindRoot();
            string dotnet = Environment.GetEnvironmentVariable("A3_DOTNET_PATH") ?? Path.Combine(root, ".dotnet", "dotnet.exe");
            var transcript = new List<string>();
            var processes = new List<ConsoleProcess>();
            try
            {
                var server = new ConsoleProcess(dotnet, Path.Combine(root, "src", "Chat.Server", "bin", "Debug", "net10.0", "Chat.Server.dll"), "server", transcript, "--port", "0");
                processes.Add(server);
                string ready = await server.ExpectAsync(line => line.StartsWith("READY ", StringComparison.Ordinal));
                string port = ready[(ready.LastIndexOf("port=", StringComparison.Ordinal) + 5)..];
                string clientDll = Path.Combine(root, "src", "Chat.Client", "bin", "Debug", "net10.0", "Chat.Client.dll");
                var alice = new ConsoleProcess(dotnet, clientDll, "Alice", transcript, "--name", "Alice", "--port", port);
                processes.Add(alice);
                var bob = new ConsoleProcess(dotnet, clientDll, "Bob", transcript, "--name", "Bob", "--port", port);
                processes.Add(bob);
                var carol = new ConsoleProcess(dotnet, clientDll, "Carol", transcript, "--name", "Carol", "--port", port);
                processes.Add(carol);
                foreach (var client in new[] { alice, bob, carol }) await client.ExpectAsync(line => line.StartsWith("REGISTERED ", StringComparison.Ordinal));

                await alice.SendAsync("/msg Bob 你好 Bob，来自 Alice 🙂");
                await bob.ExpectAsync(line => line == "[Alice] 你好 Bob，来自 Alice 🙂");
                await alice.ExpectAsync(line => line.StartsWith("[已转发] Bob", StringComparison.Ordinal));
                await bob.SendAsync("/msg Alice 已收到，双向通信成功");
                await alice.ExpectAsync(line => line == "[Bob] 已收到，双向通信成功");
                await carol.SendAsync("/msg Bob 第三个客户端也能转发");
                await bob.ExpectAsync(line => line == "[Carol] 第三个客户端也能转发");
                await alice.SendAsync("/users");
                await alice.ExpectAsync(line => line == "[在线用户] Alice, Bob, Carol");
                await alice.SendAsync("/msg Nobody 不在线的用户");
                await alice.ExpectAsync(line => line.Contains("recipient_offline:", StringComparison.Ordinal));
                await alice.SendAsync("/msg Bob");
                await alice.ExpectAsync(line => line.StartsWith("[输入错误]", StringComparison.Ordinal));

                // 同名进程应失败，不能影响原 Alice。
                var duplicate = new ConsoleProcess(dotnet, clientDll, "duplicate", transcript, "--name", "ALICE", "--port", port);
                processes.Add(duplicate);
                Check.Equal(1, await duplicate.ExitAsync());
                Check.True(duplicate.ErrorText.Contains("name_in_use:", StringComparison.Ordinal));
                await alice.SendAsync("/users");
                await alice.ExpectAsync(line => line == "[在线用户] Alice, Bob, Carol");

                await bob.SendAsync("/quit");
                Check.Equal(0, await bob.ExitAsync());
                await server.ExpectAsync(line => line == "OFFLINE Bob");
                await alice.SendAsync("/msg Bob 退出后再发送");
                await alice.ExpectAsync(line => line.Contains("recipient_offline:", StringComparison.Ordinal));

                // Alice / Carol 的标准输入保持打开，以验证关服时不会卡在 Console.ReadLine。
                await server.SendAsync("/quit");
                Check.Equal(0, await server.ExitAsync());
                Check.Equal(0, await alice.ExitAsync());
                Check.Equal(0, await carol.ExitAsync());
            }
            finally
            {
                foreach (var process in processes) await process.DisposeAsync();
                Directory.CreateDirectory(outputDirectory);
                await File.WriteAllLinesAsync(Path.Combine(outputDirectory, "process-demo.txt"), transcript, new UTF8Encoding(false));
            }
        });
    }

    private static string FindRoot()
    {
        DirectoryInfo? directory = new(AppContext.BaseDirectory);
        while (directory is not null)
        {
            if (File.Exists(Path.Combine(directory.FullName, "ChatDemo.sln"))) return directory.FullName;
            directory = directory.Parent;
        }
        throw new DirectoryNotFoundException("找不到 software_a3 项目根目录");
    }
}

// 只管理本测试创建的进程；失败时也关闭进程并保存输出。
internal sealed class ConsoleProcess : IAsyncDisposable
{
    private readonly Process _process;
    private readonly string _label;
    private readonly List<string> _transcript;
    private readonly Channel<string> _lines = Channel.CreateUnbounded<string>();
    private readonly Task _stdout;
    private readonly Task _stderr;
    private readonly StringBuilder _errors = new();
    public string ErrorText => _errors.ToString();

    public ConsoleProcess(string dotnet, string dll, string label, List<string> transcript, params string[] arguments)
    {
        _label = label;
        _transcript = transcript;
        var info = new ProcessStartInfo(dotnet)
        {
            UseShellExecute = false, CreateNoWindow = true,
            RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true,
            StandardInputEncoding = new UTF8Encoding(false), StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8, WorkingDirectory = Path.GetDirectoryName(dll)!
        };
        info.ArgumentList.Add(dll);
        foreach (string argument in arguments) info.ArgumentList.Add(argument);
        _process = Process.Start(info) ?? throw new IOException("无法启动测试进程");
        _stdout = PumpAsync(_process.StandardOutput, false);
        _stderr = PumpAsync(_process.StandardError, true);
    }

    private async Task PumpAsync(StreamReader reader, bool error)
    {
        try
        {
            while (await reader.ReadLineAsync() is { } line)
            {
                lock (_transcript) _transcript.Add($"[{_label}{(error ? ":stderr" : "")}] {line}");
                if (error) _errors.AppendLine(line);
                else await _lines.Writer.WriteAsync(line);
            }
        }
        finally { if (!error) _lines.Writer.TryComplete(); }
    }

    public async Task SendAsync(string command)
    {
        lock (_transcript) _transcript.Add($"[{_label}:input] {command}");
        await _process.StandardInput.WriteLineAsync(command);
        await _process.StandardInput.FlushAsync();
    }

    public async Task<string> ExpectAsync(Func<string, bool> matches)
    {
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(10));
        try
        {
            while (await _lines.Reader.WaitToReadAsync(timeout.Token))
                while (_lines.Reader.TryRead(out string? line)) if (matches(line)) return line;
        }
        catch (OperationCanceledException) { throw new TimeoutException($"{_label} 未在期限内输出预期内容。错误：{ErrorText}"); }
        throw new IOException($"{_label} 在预期内容到达前退出。错误：{ErrorText}");
    }

    public async Task<int> ExitAsync()
    {
        await _process.WaitForExitAsync().WaitAsync(TimeSpan.FromSeconds(10));
        await Task.WhenAll(_stdout, _stderr);
        return _process.ExitCode;
    }

    public async ValueTask DisposeAsync()
    {
        if (!_process.HasExited) _process.Kill(entireProcessTree: true);
        await _process.WaitForExitAsync();
        await Task.WhenAll(_stdout, _stderr);
        _process.Dispose();
    }
}
