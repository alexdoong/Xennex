import assert from 'node:assert/strict';
import { chromium } from 'playwright';
const base = process.env.XENNEX_TEST_URL || 'http://127.0.0.1:5179';
const browser = await chromium.launch({ channel: 'msedge', headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(() => {
    window.chrome ??= {};
    window.chrome.webview = { hostObjects: { api: {
      GetAudioProcesses: async () => '[]',
      GetCaptureMonitors: async () => JSON.stringify([
        { Id: 'secondary', Width: 1600, Height: 900, Primary: false },
        { Id: 'primary', Width: 1920, Height: 1080, Primary: true },
      ]),
    } } };
  });
  await page.goto(base);
  await page.getByLabel('Seu nome', { exact: true }).fill('Teste monitor');
  await page.getByLabel('Código ou link da sala', { exact: true }).fill('XNX-MON-' + Date.now().toString(36));
  await page.getByRole('button', { name: 'Criar sala com este código', exact: true }).click();
  await page.getByRole('button', { name: 'Sair', exact: true }).waitFor({ timeout: 30000 });
  await page.getByRole('button', { name: 'Transmitir', exact: true }).click();
  await page.getByRole('button', { name: 'Monitor / jogo fullscreen', exact: true }).click();
  const monitor = page.getByLabel('Monitor do jogo', { exact: true });
  await monitor.locator('option[value="primary"]').waitFor({ state: 'attached', timeout: 5000 });
  assert.equal(await monitor.inputValue(), 'primary', 'Default is actual primary monitor, not index zero');
  const method = page.getByLabel('Método de captura', { exact: true });
  assert.equal(await method.inputValue(), 'dxgi');
  await monitor.selectOption('secondary');
  await method.selectOption('wgc'); assert.equal(await monitor.count(), 0, 'WGC remains explicitly primary-only');
  await method.selectOption('dxgi'); assert.equal(await monitor.inputValue(), 'secondary', 'Explicit selection persists');
  await page.setViewportSize({ width: 430, height: 820 });
  assert.equal(await page.evaluate(() => { const dialog = document.querySelector('dialog'); return dialog.scrollWidth > dialog.clientWidth + 1; }), false);
  await page.getByRole('button', { name: 'Janela com áudio de processo', exact: true }).click();
  assert.match(await page.locator('.room-capture-content').innerText(), /não muda para o monitor inteiro/);
  assert.equal(await method.count(), 0);
  if (errors.length) throw new Error(errors.join('\n'));
  console.log('PASS: fullscreen source defaults to DXGI, selects actual primary/secondary monitor explicitly, preserves selection and fits mobile; no screen captured');
} finally { await browser.close(); }
