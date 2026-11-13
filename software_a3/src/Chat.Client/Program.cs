using System.Net.Sockets;
using System.Text;
using Chat.Protocol;

namespace Chat.Client;

internal static class Program
{
    private static readonly object OutputGate = new();

    private static void Print(string text)
    {
        // 内容中的换行 / 控制字符显示为转义，避免破坏控制台命令行布局。
        string safe = string.Concat(text.Select(character => char.IsControl(character)
            ? character switch { '\n' => "\\n", '\r' => "\\r", '\t' => "\\t", _ => $"\\u{(int)character:x4}" }
            : character.ToString()));
        lock (OutputGate) Console.WriteLine(safe);
    }

    private static async Task<int> Main(string[] args)
    {
        Console.InputEncoding = new UTF8Encoding(false);
        Console.OutputEncoding = new UTF8Encoding(false);
        string host = "127.0.0.1", name = "";
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
                    case "--name": name = args[++index]; break;
                    case "--port": port = int.Parse(args[++index], System.Globalization.CultureInfo.InvariantCulture); break;
                    default: throw new ArgumentException($"未知参数：{args[index]}");
                }
            }
            if (port is < 1 or > 65535 || string.IsNullOrWhiteSpace(host)) throw new ArgumentException("服务器地址或端口无效。");
            using var shutdown = new CancellationTokenSource();
            await using var client = await ChatClient.ConnectAsync(host, port, name, shutdown.Token);
            Console.CancelKeyPress += (_, eventArgs) => { eventArgs.Cancel = true; shutdown.Cancel(); client.Dispose(); };
            Print($"REGISTERED user={client.UserName}");
            Help();
            Task<int> receive = DisplayAsync(client, shutdown.Token);
            // Console.ReadLine 是同步输入；一个后台输入任务不会挡住网络接收。
            Task<int> input = Task.Run(() => InputAsync(client, shutdown.Token));
            Task<int> winner = await Task.WhenAny(receive, input);
            int exitCode = await winner;
            shutdown.Cancel();
            client.Dispose();
            await receive;
            if (input.IsCompleted) await input;
            // 不等待仍阻塞于键盘的后台任务；主程序退出时不会留下 TCP 连接。
            Print("BYE 客户端已退出。");
            return exitCode;
        }
        catch (Exception error) when (error is ArgumentException or FormatException or OverflowException or IOException or SocketException or OperationCanceledException)
        {
            Console.Error.WriteLine($"连接 / 运行失败：{error.Message}");
            return 1;
        }
    }

    private static async Task<int> InputAsync(ChatClient client, CancellationToken cancellationToken)
    {
        try
        {
            while (!cancellationToken.IsCancellationRequested)
            {
                string? line = Console.ReadLine();
                if (line is null || line.Equals("/quit", StringComparison.OrdinalIgnoreCase))
                {
                    await client.QuitAsync(cancellationToken);
                    return 0;
                }
                if (cancellationToken.IsCancellationRequested) return 0;
                try
                {
                    if (line.Equals("/users", StringComparison.OrdinalIgnoreCase)) await client.RequestUsersAsync(cancellationToken);
                    else if (line.StartsWith("/msg ", StringComparison.OrdinalIgnoreCase))
                    {
                        string body = line[5..];
                        int separator = body.IndexOf(' ');
                        if (separator < 1) throw new ArgumentException("格式：/msg Bob 你好");
                        string id = await client.SendChatAsync(body[..separator], body[(separator + 1)..], cancellationToken);
                        Print($"[已提交] id={id}");
                    }
                    else if (line.Equals("/help", StringComparison.OrdinalIgnoreCase)) Help();
                    else if (!string.IsNullOrWhiteSpace(line)) Print("[输入提示] 使用 /msg 用户 内容、/users、/quit。");
                }
                catch (Exception error) when (error is ArgumentException or ProtocolException)
                {
                    Print($"[输入错误] {error.Message}");
                }
            }
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested) { }
        catch (ObjectDisposedException) when (cancellationToken.IsCancellationRequested) { }
        catch (Exception error) when (error is IOException or SocketException or ObjectDisposedException)
        {
            if (!cancellationToken.IsCancellationRequested && !client.IsQuitting) { Print($"[发送失败] {error.Message}"); return 1; }
        }
        return 0;
    }

    private static async Task<int> DisplayAsync(ChatClient client, CancellationToken cancellationToken)
    {
        try
        {
            while (!cancellationToken.IsCancellationRequested)
            {
                ChatMessage? message = await client.ReceiveAsync(cancellationToken);
                if (message is null) { Print("[连接] 服务器已关闭连接。"); return 0; }
                switch (message.Type)
                {
                    case MessageTypes.Chat: Print($"[{message.Sender}] {message.Content}"); break;
                    case MessageTypes.Forwarded: Print($"[已转发] {message.Content} id={message.MessageId}"); break;
                    case MessageTypes.Users: Print($"[在线用户] {message.Content}"); break;
                    case MessageTypes.Error: Print($"[服务器提示] {message.Content}"); break;
                }
            }
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested) { }
        catch (ObjectDisposedException) when (cancellationToken.IsCancellationRequested) { }
        catch (Exception error) when (error is IOException or SocketException or ObjectDisposedException)
        {
            if (!cancellationToken.IsCancellationRequested && !client.IsQuitting) { Print($"[接收失败] {error.Message}"); return 1; }
        }
        return 0;
    }

    private static void Help() => Print("命令：/msg Bob 你好 | /users | /quit | /help；启动：--name Alice --host 127.0.0.1 --port 9000");
}
