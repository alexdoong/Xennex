// Real WebView2/COM + owned Python runtime; source is a prior experimental checkpoint.
const assert = require('node:assert/strict');
const { mkdir, writeFile } = require('node:fs/promises');
const { resolve } = require('node:path');
const { chromium } = require('playwright');
const phase = process.argv[2] || 'write';
const port = Number(process.argv[3] || 9232);
const root = resolve(__dirname, '../..');
let browser;
(async () => {
  try {
    for (let i = 0; i < 50; i++) {
      try { browser = await chromium.connectOverCDP('http://127.0.0.1:' + port); break; }
      catch { await new Promise(done => setTimeout(done, 200)); }
    }
    if (!browser) throw Error('WebView2 debugging endpoint unavailable.');
    const page = browser.contexts()[0].pages()[0];
    await page.waitForURL('https://appassets/**');
    await page.evaluate(async () => {
      const api = window.chrome.webview.hostObjects.api;
      await api.SetAutoHideSidebar(false); await api.SetAutoHideTitlebar(false);
      if (await api.IsSidebarMode()) await api.ToggleSidebar();
    });
    await page.reload();
    await page.waitForURL('https://appassets/**');
    await page.setViewportSize({ width: 1440, height: 1000 });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.getByTitle('IA local', { exact: true }).click();
    await page.getByRole('button', { name: 'Alice experimental', exact: true }).click();
    const panel = page.getByRole('region', { name: 'Alice experimental', exact: true });
    const state = async () => {
      for (let i = 0; i < 5; i++) {
        try { return await page.evaluate(async () => JSON.parse(await window.chrome.webview.hostObjects.api.GetAliceState())); }
        catch (error) {
          if (!error.message.includes('Execution context was destroyed')) throw error;
          await page.waitForURL('https://appassets/**');
          await page.waitForLoadState('domcontentloaded');
          await new Promise(done => setTimeout(done, 300));
        }
      }
      throw Error('WebView kept navigating while reading Alice state.');
    };
    const initial = await state();
    assert.equal(initial.running, false, 'Opening the panel never starts the runtime');
    assert.equal(initial.currentSnapshot, false, 'A saved report is not the current process');
    if (phase === 'write') {
      await panel.getByLabel('Python da Alice', { exact: true }).fill('C:/Users/Xenphi/AppData/Local/Programs/Python/Python311/python.exe');
      await panel.getByLabel('Estado inicial existente', { exact: true }).fill(resolve(root, 'bin/AliceMemory/reference-query-real-v1/final.pt'));
      await panel.getByLabel('Endereço local do Ollama', { exact: true }).fill('http://127.0.0.1:11438');
      await panel.getByLabel('Duração em segundos (0 = até parar)', { exact: true }).fill('60');
      await panel.locator('select').first().selectOption('0.9');
    } else {
      assert.equal(initial.snapshot.native_state.observations, 253);
      assert.equal(initial.settings.seconds, 60);
    }
    await panel.getByRole('button', { name: 'Iniciar Alice', exact: true }).click();
    let ready;
    for (let i = 0; i < 100; i++) {
      const value = await state();
      if (value.currentSnapshot && value.snapshot?.native_state) { ready = value; break; }
      if (value.exitCode != null && value.exitCode !== 0) throw Error('Native Alice startup failed: ' + JSON.stringify(value));
      await new Promise(done => setTimeout(done, 200));
    }
    assert.ok(ready, 'Real runtime publishes its current state through COM');
    assert.equal(ready.running, true);
    assert.equal(ready.snapshot.native_state.observations, 253);
    assert.equal(ready.snapshot.native_state.lifetime_moments, 217);
    await panel.getByRole('button', { name: 'Parar e salvar Alice', exact: true }).click();
    await panel.getByText('Processo parado', { exact: true }).waitFor({ timeout: 30000 });
    const stopped = await state();
    assert.equal(stopped.running, false);
    assert.equal(stopped.exitCode, 0);
    assert.equal(stopped.snapshot.native_state.observations, 253);
    await mkdir(resolve(root, 'bin/AliceMemory/panel-native'), { recursive: true });
    await writeFile(resolve(root, 'bin/AliceMemory/panel-native/' + phase + '.json'), JSON.stringify(stopped, null, 2));
    await panel.screenshot({ path: resolve(root, 'bin/AliceMemory/panel-native/' + phase + '.png') });
    assert.deepEqual(errors, []);
    console.log('PASS native Alice ' + phase + ': real COM, owned runtime, explicit start/stop, saved memory and no live sensors.');
    await page.evaluate(() => { void window.chrome.webview.hostObjects.api.Shutdown(); });
  } finally { if (browser) await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
