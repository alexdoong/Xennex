using System;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;
using Xennex.Models.LocalAi;

namespace Xennex.Services.LocalAi;

public sealed class AiStore
{
    public static readonly JsonSerializerOptions Json = new() { PropertyNamingPolicy = JsonNamingPolicy.CamelCase };
    public const int MaxBytes = 16 * 1024 * 1024;
    private readonly string path;
    public AiStore(string directory) { path = Path.Combine(directory, "workspace.json"); }

    public AiLibrary Load()
    {
        try
        {
            if (!File.Exists(path)) return new();
            if (new FileInfo(path).Length > MaxBytes) throw new InvalidDataException("Histórico de IA acima de 16 MiB.");
            var library = JsonSerializer.Deserialize<AiLibrary>(File.ReadAllText(path), Json);
            if (library?.SchemaVersion == 1)
            {
                // Keep the original schema independently of the rolling save backup.
                if (!File.Exists(path + ".v1.bak")) File.Copy(path, path + ".v1.bak");
                library.SchemaVersion = 2;
            }
            Validate(library);
            // Never replay interrupted jobs after restarting the application.
            foreach (var message in library.Chats.SelectMany(c => c.Messages).Where(m => m.Status is "queued" or "running"))
            {
                message.Status = "interrupted";
                message.Detail = "O aplicativo foi encerrado. A resposta parcial foi preservada.";
            }
            foreach (var run in library.Chats.Where(c => c.Project != null).SelectMany(c => c.Project.Runs).Where(r => r.Status is "queued" or "running"))
            { run.Status = "interrupted"; run.FinishedAt = DateTimeOffset.UtcNow; }
            return library;
        }
        catch (Exception error) { AppLog.Error("LocalAi.Load", error); throw new InvalidDataException("Não foi possível ler o histórico de IA. O original e seu backup .bak foram preservados.", error); }
    }

    public void Save(AiLibrary library)
    {
        string temp = path + ".tmp";
        try
        {
            Validate(library);
            var bytes = JsonSerializer.SerializeToUtf8Bytes(library, Json);
            if (bytes.Length > MaxBytes) throw new InvalidDataException("Limite de 16 MiB do histórico atingido. Exporte e remova conversas antigas.");
            Directory.CreateDirectory(Path.GetDirectoryName(path));
            using (var stream = new FileStream(temp, FileMode.Create, FileAccess.Write, FileShare.None))
            { stream.Write(bytes); stream.Flush(true); }
            if (File.Exists(path)) File.Replace(temp, path, path + ".bak");
            else File.Move(temp, path);
        }
        catch (Exception error) { AppLog.Error("LocalAi.Save", error); throw; }
        finally
        {
            try { if (File.Exists(temp)) File.Delete(temp); }
            catch (Exception error) { AppLog.Error("LocalAi.Cleanup", error); }
        }
    }

    private static void Validate(AiLibrary library)
    {
        if (library == null || library.SchemaVersion != 2 || library.Chats == null || library.Settings == null)
            throw new InvalidDataException("Formato de histórico de IA não suportado.");
        LocalModelClient.ValidateSettings(library.Settings);
        if (library.Measurements == null || library.Measurements.Count > 64 || library.Measurements.Any(m => m == null || m.Key == null || m.Key.Length > 2048 ||
            m.Samples < 0 || !double.IsFinite(m.AdditionalRamGb) || m.AdditionalRamGb < 0 || !double.IsFinite(m.AdditionalVramGb) || m.AdditionalVramGb < 0))
            throw new InvalidDataException("Histórico de estimativas inválido.");
        if (library.Chats.Count > 100 || library.Chats.Select(c => c?.Id).Distinct().Count() != library.Chats.Count)
            throw new InvalidDataException("Biblioteca de conversas inválida.");
        foreach (var chat in library.Chats)
        {
            if (chat == null || !Guid.TryParse(chat.Id, out _) || chat.Title == null || chat.Title.Length > 160 ||
                chat.Messages == null || chat.Messages.Count > (chat.Project == null ? 200 : 2000) || chat.Model == null)
                throw new InvalidDataException("Conversa inválida.");
            foreach (var message in chat.Messages)
                if (message == null || message.Role is not ("user" or "assistant") || message.Content == null || message.Content.Length > 64000)
                    throw new InvalidDataException("Mensagem inválida.");
        }
        AiRoomValidation.Library(library);
    }
}
