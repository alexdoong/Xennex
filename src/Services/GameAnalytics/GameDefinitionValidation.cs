using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Xennex.Models.GameAnalytics;

namespace Xennex.Services.GameAnalytics
{
    public static class GameDefinitionValidation
    {
        public static void Validate(GameDocument game)
        {
            var d = game.Definition ?? throw new InvalidDataException("Definição do jogo ausente.");
            GameValidation.Text(d.Category, 100, true);
            GameValidation.Text(d.EntityLabel, 80, true);
            Catalog(d.Skills); Catalog(d.Actions); Catalog(d.ContextFields); Catalog(d.Metrics);
            foreach (var metric in d.Metrics)
            {
                GameValidation.Text(metric.Unit, 30);
                if (!new[] { "neutral", "higher", "lower" }.Contains(metric.Direction))
                    throw new InvalidDataException("Interpretação da métrica inválida.");
                if (metric.SkillId == null || metric.SkillId != "" && !d.Skills.Any(s => s.Id == metric.SkillId))
                    throw new InvalidDataException("Habilidade da métrica não encontrada.");
            }
            foreach (var session in game.Sessions ?? new())
            {
                if (session == null) continue;
                if (session.ContextValues == null || session.Events == null || session.ContextValues.Count > 50 || session.Events.Count > 120)
                    throw new InvalidDataException("Limite de 50 campos de contexto e 120 ações por registro.");
                if (session.ContextValues.Any(c => c == null) || session.ContextValues.Select(c => c.DefinitionId).Distinct().Count() != session.ContextValues.Count)
                    throw new InvalidDataException("Contextos inválidos ou duplicados.");
                foreach (var context in session.ContextValues)
                {
                    if (!d.ContextFields.Any(c => c.Id == context.DefinitionId)) throw new InvalidDataException("Campo de contexto não definido.");
                    GameValidation.Text(context.Name, 80, true);
                    GameValidation.Text(context.Value, 400);
                }
                foreach (var metric in session.Metrics ?? new())
                {
                    if (metric == null) continue;
                    // Empty IDs are retained for unclassified legacy records; the editor uses the catalog.
                    if (metric.DefinitionId == null || metric.DefinitionId != "" && !d.Metrics.Any(m => m.Id == metric.DefinitionId))
                        throw new InvalidDataException("Métrica do registro não definida.");
                }
                foreach (var action in session.Events)
                {
                    if (action == null || !d.Actions.Any(a => a.Id == action.ActionId)) throw new InvalidDataException("Ação do registro não definida.");
                    GameValidation.Text(action.ActionName, 80, true);
                    GameValidation.Text(action.Actor, 100);
                    GameValidation.Text(action.Notes, 2000);
                    GameValidation.Text(action.Unit, 30);
                    GameValidation.Text(action.MetricName, 80);
                    if (!double.IsFinite(action.AtSeconds) || action.AtSeconds < 0 || action.AtSeconds > 604800)
                        throw new InvalidDataException("Tempo da ação inválido.");
                    if (action.MetricId == null || action.MetricId != "" && !d.Metrics.Any(m => m.Id == action.MetricId))
                        throw new InvalidDataException("Resultado da ação não definido.");
                    if (action.Value.HasValue && (action.MetricId == "" || !double.IsFinite(action.Value.Value) || Math.Abs(action.Value.Value) > 1e15))
                        throw new InvalidDataException("Resultado numérico da ação inválido.");
                }
            }
        }
        private static void Catalog<T>(List<T> items) where T : NamedGameDefinition
        {
            if (items == null || items.Count > 100 || items.Any(i => i == null) ||
                items.Select(i => i.Id).Distinct().Count() != items.Count)
                throw new InvalidDataException("Catálogo inválido: use até 100 definições sem IDs duplicados.");
            foreach (var item in items)
            {
                GameValidation.Id(item.Id);
                GameValidation.Text(item.Name, 80, true);
                GameValidation.Text(item.Description, 2000);
            }
        }
    }
}
