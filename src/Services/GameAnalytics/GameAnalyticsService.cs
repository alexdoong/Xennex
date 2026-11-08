using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using Xennex.Models.GameAnalytics;

namespace Xennex.Services.GameAnalytics
{
    public sealed class GameAnalyticsService
    {
        private readonly GameStore store;
        public GameAnalyticsService(string directory = null)
        {
            store = new GameStore(directory ?? Path.Combine(AppContext.BaseDirectory, "Data", "games"));
        }
        public string GetLibrary()
        {
            var games = new List<GameDocument>();
            var warnings = new List<string>();
            try
            {
                foreach (var file in store.Files())
                {
                    try { games.Add(store.ReadFile(file)); }
                    catch (Exception error)
                    {
                        AppLog.Error("Games.Read", error);
                        warnings.Add("Não foi possível ler " + Path.GetFileName(file) +
                            ". O arquivo foi preservado; verifique o backup .bak.");
                    }
                }
                return JsonSerializer.Serialize(new { games, warnings }, GameStore.Json);
            }
            catch (Exception error) { AppLog.Error("Games.Library", error); throw; }
        }
        public string SaveGame(string json)
        {
            try
            {
                var game = GameStore.Parse(json);
                return JsonSerializer.Serialize(store.Save(game), GameStore.Json);
            }
            catch (Exception error) { AppLog.Error("Games.Save", error); throw; }
        }
        public string ImportGame(string json)
        {
            try
            {
                var game = GameStore.Parse(json);
                // Restore as an independent copy: never overwrite another game's history.
                game.Id = Guid.NewGuid().ToString();
                game.Revision = 0;
                game.Name = game.Name.Length > 90 ? game.Name.Substring(0, 90) : game.Name;
                game.Name += " (cópia)";
                return JsonSerializer.Serialize(store.Save(game), GameStore.Json);
            }
            catch (Exception error) { AppLog.Error("Games.Import", error); throw; }
        }
    }
}
