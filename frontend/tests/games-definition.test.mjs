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
  await page.getByLabel('Adicionar jogo', { exact: true }).fill('Ritmo personalizado');
  await page.getByLabel('Modelo inicial').selectOption('Ritmo e execução');
  await page.getByRole('button', { name: 'Adicionar jogo', exact: true }).click();
  await page.getByRole('heading', { name: 'Como funciona este jogo?', exact: true }).waitFor();
  assert.equal(await page.getByLabel('Usa personagens, cartas ou outras peças').isChecked(), false);
  await page.getByLabel('Nome de habilidade 1', { exact: true }).fill('Controle de campos');
  await page.getByRole('button', { name: 'Adicionar habilidade', exact: true }).click();
  await page.getByLabel('Nome de habilidade 4', { exact: true }).fill('Meu vocabulário livre');
  await page.getByLabel('Nome da métrica 1', { exact: true }).fill('Execução');
  await page.getByLabel('Unidade da métrica 1', { exact: true }).fill('nota');
  await page.getByLabel('Habilidade relacionada 1', { exact: true }).selectOption({ label: 'Controle de campos' });
  await page.getByLabel('Interpretação 1', { exact: true }).selectOption('higher');
  await page.getByLabel('Nome de ação 1', { exact: true }).fill('Sequência rápida');
  await page.getByRole('button', { name: 'Adicionar contexto', exact: true }).click();
  await page.getByLabel('Nome de contexto 4', { exact: true }).fill('Setup');
  await page.getByRole('button', { name: 'Salvar definições', exact: true }).click();
  await page.getByText('Definições salvas', { exact: true }).waitFor();
  await page.getByRole('button', { name: 'Espaço visual', exact: true }).click();
  assert.equal(await page.getByRole('button', { name: 'Novo personagem', exact: true }).count(), 0);
  await page.getByRole('button', { name: 'Habilidades', exact: true }).waitFor();
  await page.getByText('Controle de campos', { exact: true }).click();
  assert.match(await page.locator('.games-skill-card[open]').innerText(), /Execução/);
  await mkdir(resolve(root, 'bin/game-ui'), { recursive: true });
  await page.locator('.games-skill-grid').scrollIntoViewIfNeeded();
  await page.screenshot({ path: resolve(root, 'bin/game-ui/skills.png'), fullPage: true });
  await page.getByRole('button', { name: 'Histórico e métricas', exact: true }).click();
  for (const [title, setup, score] of [['Treino A', 'Teclado', 8], ['Treino B', 'Controle', 9]]) {
    await page.getByRole('button', { name: 'Novo registro', exact: true }).click();
    await page.getByLabel('Título', { exact: true }).fill(title);
    await page.getByLabel('Setup', { exact: true }).fill(setup);
    await page.getByRole('button', { name: 'Adicionar métrica', exact: true }).click();
    await page.getByLabel('Valor', { exact: true }).fill(String(score));
    await page.getByRole('button', { name: 'Registrar ação', exact: true }).click();
    await page.getByLabel('Tempo em segundos 1').fill('12');
    await page.getByLabel('Quem / qual peça 1').fill('Jogador');
    await page.getByLabel('Resultado medido 1').selectOption({ label: 'Execução (nota)' });
    await page.getByLabel('Valor do resultado 1 (nota)').fill(String(score + 1));
    await page.getByRole('button', { name: 'Salvar registro', exact: true }).click();
    await page.getByRole('heading', { name: title, exact: true }).waitFor();
  }
  await page.getByLabel('Agrupar por condição').selectOption({ label: 'Setup' });
  assert.match(await page.locator('.games-table-scroll').innerText(), /Teclado/);
  assert.match(await page.locator('.games-table-scroll').innerText(), /Controle/);
  await page.getByLabel('Filtrar valor da condição').fill('Teclado');
  assert.equal(await page.locator('.games-chart circle').count(), 1);
  assert.match(await page.locator('.games-chart > p').first().innerText(), /máximo 8/);
  await page.getByLabel('Origem dos valores').selectOption('events');
  assert.match(await page.locator('.games-chart > p').first().innerText(), /máximo 9/);
  await page.locator('.games-event-history summary').click();
  assert.match(await page.locator('.games-event-history ol').innerText(), /Sequência rápida/);
  await page.getByLabel('Filtrar valor da condição').fill('');
  assert.equal(await page.locator('.games-chart circle').count(), 2);
  await page.getByRole('button', { name: 'Definir jogo', exact: true }).click();
  await page.getByLabel('Nome da métrica 1', { exact: true }).fill('Execução revisada');
  await page.getByLabel('Unidade da métrica 1', { exact: true }).fill('escala nova');
  await page.getByRole('button', { name: 'Salvar definições', exact: true }).click();
  await page.getByText('Definições salvas', { exact: true }).waitFor();
  const game = await page.evaluate(() => JSON.parse(localStorage.getItem('games-test'))[0]);
  assert.equal(game.sessions[0].metrics[0].name, 'Execução');
  assert.equal(game.sessions[0].metrics[0].unit, 'nota');
  assert.equal(game.sessions[0].events[0].value, 9);
  assert.equal(game.definition.metrics[0].unit, 'escala nova');
  assert.equal(game.definition.metrics[0].skillId, game.definition.skills[0].id);
  await page.getByLabel('Adicionar jogo', { exact: true }).fill('Cartas personalizado');
  await page.getByLabel('Modelo inicial').selectOption('Cartas');
  await page.getByRole('button', { name: 'Adicionar jogo', exact: true }).click();
  await page.getByRole('button', { name: 'Espaço visual', exact: true }).click();
  await page.getByRole('button', { name: 'Cartas', exact: true }).waitFor();
  await page.getByRole('button', { name: 'Nova peça', exact: true }).click();
  await page.getByLabel('Nome da peça', { exact: true }).fill('Escudo');
  await page.getByLabel('Função / categoria').fill('Defensiva');
  await page.getByRole('button', { name: 'Aplicar peça', exact: true }).click();
  await page.getByRole('button', { name: 'Usar no plano', exact: true }).click();
  await page.getByLabel('Peça para o quadro').waitFor();
  await page.getByRole('button', { name: 'Salvar espaço visual', exact: true }).click();
  await page.getByText('Tudo salvo', { exact: true }).waitFor();
  await page.reload(); await page.getByTitle('Jogos', { exact: true }).click();
  // Imported or reloaded definitions continue to select the appropriate kind of workspace.
  const games = await page.evaluate(() => JSON.parse(localStorage.getItem('games-test')));
  assert.equal(games.length, 2);
  assert.equal(games.find(g => g.name === 'Cartas personalizado').visual.characters[0].role, 'Defensiva');
  await page.setViewportSize({ width: 620, height: 880 });
  assert.equal(await page.locator('.games-tab').evaluate(el => el.scrollWidth > el.clientWidth + 2), false);
  assert.deepEqual(errors, []);
  console.log('Game definitions UI: free skills, catalog metrics, no forced characters, contexts, action results, grouping, historical snapshots and cards passed.');
} finally { await browser.close(); await new Promise(resolve => server.close(resolve)); }
