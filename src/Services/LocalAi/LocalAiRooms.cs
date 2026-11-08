using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Xennex.Models.LocalAi;

namespace Xennex.Services.LocalAi;

public sealed partial class LocalAiService
{
    private static T ParseRoomInput<T>(string json)
    {
        if (json == null || json.Length > 100000) throw new ArgumentException("Dados da sala acima do limite.");
        return JsonSerializer.Deserialize<T>(json, AiStore.Json) ?? throw new ArgumentException("Dados ausentes.");
    }
    private void RoomIdle(string id)
    {
        if (jobs.Any(j => j.ChatId == id && j.Status is "queued" or "running"))
            throw new InvalidOperationException("Conclua ou cancele a reunião antes de editar esta sala.");
    }
    private static AiChat FindChat(AiLibrary data, string id) => data.Chats.SingleOrDefault(c => c.Id == id) ?? throw new ArgumentException("Conversa não encontrada.");
    private static AiProject Project(AiChat chat) => chat.Project ?? throw new ArgumentException("Converta a conversa em sala primeiro.");
    private static void Revision(AiProject project, int expected)
    {
        if (project.Revision != expected) throw new InvalidOperationException("A sala mudou desde que você abriu o editor. Reabra para revisar a versão atual.");
    }
    public string SaveSpecialist(string json)
    {
        lock (sync)
        {
            EnsureLoaded();
            if (Busy) throw new InvalidOperationException("Conclua a fila antes de editar perfis usados nas respostas.");
            var item = ParseRoomInput<AiSpecialist>(json); AiRoomValidation.Specialist(item);
            var next = Copy(library); var old = next.Specialists.SingleOrDefault(s => s.Id == item.Id);
            if (old == null && item.Revision != 0 || old != null && old.Revision != item.Revision)
                throw new InvalidOperationException("O perfil mudou. Reabra o editor.");
            item.Revision++;
            next.Specialists.RemoveAll(s => s.Id == item.Id); next.Specialists.Add(item); Commit(next);
            return item.Id;
        }
    }
    public string NewProject(string title)
    {
        lock (sync)
        {
            EnsureLoaded(); AiRoomValidation.Text(title,160,"Nome da sala",true);
            var next = Copy(library);
            var chat = new AiChat { Title = title.Trim(), Project = new AiProject() };
            next.Chats.Insert(0,chat); Commit(next); return chat.Id;
        }
    }
    public void SaveProject(string id, string json)
    {
        lock (sync)
        {
            EnsureLoaded(); RoomIdle(id);
            var edit = ParseRoomInput<AiProjectEdit>(json);
            AiRoomValidation.Text(edit.Title,160,"Nome da sala",true);
            AiRoomValidation.Text(edit.Plan,12000,"Plano");
            var next = Copy(library); var chat = FindChat(next,id); chat.Project ??= new AiProject();
            var project = chat.Project; Revision(project, edit.Revision);
            string old = project.Plans.LastOrDefault()?.Content ?? "";
            if (old != edit.Plan)
            {
                if (project.Plans.Count >= 50) throw new InvalidOperationException("Limite de 50 revisões. Exporte o projeto antes de iniciar outro.");
                project.Plans.Add(new AiPlanRevision { Revision = (project.Plans.LastOrDefault()?.Revision ?? 0) + 1, Content = edit.Plan });
            }
            project.Goal = edit.Goal; project.Members = edit.Members; project.Revision++;
            chat.Title = edit.Title.Trim(); chat.UpdatedAt = DateTimeOffset.UtcNow; Commit(next);
        }
    }
    public void SaveNote(string chatId, int revision, string json)
    {
        lock (sync)
        {
            EnsureLoaded(); RoomIdle(chatId);
            var note = ParseRoomInput<AiNote>(json);
            var next = Copy(library); var chat = FindChat(next,chatId); var project = Project(chat); Revision(project,revision);
            var old = project.Notes.SingleOrDefault(n => n.Id == note.Id);
            if (!project.Members.Any(m => m.SpecialistId == note.SpecialistId)) throw new ArgumentException("Convide o especialista para editar seu caderno nesta sala.");
            note.Origin = old?.Origin ?? "user"; note.CreatedAt = old?.CreatedAt ?? DateTimeOffset.UtcNow; note.UpdatedAt = DateTimeOffset.UtcNow;
            if (old != null && old.SpecialistId != note.SpecialistId) throw new ArgumentException("Não é possível trocar o dono da nota.");
            project.Notes.RemoveAll(n => n.Id == note.Id); project.Notes.Add(note); project.Revision++;
            Commit(next);
        }
    }
    public string ExportNotebook(string chatId, string specialistId)
    {
        lock (sync)
        {
            EnsureLoaded(); var chat = FindChat(library,chatId); Project(chat);
            var specialist = library.Specialists.SingleOrDefault(s => s.Id == specialistId) ?? throw new ArgumentException("Especialista não encontrado.");
            return AiRoomContext.Notebook(chat,specialist);
        }
    }
    public void ReviewRun(string chatId, string runId, int score, int interventions, string review)
    {
        lock (sync)
        {
            EnsureLoaded();
            if (score is < -1 or > 5 || interventions is < 0 or > 1000) throw new ArgumentException("Avaliação inválida.");
            AiRoomValidation.Text(review,4000,"Avaliação");
            var next = Copy(library); var run = Project(FindChat(next,chatId)).Runs.SingleOrDefault(r => r.Id == runId) ?? throw new ArgumentException("Reunião não encontrada.");
            if (run.Status is "queued" or "running") throw new InvalidOperationException("Aguarde o encerramento para avaliar.");
            run.QualityScore = score == -1 ? null : score; run.Interventions = interventions; run.Review = review; Commit(next);
        }
    }
    public string RunProject(string chatId, string json)
    {
        lock (sync)
        {
            EnsureLoaded();
            var request = ParseRoomInput<AiRunRequest>(json);
            if (!Guid.TryParse(request.RequestId, out var requestId)) throw new ArgumentException("Identificador do pedido inválido.");
            string id = requestId.ToString("N");
            var next = Copy(library); var chat = FindChat(next,chatId); var project = Project(chat);
            // Retrying an acknowledged request must not execute it again.
            if (project.Runs.Any(r => r.Id == id)) return id;
            RoomIdle(chatId);
            if (runtimeChanging) throw new InvalidOperationException("Aguarde o motor terminar a operação.");
            AiRoomValidation.Text(request.Question,16000,"Pergunta",true);
            if (request.SpecialistIds == null || request.SpecialistIds.Count is < 1 or > 8 ||
                request.SpecialistIds.Distinct().Count() != request.SpecialistIds.Count ||
                request.SpecialistIds.Any(s => !project.Members.Any(m => m.SpecialistId == s)) ||
                request.Rounds is < 1 or > 3 || request.SpecialistIds.Count * request.Rounds > 12 ||
                request.Purpose is not ("discussion" or "memory") ||
                request.Purpose == "memory" && (request.Rounds != 1 || request.SpecialistIds.Count != 1))
                throw new ArgumentException("Selecione membros da sala, até 3 rodadas e 12 respostas. Memória usa um especialista por vez.");
            int count = request.SpecialistIds.Count * request.Rounds;
            if (jobs.Count(j => j.Status is "queued" or "running") + count > 20) throw new InvalidOperationException("A fila comporta 20 respostas. Aguarde outras tarefas.");
            if (project.Runs.Count >= 100 || chat.Messages.Count + count + 1 > 2000 || (request.Purpose == "memory" && project.Notes.Count >= 200))
                throw new InvalidOperationException("Limite de histórico da sala atingido. Exporte o projeto e comece uma nova sala.");
            var run = new AiRun { Id = id, Question = request.Question.Trim(), Rounds = request.Rounds, Purpose = request.Purpose,
                SpecialistIds = request.SpecialistIds, PlanRevision = project.Plans.LastOrDefault()?.Revision ?? 0 };
            project.Runs.Add(run);
            chat.Messages.Add(new AiMessage { Role = "user", Content = run.Question, RunId = id, Purpose = run.Purpose });
            var queued = new List<AiJob>();
            for (int round = 1; round <= run.Rounds; round++)
            foreach (var specialistId in run.SpecialistIds)
            {
                var specialist = next.Specialists.Single(s => s.Id == specialistId);
                var settings = Copy(next.Settings); if (specialist.Model != "") settings.Model = specialist.Model;
                if (string.IsNullOrWhiteSpace(settings.Model)) throw new InvalidOperationException("Escolha um modelo no perfil ou na conexão global.");
                LocalModelClient.ValidateSettings(settings);
                var message = new AiMessage { Role = "assistant", Status = "queued", AuthorId = specialist.Id, AuthorName = specialist.Name,
                    AuthorRole = specialist.Role, Model = settings.Model, RunId = id, Purpose = run.Purpose };
                chat.Messages.Add(message);
                var job = new AiJob { ChatId = chatId, MessageId = message.Id, RunId = id, Specialist = Copy(specialist), Round = round, Settings = settings,
                    Team = string.Join("; ", project.Members.Select(m => next.Specialists.Single(s => s.Id == m.SpecialistId)).Select(s => s.Name + " (" + s.Role + ")")) };
                AiRoomContext.Build(chat,job); // Fail before enqueue when essential context cannot fit.
                queued.Add(job);
            }
            chat.UpdatedAt = DateTimeOffset.UtcNow; Commit(next); jobs.AddRange(queued); TrimJobs(); StartWorker(); return id;
        }
    }
    private void TrimJobs()
    {
        while (jobs.Count > 100) jobs.RemoveAt(jobs.FindIndex(j => j.Status is not ("queued" or "running")));
    }
    private AiMessage Message(AiJob job) => FindChat(library,job.ChatId).Messages.Single(m => m.Id == job.MessageId);
    private AiMessage[] PrepareHistory(AiJob job)
    {
        var chat = FindChat(library,job.ChatId);
        if (job.RunId == "") return chat.Messages.Where(m => m.Status == "complete").Select(Copy).ToArray();
        var context = AiRoomContext.Build(chat,job); Message(job).Context = context.Report;
        Project(chat).Runs.Single(r => r.Id == job.RunId).Status = "running";
        return context.History;
    }
    private void FinishRoomTurn(AiJob job, string status)
    {
        if (job.RunId == "") return;
        var chat = FindChat(library,job.ChatId); var project = Project(chat);
        var run = project.Runs.Single(r => r.Id == job.RunId);
        if (job.StartedAt != null) run.GenerationSeconds += (DateTimeOffset.UtcNow - job.StartedAt.Value).TotalSeconds;
        if (status == "complete") run.CompletedTurns++;
        else
        {
            foreach (var sibling in jobs.Where(j => j.RunId == job.RunId && j.Status == "queued"))
            {
                sibling.Status = "cancelled"; sibling.Detail = "Reunião interrompida; nenhuma etapa dependente será executada.";
                var skipped = Message(sibling); skipped.Status = "cancelled"; skipped.Detail = sibling.Detail;
            }
            run.Status = status; run.FinishedAt = DateTimeOffset.UtcNow;
        }
        if (status != "complete" || jobs.Any(j => j.RunId == job.RunId && j.Status is "queued" or "running")) return;
        run.Status = "complete"; run.FinishedAt = DateTimeOffset.UtcNow;
        if (run.Purpose != "memory") return;
        var message = Message(job);
        if (message.Content.Trim().Length == 0) return;
        project.Notes.Add(new AiNote { SpecialistId = job.Specialist.Id, Content = message.Content.Length <= 12000 ? message.Content : message.Content.Substring(0,11880) + "\n\n[Proposta parcial: consulte a mensagem de origem para o texto completo.]",
            Origin = "model:" + job.Settings.Model, Status = "proposed",
            SourceMessageIds = (message.Context?.MessageIds ?? new()).Append(message.Id).Distinct().Take(32).ToList() });
        project.Revision++;
    }
}
