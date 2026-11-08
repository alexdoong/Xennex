// Run after npm run build. Uses only a mocked native bridge and generated art fixtures.
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
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jN1EAAAAASUVORK5CYII=', 'base64');
const server = createServer(async (request, response) => {
  const name = decodeURIComponent(new URL(request.url, 'http://localhost').pathname);
  if (name.startsWith('/__asset/')) { response.setHeader('Content-Type', 'image/png'); response.end(png); return; }
  const path = resolve(web, '.' + (name === '/' ? '/index.html' : name));
  if (!path.startsWith(web + sep)) { response.writeHead(403); response.end(); return; }
  try {
    response.setHeader('Content-Type', { '.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html' }[extname(path)] || 'application/octet-stream');
    response.end(await readFile(path));
  } catch { response.writeHead(404); response.end(); }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const browser = await chromium.launch({ channel: 'msedge', headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1300, height: 850 } });
  await page.route('https://xennex-media.invalid/__asset/**', route => route.fulfill({ status: 200, contentType: 'image/png', body: png }));
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(() => {
    const id = '1'.repeat(32);
    const roots = [{ id: 'r1', path: 'C:\\Arts', online: true }];
    const prompt = {
      1: { class_type: 'CheckpointLoaderSimple', inputs: { ckpt_name: 'waiIllustriousSDXL_v170.safetensors' } },
      2: { class_type: 'LoraLoader', inputs: { lora_name: 'boryart_illustrious_lora.safetensors', strength_model: 1, strength_clip: 1 } },
      3: { class_type: 'CLIPTextEncode', inputs: { text: 'alice, cerulean blue hair' } },
      4: { class_type: 'CLIPTextEncode', inputs: { text: 'bad anatomy' } },
      5: { class_type: 'EmptyLatentImage', inputs: { width: 896, height: 1152 } },
      6: { class_type: 'KSampler', inputs: { seed: 1631402693, steps: 24, cfg: 6.5, sampler_name: 'euler', scheduler: 'normal', denoise: 1, positive: ['3', 0], negative: ['4', 0], latent_image: ['5', 0] } }
    };
    const metadata = JSON.stringify({ source: 'PNG text chunks', fields: { prompt: JSON.stringify(prompt) } });
    const workflow = JSON.stringify({ source: 'PNG text chunks', fields: { workflow: JSON.stringify({
      nodes: [{ id: 1, type: 'LoadImage', title: 'Origem' }, { id: 2, type: 'SaveImage', title: 'Saída' }],
      links: [[1, 1, 0, 2, 0, 'IMAGE']]
    }) } });
    const assets = [{ id, rootId: 'r1', relativePath: 'art.png', name: 'art.png', isDirectory: false,
      isImage: true, available: true, size: 100, modifiedUtc: Date.now(), favorite: false, notes: '', metadata, hasMetadata: true, tags: [] },
      { id: '2'.repeat(32), rootId: 'r1', relativePath: 'other.png', name: 'other.png', isDirectory: false,
        isImage: true, available: true, size: 120, modifiedUtc: Date.now(), favorite: false, notes: '', metadata: workflow, hasMetadata: true, tags: [] }];
    const collections = [];
    const members = new Set();
    window.__assetFixture = { assets, members };
    let plan;
    const handlers = {
      GetAssetVrState: () => JSON.stringify(window.__assetFixture.vr || { state: 'stopped', count: 0, index: 0, zoom: 1, name: '', error: '', pinned: false }),
      StartAssetVr: json => {
        if (window.__assetFixture.failVr) throw new Error('SteamVR desconectado');
        window.__assetFixture.vrRequest = JSON.parse(json);
        const chosen = assets.find(item => item.id === window.__assetFixture.vrRequest.initialId);
        const library = window.__assetFixture.vrRequest.mode === 'library';
        window.__assetFixture.vr = { state: 'running', count: library ? assets.length : window.__assetFixture.vrRequest.assetIds.length, index: 0, zoom: 1, name: chosen?.name || '', error: '', pinned: false,
          view: library ? window.__assetFixture.vrRequest.view : 'image', location: 'Todos os acervos', canPrevious: false,
          canNext: !library && window.__assetFixture.vrRequest.assetIds.length > 1 };
        return JSON.stringify(window.__assetFixture.vr);
      },
      ControlAssetVr: action => { window.__assetFixture.vrAction = action; },
      StopAssetVr: () => { window.__assetFixture.vr.state = 'stopped'; },
      MinimizeToTray: () => { window.__assetFixture.minimizes = (window.__assetFixture.minimizes || 0) + 1; },
      GetAssetRoots: () => { if (localStorage.getItem('simulateMissingAssetBridge')) throw new Error('Nome desconhecido. (0x80020006)'); return JSON.stringify(roots); },
      IsAssetIndexPaused: () => false, SetAssetIndexPaused: () => {},
      GetAssetCollections: () => JSON.stringify(collections),
      GetSavedAssetQueries: () => '[]',
      GetRecentAssetFileOperations: () => '[]',
      GetAssetTags: () => JSON.stringify([...new Set(assets.flatMap(item => item.tags))]),
      GetAssetTagOverview: json => {
        const query = JSON.parse(json);
        const counts = new Map();
        const add = (term, source) => {
          const key = term.toLowerCase();
          const value = counts.get(key) || { term, manual: 0, positive: 0, negative: 0 };
          value[source]++;
          counts.set(key, value);
        };
        for (const item of assets.filter(value => value.isImage)) for (const term of item.tags) add(term, 'manual');
        add('alice', 'positive'); add('cerulean blue hair', 'positive'); add('bad anatomy', 'negative');
        const items = [...counts.values()].filter(item => item.term.toLowerCase().includes(query.search.toLowerCase()) &&
          (query.source === 'all' || item[query.source] > 0));
        return JSON.stringify({ items: items.slice(query.offset, query.offset + query.limit), total: items.length,
          nextOffset: Math.min(items.length, query.offset + query.limit) });
      },
      QueryAssets: json => {
        const query = JSON.parse(json);
        const filtered = assets.filter(item => (!query.imagesOnly || item.isImage) && (!query.directoriesOnly || item.isDirectory) &&
          (!query.metadataOnly || item.isImage && item.hasMetadata) &&
          (!query.rootId || item.rootId === query.rootId) && (!query.search || item.name.includes(query.search)) &&
          (!query.folder || item.relativePath.startsWith(query.folder + '/')) &&
          (!query.tag || item.tags.includes(query.tag)) && (!query.favoritesOnly || item.favorite) &&
          (!query.term || (query.termSource === 'all' || query.termSource === 'manual') && item.tags.includes(query.term) ||
            item.name === 'art.png' && (query.termSource === 'all' || query.termSource === 'positive') && ['alice','cerulean blue hair'].includes(query.term) ||
            item.name === 'art.png' && (query.termSource === 'all' || query.termSource === 'negative') && query.term === 'bad anatomy') &&
          (!query.collectionId || members.has(query.collectionId + ':' + item.id)));
        return JSON.stringify({ items: filtered.slice(query.offset, query.offset + query.limit), total: filtered.length, nextOffset: Math.min(filtered.length, query.offset + query.limit) });
      },
      GetAssetDetails: assetId => JSON.stringify(assets.find(item => item.id === assetId)),
      EditAsset: json => { const edit = JSON.parse(json); const item = assets.find(value => value.id === edit.id);
        if (edit.favorite !== null) item.favorite = edit.favorite;
        if (edit.notes !== null) item.notes = edit.notes;
        if (edit.addTag) item.tags.push(edit.addTag);
        if (edit.removeTag) item.tags = item.tags.filter(value => value !== edit.removeTag);
        return JSON.stringify(item);
      },
      EditAssets: json => { const edit = JSON.parse(json); for (const item of assets.filter(value => edit.ids.includes(value.id))) {
        if (edit.favorite !== null) item.favorite = edit.favorite;
        if (edit.addTag && !item.tags.includes(edit.addTag)) item.tags.push(edit.addTag);
        if (edit.removeTag) item.tags = item.tags.filter(value => value !== edit.removeTag);
        if (edit.collectionPresent === true) members.add(edit.collectionId + ':' + item.id);
        if (edit.collectionPresent === false) members.delete(edit.collectionId + ':' + item.id);
      } },
      AddAssetCollection: name => { const value = { id: String(collections.length + 1), name }; collections.push(value); return JSON.stringify(value); },
      SetAssetCollectionItem: () => {},
      PlanAssetFileOperation: json => {
        plan = JSON.parse(json); window.__assetFixture.lastRequest = plan;
        let number = plan.naming?.autoContinue ? 23 : plan.naming?.startNumber;
        const startNumber = number ?? null;
        const items = plan.assetIds.map(assetId => {
          const item = assets.find(value => value.id === assetId);
          const choice = plan.choices.find(value => value.assetId === assetId);
          const skipped = choice?.action === 'skip';
          let name = choice?.action === 'rename' ? choice.name : plan.newName || item.name;
          if (plan.naming && !choice && !skipped) name = plan.naming.pattern.replace('{base}', plan.naming.baseName)
            .replace('{number}', String(number++).padStart(plan.naming.digits, '0')) + '.png';
          const conflict = !!window.__assetFixture.simulateNameConflict && !choice && !plan.naming && plan.conflictPolicy === 'ask';
          return { assetId, sourcePath: 'C:\\Arts\\' + item.name, destinationPath: 'C:\\Arts\\' + name,
            isDirectory: item.isDirectory, conflict, skipped, note: conflict ? 'O nome de destino está ocupado.' : '' };
        });
        return JSON.stringify({ id: 'plan1', type: plan.type, expiresUtc: Date.now() + 300000,
          canExecute: items.some(item => !item.skipped) && items.every(item => !item.conflict), startNumber, items });
      },
      ExecuteAssetFileOperation: () => { assets[0].name = plan.newName; assets[0].relativePath = plan.newName; return 'job1'; },
      GetAssetJob: () => JSON.stringify({ id: 'job1', state: 'completed', seen: 1, rootId: '', error: '' }),
      GetSkinConfig: () => '{}', GetActiveSkin: () => 'default', GetSidebarPosition: () => 'MiddleRight', GetStreamConfig: () => '{}',
      GetGameLibrary: () => JSON.stringify({ games: [], warnings: [] }), GetAiState: () => '{}'
    };
    const api = new Proxy({}, { get: (_, key) => async (...args) => key in handlers ? handlers[key](...args) : false });
    Object.defineProperty(window, 'chrome', { configurable: true, value: { webview: { hostObjects: { api }, postMessage: () => {} } } });
  });
  await page.goto('http://127.0.0.1:' + server.address().port);
  await page.getByTitle('Biblioteca', { exact: true }).click();
  await page.getByRole('heading', { name: 'Suas artes, do seu jeito.' }).waitFor();
  await page.locator('.assets-card').first().waitFor();
  await page.locator('.assets-card').filter({ hasText: 'other.png' }).click();
  await page.getByRole('button', { name: 'Abrir no VR', exact: true }).click();
  const vr = page.getByRole('dialog', { name: 'Biblioteca no VR' });
  assert.equal(await vr.getByLabel('Conteúdo do painel VR').inputValue(), 'library', 'Full library is the default even with one selected image');
  await vr.getByLabel('Conteúdo do painel VR').selectOption('selection');
  await vr.getByText('Painel fechado', { exact: true }).waitFor();
  await page.evaluate(() => { window.__assetFixture.failVr = true; });
  await vr.getByRole('button', { name: 'Abrir no SteamVR' }).click();
  await vr.getByRole('alert').getByText('SteamVR desconectado', { exact: false }).waitFor();
  assert.equal(await page.evaluate(() => window.__assetFixture.minimizes || 0), 0, 'Connection failure must not hide the app');
  await page.evaluate(() => { window.__assetFixture.failVr = false; });
  await vr.getByRole('button', { name: 'Abrir no SteamVR' }).click();
  await vr.getByText('1 / 1 · other.png · Zoom 100%', { exact: true }).waitFor();
  assert.deepEqual(await page.evaluate(() => window.__assetFixture.vrRequest.assetIds), ['2'.repeat(32)], 'VR opens selected images only');
  assert.equal(await page.evaluate(() => window.__assetFixture.minimizes), 1);
  await vr.getByRole('button', { name: 'Zoom +', exact: true }).click();
  assert.equal(await page.evaluate(() => window.__assetFixture.vrAction), 'zoomIn');
  assert.equal(await vr.getByRole('button', { name: 'Próxima', exact: true }).isDisabled(), true, 'Single-image selection has no Next action');
  await vr.getByRole('button', { name: 'Aumentar painel', exact: true }).click();
  assert.equal(await page.evaluate(() => window.__assetFixture.vrAction), 'sizeUp', 'Panel size is independent of image zoom');
  await vr.getByRole('button', { name: 'Encerrar VR' }).click();
  await vr.getByLabel('Conteúdo do painel VR').selectOption('library');
  await vr.getByRole('button', { name: 'Abrir no SteamVR' }).click();
  await vr.getByText('Todos os acervos · 2 itens · Página 1', { exact: true }).waitFor();
  assert.equal(await page.evaluate(() => window.__assetFixture.vrRequest.mode), 'library');
  assert.equal(await page.evaluate(() => window.__assetFixture.vrRequest.query.imagesOnly), true, 'Library receives current gallery filters');
  await vr.getByRole('button', { name: 'Explorador', exact: true }).click();
  assert.equal(await page.evaluate(() => window.__assetFixture.vrAction), 'explorer');
  await vr.getByRole('button', { name: 'Encerrar VR' }).click();
  await vr.getByLabel('Conteúdo do painel VR').selectOption('selection');
  await vr.getByText('Painel fechado', { exact: true }).waitFor();
  await vr.getByLabel('Minimizar o Xennex à bandeja após abrir no VR').uncheck();
  await vr.getByRole('button', { name: 'Abrir no SteamVR' }).click();
  await vr.getByText('1 / 1 · other.png · Zoom 100%', { exact: true }).waitFor();
  assert.equal(await page.evaluate(() => window.__assetFixture.minimizes), 2, 'Unchecked minimization keeps the desktop visible');
  await vr.getByRole('button', { name: 'Encerrar VR' }).click();
  await vr.getByRole('button', { name: 'Voltar à Biblioteca' }).click();
  await page.getByRole('button', { name: 'Limpar seleção' }).click();
  const beforeExpand = await page.locator('.assets-workspace').boundingBox();
  await page.getByRole('button', { name: 'Expandir área' }).click();
  const afterExpand = await page.locator('.assets-workspace').boundingBox();
  assert(afterExpand.y < beforeExpand.y - 35, 'Expanding should move the explorer upward');
  await mkdir(resolve(root, 'bin'), { recursive: true });
  await page.screenshot({ path: resolve(root, 'bin', 'assets-expanded.png') });
  await page.getByRole('button', { name: 'Mostrar cabeçalho' }).click();
  await page.locator('.assets-card img').first().evaluate(image => image.decode());
  await mkdir(resolve(root, 'bin'), { recursive: true });
  await page.screenshot({ path: resolve(root, 'bin', 'assets-ui.png') });
  assert.equal(await page.locator('.assets-card-metadata').count(), 2);
  await page.evaluate(() => window.__assetFixture.assets.push({ id: '4'.repeat(32), rootId: 'r1', relativePath: 'plain.png', name: 'plain.png',
    isDirectory: false, isImage: true, available: true, size: 80, modifiedUtc: Date.now(), favorite: false, notes: '', metadata: '', hasMetadata: false, tags: [] }));
  await page.getByRole('button', { name: 'Com metadados' }).click();
  await page.waitForFunction(() => document.querySelectorAll('.assets-card').length === 2);
  assert.equal(await page.locator('.assets-card').count(), 2);
  assert.equal(await page.getByRole('button', { name: 'Com metadados' }).getAttribute('aria-pressed'), 'true');
  await page.getByRole('button', { name: 'Com metadados' }).click();
  await page.waitForFunction(() => document.querySelectorAll('.assets-card').length === 3);
  assert.equal(await page.locator('.assets-card').count(), 3);
  await page.evaluate(() => window.__assetFixture.assets.pop());
  await page.getByRole('button', { name: 'Com metadados' }).click();
  await page.waitForFunction(() => document.querySelectorAll('.assets-card').length === 2);
  await page.getByRole('button', { name: 'Com metadados' }).click();
  assert.equal(await page.locator('.assets-card').count(), 2);
  await page.getByRole('button', { name: 'art.png' }).first().click();
  const inspector = page.getByLabel('Detalhes do item selecionado');
  await inspector.getByText('waiIllustriousSDXL_v170.safetensors', { exact: true }).waitFor();
  assert.equal(await inspector.getByText('1631402693', { exact: true }).count(), 1);
  assert.equal(await inspector.getByText('alice, cerulean blue hair', { exact: true }).count(), 1);
  assert.equal(await inspector.getByText('896 × 1152', { exact: true }).count(), 1);
  await inspector.getByRole('button', { name: 'Ver geração e nodes' }).click();
  const generation = page.getByRole('dialog', { name: 'Dados de geração de art.png' });
  await generation.getByRole('tab', { name: 'Nodes (6)' }).waitFor();
  assert.equal(await generation.locator('.assets-generation-node').count(), 6);
  assert.equal(await generation.locator('.assets-generation-links path').count(), 3);
  await generation.getByRole('tab', { name: 'Texto original' }).click();
  await generation.getByText('prompt', { exact: true }).click();
  assert.equal(await generation.locator('pre').getByText('KSampler', { exact: false }).count(), 1);
  await generation.getByRole('button', { name: 'Fechar dados de geração' }).click();
  await page.getByRole('button', { name: 'other.png' }).first().click();
  await inspector.getByRole('button', { name: 'Ver geração e nodes' }).click();
  const workflowDialog = page.getByRole('dialog', { name: 'Dados de geração de other.png' });
  assert.equal(await workflowDialog.locator('.assets-generation-node').count(), 2);
  assert.equal(await workflowDialog.locator('.assets-generation-links path').count(), 1);
  await workflowDialog.getByRole('button', { name: 'Fechar dados de geração' }).click();
  await page.getByRole('button', { name: 'art.png' }).first().click();
  await page.getByRole('button', { name: 'Favoritar' }).click();
  await page.getByLabel('Nova tag').fill('favorita');
  await page.getByTitle('Adicionar tag').click();
  assert.equal(await page.getByText('favorita').count() > 0, true);
  await page.getByRole('button', { name: 'Todas as tags' }).first().click();
  const tagBrowser = page.getByRole('dialog', { name: 'Todas as tags' });
  await tagBrowser.getByRole('tab', { name: 'Manuais' }).click();
  await tagBrowser.getByRole('button', { name: 'favorita' }).waitFor();
  await tagBrowser.getByRole('tab', { name: 'Prompt negativo' }).click();
  await tagBrowser.getByRole('button', { name: 'bad anatomy' }).waitFor();
  await tagBrowser.getByRole('tab', { name: 'Juntas' }).click();
  await tagBrowser.getByTitle('Filtrar prompt negativo').click();
  await page.getByRole('button', { name: 'Limpar filtro de tag' }).waitFor();
  assert.equal(await page.locator('.assets-card').count(), 1);
  await page.getByRole('button', { name: 'Limpar filtro de tag' }).click();
  await page.getByRole('button', { name: 'Dois painéis' }).click();
  await page.getByLabel('Orientação dos painéis').selectOption('rows');
  assert.equal(await page.locator('.assets-panes.is-stacked').count(), 1);
  await page.getByLabel('Tamanho do painel principal').fill('65');
  assert.equal(await page.locator('.assets-panes').evaluate(element => element.style.gridTemplateRows.includes('65fr')), true);
  await page.getByRole('button', { name: 'Fechar segundo painel' }).click();
  assert.equal(await page.locator('.assets-secondary-pane').count(), 0);
  await page.getByRole('button', { name: 'Dois painéis' }).click();
  await page.getByRole('button', { name: 'Fechar este painel' }).click();
  assert.equal(await page.locator('.assets-secondary-pane').count(), 0);
  await page.getByRole('button', { name: 'Galeria' }).click();
  await page.getByLabel('Nova coleção').fill('Teste');
  await page.getByTitle('Criar coleção').click();
  await page.getByRole('button', { name: 'Teste' }).click();
  await page.getByRole('button', { name: 'Selecionar vários' }).click();
  await page.locator('.assets-card').filter({ hasText: 'art.png' }).click();
  await page.locator('.assets-card').filter({ hasText: 'other.png' }).click();
  assert.equal(await page.locator('.assets-card.selected').count(), 2);
  await page.getByRole('button', { name: 'Renomear', exact: true }).click();
  const namingDialog = page.getByRole('dialog', { name: 'Renomear', exact: true });
  await namingDialog.getByLabel('Nome base', { exact: true }).fill('denia');
  await namingDialog.getByLabel('Padrão', { exact: true }).fill('{base}_{number}');
  await namingDialog.getByLabel('Dígitos', { exact: true }).fill('3');
  await namingDialog.getByRole('button', { name: 'Descer art.png · 1' }).click();
  await namingDialog.getByRole('button', { name: 'Ver prévia', exact: true }).click();
  await namingDialog.getByText('Destino: C:\\Arts\\denia_023.png', { exact: true }).waitFor();
  const namingRequest = await page.evaluate(() => window.__assetFixture.lastRequest);
  assert.deepEqual(namingRequest.assetIds, ['2'.repeat(32), '1'.repeat(32)]);
  assert.equal(namingRequest.naming.autoContinue, true);
  assert.equal(namingRequest.naming.digits, 3);
  assert.equal(await namingDialog.getByRole('button', { name: 'Confirmar renomear' }).isEnabled(), true);
  await page.screenshot({ path: resolve(root, 'bin', 'assets-naming-ui.png') });
  await namingDialog.getByLabel('Nome base', { exact: true }).fill('alice');
  assert.equal(await namingDialog.getByRole('button', { name: 'Confirmar renomear' }).isDisabled(), true,
    'Changed options must invalidate the old preview');
  await namingDialog.getByLabel('Continuar após o maior número existente no destino').uncheck();
  await namingDialog.getByLabel('Começar em', { exact: true }).fill('0');
  await namingDialog.getByLabel('Ação para art.png · 2', { exact: true }).selectOption('skip');
  await namingDialog.getByRole('button', { name: 'Atualizar prévia' }).click();
  await namingDialog.getByText('Destino: C:\\Arts\\alice_000.png', { exact: true }).waitFor();
  const skippedRequest = await page.evaluate(() => window.__assetFixture.lastRequest);
  assert.equal(skippedRequest.naming.startNumber, 0);
  assert.deepEqual(skippedRequest.choices, [{ assetId: '1'.repeat(32), action: 'skip', name: 'art.png' }]);
  await namingDialog.getByRole('button', { name: 'Fechar', exact: true }).click();
  await page.evaluate(() => { window.__assetFixture.simulateNameConflict = true; });
  await page.getByRole('button', { name: 'Mover', exact: true }).click();
  const conflictDialog = page.getByRole('dialog', { name: 'Mover arquivos' });
  await conflictDialog.getByRole('button', { name: 'Ver prévia', exact: true }).click();
  await conflictDialog.getByText('2 conflito(s).', { exact: false }).waitFor();
  assert.equal(await conflictDialog.getByRole('button', { name: 'Confirmar mover arquivos' }).isDisabled(), true);
  await conflictDialog.getByLabel('Ação para art.png · 1', { exact: true }).selectOption('rename');
  await conflictDialog.getByLabel('Novo nome de art.png · 1', { exact: true }).fill('escolhida.png');
  await conflictDialog.getByLabel('Ação para other.png · 2', { exact: true }).selectOption('skip');
  await conflictDialog.getByRole('button', { name: 'Atualizar prévia' }).click();
  await conflictDialog.getByText('Destino: C:\\Arts\\escolhida.png', { exact: true }).waitFor();
  assert.equal(await conflictDialog.getByRole('button', { name: 'Confirmar mover arquivos' }).isEnabled(), true);
  assert.equal(await conflictDialog.locator('.assets-operation-list .skipped').count(), 1);
  await conflictDialog.getByRole('button', { name: 'Fechar', exact: true }).click();
  await page.evaluate(() => { window.__assetFixture.simulateNameConflict = false; });
  await page.locator('.assets-card').filter({ hasText: 'art.png' }).click({ button: 'right' });
  await page.getByRole('menu', { name: 'Ações da seleção' }).getByRole('menuitem', { name: 'Editar tags, favoritos e coleções' }).click();
  assert.equal(await page.getByRole('dialog', { name: 'Editar seleção' }).count(), 1);
  await page.getByRole('button', { name: 'Fechar edição em lote' }).click();
  await page.getByRole('button', { name: 'Limpar seleção' }).click();
  await page.getByRole('button', { name: 'Selecionar vários' }).click();
  await page.locator('.assets-card').filter({ hasText: 'art.png' }).click();
  await page.locator('.assets-card').filter({ hasText: 'other.png' }).click({ modifiers: ['Shift'] });
  await page.getByRole('button', { name: 'Editar seleção' }).click();
  const editor = page.getByRole('dialog', { name: 'Editar seleção' });
  await editor.getByLabel('Favoritos').selectOption('yes');
  await editor.getByLabel('Adicionar tag').fill('Lote');
  await editor.locator('.assets-bulk-collection select').first().selectOption('1');
  await editor.getByRole('button', { name: 'Aplicar a 2 itens' }).click();
  const changed = await page.evaluate(() => window.__assetFixture.assets.map(item => ({ favorite: item.favorite, tags: item.tags })));
  assert(changed.every(item => item.favorite && item.tags.includes('Lote')));
  assert.equal(await page.evaluate(() => window.__assetFixture.members.size), 2);
  await page.locator('.assets-card').filter({ hasText: 'art.png' }).dblclick();
  const viewer = page.locator('.assets-viewer');
  await viewer.waitFor();
  const previous = viewer.getByRole('button', { name: 'Imagem anterior' });
  const previousBounds = await previous.boundingBox();
  assert(previousBounds.x > 150, 'Viewer navigation must stay clear of the edge sidebar');
  await viewer.getByRole('button', { name: 'Próxima imagem' }).click();
  assert.equal(await viewer.getByRole('button', { name: 'Imagem anterior' }).isEnabled(), true);
  await viewer.getByRole('button', { name: 'Fechar' }).click();
  await page.evaluate(() => window.__assetFixture.assets.push({ id: '3'.repeat(32), rootId: 'r1', relativePath: 'Organizadas', name: 'Organizadas',
    isDirectory: true, isImage: false, available: true, size: 0, modifiedUtc: Date.now(), favorite: false, notes: '', metadata: '', tags: [] }));
  await page.getByRole('button', { name: 'Explorador' }).click();
  await page.getByRole('list', { name: 'Arquivos da pasta' }).getByText('art.png').waitFor();
  await page.getByRole('button', { name: 'Selecionar página' }).click();
  assert.equal(await page.locator('.assets-row.selected').count(), 3);
  await page.locator('.assets-row').filter({ hasText: 'other.png' }).click({ button: 'right' });
  await page.getByRole('menu', { name: 'Ações da seleção' }).getByRole('menuitem', { name: 'Mover' }).click();
  assert.equal(await page.getByRole('dialog', { name: 'Mover arquivos' }).count(), 1);
  await page.getByRole('list', { name: 'Subpastas disponíveis' }).getByText('Organizadas').click();
  await page.getByRole('dialog', { name: 'Mover arquivos' }).getByText('C:\\Arts\\Organizadas', { exact: true }).waitFor();
  await page.getByRole('dialog', { name: 'Mover arquivos' }).getByRole('button', { name: 'Fechar' }).click();
  await page.getByRole('button', { name: 'Limpar seleção' }).click();
  await page.locator('.assets-row').filter({ hasText: 'art.png' }).click();
  await page.getByRole('button', { name: 'Renomear' }).click();
  await page.getByRole('dialog', { name: 'Renomear' }).getByLabel('Nome', { exact: true }).fill('nova.png');
  await page.getByRole('button', { name: 'Ver prévia' }).click();
  await page.getByText('Destino: C:\\Arts\\nova.png').waitFor();
  await page.getByRole('button', { name: 'Confirmar renomear' }).click();
  await page.getByRole('list', { name: 'Arquivos da pasta' }).getByText('nova.png').waitFor();
  await page.getByRole('button', { name: 'Busca rápida' }).click();
  await page.getByLabel('Buscar arquivos').fill('nova');
  await page.waitForFunction(() => document.querySelectorAll('.assets-row').length === 1);
  assert.equal(await page.locator('.assets-row').count(), 1);
  await page.evaluate(() => localStorage.setItem('simulateMissingAssetBridge', '1'));
  await page.reload();
  await page.getByTitle('Biblioteca', { exact: true }).click();
  await page.getByText('A interface da Biblioteca está mais recente que o executável aberto.', { exact: false }).waitFor();
  assert(await page.locator('.assets-heading').getByRole('button', { name: 'Adicionar pasta' }).isDisabled());
  await page.evaluate(() => localStorage.removeItem('simulateMissingAssetBridge'));
  assert.deepEqual(errors, []);
  console.log('assets UI: gallery, explorer, edits, file preview and VR controls passed');
} finally { await browser.close(); server.close(); }
