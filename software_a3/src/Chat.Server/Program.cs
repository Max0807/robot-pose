using System.Net;
using System.Net.Sockets;
using System.Text;

namespace Chat.Server;

internal static class Program
{
    private static async Task<int> Main(string[] args)
    {
        Console.InputEncoding = new UTF8Encoding(false);
        Console.OutputEncoding = new UTF8Encoding(false);
        string host = "127.0.0.1";
        int port = 9000;
        try
        {
            for (int index = 0; index < args.Length; index++)
            {
                if (args[index] == "--help") { Help(); return 0; }
                if (index + 1 >= args.Length) throw new ArgumentException("启动参数缺少值。");
                switch (args[index])
                {
                    case "--host": host = args[++index]; break;
                    case "--port": port = int.Parse(args[++index], System.Globalization.CultureInfo.InvariantCulture); break;
                    default: throw new ArgumentException($"未知参数：{args[index]}");
                }
            }
            if (!IPAddress.TryParse(host, out var address) || port is < 0 or > 65535)
                throw new ArgumentException("host 须为 IP 地址，port 须在 0-65535 之间（0 用于自动测试端口）。");
            using var shutdown = new CancellationTokenSource();
            Console.CancelKeyPress += (_, eventArgs) => { eventArgs.Cancel = true; shutdown.Cancel(); };
            await using var server = new ChatServer(address, port, text => Console.WriteLine(text));
            server.Start();
            Console.WriteLine($"READY host={address} port={server.Port}");
            Console.WriteLine("服务器已启动。输入 /quit 或按 Ctrl+C 正常退出。");
            _ = Task.Run(() =>
            {
                while (!shutdown.IsCancellationRequested)
                {
                    string? line = Console.ReadLine();
                    if (line is null) return; // 无标准输入时，服务器仍可继续提供服务。
                    if (line.Trim().Equals("/quit", StringComparison.OrdinalIgnoreCase)) { shutdown.Cancel(); return; }
                }
            });
            Task stop = Task.Delay(Timeout.InfiniteTimeSpan, shutdown.Token);
            Task winner = await Task.WhenAny(server.Completion, stop);
            if (winner == server.Completion) await server.Completion;
            await server.StopAsync();
            Console.WriteLine("STOPPED 服务器已关闭，连接已释放。");
            return 0;
        }
        catch (Exception error) when (error is ArgumentException or FormatException or OverflowException or IOException or SocketException)
        {
            Console.Error.WriteLine($"启动 / 运行失败：{error.Message}");
            return 1;
        }
    }

    private static void Help() => Console.WriteLine("Chat.Server --host 127.0.0.1 --port 9000");
}
