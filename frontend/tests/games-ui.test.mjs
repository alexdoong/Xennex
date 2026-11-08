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
  await page.getByLabel('Adicionar jogo', { exact: true }).fill('osu!');
  await page.getByLabel('Modelo inicial', { exact: true }).selectOption('Ritmo e execução');
  await page.getByRole('button', { name: 'Adicionar jogo', exact: true }).click();
  await page.getByRole('button', { name: 'Histórico e métricas', exact: true }).click();
  await page.getByRole('button', { name: 'Novo registro', exact: true }).click();
  await page.getByLabel('Título', { exact: true }).fill('Treino A');
  await page.getByLabel('Data e hora local').fill('2026-09-10T18:00');
  await page.getByLabel('Contexto', { exact: true }).fill('Mapa A sem mods');
  await page.getByLabel('Notas', { exact: true }).fill('Primeira observação');
  await page.getByRole('button', { name: 'Adicionar métrica', exact: true }).click();
  await page.getByLabel('Métrica do registro 1').selectOption({ label: 'Precisão' });
  await page.getByLabel('Valor', { exact: true }).fill('98,5');
  assert.equal(await page.getByLabel('Unidade', { exact: true }).inputValue(), '%');
  await page.getByRole('button', { name: 'Salvar registro', exact: true }).click();
  await page.getByRole('heading', { name: 'Treino A', exact: true }).waitFor();
  await page.getByRole('button', { name: 'Histórico e métricas', exact: true }).click();
  await page.getByRole('button', { name: 'Novo registro', exact: true }).click();
  await page.getByLabel('Título', { exact: true }).fill('Treino B');
  await page.getByLabel('Data e hora local').fill('2026-09-11T18:00');
  await page.getByRole('button', { name: 'Adicionar métrica', exact: true }).click();
  await page.getByLabel('Métrica do registro 1').selectOption({ label: 'Precisão' });
  await page.getByLabel('Valor', { exact: true }).fill('99');
  assert.equal(await page.getByLabel('Unidade', { exact: true }).inputValue(), '%');
  await page.evaluate(() => { window.gameTest.failSave = true; });
  await page.getByRole('button', { name: 'Salvar registro', exact: true }).click();
  await page.getByRole('alert').filter({ hasText: 'Falha simulada' }).waitFor();
  assert.equal(await page.getByLabel('Título', { exact: true }).inputValue(), 'Treino B');
  await page.evaluate(() => { window.gameTest.failSave = false; });
  await page.getByRole('button', { name: 'Salvar registro', exact: true }).click();
  await page.getByRole('heading', { name: 'Treino B', exact: true }).waitFor();
  await page.getByLabel('Comparar Treino A', { exact: true }).check();
  await page.getByLabel('Comparar Treino B', { exact: true }).check();
  assert.match(await page.locator('.games-comparison').innerText(), /0,5/);
  assert.equal(await page.locator('.games-chart circle').count(), 2);
  await page.getByLabel('De', { exact: true }).fill('2026-09-11');
  assert.equal(await page.locator('.games-timeline article').count(), 1);
  await page.getByLabel('De', { exact: true }).fill('');
  await page.locator('.games-timeline article').filter({ has: page.getByRole('heading', { name: 'Treino A', exact: true }) }).getByRole('button', { name: 'Editar registro' }).click();
  await page.getByLabel('Notas', { exact: true }).fill('Nota revisada');
  await page.getByRole('button', { name: 'Salvar registro', exact: true }).click();
  await page.getByText('Nota revisada', { exact: true }).waitFor();
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Exportar jogo', exact: true }).click();
  const download = await downloadPromise;
  const exported = JSON.parse(await readFile(await download.path(), 'utf8'));
  assert.equal(exported.sessions.length, 2);
  assert.equal(exported.sessions.find(s => s.title === 'Treino A').notes, 'Nota revisada');
  await page.locator('input[type=file]').setInputFiles({ name: 'jogo.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(exported)) });
  await page.getByRole('button', { name: 'Importar como cópia', exact: true }).click();
  await page.getByRole('heading', { name: 'osu! (cópia)', exact: true }).waitFor();
  await page.reload();
  await page.getByTitle('Jogos', { exact: true }).click();
  await page.getByRole('button', { name: 'Histórico e métricas', exact: true }).click();
  await page.getByText('Nota revisada', { exact: true }).waitFor();
  assert.equal(await page.locator('.games-library button').count(), 2);
  await page.getByLabel('Comparar Treino A', { exact: true }).check();
  await page.getByLabel('Comparar Treino B', { exact: true }).check();
  await mkdir(resolve(root, 'bin/game-ui'), { recursive: true });
  assert.equal(await page.locator('.games-tab > .glass-panel').evaluateAll(panels => panels.some(p => p.scrollHeight > p.clientHeight + 2)), false, 'Panels do not clip their content');
  await page.locator('.content-wrapper').evaluate(el => { el.scrollTop = 0; });
  await page.waitForTimeout(350);
  await page.screenshot({ path: resolve(root, 'bin/game-ui/desktop.png'), fullPage: true });
  await page.locator('.games-chart').scrollIntoViewIfNeeded();
  await page.screenshot({ path: resolve(root, 'bin/game-ui/chart.png'), fullPage: true });
  await page.setViewportSize({ width: 620, height: 880 });
  assert.equal(await page.locator('.games-tab').evaluate(el => el.scrollWidth > el.clientWidth + 2), false, 'No narrow-layout overflow');
  await page.screenshot({ path: resolve(root, 'bin/game-ui/compact.png'), fullPage: true });
  assert.deepEqual(errors, []);
  console.log('Games UI: create, metrics, save failure, edit, filters, compare, export, import, reload and compact layout passed.');
} finally { await browser.close(); await new Promise(resolve => server.close(resolve)); }
