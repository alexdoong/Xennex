using System;
using System.IO;
using System.Linq;
using System.Text.Json;
using Xennex.Models.GameAnalytics;
using Xennex.Services.GameAnalytics;

var directory = Path.Combine(Path.GetTempPath(), "XennexGameTests-" + Guid.NewGuid());
Directory.CreateDirectory(directory);
var checks = 0;
void Check(bool value, string name) { if (!value) throw new Exception(name); checks++; }
void Rejected(Action action, string name) {
    try { action(); } catch (Exception e) when (e is InvalidDataException || e is JsonException) { checks++; return; }
    throw new Exception("Accepted invalid input: " + name);
}
string Encode(GameDocument game) => JsonSerializer.Serialize(game, GameStore.Json);
GameDocument Decode(string json) => GameStore.Parse(json);
try {
    var service = new GameAnalyticsService(directory);
    Check(JsonDocument.Parse(service.GetLibrary()).RootElement.GetProperty("games").GetArrayLength() == 0, "Empty library");
    var game = new GameDocument { Id = Guid.NewGuid().ToString(), Name = "osu! teste" };
    var now = DateTimeOffset.Now;
    var session = new GameSession { Id = Guid.NewGuid().ToString(), Title = "Treino",
        OccurredAt = now.AddDays(-3), CreatedAt = now, UpdatedAt = now,
        Context = "Mapa A · sem mods", Patch = "desconhecido", Notes = "Observação\nSegunda linha" };
    session.Metrics.Add(new GameMetric { Name = "Precisão", Value = 98.5, Unit = "%" });
    session.Metrics.Add(new GameMetric { Name = "Falhas", Value = 0, Unit = "" });
    game.Sessions.Add(session);
    var character = new GameCharacter { Id = Guid.NewGuid().ToString(), Name = "Suporte", Role = "Buffs",
        Image = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jN1EAAAAASUVORK5CYII=", Focus = 35 };
    game.Visual.Cover = character.Image;
    game.Visual.Characters.Add(character);
    var board = new StrategyBoard { Id = Guid.NewGuid().ToString(), Name = "Rotação", Goal = "Testar sequência" };
    board.Cards.Add(new StrategyCard { Id = Guid.NewGuid().ToString(), CharacterId = character.Id, Title = "Buff", X = 50, Y = 100 });
    board.Cards.Add(new StrategyCard { Id = Guid.NewGuid().ToString(), Title = "Atacar", X = 400, Y = 250 });
    board.Links.Add(new StrategyLink { From = board.Cards[0].Id, To = board.Cards[1].Id });
    game.Visual.Boards.Add(board);
    var saved = Decode(service.SaveGame(Encode(game)));
    Check(saved.Revision == 1, "Initial revision");
    var path = Path.Combine(directory, game.Id + ".json");
    var reloaded = new GameStore(directory).ReadFile(path);
    Check(reloaded.Sessions[0].Metrics[1].Value == 0 && reloaded.Sessions[0].Notes == session.Notes, "Reload zero and multiline");
    Check(reloaded.Sessions[0].OccurredAt == session.OccurredAt, "Timestamp round trip");
    Rejected(() => service.SaveGame(Encode(game)), "Stale update");
    saved.Sessions[0].Title = "Treino revisado";
    saved = Decode(service.SaveGame(Encode(saved)));
    Check(saved.Revision == 2 && File.Exists(path + ".bak"), "Update backup");
    Check(new GameStore(directory).ReadFile(path + ".bak").Sessions[0].Title == "Treino", "Previous version retained");
    var exported = Encode(saved);
    var imported = Decode(service.ImportGame(exported));
    Check(imported.Id != saved.Id && imported.Revision == 1, "Independent import");
    Check(imported.Sessions[0].OccurredAt == session.OccurredAt &&
        imported.Sessions[0].Metrics[0].Value == 98.5, "Import preserves content");
    Check(new GameStore(directory).ReadFile(path).Revision == 2, "Import preserves existing game");
    Check(imported.Visual.Cover == character.Image && imported.Visual.Characters[0].Focus == 35, "Images and crop survive import");
    Check(imported.Visual.Boards[0].Cards[1].X == 400 &&
        imported.Visual.Boards[0].Links[0].To == board.Cards[1].Id, "Positions and links survive import");
    void BadVisual(Action<GameDocument> mutate, string label) {
        var clone = Decode(exported); mutate(clone); Rejected(() => service.ImportGame(Encode(clone)), label);
    }
    BadVisual(g => g.Visual.Cover = "https://example.com/image.png", "External image rejected");
    BadVisual(g => g.Visual.Characters[0].Image = "data:image/png;base64,YmFk", "Invalid image bytes");
    BadVisual(g => g.Visual.Boards[0].Cards[0].X = 1200, "Off-board position");
    BadVisual(g => g.Visual.Boards[0].Links[0].To = Guid.NewGuid().ToString(), "Dangling link");
    BadVisual(g => g.Visual.Boards[0].Cards[0].CharacterId = Guid.NewGuid().ToString(), "Missing character");
    BadVisual(g => g.Visual.Boards[0].Cards.Add(g.Visual.Boards[0].Cards[0]), "Duplicate cards");
    BadVisual(g => g.Visual.Boards[0].Links.Add(g.Visual.Boards[0].Links[0]), "Duplicate links");
    BadVisual(g => g.Visual.Characters[0].Color = "url(example.com)", "Invalid card color");
    BadVisual(g => g.Visual = null, "Null workspace");
    var legacy = System.Text.Json.Nodes.JsonNode.Parse(exported).AsObject();
    legacy["schemaVersion"] = 1; legacy.Remove("visual");
    var legacyDirectory = Path.Combine(directory, "legacy");
    Directory.CreateDirectory(legacyDirectory);
    var legacyPath = Path.Combine(legacyDirectory, saved.Id + ".json");
    File.WriteAllText(legacyPath, legacy.ToJsonString());
    var legacyStore = new GameStore(legacyDirectory);
    var migrated = legacyStore.ReadFile(legacyPath);
    Check(migrated.SchemaVersion == 3 && migrated.Visual.Characters.Count == 0 &&
        migrated.Sessions.Count == 1, "V1 migration preserves history");
    Check(File.ReadAllText(legacyPath) == legacy.ToJsonString(), "Reading never rewrites V1");
    legacyStore.Save(migrated);
    Check(File.ReadAllText(legacyPath + ".bak") == legacy.ToJsonString(), "V1 original backed up on first write");
    Rejected(() => service.ImportGame(exported.Replace("\"schemaVersion\": 3,", "")), "Missing schema");
    Rejected(() => service.ImportGame(exported.Replace("\"value\": 98.5,", "")), "Missing value is not zero");
    Rejected(() => service.ImportGame(exported.Replace("98.5", "1e100")), "Out-of-range metric");
    saved.SchemaVersion = 99;
    Rejected(() => service.SaveGame(Encode(saved)), "Future schema");
    saved.SchemaVersion = 1;
    saved.Id = "../escape";
    Rejected(() => service.SaveGame(Encode(saved)), "Path traversal");
    saved.Id = game.Id;
    saved.Sessions.Add(saved.Sessions[0]);
    Rejected(() => service.ImportGame(Encode(saved)), "Duplicate sessions");
    saved.Sessions.RemoveAt(1);
    saved.Sessions[0].Metrics.Add(new GameMetric { Name = " precisão ", Value = 1, Unit = "%" });
    Rejected(() => service.SaveGame(Encode(saved)), "Duplicate metric");
    saved.Sessions[0].Metrics.RemoveAt(2);
    saved.Sessions[0].Metrics = null;
    Rejected(() => service.SaveGame(Encode(saved)), "Null metrics");
    Rejected(() => service.ImportGame(new string(' ', GameStore.MaxBytes + 1)), "Oversized import");
    Rejected(() => service.ImportGame("{bad json"), "Broken JSON");
    var bytes = File.ReadAllBytes(path);
    File.WriteAllText(path, "corrupted");
    var library = JsonDocument.Parse(service.GetLibrary()).RootElement;
    Check(library.GetProperty("games").GetArrayLength() == 1 &&
        library.GetProperty("warnings").GetArrayLength() == 1, "Isolate corrupt file");
    Rejected(() => service.SaveGame(exported), "Never overwrite corrupt existing file");
    Check(File.ReadAllText(path) == "corrupted", "Corrupt original preserved");
    File.WriteAllBytes(path, bytes);
    Check(!Directory.EnumerateFiles(directory, "*.tmp").Any(), "No temporary files left");
    var defined = Decode(exported);
    defined.Id = Guid.NewGuid().ToString(); defined.Revision = 0;
    var skillId = Guid.NewGuid().ToString(); var metricId = Guid.NewGuid().ToString();
    var actionId = Guid.NewGuid().ToString(); var fieldId = Guid.NewGuid().ToString();
    defined.Definition.Category = "Meu jogo híbrido";
    defined.Definition.HasEntities = false; defined.Definition.HasRanked = true;
    defined.Definition.Skills.Add(new NamedGameDefinition { Id = skillId, Name = "Controle de campos" });
    defined.Definition.Actions.Add(new NamedGameDefinition { Id = actionId, Name = "Usar habilidade" });
    defined.Definition.ContextFields.Add(new NamedGameDefinition { Id = fieldId, Name = "Build" });
    defined.Definition.Metrics.Add(new MetricDefinition { Id = metricId, Name = "Precisão", Unit = "%", SkillId = skillId, Direction = "higher" });
    defined.Sessions[0].Metrics[0].DefinitionId = metricId;
    defined.Sessions[0].ContextValues.Add(new SessionContext { DefinitionId = fieldId, Name = "Build", Value = "A" });
    defined.Sessions[0].Events.Add(new SessionEvent { ActionId = actionId, ActionName = "Usar habilidade", Actor = "Jogador", AtSeconds = 5, MetricId = metricId, MetricName = "Precisão", Value = 0, Unit = "%" });
    var definitionsService = new GameAnalyticsService(Path.Combine(directory, "definitions"));
    defined = Decode(definitionsService.SaveGame(Encode(defined)));
    Check(!defined.Definition.HasEntities && defined.Definition.Skills[0].Name == "Controle de campos", "Free skills and game type");
    Check(defined.Sessions[0].ContextValues[0].Value == "A" && defined.Sessions[0].Events[0].Value == 0, "Context and zero-valued action output");
    defined.Definition.Metrics[0].Name = "Nova leitura";
    defined.Definition.Metrics[0].Unit = "nota";
    defined.Definition.Metrics[0].Archived = true;
    defined.Definition.Actions[0].Archived = true;
    defined = Decode(definitionsService.SaveGame(Encode(defined)));
    Check(defined.Sessions[0].Metrics[0].Name == "Precisão" && defined.Sessions[0].Metrics[0].Unit == "%", "Definition edits preserve measurement snapshots");
    Check(defined.Sessions[0].Events[0].ActionName == "Usar habilidade" && defined.Sessions[0].Events[0].Unit == "%", "Archiving preserves event history");
    var definitionsExport = Encode(defined);
    var definitionsImport = Decode(definitionsService.ImportGame(definitionsExport));
    Check(definitionsImport.Definition.Metrics[0].SkillId == skillId && definitionsImport.Sessions[0].Events[0].ActionId == actionId, "Definition links survive export/import");
    void BadDefinition(Action<GameDocument> mutate, string label) {
        var copy = Decode(definitionsExport); mutate(copy); Rejected(() => definitionsService.ImportGame(Encode(copy)), label);
    }
    BadDefinition(g => g.Definition = null, "Missing game definition");
    BadDefinition(g => g.Definition.Skills.Add(g.Definition.Skills[0]), "Duplicate skill IDs");
    BadDefinition(g => g.Definition.Metrics[0].SkillId = Guid.NewGuid().ToString(), "Dangling skill link");
    BadDefinition(g => g.Definition.Metrics.Clear(), "Cannot delete referenced metric");
    BadDefinition(g => g.Sessions[0].ContextValues[0].DefinitionId = Guid.NewGuid().ToString(), "Undefined context");
    BadDefinition(g => g.Sessions[0].Events[0].ActionId = Guid.NewGuid().ToString(), "Undefined action");
    BadDefinition(g => g.Sessions[0].Events[0].AtSeconds = -1, "Negative action time");
    BadDefinition(g => g.Sessions[0].Events[0].MetricId = "", "Output without metric");
    BadDefinition(g => g.Sessions[0].Events = null, "Null sequence");
    var legacyAgain = legacyStore.ReadFile(legacyPath + ".bak");
    Check(legacyAgain.Sessions[0].Metrics[0].DefinitionId == migrated.Sessions[0].Metrics[0].DefinitionId, "Stable legacy metric IDs across reads");

    Console.WriteLine(checks + " verificações de jogos aprovadas.");
}
finally { Directory.Delete(directory, true); }

namespace Xennex.Services {
    public static class AppLog { public static void Error(string source, Exception error) { } }
}
