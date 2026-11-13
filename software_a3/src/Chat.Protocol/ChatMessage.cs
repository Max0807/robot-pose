using System.Text;
using System.Text.Json.Serialization;

namespace Chat.Protocol;

public static class MessageTypes
{
    public const string Register = "register";
    public const string RegisterOk = "register_ok";
    public const string Chat = "chat";
    public const string Error = "error";
    public const string UsersRequest = "users_request";
    public const string Users = "users";
    public const string Quit = "quit";
    public const string Forwarded = "forwarded";

    public static bool IsKnown(string value) => value is
        Register or RegisterOk or Chat or Error or UsersRequest or Users or Quit or Forwarded;
}

public static class NameRules
{
    public const string Server = "server";

    // 名字限制用于控制台命令解析；聊天内容本身支持完整 UTF-8。
    public static bool IsProtocolName(string? value) =>
        value is { Length: >= 1 and <= 20 } && char.IsAsciiLetter(value[0]) &&
        value.All(character => char.IsAsciiLetterOrDigit(character) || character == '_');

    public static bool IsUserName(string? value) => IsProtocolName(value) &&
        !string.Equals(value, Server, StringComparison.OrdinalIgnoreCase);
}

public sealed record ChatMessage
{
    [JsonRequired] public string Type { get; init; } = "";
    [JsonRequired] public string Sender { get; init; } = "";
    [JsonRequired] public string Receiver { get; init; } = "";
    [JsonRequired] public int ContentLength { get; init; }
    [JsonRequired] public string Content { get; init; } = "";
    [JsonRequired] public string MessageId { get; init; } = "";

    public static ChatMessage Create(string type, string sender, string receiver, string content,
        string? messageId = null)
    {
        var message = new ChatMessage
        {
            Type = type, Sender = sender, Receiver = receiver, Content = content,
            ContentLength = MessageRules.Utf8.GetByteCount(content),
            MessageId = messageId ?? Guid.NewGuid().ToString("N")
        };
        MessageRules.Validate(message);
        return message;
    }
}

public sealed class ProtocolException(string message, Exception? inner = null) : IOException(message, inner);

public static class MessageRules
{
    public const int MaxContentBytes = 16 * 1024;
    public static readonly UTF8Encoding Utf8 = new(false, true);

    public static void Validate(ChatMessage message)
    {
        if (!MessageTypes.IsKnown(message.Type))
            throw new ProtocolException("unknown_type: 未知消息类型。");
        if (!NameRules.IsProtocolName(message.Sender) || !NameRules.IsProtocolName(message.Receiver))
            throw new ProtocolException("invalid_address: 发送方 / 接收方格式无效。");
        if (message.MessageId is not { Length: >= 1 and <= 64 } ||
            message.MessageId.Any(character => !char.IsAsciiLetterOrDigit(character) && character is not '.' and not '_' and not '-' and not ':'))
            throw new ProtocolException("invalid_id: 消息编号格式无效。");
        if (message.Content is null)
            throw new ProtocolException("invalid_content: content 不能为 null。");
        int actual;
        try { actual = Utf8.GetByteCount(message.Content); }
        catch (EncoderFallbackException error) { throw new ProtocolException("invalid_utf8: 内容包含无效 Unicode。", error); }
        if (actual > MaxContentBytes || message.ContentLength != actual)
            throw new ProtocolException("invalid_content_length: 内容长度必须等于 UTF-8 字节数，且不超过 16 KiB。");
    }
}
