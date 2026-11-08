using System;
using System.Linq;
using System.Text;
using Xennex.Models.LocalAi;
using Xennex.Services.LocalAi;

internal static class HistoryTests
{
    internal static int Run()
    {
        int count = 0;
        void Check(bool ok, string text) { if (!ok) throw new Exception(text); count++; Console.WriteLine("PASS " + text); }
        var profile = new AiSpecialist { Name = "Nissi", Role = "Conversa e planejamento" };
        var oldRun = new AiRun { Status = "complete", Question = "Apresente suas capacidades." };
        var failedRun = new AiRun { Status = "failed", Question = "PERGUNTA-DA-TENTATIVA-FALHA" };
        var current = new AiRun { Question = "Você tem acesso ao seu caderno?", Status = "queued" };
        var question = new AiMessage { RunId = oldRun.Id, Content = oldRun.Question };
        var answer = new AiMessage { Role = "assistant", AuthorId = profile.Id, AuthorName = "Nissi", RunId = oldRun.Id,
            Content = "Já me apresentei. " + string.Concat(Enumerable.Repeat("Explicação antiga sobre capacidades. ", 120)) + "FIM-DA-RESPOSTA-ANTERIOR" };
        var output = new AiMessage { Role = "assistant", RunId = current.Id, Status = "queued" };
        var chat = new AiChat { Project = new AiProject { Members = new() { new() { SpecialistId = profile.Id } },
            Runs = new() { oldRun, failedRun, current } },
            Messages = new() { question, answer, new() { Content = failedRun.Question, RunId = failedRun.Id },
                new() { Role = "assistant", Status = "failed", RunId = failedRun.Id }, new() { RunId = current.Id, Content = current.Question }, output } };
        var job = new AiJob { MessageId = output.Id, RunId = current.Id, Specialist = profile,
            Settings = new() { Provider = "ollama", ContextTokens = 4096, MaxOutputTokens = 1024 }, Team = "Nissi", Round = 1 };
        var context = AiRoomContext.Build(chat, job);
        Check(context.History[^1].Role == "user" && context.History[^1].Content == current.Question, "latest question remains last");
        Check(context.History.Any(m => m.Role == "assistant" && m.Content.Contains("FIM-DA-RESPOSTA-ANTERIOR")), "long previous answer remains the specialist's own reply");
        Check(context.Report.MessageIds.Contains(question.Id) && context.Report.MessageIds.Contains(answer.Id), "previous question is kept together with its answer");
        Check(context.Report.ExcerptMessageIds.Contains(answer.Id) && context.History.Any(m => m.Content.Contains("trecho omitido")), "bounded excerpts are explicit in payload and audit");
        Check(Array.FindIndex(context.History,m=>m.Content==question.Content) < Array.FindIndex(context.History,m=>m.Role=="assistant"), "conversation is chronological");
        Check(!context.History.Any(m=>m.Content.Contains(failedRun.Question)), "failed attempt does not resurrect an old unanswered question");
        Check(context.History[0].Content.Contains("nenhuma nota revisada"), "empty notebook is explicitly reported to model");
        OllamaChatClient.CheckContext(job.Settings, context.History);
        Check(context.Report.EstimatedBytes == context.History.Sum(m=>Encoding.UTF8.GetByteCount(m.Content)+32), "context audit matches actual bounded payload");
        chat.Project.Members[0].ShareHistory=false;
        var privateContext=AiRoomContext.Build(chat,job);
        Check(!privateContext.History.Any(m=>m.Role=="assistant")&&!privateContext.Report.MessageIds.Contains(answer.Id), "history permission also excludes excerpts");
        chat.Project.Members[0].ShareHistory=true;
        answer.AuthorId="colleague";answer.AuthorName="Revisora";
        var colleague=AiRoomContext.Build(chat,job);
        Check(colleague.History.Any(m=>m.Role=="user"&&m.Content.Contains("Contribuição de Revisora"))&&!colleague.History.Any(m=>m.Role=="assistant"), "colleague is not impersonated as the current specialist");
        var shortPair=new[]{new AiMessage{Content="Pergunta recente"},new AiMessage{Role="assistant",AuthorId=profile.Id,Content="Resposta recente"}};
        var priorPair=new[]{question,answer};
        var selection=AiHistoryWindow.Select(new[]{priorPair,shortPair},profile.Id,500);
        Check(selection.Count==2&&selection[0].Source.Id==shortPair[0].Id, "older long exchange never leaves an orphan question after recent pair");
        var unicodePair=new[]{new AiMessage{Content="Explique"},new AiMessage{Role="assistant",AuthorId=profile.Id,Content=string.Concat(Enumerable.Repeat("ação 🎸 日本語 ",100))}};
        var unicode=AiHistoryWindow.Select(new[]{unicodePair},profile.Id,512);
        Check(unicode.Sum(e=>e.Bytes)<=512&&!unicode.Any(e=>e.Content.Contains('�')), "UTF-8 excerpts respect byte budget and complete Unicode characters");
        return count;
    }
}
