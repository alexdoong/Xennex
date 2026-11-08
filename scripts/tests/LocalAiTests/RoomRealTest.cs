using System;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Xennex.Models.LocalAi;
using Xennex.Services.LocalAi;

internal static class RoomRealTest
{
    internal static async Task Run(string model)
    {
        string directory=Path.Combine(Path.GetTempPath(),"XennexRoomReal-"+Guid.NewGuid().ToString("N"));
        var service=new LocalAiService(directory);
        string Json<T>(T value)=>JsonSerializer.Serialize(value,AiStore.Json);
        JsonElement State()=>JsonDocument.Parse(service.GetState()).RootElement.Clone();
        try
        {
            Console.WriteLine("Starting owned local Ollama; no model downloads.");
            Console.WriteLine(await service.StartRuntime());
            service.SaveSettings(Json(new AiSettings{Provider="ollama",Endpoint=OllamaProcessHost.Endpoint,Model=model,AutoBudget=true,ContextTokens=4096,MaxOutputTokens=128,MemoryLimitPercent=75,KeepAliveSeconds=60}));
            var first=new AiSpecialist{Name="Calculista",Role="Cálculo",Instructions="Responda em uma frase curta."};
            var second=new AiSpecialist{Name="Revisor",Role="Verificar o cálculo",Instructions="Confira a resposta anterior em uma frase curta."};
            service.SaveSpecialist(Json(first));service.SaveSpecialist(Json(second));
            string chat=service.NewProject("Validação local de especialistas");
            service.SaveProject(chat,Json(new AiProjectEdit{Title="Validação local de especialistas",Goal="Verificar uma soma simples",Plan="Responder e revisar sem ferramentas.",Members=new(){new(){SpecialistId=first.Id},new(){SpecialistId=second.Id}}}));
            string run=service.RunProject(chat,Json(new AiRunRequest{RequestId=Guid.NewGuid().ToString("N"),Question="Quanto é 17 + 25? Escreva o resultado numérico e confira a soma.",SpecialistIds=new(){first.Id,second.Id}}));
            bool done=false;
            for(int i=0;i<300;i++)
            {
                var state=State();string status=state.GetProperty("chats")[0].GetProperty("project").GetProperty("runs")[0].GetProperty("status").GetString();
                if(status is not ("queued" or "running")){if(status!="complete")throw new Exception("Real meeting failed: "+state.GetProperty("jobs"));done=true;break;}
                if(i%40==0)Console.WriteLine("Meeting: "+state.GetProperty("jobs"));
                await Task.Delay(500);
            }
            if(!done)throw new Exception("Meeting did not complete within 150 seconds; resource gate or model latency: "+State().GetProperty("jobs"));
            var final=State();
            var answers=final.GetProperty("chats")[0].GetProperty("messages").EnumerateArray().Where(m=>m.GetProperty("role").GetString()=="assistant").ToArray();
            foreach(var answer in answers)
            {
                Console.WriteLine(answer.GetProperty("authorName").GetString()+": "+answer.GetProperty("content").GetString());
                if(!answer.GetProperty("content").GetString().Contains("42"))throw new Exception("Real arithmetic answer did not contain 42.");
            }
            if(answers.Length!=2)throw new Exception("Unexpected response count.");
            var jobs=final.GetProperty("jobs").EnumerateArray().ToArray();
            if(!jobs[1].GetProperty("demand").GetProperty("alreadyLoaded").GetBoolean())throw new Exception("Second specialist did not reuse resident model.");
            var releaseSettings=JsonSerializer.Deserialize<AiSettings>(State().GetProperty("settings").GetRawText(),AiStore.Json);
            releaseSettings.Model=""; service.SaveSettings(Json(releaseSettings));
            await service.ReleaseModel();
            using var timeout=new CancellationTokenSource(TimeSpan.FromSeconds(10));
            if((await new OllamaRuntimeClient().Inspect(OllamaProcessHost.Endpoint,timeout.Token)).Models.Any(m=>m.Loaded))throw new Exception("Model unload failed.");
            Console.WriteLine("PASS real room: two specialists, 75% budget, 42 verified twice, sequential reuse and model release.");
        }
        finally
        {
            foreach(var job in State().GetProperty("jobs").EnumerateArray().Where(j=>j.GetProperty("status").GetString() is "queued" or "running"))
                service.Cancel(job.GetProperty("id").GetString());
            for(int i=0;i<40&&State().GetProperty("jobs").EnumerateArray().Any(j=>j.GetProperty("status").GetString()=="running");i++)await Task.Delay(50);
            service.Stop();if(Directory.Exists(directory))Directory.Delete(directory,true);
        }
    }
}
