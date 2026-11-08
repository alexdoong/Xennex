using System;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using Xennex.Models.GameAnalytics;

namespace Xennex.Services.GameAnalytics
{
    public static class GameVisualValidation
    {
        public static void Validate(GameVisual visual)
        {
            if (visual == null || visual.Characters == null || visual.Boards == null ||
                visual.Characters.Count > 100 || visual.Boards.Count > 24)
                throw new InvalidDataException("Use até 100 personagens e 24 planos por jogo.");
            Image(visual.Cover, 500000);
            var characters = visual.Characters;
            if (characters.Any(c => c == null) || characters.Select(c => c.Id).Distinct().Count() != characters.Count)
                throw new InvalidDataException("Personagens duplicados ou inválidos.");
            foreach (var character in characters)
            {
                GameValidation.Id(character.Id);
                GameValidation.Text(character.Name, 100, true);
                GameValidation.Text(character.Role, 80);
                GameValidation.Text(character.Notes, 2000);
                Image(character.Image, 250000);
                Number(character.Focus, 100);
                Color(character.Color);
            }
            if (visual.Boards.Any(b => b == null) || visual.Boards.Select(b => b.Id).Distinct().Count() != visual.Boards.Count)
                throw new InvalidDataException("Planos duplicados ou inválidos.");
            foreach (var board in visual.Boards)
            {
                GameValidation.Id(board.Id);
                GameValidation.Text(board.Name, 100, true);
                GameValidation.Text(board.Goal, 2000);
                if (board.Cards == null || board.Links == null || board.Cards.Count > 60 || board.Links.Count > 120 ||
                    board.Cards.Any(c => c == null) || board.Links.Any(l => l == null) ||
                    board.Cards.Select(c => c.Id).Distinct().Count() != board.Cards.Count)
                    throw new InvalidDataException("Use até 60 cartões e 120 conexões por plano, sem duplicar cartões.");
                foreach (var card in board.Cards)
                {
                    GameValidation.Id(card.Id);
                    GameValidation.Text(card.Title, 100, true);
                    GameValidation.Text(card.Notes, 2000);
                    if (card.CharacterId == null || (card.CharacterId != "" && !characters.Any(c => c.Id == card.CharacterId)))
                        throw new InvalidDataException("Personagem do cartão não encontrado.");
                    Number(card.X, 1000);
                    Number(card.Y, 550);
                    Color(card.Color);
                }
                if (board.Links.Select(l => l.From + ":" + l.To).Distinct().Count() != board.Links.Count)
                    throw new InvalidDataException("Conexões duplicadas.");
                foreach (var link in board.Links)
                {
                    if (link.From == link.To || !board.Cards.Any(c => c.Id == link.From) || !board.Cards.Any(c => c.Id == link.To))
                        throw new InvalidDataException("Conexão aponta para um cartão inexistente.");
                }
            }
        }
        private static void Number(double value, double max)
        {
            if (!double.IsFinite(value) || value < 0 || value > max)
                throw new InvalidDataException("Posição do elemento fora do quadro.");
        }
        private static void Color(string value)
        {
            if (value == null || !Regex.IsMatch(value, "^#[0-9a-fA-F]{6}$"))
                throw new InvalidDataException("Cor inválida.");
        }
        private static void Image(string value, int max)
        {
            if (value == "") return;
            if (value == null || value.Length > max)
                throw new InvalidDataException("Imagem muito grande. Escolha a imagem novamente pelo aplicativo.");
            var formats = new[] { "data:image/webp;base64,", "data:image/png;base64,", "data:image/jpeg;base64," };
            var prefix = formats.FirstOrDefault(p => value.StartsWith(p, StringComparison.Ordinal));
            if (prefix == null) throw new InvalidDataException("Imagem deve estar incorporada ao arquivo (WebP, PNG ou JPEG).");
            byte[] bytes;
            try { bytes = Convert.FromBase64String(value.Substring(prefix.Length)); }
            catch (FormatException) { throw new InvalidDataException("Conteúdo da imagem inválido."); }
            var valid = bytes.Length >= 12 && (prefix == formats[0]
                ? Encoding.ASCII.GetString(bytes, 0, 4) == "RIFF" && Encoding.ASCII.GetString(bytes, 8, 4) == "WEBP"
                : prefix == formats[1] ? bytes.Take(8).SequenceEqual(new byte[] { 137,80,78,71,13,10,26,10 })
                : bytes[0] == 255 && bytes[1] == 216 && bytes[2] == 255);
            if (!valid) throw new InvalidDataException("O conteúdo não corresponde ao formato da imagem.");
        }
    }
}
