using System;
using System.IO;
using System.Linq;
using Xennex.Models.LocalAi;

namespace Xennex.Services.LocalAi;

internal static class AiRoomValidation
{
    internal static void Text(string value, int max, string field, bool required = false)
    {
        if (value == null || value.Length > max || (required && string.IsNullOrWhiteSpace(value)))
            throw new InvalidDataException(field + ": conteúdo ausente ou acima do limite de " + max + " caracteres.");
    }
    internal static void Specialist(AiSpecialist item)
    {
        if (item == null || !Guid.TryParse(item.Id, out _) || item.Revision < 0) throw new InvalidDataException("Especialista inválido.");
        Text(item.Name, 60, "Nome", true); Text(item.Role, 120, "Papel", true);
        Text(item.Model, 200, "Modelo"); Text(item.Instructions, 4000, "Instruções");
    }
    internal static void Library(AiLibrary library)
    {
        if (library.Specialists == null || library.Specialists.Count > 32 ||
            library.Specialists.Select(s => s?.Id).Distinct().Count() != library.Specialists.Count)
            throw new InvalidDataException("Catálogo de especialistas inválido.");
        foreach (var item in library.Specialists) Specialist(item);
        foreach (var chat in library.Chats)
        {
            if (chat.Messages.Select(m => m?.Id).Distinct().Count() != chat.Messages.Count ||
                chat.Messages.Any(m => m == null || !Guid.TryParse(m.Id, out _) || m.AuthorName == null || m.AuthorName.Length > 60 ||
                m.AuthorRole == null || m.AuthorRole.Length > 120 || m.Model == null || m.Model.Length > 200 || m.Purpose is not ("discussion" or "memory")))
                throw new InvalidDataException("Autoria das mensagens inválida.");
            var project = chat.Project; if (project == null) continue;
            Text(project.Goal, 2000, "Objetivo");
            if (project.Revision < 0 || project.Members == null || project.Members.Count > 8 ||
                project.Members.Select(m => m?.SpecialistId).Distinct().Count() != project.Members.Count ||
                project.Members.Any(m => m == null || !library.Specialists.Any(s => s.Id == m.SpecialistId)))
                throw new InvalidDataException("Membros inválidos; limite de oito especialistas por sala.");
            if (project.Plans == null || project.Plans.Count > 50 || project.Plans.Any(p => p == null || p.Revision < 1) ||
                project.Plans.Select(p => p.Revision).Distinct().Count() != project.Plans.Count)
                throw new InvalidDataException("Histórico de plano inválido.");
            foreach (var plan in project.Plans) Text(plan.Content, 12000, "Plano");
            if (project.Notes == null || project.Notes.Count > 200 || project.Notes.Select(n => n?.Id).Distinct().Count() != project.Notes.Count)
                throw new InvalidDataException("Caderno inválido; limite de 200 notas por projeto.");
            foreach (var note in project.Notes)
            {
                if (note == null || !Guid.TryParse(note.Id, out _) || !library.Specialists.Any(s => s.Id == note.SpecialistId) ||
                    note.Status is not ("proposed" or "hypothesis" or "confirmed" or "superseded") ||
                    note.SourceMessageIds == null || note.SourceMessageIds.Count > 32 || note.SourceMessageIds.Any(id => !chat.Messages.Any(m => m.Id == id)))
                    throw new InvalidDataException("Nota ou referências inválidas.");
                Text(note.Content, 12000, "Nota", true); Text(note.Origin, 240, "Origem");
            }
            if (project.Runs == null || project.Runs.Count > 100 || project.Runs.Select(r => r?.Id).Distinct().Count() != project.Runs.Count)
                throw new InvalidDataException("Histórico de reuniões inválido.");
            foreach (var run in project.Runs)
            {
                if (run == null || !Guid.TryParse(run.Id, out _) || run.Rounds is < 1 or > 3 || run.SpecialistIds == null ||
                    run.SpecialistIds.Count is < 1 or > 8 || run.Rounds * run.SpecialistIds.Count > 12 ||
                    run.SpecialistIds.Any(id => !library.Specialists.Any(s => s.Id == id)) ||
                    run.Status is not ("queued" or "running" or "complete" or "interrupted" or "cancelled" or "failed") ||
                    run.Purpose is not ("discussion" or "memory") || run.QualityScore is < 0 or > 5 || run.Interventions is < 0 or > 1000)
                    throw new InvalidDataException("Reunião inválida.");
                Text(run.Question, 16000, "Pergunta", true); Text(run.Review, 4000, "Avaliação");
            }
        }
    }
}
