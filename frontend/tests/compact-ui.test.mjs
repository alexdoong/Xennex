// Run after npm run build. No app instance or personal configuration required.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { createServer } from 'node:http';
import { readFile, mkdir } from 'node:fs/promises';
import { resolve, extname, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = resolve(fileURLToPath(new URL('../../', import.meta.url)));
const web = resolve(root, 'wwwroot');
const server = createServer(async (request, response) => {
  const name = decodeURIComponent(new URL(request.url, 'http://localhost').pathname);
  const path = resolve(web, '.' + (name === '/' ? '/index.html' : name));
  if (!path.startsWith(web + sep)) { response.writeHead(403); response.end(); return; }
  try {
    response.setHeader('Content-Type', { '.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html', '.json': 'application/json' }[extname(path)] || 'application/octet-stream');
    response.end(await readFile(path));
  } catch { response.writeHead(404); response.end(); }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const browser = await chromium.launch({ channel: 'msedge', headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1000, height: 760 } });
  const errors = []; page.on('pageerror', e => errors.push(e.message));
  await page.addInitScript(() => {
    let compact=false, pinned=false, position='MiddleRight', collapseEdge='Auto', inset=0, vertical=-1;
    const skins = { default: {name:'default'}, Personal: {name:'Personal',primaryColor:'#2244aa'} };
    let activeSkin='default';
    const aiState={settings:{model:'test-local',provider:'ollama',memoryLimitPercent:75},
      chats:[{id:'c1',title:'Conversa um',messages:[]},{id:'c2',title:'Conversa dois',messages:[]}],
      jobs:[],specialists:[],resources:{ramUsedGb:null,ramTotalGb:null,vramUsedGb:null,vramTotalGb:null},paused:false};
    const geometry = () => window.updateSidebarGeometry?.(360,680,collapseEdge==='Auto' ? (position==='TopLeft' ? 'Top' : position==='MiddleLeft' ? 'Left':'Right') : collapseEdge);
    const handlers = {
      IsSidebarMode: () => compact, IsSidebarPinned: () => pinned, SetSidebarPinned: v => { pinned=v; },
      GetSidebarAnimationFps: () => window.animationFps ?? 0, SetSidebarAnimationFps: v => { window.animationFps=v; },
      GetSidebarInset: () => inset, GetSidebarVerticalPercent: () => vertical,
      SetSidebarPlacement: (gap,height) => { inset=gap; vertical=height; },
      GetSidebarPosition: () => position, SetSidebarPosition: p => { position=p; geometry(); },
      GetSidebarCollapseEdge: () => collapseEdge, SetSidebarCollapseEdge: e => { collapseEdge=e; geometry(); },
      SetCompactInteracting: value => { window.compactInteracting=value; },
      GetAiState: () => JSON.stringify(aiState),
      GetSkinConfig: name => JSON.stringify(skins[name] || {name}), GetActiveSkin: () => activeSkin, GetAvailableSkins: () => Object.keys(skins),
      SetActiveSkin: name => { activeSkin=name; },
      SaveSkinConfig: (name,json) => { skins[name]=JSON.parse(json); activeSkin=name; return true; },
      SaveSkinAs: (name,source,json) => { skins[name]={...JSON.parse(json),name}; activeSkin=name; return JSON.stringify(skins[name]); },
      GetStreamConfig: () => '{}', GetGameLibrary: () => JSON.stringify({ games:[], warnings:[] }),
      GetAssetRoots: () => '[]', GetAssetCollections: () => '[]', GetAssetTags: () => '[]',
      GetSavedAssetQueries: () => '[]', GetRecentAssetFileOperations: () => '[]',
      IsAssetIndexPaused: () => false,
      QueryAssets: () => JSON.stringify({items:[],total:0,nextOffset:0}),
      GetAiLibrary: () => '{}', GetAppVersion: () => '0.2.3',
    };
    const api = new Proxy({}, { get: (_, key) => async (...args) => key in handlers ? handlers[key](...args) : false });
    Object.defineProperty(window, 'chrome', { configurable:true, value:{ webview:{ hostObjects:{ api },
      postMessage: message => {
        if(message==='enterSidebar' || message==='exitSidebar') {
          compact=message==='enterSidebar'; pinned=false; window.updateSidebarMode?.(compact); if(compact) geometry();
        }
      } } } });
  });
  await page.goto('http://127.0.0.1:'+server.address().port);
  await page.getByTitle('Config',{exact:true}).click();
  await page.waitForSelector('#settings-tab');
  await page.evaluate(() => {
    window.retainedContent = document.querySelector('#content');
    window.retainedStream = document.querySelector('.stream-workspace');
    window.retainedAi = document.querySelector('.local-ai-tab');
    window.retainedGames = document.querySelector('.games-tab');
  });
  await page.getByRole('button',{name:'Abrir painel compacto',exact:true}).last().click();
  await page.setViewportSize({width:360,height:680});
  await page.getByRole('region',{name:'Painel compacto'}).waitFor();
  assert.equal(await page.locator('#content').isVisible(),false);
  assert.equal(await page.locator('.left-sidebar').isVisible(),false);
  assert.equal(await page.locator('.floating-titlebar').isVisible(),false);
  assert.equal(await page.getByRole('button',{name:'Expandir Xennex'}).isVisible(),true);
  await page.getByRole('button',{name:'Manter painel aberto'}).click();
  assert.equal(await page.getByRole('button',{name:'Manter painel aberto'}).getAttribute('aria-pressed'),'true');
  await page.getByLabel('Posição na tela').selectOption('MiddleLeft');
  await page.waitForSelector('.pos-middleleft');
  await page.getByText('Ajustar posição',{exact:true}).click();
  await page.getByLabel('Distância da lateral (px)').fill('160');
  await page.getByLabel('Altura na tela',{exact:true}).fill('0');
  await page.getByLabel('FPS da animação',{exact:true}).selectOption('60');
  await page.getByRole('button',{name:'Aplicar posição',exact:true}).click();
  await page.getByRole('status').filter({hasText:'Posição salva.'}).waitFor();
  assert.equal(await page.evaluate(()=>window.chrome.webview.hostObjects.api.GetSidebarInset()),160);
  assert.equal(await page.evaluate(()=>window.chrome.webview.hostObjects.api.GetSidebarAnimationFps()),60);
  await page.getByText('Ajustar posição',{exact:true}).click();
  // Extreme skin spacing must not push native compact controls off-screen.
  await page.evaluate(() => {
    document.documentElement.style.setProperty('--content-scale','1.5');
    document.documentElement.style.setProperty('--panel-padding','48px');
    document.documentElement.style.setProperty('--sidebar-width','120px');
    document.documentElement.style.setProperty('--primary','#ee4aa5');
    document.documentElement.style.setProperty('--radius-lg','48px');
    document.documentElement.style.setProperty('--window-radius','48px');
  });
  for(const size of [{width:360,height:680},{width:360,height:450}]) {
    await page.setViewportSize(size);
    assert.equal(await page.locator('.compact-panel').evaluate(e=>e.scrollWidth<=e.clientWidth),true);
    const header=await page.locator('.compact-header').boundingBox();
    assert.ok(header.x>=0 && header.x+header.width<=size.width);
    await page.getByLabel('Posição na tela').scrollIntoViewIfNeeded();
    assert.ok(await page.getByLabel('Posição na tela').isVisible());
  }
  await page.setViewportSize({width:360,height:680});
  await mkdir(resolve(root,'bin/compact-ui'),{recursive:true});
  await page.screenshot({path:resolve(root,'bin/compact-ui/panel.png')});

  await page.getByRole('button',{name:'Abrir Início',exact:true}).click();
  assert.equal(await page.locator('.compact-grid').isVisible(),true);

  // Verify internal compact navigation
  // 1. Stream compact view
  await page.getByRole('button',{name:'Abrir Transmissões',exact:true}).click();
  await page.locator('.compact-stream').waitFor({state:'visible'});
  await page.getByRole('button',{name:'Voltar ao início',exact:true}).click();
  await page.locator('.compact-grid').waitFor({state:'visible'});

  // 2. Local AI compact view
  await page.getByRole('button',{name:'Abrir IA local',exact:true}).click();
  await page.locator('.compact-local-ai').waitFor({state:'visible'});
  await page.getByRole('button',{name:'Voltar ao início',exact:true}).click();
  await page.locator('.compact-grid').waitFor({state:'visible'});

  // 3. Games compact view
  await page.getByRole('button',{name:'Abrir Jogos',exact:true}).click();
  await page.locator('.compact-games').waitFor({state:'visible'});
  await page.getByRole('button',{name:'Voltar ao início',exact:true}).click();
  await page.locator('.compact-grid').waitFor({state:'visible'});

  // 4. Gestures compact view
  await page.getByRole('button',{name:'Abrir Gestures',exact:true}).click();
  await page.locator('.compact-gestures').waitFor({state:'visible'});
  await page.getByRole('button',{name:'Voltar ao início',exact:true}).click();
  await page.locator('.compact-grid').waitFor({state:'visible'});

  // 5. Settings compact view
  await page.getByRole('button',{name:'Abrir Configurações',exact:true}).click();
  await page.locator('.compact-settings').waitFor({state:'visible'});

  // Expand from settings compact view restores full window on settings tab
  await page.getByRole('button',{name:'Expandir Xennex'}).click();
  await page.setViewportSize({width:1000,height:760});
  await page.locator('#settings-tab').waitFor({state:'visible'});
  assert.equal(await page.evaluate(() =>
    window.retainedStream && window.retainedAi && window.retainedGames &&
    window.retainedContent===document.querySelector('#content') &&
    window.retainedStream===document.querySelector('.stream-workspace') &&
    window.retainedAi===document.querySelector('.local-ai-tab') &&
    window.retainedGames===document.querySelector('.games-tab')),true);
  assert.equal(await page.getByLabel('Posição do painel').inputValue(),'MiddleLeft');

  // Test expanding directly from inside an area's compact view
  for(let i=0;i<3;i++) {
    await page.getByRole('button',{name:'Abrir painel compacto',exact:true}).first().click();
    await page.getByRole('button',{name:'Abrir Transmissões',exact:true}).click();
    await page.locator('.compact-stream').waitFor({state:'visible'});
    await page.getByRole('button',{name:'Expandir Xennex'}).click();
    await page.locator('.stream-workspace').waitFor({state:'visible'});
  }
  assert.equal(await page.locator('.compact-panel').count(),0);

  // Draft and selection survive module navigation and expansion.
  await page.getByRole('button',{name:'Abrir painel compacto',exact:true}).first().click();
  await page.setViewportSize({width:360,height:680});
  await page.getByRole('button',{name:'Abrir IA local',exact:true}).click();
  await page.getByLabel('Conversa',{exact:true}).selectOption('c2');
  await page.getByLabel('Mensagem compacta').fill('Rascunho preservado');
  await page.waitForFunction(()=>window.compactInteracting===true);
  await page.getByRole('button',{name:'Voltar ao início',exact:true}).click();
  await page.waitForFunction(()=>window.compactInteracting===false);
  await page.getByRole('button',{name:'Abrir IA local',exact:true}).click();
  assert.equal(await page.getByLabel('Mensagem compacta').inputValue(),'Rascunho preservado');
  await page.getByRole('button',{name:'Expandir Xennex'}).click();
  await page.setViewportSize({width:1000,height:760});
  assert.equal(await page.locator('#ai-prompt').inputValue(),'Rascunho preservado');
  assert.equal(await page.locator('.ai-chat-link.selected strong').innerText(),'Conversa dois');

  // Skin selection applies immediately, and the same editor saves inside compact.
  await page.getByRole('button',{name:'Abrir painel compacto',exact:true}).first().click();
  await page.setViewportSize({width:360,height:680});
  await page.getByRole('button',{name:'Aparência',exact:true}).click();
  await page.getByLabel('Skin ativa',{exact:true}).selectOption('Personal');
  await page.waitForFunction(()=>getComputedStyle(document.documentElement).getPropertyValue('--primary').trim()==='#2244aa');
  await page.getByRole('button',{name:'Editar skin no compacto',exact:true}).click();
  await page.waitForFunction(()=>!document.querySelector('.skin-dock fieldset').disabled);
  await page.getByRole('button',{name:'Cores',exact:true}).click();
  await page.getByLabel('Cor principal',{exact:true}).fill('#14aacc');
  await page.getByRole('button',{name:'Salvar e aplicar',exact:true}).click();
  await page.getByText('Skin salva e aplicada.',{exact:true}).waitFor();
  assert.equal(await page.evaluate(async()=>JSON.parse(await window.chrome.webview.hostObjects.api.GetSkinConfig('Personal')).primaryColor),'#14aacc');
  assert.equal(await page.locator('.sidebar-mode').count(),1);
  const skinBounds=await page.locator('.skin-dock').boundingBox();
  assert.ok(skinBounds.x>=0 && skinBounds.x+skinBounds.width<=360 && skinBounds.y+skinBounds.height<=680);
  await page.screenshot({path:resolve(root,'bin/compact-ui/skin-editor.png')});
  await page.getByTitle('Fechar editor',{exact:true}).click();
  await page.getByRole('button',{name:'Expandir Xennex'}).click();
  await page.setViewportSize({width:1000,height:760});

  await page.getByTitle('Personalizar aparência',{exact:true}).click();
  await page.getByRole('complementary',{name:'Editor de skins'}).waitFor();
  await page.getByRole('button',{name:'Estrutura',exact:true}).click();
  await page.getByLabel('Navegação',{exact:true}).selectOption('right');
  await page.waitForFunction(() => { const nav=document.querySelector('.left-sidebar')?.getBoundingClientRect();
    const main=document.querySelector('.main-window')?.getBoundingClientRect(); return nav && main && nav.x>=main.right-1; });
  await page.getByRole('group',{name:'Estilos prontos'}).getByRole('button',{name:/^Terminal/}).click();
  await page.getByTitle('Descer Dashboard',{exact:true}).click();
  await page.getByLabel('Colunas em Configurações',{exact:true}).selectOption('2');
  await page.getByTitle('Subir bloco Skins',{exact:true}).click();
  await page.getByLabel('Controles da janela',{exact:true}).selectOption('center');
  await page.getByRole('button',{name:'Cartões',exact:true}).click();
  await page.getByLabel('Cor dos cartões internos',{exact:true}).fill('#10301d');
  await page.getByLabel('Opacidade dos cartões valor',{exact:true}).fill('1');
  await page.getByLabel('Espaço interno dos cartões valor',{exact:true}).fill('12');
  assert.equal(await page.locator('.left-sidebar .tabs .tab-btn').first().getAttribute('title'),'Jogos');
  await page.waitForFunction(()=>document.querySelector('.app-container')?.classList.contains('skin-nav-bottom'));
  assert.equal(await page.locator('.app-container.skin-controls-center.skin-frame-filled.skin-surface-terminal').count(),1);
  const navBox=await page.locator('.left-sidebar').boundingBox();
  const mainBox=await page.locator('.main-window').boundingBox();
  assert.ok(navBox.y>=mainBox.y+mainBox.height-1,'Bottom navigation stays below content');
  await page.waitForFunction(()=>document.querySelector('.app-container')?.classList.contains('skin-controls-center'));
  await page.waitForFunction(() => { const controls=document.querySelector('.floating-titlebar')?.getBoundingClientRect();
    const main=document.querySelector('.main-window')?.getBoundingClientRect();
    return controls && main && Math.abs(controls.x+controls.width/2-(main.x+main.width/2))<3; });
  await page.getByTitle('Recolher editor',{exact:true}).click();
  await page.screenshot({path:resolve(root,'bin/compact-ui/layout-terminal.png')});
  await page.setViewportSize({width:1300,height:800});
  await page.getByTitle('Config',{exact:true}).click();
  await page.locator('#settings-tab .settings-shell.settings-cols-2').waitFor();
  const settingsStyle=await page.locator('#settings-tab .settings-shell').evaluate(el=>getComputedStyle(el).gridTemplateColumns);
  assert.equal(settingsStyle.split(' ').length,2,'Settings uses two columns at wide viewport');
  assert.equal(await page.locator('#settings-tab [data-section="skins"]').evaluate(el=>getComputedStyle(el).order),'1');
  assert.equal(await page.locator('#settings-tab [data-section="layout"]').evaluate(el=>getComputedStyle(el).order),'2');
  const cardStyle=await page.locator('#settings-tab [data-section="skins"]').evaluate(el=>({padding:getComputedStyle(el).padding,background:getComputedStyle(el).backgroundColor}));
  assert.equal(cardStyle.padding,'12px');
  assert.equal(cardStyle.background,'rgb(16, 48, 29)');
  await page.screenshot({path:resolve(root,'bin/compact-ui/layout-settings-cards.png')});
  await page.getByRole('button',{name:/Editar skin/}).click();
  await page.getByTitle('Fechar editor',{exact:true}).click();
  await page.getByRole('button',{name:'Descartar',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('.app-container')?.classList.contains('skin-nav-left'));
  await page.getByTitle('Personalizar aparência',{exact:true}).click();
  await page.getByRole('complementary',{name:'Editor de skins'}).waitFor();
  await page.waitForFunction(()=>!document.querySelector('.skin-dock fieldset').disabled);
  await page.getByRole('button',{name:'Estrutura',exact:true}).click();
  await page.getByRole('group',{name:'Estilos prontos'}).getByRole('button',{name:/^Liquid Moon/}).click();
  await page.waitForFunction(()=>document.querySelector('.app-container')?.classList.contains('skin-surface-liquid'));
  assert.equal(await page.getByLabel('Acabamento',{exact:true}).inputValue(),'liquid');
  await page.getByRole('button',{name:'Painéis',exact:true}).click();
  await page.getByLabel('Reflexos do Liquid Glass valor',{exact:true}).fill('.73');
  await page.waitForFunction(()=>getComputedStyle(document.documentElement).getPropertyValue('--glass-rim').includes('0.4745'));
  const liquidSurface = await page.locator('#settings-tab .glass-panel').first().evaluate(el=>({
    image:getComputedStyle(el).backgroundImage,blur:getComputedStyle(el).backdropFilter,shadow:getComputedStyle(el).boxShadow
  }));
  assert(liquidSurface.image.includes('linear-gradient') && liquidSurface.blur.includes('22px') && liquidSurface.shadow.includes('inset'));
  assert.equal(await page.locator('.main-window').evaluate(el=>getComputedStyle(el,'::after').pointerEvents),'none');
  // Preview can be reverted without leaving reflections behind on other finishes.
  await page.getByTitle('Desfazer',{exact:true}).click();
  await page.getByTitle('Refazer',{exact:true}).click();
  await page.getByRole('button',{name:'Salvar e aplicar',exact:true}).click();
  await page.getByText('Skin salva e aplicada.',{exact:true}).waitFor();
  const liquidSaved = await page.evaluate(async()=>JSON.parse(await window.chrome.webview.hostObjects.api.GetSkinConfig('Personal')));
  assert.equal(liquidSaved.surfaceStyle,'liquid'); assert.equal(liquidSaved.glassHighlight,.73);
  await page.getByTitle('Recolher editor',{exact:true}).click();
  await page.screenshot({path:resolve(root,'bin/compact-ui/liquid-moon-settings.png')});
  await page.getByTitle('Biblioteca',{exact:true}).click();
  await page.locator('.assets-workspace').waitFor();
  assert((await page.locator('.assets-workspace').evaluate(el=>getComputedStyle(el).backgroundImage)).includes('linear-gradient'));
  await page.screenshot({path:resolve(root,'bin/compact-ui/liquid-moon-gallery.png')});
  await page.getByTitle('Compartilhamento de Tela & Streams',{exact:true}).click();
  await page.locator('.room-entry').waitFor();
  assert((await page.locator('.room-entry').evaluate(el=>getComputedStyle(el).backdropFilter)).includes('22px'));
  await page.getByTitle('Config',{exact:true}).click();
  await page.getByRole('button',{name:'Abrir painel compacto',exact:true}).first().click();
  await page.setViewportSize({width:360,height:680});
  await page.locator('.compact-panel').waitFor();
  const compactGlass = await page.locator('.compact-panel').evaluate(el=>({
    image:getComputedStyle(el).backgroundImage,blur:getComputedStyle(el).backdropFilter,scroll:el.scrollWidth,width:el.clientWidth
  }));
  assert(compactGlass.image.includes('linear-gradient') && compactGlass.blur==='none', 'Compact glass does not add a blur layer');
  assert(compactGlass.scroll<=compactGlass.width+1,'Compact theme keeps its width');
  await page.screenshot({path:resolve(root,'bin/compact-ui/liquid-moon-compact.png')});
  await page.getByRole('button',{name:'Expandir Xennex'}).click();
  await page.setViewportSize({width:1300,height:800});
  await page.getByRole('button',{name:/Editar skin/}).click();
  await page.getByRole('button',{name:'Estrutura',exact:true}).click();
  await page.getByLabel('Acabamento',{exact:true}).selectOption('glass');
  await page.waitForFunction(()=>document.querySelector('.app-container')?.classList.contains('skin-surface-glass'));
  assert.equal(await page.locator('.main-window').evaluate(el=>getComputedStyle(el,'::after').content),'none');
  await page.getByTitle('Fechar editor',{exact:true}).click();
  await page.getByRole('button',{name:'Descartar',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('.app-container')?.classList.contains('skin-surface-liquid'));
  await page.getByTitle('Personalizar aparência',{exact:true}).click();
  await page.getByRole('complementary',{name:'Editor de skins'}).waitFor();
  await page.evaluate(() => { window.retainedEditor=document.querySelector('.skin-dock'); window.chrome.webview.postMessage('enterSidebar'); });
  assert.equal(await page.locator('.skin-dock').isVisible(),true);
  const editorBounds=await page.locator('.skin-dock').boundingBox();
  assert.ok(editorBounds.x>=0 && editorBounds.width>0);
  await page.getByRole('button',{name:'Expandir Xennex'}).click();
  assert.equal(await page.evaluate(()=>window.retainedEditor===document.querySelector('.skin-dock')),true);
  await page.evaluate(() => window.chrome.webview.postMessage('enterSidebar'));
  await page.evaluate(() => window.showCloseModal());
  await page.getByText('Fechar Xennex',{exact:true}).waitFor();
  assert.equal(await page.locator('.compact-panel').count(),0);
  // Standalone browser and native viewer entry points must own their room provider.
  const watch=await browser.newPage();
  const watchErrors=[]; watch.on('pageerror',e=>watchErrors.push(e.message));
  await watch.goto('http://127.0.0.1:'+server.address().port+'/watch.html');
  await watch.locator('.room-entry').waitFor();
  assert.deepEqual(watchErrors,[]);
  await watch.close();
  assert.deepEqual(errors,[]);
  console.log('PASS compact UI: controls, internal navigation, small viewport, skin spacing, retained routes, repeated transitions');
} finally { await browser.close(); await new Promise(resolve=>server.close(resolve)); }
