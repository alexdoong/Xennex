// Real WebView2/COM with a bounded local model fixture; no personal workspace is used.
const assert=require('node:assert/strict');
const {createServer}=require('node:http');
const {mkdir}=require('node:fs/promises');
const {resolve}=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const phase=process.argv[2]||'write',port=process.argv[3]||9232;
const calls=[];
const server=createServer(async(req,res)=>{
  if(req.url==='/v1/models'){res.setHeader('Content-Type','application/json');res.end(JSON.stringify({data:[{id:'room-model'}]}));return;}
  if(req.url!=='/v1/chat/completions'){res.writeHead(404).end();return;}
  let raw='';for await(const part of req)raw+=part;
  const body=JSON.parse(raw);calls.push(body);
  assert.equal(body.messages.filter(m=>m.role==='system').length,1);
  res.writeHead(200,{'Content-Type':'text/event-stream'});
  res.write('data: '+JSON.stringify({choices:[{delta:{content:'Proposta local '+calls.length+': verificar evidências e medir latência.'}}]})+'\n\n');
  setTimeout(()=>res.end('data: [DONE]\n\n'),120);
});
(async()=>{
 let browser,page;
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 try {
  for(let i=0;i<50;i++){try{browser=await chromium.connectOverCDP('http://127.0.0.1:'+port);break;}catch{await new Promise(r=>setTimeout(r,200));}}
  assert.ok(browser);page=browser.contexts()[0].pages()[0];await page.waitForURL('https://appassets/**');
  await page.evaluate(async()=>{const api=window.chrome.webview.hostObjects.api;await api.SetAutoHideSidebar(false);await api.SetAutoHideTitlebar(false);});
  await page.reload();await page.setViewportSize({width:1200,height:850});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const state=()=>page.evaluate(async()=>JSON.parse(await window.chrome.webview.hostObjects.api.GetAiState()));
  const activate=async locator=>{if(phase==='read')await locator.evaluate(el=>el.click());else await locator.click();};
  await activate(page.getByTitle('IA local',{exact:true}));
  await page.getByRole('heading',{name:'Recursos e fila',exact:true}).waitFor();
  if(phase==='read'){
    const restored=await state();
    assert.equal(restored.specialists.length,2);
    assert.equal(restored.chats[0].project.notes.length,2);
    assert.equal(restored.chats[0].project.runs.length,3);
    assert.equal(restored.jobs.length,0);
    assert.equal(restored.chats[0].project.runs[0].qualityScore,4);
    await activate(page.getByRole('button',{name:'Cadernos',exact:true}));
    await page.getByText('MEMORIA-ARQUITETA: usar medições de latência.',{exact:true}).waitFor();
  } else {
    await page.evaluate(async endpoint=>{
      const api=window.chrome.webview.hostObjects.api;
      const s=JSON.parse(await api.GetAiState()).settings;
      await api.SaveAiSettings(JSON.stringify({...s,provider:'compatible',endpoint,model:'room-model',contextTokens:8192,maxOutputTokens:128,additionalRamGb:.25,additionalVramGb:.25}));
    },'http://127.0.0.1:'+server.address().port+'/v1');
    await page.getByRole('button',{name:'Especialistas',exact:true}).click();
    for(const [name,role]of[['Arquiteta','Planejamento'],['Revisora','Verificação']]){
      await page.getByLabel('Nome do especialista',{exact:true}).fill(name);
      await page.getByLabel('Papel / especialidade',{exact:true}).fill(role);
      await page.getByLabel('Instruções do especialista',{exact:true}).fill('Seja breve e diferencie evidência de hipótese.');
      await page.getByRole('button',{name:'Salvar especialista',exact:true}).click();
      await page.waitForFunction(async name=>JSON.parse(await window.chrome.webview.hostObjects.api.GetAiState()).specialists.some(p=>p.name===name),name);
      await page.getByLabel('Nome do especialista',{exact:true}).fill('');
    }
    await page.getByRole('button',{name:'Especialistas',exact:true}).click();
    await page.getByRole('button',{name:'Nova sala de projeto',exact:true}).click();
    await page.getByLabel('Nome do novo projeto',{exact:true}).fill('Laboratório de áudio');
    await page.getByRole('button',{name:'Criar sala',exact:true}).click();
    await page.getByRole('heading',{name:'Laboratório de áudio',exact:true}).waitFor();
    await page.getByRole('button',{name:'Editar plano e membros',exact:true}).click();
    await page.getByLabel('Objetivo do projeto',{exact:true}).fill('Comparar alternativas sem perder evidências.');
    await page.getByLabel('Plano geral (Markdown)',{exact:true}).fill('PLANO-RESERVADO: validar antes de implementar.');
    await page.getByLabel('Arquiteta · Planejamento',{exact:true}).check();
    await page.getByLabel('Revisora · Verificação',{exact:true}).check();
    const reviewer=page.locator('.ai-member-edit').filter({hasText:'Revisora'});
    await reviewer.getByLabel('Plano e objetivo',{exact:true}).uncheck();
    await reviewer.getByLabel('Próprio caderno',{exact:true}).uncheck();
    await page.getByRole('button',{name:'Salvar sala',exact:true}).click();
    await page.locator('.ai-project-editor').waitFor({state:'hidden'});
    await page.getByRole('button',{name:'Cadernos',exact:true}).click();
    await page.getByRole('button',{name:'Nova nota',exact:true}).click();
    await page.getByLabel('Conteúdo da nota (Markdown)',{exact:true}).fill('MEMORIA-ARQUITETA: usar medições de latência.');
    await page.getByLabel('Estado da nota',{exact:true}).selectOption('confirmed');
    await page.getByRole('button',{name:'Salvar nota revisada',exact:true}).click();
    await page.getByText('MEMORIA-ARQUITETA: usar medições de latência.',{exact:true}).waitFor();
    await page.getByRole('button',{name:'Sala',exact:true}).click();
    await page.getByRole('button',{name:'Selecionar equipe',exact:true}).click();
    await page.getByLabel('Rodadas',{exact:true}).selectOption('2');
    await page.getByLabel('Pergunta para a sala',{exact:true}).fill('Como avaliar a latência?');
    await page.getByRole('button',{name:'Iniciar discussão',exact:true}).click();
    await page.waitForFunction(async()=>JSON.parse(await window.chrome.webview.hostObjects.api.GetAiState()).chats[0].project.runs[0]?.status==='complete');
    await page.getByText('Proposta local 4: verificar evidências e medir latência.',{exact:true}).waitFor();
    assert.equal(calls.length,4);
    assert.ok(JSON.stringify(calls[0]).includes('MEMORIA-ARQUITETA'));
    // Reviewer has discussion permission, but private plan/notebook are not directly included.
    assert.ok(!JSON.stringify(calls[1]).includes('PLANO-RESERVADO'));
    assert.ok(!JSON.stringify(calls[1]).includes('MEMORIA-ARQUITETA'));
    await page.getByLabel('Revisora',{exact:true}).uncheck();
    await page.getByLabel('Rodadas',{exact:true}).selectOption('1');
    await page.getByLabel('Pergunta para a sala',{exact:true}).fill('Como avaliar a latência?');
    await page.getByRole('button',{name:'Iniciar discussão',exact:true}).click();
    await page.waitForFunction(async()=>JSON.parse(await window.chrome.webview.hostObjects.api.GetAiState()).chats[0].project.runs[1]?.status==='complete');
    await page.getByRole('button',{name:'Execuções',exact:true}).click();
    await page.locator('.ai-run').last().getByText('Avaliar resultado',{exact:true}).click();
    await page.getByLabel('Qualidade verificada',{exact:true}).selectOption('4');
    await page.getByLabel('Intervenções suas',{exact:true}).fill('1');
    await page.getByLabel('Evidências da avaliação',{exact:true}).fill('Resultado conferido nesta fixture.');
    await page.getByRole('button',{name:'Salvar avaliação',exact:true}).click();
    await page.getByText('Avaliação salva.',{exact:true}).waitFor();
    for(const box of await page.locator('.ai-run>.ai-check input').all())await box.check();
    await page.getByRole('table').waitFor();
    await page.getByRole('button',{name:'Cadernos',exact:true}).click();
    await page.getByRole('button',{name:'Propor memória',exact:true}).click();
    await page.waitForFunction(async()=>JSON.parse(await window.chrome.webview.hostObjects.api.GetAiState()).chats[0].project.notes.length===2);
    await page.locator('.ai-note').filter({hasText:'Proposta local 6'}).waitFor();
    assert.equal((await state()).chats[0].project.notes[1].status,'proposed');
    const download=page.waitForEvent('download');
    await page.getByRole('button',{name:'Exportar Markdown',exact:true}).click();
    assert.ok((await download).suggestedFilename().endsWith('.md'));
    await mkdir(resolve(__dirname,'../../bin/ai-rooms-ui'),{recursive:true});
    await page.screenshot({path:resolve(__dirname,'../../bin/ai-rooms-ui/notebooks.png'),fullPage:true});
    await page.getByRole('button',{name:'Sala',exact:true}).click();
    await page.screenshot({path:resolve(__dirname,'../../bin/ai-rooms-ui/room.png'),fullPage:true});
    await page.setViewportSize({width:780,height:720});
    await page.screenshot({path:resolve(__dirname,'../../bin/ai-rooms-ui/room-small.png'),fullPage:true});
  }
  assert.deepEqual(errors,[]);
  console.log('PASS native AI rooms '+phase);
 } catch(error) {
   if(page){console.error((await page.locator('body').innerText()).slice(-4500));await mkdir(resolve(__dirname,'../../bin/ai-rooms-ui'),{recursive:true});await page.screenshot({path:resolve(__dirname,'../../bin/ai-rooms-ui/failure.png'),fullPage:true});}
   throw error;
 } finally {
   if(page)await page.evaluate(async()=>await window.chrome.webview.hostObjects.api.Shutdown()).catch(()=>{});
   if(browser)await browser.close();server.close();
 }
})().catch(error=>{console.error(error);process.exitCode=1;});
