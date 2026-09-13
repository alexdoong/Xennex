// Integration test: use a dedicated app instance with local WebView2 debugging enabled.
// The test creates temporary rooms and shuts down that app instance on success.
const {chromium}=require(process.env.XENNEX_PLAYWRIGHT_PATH || 'playwright');
(async()=>{
 const browser=await chromium.connectOverCDP(process.env.XENNEX_WEBVIEW_CDP || 'http://127.0.0.1:9226');
 const page=browser.contexts()[0].pages().find(p=>p.url().includes('appassets'));
 page.on('console',m=>{if(m.type()==='error')console.log('CONSOLE',m.text())});page.on('pageerror',e=>console.log('ERROR',e.message));
 console.log('URL',page.url());
 const saved = await page.evaluate(()=>Object.fromEntries(['xennex_display_name','xennex_room_history_v2'].map(key=>[key,localStorage.getItem(key)]))); 
 await page.getByTitle('Compartilhamento de Tela & Streams',{exact:true}).evaluate(el=>el.click());
 const browserTest=await chromium.launch({channel:'msedge',headless:true});
 const guest=await browserTest.newPage();
 const base=process.env.XENNEX_TEST_URL || 'http://127.0.0.1:5179';
 const set=async(label,value)=>page.getByLabel(label,{exact:true}).evaluate((el,value)=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,value);el.dispatchEvent(new Event('input',{bubbles:true}))},value);
 try {
 for(let i=0;i<3;i++){
  const code='CRIA-QA-'+Date.now();
  await set('Seu nome','Diagnóstico app');await set('Código ou link da sala',code);
  await page.getByRole('button',{name:'Criar sala com este código',exact:true}).evaluate(el=>el.click());
  await page.locator('.room-status-connected').waitFor({timeout:42000,state:'attached'});
  await guest.goto(base+'/?room='+code);await guest.getByLabel('Seu nome',{exact:true}).fill('Browser QA');
  await guest.getByRole('button',{name:'Entrar na sala',exact:true}).click();await guest.locator('.room-status-connected').waitFor({timeout:30000});
  console.log('PASS app creates and browser joins: iteration',i+1);
  await page.getByRole('button',{name:'Sair',exact:true}).evaluate(el=>el.click());
  await guest.getByText('COORDENANDO A SALA',{exact:true}).waitFor({timeout:40000});
  await page.getByRole('button',{name:'Entrar na sala',exact:true}).evaluate(el=>el.click());
  await page.locator('.room-status-connected').waitFor({timeout:40000,state:'attached'});
  console.log('PASS app rejoins after coordinator migration: iteration',i+1);
  await page.getByRole('button',{name:'Sair',exact:true}).evaluate(el=>el.click());
  await guest.getByRole('button',{name:'Sair',exact:true}).click();
 }
 } finally {await browserTest.close(); await page.evaluate(saved=>{for(const [key,value] of Object.entries(saved)){if(value===null)localStorage.removeItem(key);else localStorage.setItem(key,value)}},saved);}
 await page.evaluate(()=>window.chrome.webview.hostObjects.api.Shutdown()).catch(()=>{});
})().catch(e=>{console.error(e);process.exit(1)});
