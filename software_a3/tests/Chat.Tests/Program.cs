using System.Diagnostics;
using System.Text;
using System.Text.Encodings.Web;
using System.Text.Json;

namespace Chat.Tests;

internal static class Program
{
    // 无第三方测试框架，随项目提供可执行的自动验收程序。
    private static async Task<int> Main(string[] args)
    {
        Console.OutputEncoding = new UTF8Encoding(false);
        string filter = "", outputDirectory = "output";
        for (int index = 0; index < args.Length; index++)
        {
            if (index + 1 >= args.Length) { Console.Error.WriteLine("参数缺少值"); return 2; }
            switch (args[index])
            {
                case "--filter": filter = args[++index]; break;
                case "--output-dir": outputDirectory = args[++index]; break;
                default: Console.Error.WriteLine($"未知参数：{args[index]}"); return 2;
            }
        }
        outputDirectory = Path.GetFullPath(outputDirectory);
        TestCase[] tests = ProtocolTests.Cases().Concat(NetworkTests.Cases()).Concat(ProcessTests.Cases(outputDirectory))
            .Where(test => test.Name.Contains(filter, StringComparison.OrdinalIgnoreCase)).ToArray();
        if (tests.Length == 0) { Console.Error.WriteLine("没有匹配的测试"); return 2; }
        var results = new List<object>();
        var lines = new List<string>();
        int failed = 0;
        foreach (var test in tests)
        {
            var timer = Stopwatch.StartNew();
            string? error = null;
            try { await test.Run().WaitAsync(TimeSpan.FromSeconds(40)); }
            catch (Exception exception) { failed++; error = exception.ToString(); }
            string line = $"{(error is null ? "PASS" : "FAIL")} {test.Name} ({timer.ElapsedMilliseconds} ms)";
            Console.WriteLine(line);
            if (error is not null) Console.WriteLine(error);
            lines.Add(line);
            if (error is not null) lines.Add(error);
            results.Add(new { name = test.Name, passed = error is null, milliseconds = timer.ElapsedMilliseconds, error });
        }
        string summary = $"总计 {tests.Length}，通过 {tests.Length - failed}，失败 {failed}";
        Console.WriteLine(summary); lines.Add(summary);
        Directory.CreateDirectory(outputDirectory);
        string reportName = string.IsNullOrEmpty(filter) ? "test-results" : "test-results-filtered";
        await File.WriteAllLinesAsync(Path.Combine(outputDirectory, reportName + ".txt"), lines, new UTF8Encoding(false));
        await File.WriteAllTextAsync(Path.Combine(outputDirectory, reportName + ".json"), JsonSerializer.Serialize(new
        {
            timeUtc = DateTimeOffset.UtcNow, framework = System.Runtime.InteropServices.RuntimeInformation.FrameworkDescription,
            filter, total = tests.Length, passed = tests.Length - failed, failed, results
        }, new JsonSerializerOptions { WriteIndented = true, Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping }));
        return failed == 0 ? 0 : 1;
    }
}
