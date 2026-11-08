// Run after npm run build. PLAYWRIGHT_MODULE may point to a preinstalled Playwright package.
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
  const page = await browser.newPage({ viewport: { width: 1280, height: 960 } });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.addInitScript(() => {
    let games = JSON.parse(localStorage.getItem('games-test') || '[]');
    window.gameTest = { failSave: false };
    const write = json => {
      if (window.gameTest.failSave) throw Error('Falha simulada ao salvar');
      const game = JSON.parse(json); game.revision++;
      games = [...games.filter(g => g.id !== game.id), game];
      localStorage.setItem('games-test', JSON.stringify(games));
      return JSON.stringify(game);
    };
    const handlers = {
      GetGameLibrary: () => JSON.stringify({ games, warnings: [] }),
      SaveGame: write,
      ImportGame: json => {
        const game = JSON.parse(json); game.id = crypto.randomUUID(); game.name += ' (cópia)'; game.revision = 0;
        return write(JSON.stringify(game));
      },
      GetSkinConfig: () => '{}', GetActiveSkin: () => 'default', GetSidebarPosition: () => 'MiddleRight', GetStreamConfig: () => '{}'
    };
    const api = new Proxy({}, { get: (_, key) => async (...args) => key in handlers ? handlers[key](...args) : false });
    Object.defineProperty(window, 'chrome', { configurable: true, value: { webview: { hostObjects: { api }, postMessage: () => {} } } });
  });
  const url = 'http://127.0.0.1:' + server.address().port;
  await page.goto(url);
  await page.getByTitle('Jogos', { exact: true }).click();
  await page.getByLabel('Adicionar jogo', { exact: true }).fill('WuWa · laboratório visual');
  await page.getByRole('button', { name: 'Adicionar jogo', exact: true }).click();
  await page.getByRole('button', { name: 'Espaço visual', exact: true }).click();
  await page.getByRole('button', { name: 'Novo personagem', exact: true }).waitFor();
  const picture = resolve(root, 'assets/icon.png');
  await page.getByLabel('Escolher capa do jogo', { exact: true }).setInputFiles(picture);
  await page.locator('.games-hero-image').waitFor();
  for (const [name, role] of [['Suporte', 'Buffs'], ['Dano', 'Finalizador']]) {
    await page.getByRole('button', { name: 'Novo personagem', exact: true }).click();
    await page.getByLabel('Nome do personagem').fill(name);
    await page.getByLabel('Função / categoria').fill(role);
    await page.getByLabel('Escolher imagem do personagem').setInputFiles(picture);
    await page.locator('.games-portrait-preview img').waitFor();
    await page.getByLabel('Enquadramento vertical').fill('30');
    await page.getByRole('button', { name: 'Aplicar personagem', exact: true }).click();
  }
  assert.equal(await page.locator('.games-character-art img').count(), 2);
  await page.locator('.games-character').filter({ has: page.getByRole('heading', { name: 'Suporte', exact: true }) }).getByRole('button', { name: 'Usar no plano' }).click();
  await page.getByLabel('Nome do plano').fill('Rotação com buffs');
  await page.getByLabel('Objetivo do plano').fill('Aplicar suporte antes do dano principal');
  await page.getByLabel('Personagem para o quadro').selectOption({ label: 'Dano' });
  await page.getByRole('button', { name: 'Adicionar ao quadro', exact: true }).click();
  const first = page.getByRole('button', { name: 'Cartão Suporte', exact: true });
  await first.scrollIntoViewIfNeeded();
  const before = await first.evaluate(el => ({ x: parseInt(el.style.left), y: parseInt(el.style.top) }));
  const rect = await first.boundingBox();
  await page.mouse.move(rect.x + 70, rect.y + 50); await page.mouse.down();
  await page.mouse.move(rect.x + 210, rect.y + 120, { steps: 8 }); await page.mouse.up();
  const after = await first.evaluate(el => ({ x: parseInt(el.style.left), y: parseInt(el.style.top) }));
  assert.ok(Math.abs(after.x - (before.x + 140 / (rect.width / 200))) <= 1);
  assert.ok(Math.abs(after.y - (before.y + 70 / (rect.width / 200))) <= 1);
  await first.press('ArrowRight');
  assert.equal(await first.evaluate(el => parseInt(el.style.left)), after.x + 10);
  await page.getByLabel('Instruções / hipótese').fill('Buff → troca para personagem de dano');
  await page.getByLabel('Conectar com').selectOption({ label: 'Dano' });
  await page.getByRole('button', { name: 'Criar conexão', exact: true }).click();
  assert.equal(await page.locator('.games-board-links > path').count(), 1);
  await page.getByRole('button', { name: 'Adicionar anotação', exact: true }).click();
  await page.getByLabel('Título do cartão').fill('Reavaliar energia');
  await page.getByLabel('Instruções / hipótese').fill('Comparar com outra composição');
  await page.getByRole('button', { name: 'Duplicar plano', exact: true }).click();
  assert.equal(await page.locator('.games-plan-tabs button').count(), 2);
  assert.equal(await page.locator('.games-board-links > path').count(), 1);
  // A temporary tab change preserves the unsaved board.
  await page.getByTitle('Dashboard', { exact: true }).click();
  await page.getByTitle('Jogos', { exact: true }).click();
  assert.equal(await page.getByLabel('Nome do plano').inputValue(), 'Rotação com buffs (cópia)');
  await page.evaluate(() => { window.gameTest.failSave = true; });
  await page.getByRole('button', { name: 'Salvar espaço visual', exact: true }).click();
  await page.locator('.games-visual [role=alert]').filter({ hasText: 'Falha simulada' }).waitFor();
  assert.equal(await page.locator('.games-board-card').count(), 3);
  await page.evaluate(() => { window.gameTest.failSave = false; });
  await page.getByRole('button', { name: 'Salvar espaço visual', exact: true }).click();
  await page.getByText('Tudo salvo', { exact: true }).waitFor();
  const original = await page.evaluate(() => JSON.parse(localStorage.getItem('games-test'))[0]);
  assert.equal(original.schemaVersion, 3);
  assert.ok(original.visual.characters[0].image.startsWith('data:image/webp;base64,'));
  assert.equal(original.visual.boards[0].cards[0].x, after.x + 10);
  const originalIds = new Set(original.visual.boards[0].cards.map(c => c.id));
  assert.ok(original.visual.boards[1].cards.every(c => !originalIds.has(c.id)));
  assert.ok(original.visual.boards[1].cards.some(c => c.id === original.visual.boards[1].links[0].from));
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Exportar jogo', exact: true }).click();
  const downloaded = JSON.parse(await readFile(await (await downloadPromise).path(), 'utf8'));
  assert.deepEqual(downloaded.visual, original.visual);
  await page.locator('input[type=file][accept=".json,application/json"]').setInputFiles({
    name: 'visual.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(downloaded))
  });
  await page.getByRole('button', { name: 'Importar como cópia', exact: true }).click();
  await page.getByRole('heading', { name: 'WuWa · laboratório visual (cópia)', exact: true }).waitFor();
  assert.equal(await page.locator('.games-character-art img').count(), 2);
  await page.reload(); await page.getByTitle('Jogos', { exact: true }).click();
  await page.locator('.games-character-art img').first().waitFor();
  assert.equal(await page.locator('.games-character-art img').count(), 2);
  await mkdir(resolve(root, 'bin/game-ui'), { recursive: true });
  await page.locator('.games-roster').scrollIntoViewIfNeeded();
  await page.waitForTimeout(350);
  await page.screenshot({ path: resolve(root, 'bin/game-ui/characters.png'), fullPage: true });
  await page.getByRole('button', { name: 'Planejamento', exact: true }).click();
  assert.equal(await page.locator('.games-board-card').count(), 3);
  await page.locator('.games-board-scroll').scrollIntoViewIfNeeded();
  await page.screenshot({ path: resolve(root, 'bin/game-ui/planner.png'), fullPage: true });
  await page.getByRole('button', { name: 'Cartão Dano', exact: true }).click();
  await page.getByRole('button', { name: 'Remover cartão', exact: true }).click();
  assert.equal(await page.locator('.games-board-links > path').count(), 0);
  await page.getByRole('button', { name: 'Descartar alterações', exact: true }).click();
  assert.equal(await page.locator('.games-board-card').count(), 3);
  await page.getByRole('button', { name: 'Remover plano', exact: true }).click();
  assert.equal(await page.locator('.games-plan-tabs button').count(), 1);
  await page.getByRole('button', { name: 'Descartar alterações', exact: true }).click();
  await page.getByRole('button', { name: 'Personagens', exact: true }).click();
  await page.getByRole('button', { name: 'Editar Dano', exact: true }).click();
  await page.getByRole('button', { name: 'Remover personagem do elenco', exact: true }).click();
  await page.getByRole('button', { name: 'Salvar espaço visual', exact: true }).click();
  await page.getByText('Tudo salvo', { exact: true }).waitFor();
  const removed = await page.evaluate(id => JSON.parse(localStorage.getItem('games-test')).find(g => g.id === id), original.id);
  assert.equal(removed.visual.characters.length, 1);
  assert.ok(removed.visual.boards.every(b => b.cards.every(c => c.characterId === '' || removed.visual.characters.some(p => p.id === c.characterId))));
  await page.setViewportSize({ width: 620, height: 880 });
  await page.getByRole('button', { name: 'Planejamento', exact: true }).click();
  assert.equal(await page.locator('.games-tab').evaluate(el => el.scrollWidth > el.clientWidth + 2), false, 'Only board scrolls horizontally');
  assert.deepEqual(errors, []);
  console.log('Visual games UI: image upload, crop, drag, keyboard, links, duplicate, draft, errors, save, export/import, reload, removals and compact layout passed.');
} finally { await browser.close(); await new Promise(resolve => server.close(resolve)); }
