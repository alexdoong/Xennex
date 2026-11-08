using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Xennex.Models.LocalAi;
using Xennex.Services.LocalAi;

internal static class RoomTests
{
    internal static async Task<int> Run()
    {
        int count = 0;
        void Check(bool condition,string name) { if(!condition)throw new Exception(name); count++; Console.WriteLine("PASS "+name); }
        void Reject(Action action,string name) { try { action(); } catch { Check(true,name); return; } throw new Exception(name); }
        async Task Wait(Func<bool> ready,string name)
        { for(int i=0;i<200;i++){if(ready()){Check(true,name);return;}await Task.Delay(30);}throw new Exception("Timeout "+name); }
        string Json<T>(T value)=>JsonSerializer.Serialize(value,AiStore.Json);
        AiChat Chat(LocalAiService service,string id)=>JsonSerializer.Deserialize<RoomState>(service.GetState(),AiStore.Json).Chats.Single(c=>c.Id==id);
        string root=Path.Combine(Path.GetTempPath(),"XennexRooms-"+Guid.NewGuid().ToString("N"));
        var model=new RoomModel(); var service=new LocalAiService(root,model,new RoomProbe());
        try
        {
            var settings=new AiSettings { Model="room-model",ContextTokens=8192,MaxOutputTokens=128,AdditionalRamGb=.25,AdditionalVramGb=.25 };
            service.SaveSettings(Json(settings));
            var architect=new AiSpecialist{Name="Arquiteta",Role="Arquitetura",Instructions="Proponha etapas verificáveis."};
            var reviewer=new AiSpecialist{Name="Revisora",Role="Revisão",Model="review-model",Instructions="Procure falhas."};
            service.SaveSpecialist(Json(architect));service.SaveSpecialist(Json(reviewer));
            Reject(()=>service.SaveSpecialist(Json(architect)),"stale specialist update rejected");
            var id=service.NewProject("Projeto de teste");
            AiProjectEdit Edit() { var c=Chat(service,id);return new AiProjectEdit{Revision=c.Project.Revision,Title=c.Title,Goal="Objetivo reservado",Plan="PLANO-PRIVADO: validar áudio.",Members=c.Project.Members}; }
            var edit=Edit();edit.Members=new(){new(){SpecialistId=architect.Id},new(){SpecialistId=reviewer.Id,SharePlan=false,ShareHistory=false,ShareNotebook=false}};
            service.SaveProject(id,Json(edit));
            Reject(()=>service.SaveProject(id,Json(edit)),"stale project revision rejected");
            var own=new AiNote{SpecialistId=architect.Id,Content="MEMORIA-ARQUITETA: avaliar latência.",Status="confirmed"};
            service.SaveNote(id,Chat(service,id).Project.Revision,Json(own));
            var other=new AiNote{SpecialistId=reviewer.Id,Content="SEGREDO-REVISORA",Status="confirmed"};
            service.SaveNote(id,Chat(service,id).Project.Revision,Json(other));
            var proposal=new AiNote{SpecialistId=architect.Id,Content="PROPOSTA-NAO-APROVADA",Status="proposed"};
            service.SaveNote(id,Chat(service,id).Project.Revision,Json(proposal));
            var request=new AiRunRequest{RequestId=Guid.NewGuid().ToString("N"),Question="Como validar a latência?",Rounds=2,SpecialistIds=new(){architect.Id,reviewer.Id}};
            service.Pause(true);
            string runId=service.RunProject(id,Json(request));
            Check(service.RunProject(id,Json(request))==runId&&Chat(service,id).Messages.Count==5,"duplicate request is idempotent");
            Reject(()=>service.SaveProject(id,Json(Edit())),"plan and permissions cannot change during queued meeting");
            Reject(()=>service.SaveSpecialist(Json(new AiSpecialist{Name="Outro",Role="Teste"})),"profiles cannot change during a meeting");
            service.Pause(false);
            await Wait(()=>Chat(service,id).Project.Runs.Single(r=>r.Id==runId).Status=="complete","bounded meeting completes all four turns");
            Check(model.Calls.Count==4&&model.MaxConcurrent==1,"specialists share one serial resource queue");
            Check(model.Calls[0].Model=="room-model"&&model.Calls[1].Model=="review-model","per-specialist model selection preserved");
            string a=string.Join("\n",model.Calls[0].History.Select(m=>m.Content));
            string b=string.Join("\n",model.Calls[1].History.Select(m=>m.Content));
            Check(a.Contains("Revisora (Revisão)"),"specialist knows the available colleagues and roles");
            Check(a.Contains("PLANO-PRIVADO")&&a.Contains("MEMORIA-ARQUITETA")&&!a.Contains("SEGREDO-REVISORA")&&!a.Contains("PROPOSTA-NAO-APROVADA"),"only own reviewed notebook enters context");
            Check(!b.Contains("PLANO-PRIVADO")&&!b.Contains("MEMORIA-ARQUITETA")&&!b.Contains("SEGREDO-REVISORA")&&!b.Contains("Resposta local"),"denied plan history and notebook are absent from payload");
            Check(string.Join("\n",model.Calls[2].History.Select(m=>m.Content)).Contains("Resposta local 2"),"later rounds receive permitted colleague contributions");
            var savedChat=Chat(service,id);
            Check(savedChat.Messages.Where(m=>m.Role=="assistant").All(m=>m.AuthorId!=""&&m.Model!=""&&m.Context!=null),"authorship and context audit persisted");
            Check(savedChat.Project.Runs[0].CompletedTurns==4&&savedChat.Project.Runs[0].GenerationSeconds>0,"run metrics reflect actual completed calls");
            service.ReviewRun(id,runId,4,1,"Verifiquei a proposta.");
            Check(Chat(service,id).Project.Runs[0].QualityScore==4,"human evaluation persists");
            Reject(()=>service.ReviewRun(id,runId,9,0,""),"invalid quality score rejected");
            var memory=new AiRunRequest{RequestId=Guid.NewGuid().ToString("N"),Question="Resumo da revisão.",Purpose="memory",SpecialistIds=new(){architect.Id}};
            var memoryId=service.RunProject(id,Json(memory));
            await Wait(()=>Chat(service,id).Project.Runs.Single(r=>r.Id==memoryId).Status=="complete","memory checkpoint generated");
            var note=Chat(service,id).Project.Notes.Last();
            Check(note.Status=="proposed"&&note.Origin.StartsWith("model:")&&note.SourceMessageIds.Count>0,"model memory remains proposed with evidence links");
            Check(service.ExportNotebook(id,architect.Id).Contains("MEMORIA-ARQUITETA"),"notebook exports editable Markdown");
            var restart=new LocalAiService(root,model,new RoomProbe());
            Check(Chat(restart,id).Project.Notes.Count==4&&Chat(restart,id).Project.Members.Count==2,"project notebooks and memberships survive restart");
            Check(JsonDocument.Parse(restart.GetState()).RootElement.GetProperty("jobs").GetArrayLength()==0,"completed meeting never replays after restart");
            var tooBig=new AiRunRequest{RequestId=Guid.NewGuid().ToString("N"),Question=new string('x',15000),SpecialistIds=new(){architect.Id}};
            int before=Chat(service,id).Messages.Count;
            Reject(()=>service.RunProject(id,Json(tooBig)),"essential context overflow rejected before enqueue");
            Check(Chat(service,id).Messages.Count==before,"rejected context leaves no partial meeting");
            var unknown=new AiRunRequest{RequestId=Guid.NewGuid().ToString("N"),Question="oi",SpecialistIds=new(){Guid.NewGuid().ToString("N")}};
            Reject(()=>service.RunProject(id,Json(unknown)),"nonmember cannot be invoked");
            model.Fail=true;
            int callsBeforeFailure=model.Calls.Count;
            var failure=new AiRunRequest{RequestId=Guid.NewGuid().ToString("N"),Question="Falha controlada",SpecialistIds=new(){architect.Id,reviewer.Id}};
            string failureId=service.RunProject(id,Json(failure));
            await Wait(()=>Chat(service,id).Project.Runs.Single(r=>r.Id==failureId).Status=="failed","model failure aborts meeting");
            Check(model.Calls.Count==callsBeforeFailure+1&&!Chat(service,id).Messages.Any(m=>m.RunId==failureId&&m.Status is "queued" or "running"),"dependent specialists never run after failed response");
            model.Fail=false;
            model.Block=true;
            var cancelled=new AiRunRequest{RequestId=Guid.NewGuid().ToString("N"),Question="Trabalho cancelável",Rounds=2,SpecialistIds=new(){architect.Id,reviewer.Id}};
            var cancelledId=service.RunProject(id,Json(cancelled));
            await Wait(()=>Chat(service,id).Messages.Any(m=>m.RunId==cancelledId&&m.Status=="running"),"cancellable meeting starts");
            var queuedSibling=JsonDocument.Parse(service.GetState()).RootElement.GetProperty("jobs").EnumerateArray().First(j=>j.GetProperty("runId").GetString()==cancelledId&&j.GetProperty("status").GetString()=="queued").GetProperty("id").GetString();
            service.Cancel(queuedSibling);
            await Wait(()=>!Chat(service,id).Messages.Any(m=>m.RunId==cancelledId&&m.Status is "queued" or "running"),"cancelling queued sibling also stops current turn and dependents");
            Check(Chat(service,id).Project.Runs.Single(r=>r.Id==cancelledId).Status!="complete","cancelled meeting is never reported successful");
            model.Block=false;
            service.Pause(true);
            var unfinished=new AiRunRequest{RequestId=Guid.NewGuid().ToString("N"),Question="Não repetir",SpecialistIds=new(){architect.Id,reviewer.Id}};
            string unfinishedId=service.RunProject(id,Json(unfinished));
            var recovered=new LocalAiService(root,new RoomModel(),new RoomProbe());
            Check(Chat(recovered,id).Project.Runs.Single(r=>r.Id==unfinishedId).Status=="interrupted","unfinished meeting recovers as interrupted without replay");
            var legacyDir=Path.Combine(root,"legacy");Directory.CreateDirectory(legacyDir);
            File.WriteAllText(Path.Combine(legacyDir,"workspace.json"),"""{"schemaVersion":1,"settings":{"model":"legacy"},"chats":[{"id":"00000000000000000000000000000001","title":"Legado","model":"legacy","messages":[{"role":"user","content":"Olá"}]}]}""");
            var legacy=new AiStore(legacyDir).Load();
            Check(legacy.SchemaVersion==2&&legacy.Chats[0].Messages[0].Content=="Olá"&&legacy.Chats[0].Messages[0].Id!="","legacy schema migrates without losing messages");
            Check(File.ReadAllText(Path.Combine(legacyDir,"workspace.json.v1.bak")).Contains("\"schemaVersion\":1"),"original legacy schema retained in separate migration backup");
        }
        finally { service.Stop(); if(Directory.Exists(root))Directory.Delete(root,true); }
        return count;
    }
    private sealed class RoomState { public List<AiChat> Chats {get;set;}=new(); }
    private sealed class RoomProbe:IResourceProbe { public ResourceSnapshot Read()=>new(){RamTotalGb=32,RamUsedGb=8,VramTotalGb=16,VramUsedGb=2}; }
    private sealed class RoomModel:ILocalModelClient
    {
        internal readonly List<(string Model,AiMessage[] History)> Calls=new();
        internal bool Block,Fail;
        internal int Concurrent,MaxConcurrent;
        public Task<string[]> Models(AiSettings settings,CancellationToken token)=>Task.FromResult(new[]{"room-model","review-model"});
        public async Task Stream(AiSettings settings,AiMessage[] history,Action<string> append,CancellationToken token)
        {
            int n;lock(Calls){Calls.Add((settings.Model,history));n=Calls.Count;}
            int active=Interlocked.Increment(ref Concurrent);MaxConcurrent=Math.Max(MaxConcurrent,active);
            try { append("Resposta local "+n);if(Fail)throw new IOException("Fixture failure");await Task.Delay(Block?Timeout.Infinite:40,token); }
            finally { Interlocked.Decrement(ref Concurrent); }
        }
    }
}
