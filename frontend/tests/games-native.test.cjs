// Launched by scripts/tests/test_games_native.ps1 against an isolated app copy.
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async () => {
  let browser;
  for (let i = 0; i < 40; i++) {
    try { browser = await chromium.connectOverCDP('http://127.0.0.1:9231', { timeout: 1000 }); break; }
    catch { await new Promise(resolve => setTimeout(resolve, 250)); }
  }
  if (!browser) throw Error('WebView debugger unavailable');
  const page = browser.contexts()[0].pages()[0];
  try {
    console.log('Native WebView initial URL: ' + page.url());
    await page.waitForURL('https://appassets/**');
    await page.getByTitle('Jogos', { exact: true }).waitFor();
    await page.waitForFunction(() => !!window.chrome?.webview?.hostObjects?.api);
    if (process.argv[2] === 'write') {
      const count = await page.evaluate(async () => {
        const api = window.chrome.webview.hostObjects.api;
        const before = JSON.parse(await api.GetGameLibrary());
        if (before.games.length) throw Error('Expected a clean, isolated test directory');
        const now = new Date().toISOString();
        const game = { schemaVersion: 1, id: crypto.randomUUID(), name: 'Teste nativo Jogos', revision: 0,
          sessions: [{ id: crypto.randomUUID(), title: 'Registro persistente', occurredAt: now,
            createdAt: now, updatedAt: now, patch: '', context: 'Teste isolado', notes: 'Persistiu após reiniciar',
            source: 'manual', metrics: [{ name: 'Precisão', value: 98.5, unit: '%' }] }] };
        const saved = JSON.parse(await api.SaveGame(JSON.stringify(game)));
        const canvas = document.createElement('canvas'); canvas.width = 100; canvas.height = 150;
        canvas.getContext('2d').fillRect(0, 0, 100, 150);
        const characterId = crypto.randomUUID(), first = crypto.randomUUID(), second = crypto.randomUUID();
        saved.visual = { cover: canvas.toDataURL('image/png'), characters: [{ id: characterId, name: 'Personagem nativo', role: 'Teste', notes: '', image: canvas.toDataURL('image/png'), focus: 35, color: '#a78bfa' }],
          boards: [{ id: crypto.randomUUID(), name: 'Plano nativo', goal: 'Persistência', cards: [
            { id: first, characterId, title: 'Primeiro passo', notes: 'Preparar', color: '#a78bfa', x: 50, y: 100 },
            { id: second, characterId: '', title: 'Segundo passo', notes: 'Executar', color: '#fbbf24', x: 450, y: 100 }
          ], links: [{ from: first, to: second }] }] };
        const skillId = crypto.randomUUID(), contextId = crypto.randomUUID(), actionId = crypto.randomUUID();
        saved.definition.category = 'Jogo experimental';
        saved.definition.skills = [{ id: skillId, name: 'Controle de campo', description: 'Critério pessoal', archived: false }];
        saved.definition.contextFields = [{ id: contextId, name: 'Build', description: '', archived: false }];
        saved.definition.actions = [{ id: actionId, name: 'Habilidade principal', description: '', archived: false }];
        saved.definition.metrics[0].skillId = skillId;
        saved.sessions[0].contextValues = [{ definitionId: contextId, name: 'Build', value: 'Alternativa A' }];
        saved.sessions[0].events = [{ actionId, actionName: 'Habilidade principal', actor: 'Personagem nativo', atSeconds: 3,
          metricId: saved.definition.metrics[0].id, metricName: 'Precisão', value: 99, unit: '%', notes: 'Teste nativo' }];
        const withVisual = await api.SaveGame(JSON.stringify(saved));
        await api.ImportGame(withVisual);
        return JSON.parse(await api.GetGameLibrary()).games.length;
      });
      assert.equal(count, 2);
    }
    await page.getByTitle('Jogos', { exact: true }).dispatchEvent('click');
    await page.getByRole('button', { name: 'Recarregar', exact: true }).dispatchEvent('click');
    await page.getByRole('button', { name: 'Histórico e métricas', exact: true }).waitFor();
    await page.getByRole('button', { name: 'Histórico e métricas', exact: true }).dispatchEvent('click');
    await page.getByRole('heading', { name: 'Registro persistente', exact: true }).waitFor();
    const library = await page.evaluate(async () => JSON.parse(await window.chrome.webview.hostObjects.api.GetGameLibrary()));
    assert.equal(library.games.length, 2);
    assert.equal(library.games[0].sessions[0].metrics[0].value, 98.5);
    assert.deepEqual(library.warnings, []);
    assert.equal(library.games[0].schemaVersion, 3);
    assert.equal(library.games[0].definition.skills[0].name, 'Controle de campo');
    assert.equal(library.games[0].sessions[0].contextValues[0].value, 'Alternativa A');
    assert.equal(library.games[0].sessions[0].events[0].value, 99);
    assert.equal(library.games[0].visual.characters[0].focus, 35);
    assert.equal(library.games[0].visual.boards[0].cards[1].x, 450);
    assert.equal(library.games[0].visual.boards[0].links.length, 1);
    await page.getByRole('button', { name: 'Espaço visual', exact: true }).dispatchEvent('click');
    await page.getByRole('button', { name: 'Editar Personagem nativo', exact: true }).waitFor();
    await page.getByRole('button', { name: 'Planejamento', exact: true }).dispatchEvent('click');
    await page.getByRole('button', { name: 'Cartão Primeiro passo', exact: true }).waitFor();
    assert.equal(await page.locator('.games-board-links > path').count(), 1);
    console.log('PASS native Games ' + process.argv[2] + ': real COM bridge, independent import and persisted data.');
  } finally {
    await page.evaluate(() => window.chrome.webview.hostObjects.api.Shutdown()).catch(() => {});
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
