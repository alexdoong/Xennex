using System;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using Xennex.Models.LocalAi;
using Xennex.Services.LocalAi;

internal static class ConversationRealTest
{
    internal static async Task Run(string model)
    {
        string directory=Path.Combine(Directory.GetCurrentDirectory(),"bin","AiConversationReal-"+DateTime.UtcNow.ToString("yyyyMMdd-HHmmss"));
        var service=new LocalAiService(directory);
        string Json<T>(T value)=>JsonSerializer.Serialize(value,AiStore.Json);
        AiLibrary Library()=>JsonSerializer.Deserialize<AiLibrary>(service.GetState(),AiStore.Json);
        try
        {
            Console.WriteLine(await service.StartRuntime());
            service.SaveSettings(Json(new AiSettings { Provider="ollama",Endpoint=OllamaProcessHost.Endpoint,Model=model,AutoBudget=true,
                ContextTokens=4096,MaxOutputTokens=256,MemoryLimitPercent=75,KeepAliveSeconds=60 }));
            var nissi=new AiSpecialist {Name="Nissi",Role="Conversa e planejamento",Instructions="Entenda o projeto e incorpore feedback explícito do usuário. Seja breve."};
            service.SaveSpecialist(Json(nissi));
            string id=service.NewProject("Teste de continuidade");
            service.SaveProject(id,Json(new AiProjectEdit{Title="Teste de continuidade",Goal="Verificar conversa contínua e memória revisável.",
                Members=new(){new(){SpecialistId=nissi.Id}}}));
            async Task<AiMessage> Ask(string question,string purpose="discussion")
            {
                string run=service.RunProject(id,Json(new AiRunRequest { RequestId=Guid.NewGuid().ToString("N"),Question=question,Purpose=purpose,SpecialistIds=new(){nissi.Id} }));
                for(int i=0;i<240;i++)
                {
                    var chat=Library().Chats.Single(c=>c.Id==id);
                    if(chat.Project.Runs.Single(r=>r.Id==run).Status is not ("queued" or "running"))
                    {
                        var message=chat.Messages.Last(m=>m.RunId==run&&m.Role=="assistant");
                        Console.WriteLine(question+"\n"+message.Content+"\n");
                        if(message.Status!="complete"||string.IsNullOrWhiteSpace(message.Content))throw new Exception("Response failed: "+message.Detail);
                        return message;
                    }
                    await Task.Delay(500);
                }
                throw new Exception("Test timed out; inspect queue: "+service.GetState());
            }
            await Ask("Meu nome é Ale. Como você pode me ajudar a planejar um projeto? Responda em até duas frases.");
            var notebook=await Ask("Você tem acesso ao seu caderno agora? Responda em até duas frases.");
            var number=await Ask("Prefiro respostas curtas e exemplos práticos. Não repita apresentações. Quanto é 17 + 25? Responda somente o número.");
            if(number.Content.Trim().Trim('.','!')!="42")throw new Exception("Latest arithmetic answer was not direct: "+number.Content);
            await Ask("Registre preferências explícitas do usuário para orientar futuras respostas; não invente preferências.","memory");
            var chat=Library().Chats.Single(c=>c.Id==id);
            var note=chat.Project.Notes.Last();
            if(note.Status!="proposed")throw new Exception("Memory was not proposed.");
            note.Status="confirmed";service.SaveNote(id,chat.Project.Revision,Json(note));
            chat=Library().Chats.Single(c=>c.Id==id);
            chat.Project.Members[0].ShareHistory=false;
            service.SaveProject(id,Json(new AiProjectEdit{Revision=chat.Project.Revision,Title=chat.Title,Goal=chat.Project.Goal,Plan="",Members=chat.Project.Members}));
            var recall=await Ask("Como eu prefiro que você me responda? Uma frase.");
            if(model.Contains("coder"))await Ask("Escreva somente uma função C# static bool EhPar(int n) que testa se um inteiro é par, incluindo negativos.");
            if(!System.Text.RegularExpressions.Regex.IsMatch(recall.Content,"curt|brev|concis",System.Text.RegularExpressions.RegexOptions.IgnoreCase)||!recall.Content.Contains("exemplo",StringComparison.OrdinalIgnoreCase))
                throw new Exception("Reviewed preference not recovered: "+recall.Content);
            await service.ReleaseModel();
            Console.WriteLine("PASS conversation + reviewed memory: "+model+"; inspect notebook answer for factual accuracy.");
            Console.WriteLine("Artifacts: "+directory);
        }
        finally { service.Stop(); }
    }
}
