using System;
using System.IO;
using System.Linq;
using Xennex.Models.GameAnalytics;

namespace Xennex.Services.GameAnalytics
{
    public static class GameValidation
    {
        public static void Validate(GameDocument game)
        {
            if (game == null || game.SchemaVersion != 3)
                throw new InvalidDataException("Formato de jogos incompatível (esperado: versão 3).");
            GameVisualValidation.Validate(game.Visual);
            GameDefinitionValidation.Validate(game);
            Id(game.Id);
            Text(game.Name, 100, true);
            if (game.Revision < 0 || game.Revision == int.MaxValue)
                throw new InvalidDataException("Revisão inválida.");
            if (game.Sessions == null || game.Sessions.Count > 2000)
                throw new InvalidDataException("Limite desta etapa: 2.000 registros por jogo.");
            if (game.Sessions.Any(s => s == null) ||
                game.Sessions.Select(s => s.Id).Distinct().Count() != game.Sessions.Count)
                throw new InvalidDataException("Registros duplicados ou inválidos.");
            foreach (var session in game.Sessions)
            {
                Id(session.Id);
                Text(session.Title, 160, true);
                Text(session.Patch, 80);
                Text(session.Context, 400);
                Text(session.Notes, 8000);
                if (session.Source != "manual")
                    throw new InvalidDataException("Esta versão aceita somente registros manuais.");
                if (session.OccurredAt.Year < 1970 || session.CreatedAt.Year < 1970 ||
                    session.UpdatedAt < session.CreatedAt)
                    throw new InvalidDataException("Datas do registro inválidas.");
                if (session.Metrics == null || session.Metrics.Count > 12 ||
                    session.Metrics.Any(m => m == null))
                    throw new InvalidDataException("Use até 12 métricas por registro.");
                foreach (var metric in session.Metrics)
                {
                    Text(metric.Name, 80, true);
                    Text(metric.Unit, 30);
                    if (!double.IsFinite(metric.Value) || Math.Abs(metric.Value) > 1e15)
                        throw new InvalidDataException("Métrica deve ter um valor finito entre -10^15 e 10^15.");
                }
                if (session.Metrics.Select(m => m.DefinitionId != "" ? m.DefinitionId : m.Name.Trim().ToUpperInvariant() + "\n" +
                    m.Unit.Trim().ToUpperInvariant()).Distinct().Count() != session.Metrics.Count)
                    throw new InvalidDataException("Não repita a mesma métrica e unidade no registro.");
            }
        }
        public static void Id(string value)
        {
            if (!Guid.TryParseExact(value, "D", out _))
                throw new InvalidDataException("Identificador de jogo ou registro inválido.");
        }
        public static void Text(string value, int max, bool required = false)
        {
            if (value == null || value.Length > max || (required && string.IsNullOrWhiteSpace(value)))
                throw new InvalidDataException("Campo vazio ou acima do tamanho permitido.");
        }
    }
}
