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
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(() => {
    const binding = (id, source, action, value = '') => ({ id, name: id, source, enabled: true, holdMs: 220, cooldownMs: 1000, threshold: .22, action: { type: action, value }, samples: [] });
    let config = { version: 1, hand: 'Any', preview: false, smoothing: .45, swipeThreshold: .18, dragTarget: 'titlebar',
      gestures: [binding('Indicador', 'point', 'pointer'), binding('Pinch', 'pinch', 'drag_window'), binding('Esquerda', 'swipe_left', 'shortcut', 'win+left')] };
    const status = { running: false, armed: false, message: 'Câmera desligada.', revision: 0, recording: false, metrics: {fps:15, inferenceMs:16, frameAgeMs:16} };
    window.gestureTest = { status, failSave: false };
    const handlers = {
      GetGestureConfig: () => JSON.stringify(config),
      GetGestureStatus: () => JSON.stringify(status),
      GetHandMotionCameraIndex: () => 0,
      SaveGestureConfig: json => {
        if (window.gestureTest.failSave) throw Error('Falha simulada ao salvar');
        const next = JSON.parse(json);
        next.gestures.forEach(g => { g.samples = config.gestures.find(old => old.id === g.id)?.samples || []; });
        config = next; status.armed = false; status.revision++;
      },
      StartHandMotion: () => { status.running = true; status.armed = false; status.message = 'Câmera pronta. Modo de teste.'; },
      StopHandMotion: () => { status.running = false; status.armed = false; },
      SetGestureControl: enabled => { status.armed = enabled; },
      RecordGestureSample: id => {
        status.recording = true; status.armed = false; status.stage = 'countdown'; status.remaining = 3;
        setTimeout(() => {
          if (!status.recording) return;
          config.gestures.find(g => g.id === id).samples.push({ duration: 1, frames: [] });
          status.recording = false; status.revision++; status.message = 'Amostra salva.';
        }, 400);
      },
      CancelGestureRecording: () => { status.recording = false; },
      ClearGestureSamples: id => { config.gestures.find(g => g.id === id).samples = []; status.revision++; },
      GetSkinConfig: () => '{}', GetActiveSkin: () => 'default', GetSidebarPosition: () => 'MiddleRight',
      GetStreamConfig: () => '{}',
    };
    const api = new Proxy({}, { get: (_, key) => async (...args) => key in handlers ? handlers[key](...args) : false });
    Object.defineProperty(window, 'chrome', { configurable: true, value: { webview: { hostObjects: { api }, postMessage: () => {} } } });
  });
  await page.goto('http://127.0.0.1:' + server.address().port);
  await page.getByTitle('Gestures', { exact: true }).click();
  await page.getByRole('heading', { name: 'Gestures', exact: true }).waitFor();
  await page.getByRole('button', { name: 'Iniciar câmera em teste' }).click();
  await page.getByText('Câmera pronta. Modo de teste.').waitFor();
  await page.getByText('Captura processada: 15 FPS', {exact:false}).waitFor();
  assert.equal(await page.evaluate(() => window.gestureTest.status.armed), false);
  await page.getByRole('button', { name: 'Ativar controle do PC' }).click();
  await page.getByRole('button', { name: 'Pausar controle' }).waitFor();
  assert.equal(await page.getByRole('button', { name: 'Adicionar gesto' }).isEnabled(), false);
  await page.getByRole('button', { name: 'Pausar controle' }).click();
  await page.getByPlaceholder('Ex.: fechar a mão para pausar').fill('Minha pose');
  await page.getByRole('button', { name: 'Adicionar gesto' }).click();
  await page.getByRole('button', { name: 'Salvar alterações' }).click();
  const card = page.locator('.gestures-card').filter({ has: page.locator('input[value="Minha pose"]') });
  await card.getByRole('button', { name: 'Gravar amostra' }).click();
  await card.getByText('1/8 amostras', { exact: false }).waitFor();
  await card.getByRole('button', { name: 'Limpar amostras' }).click();
  await card.getByText('0/8 amostras', { exact: false }).waitFor();
  await card.getByLabel('Nome', { exact: true }).fill('Pose revisada');
  await page.evaluate(() => { window.gestureTest.failSave = true; });
  await page.getByRole('button', { name: 'Salvar alterações' }).click();
  await page.getByRole('alert').filter({ hasText: 'Falha simulada' }).waitFor();
  assert.equal(await page.getByRole('button', { name: 'Ativar controle do PC' }).isEnabled(), false);
  await page.evaluate(() => { window.gestureTest.failSave = false; });
  await page.getByRole('button', { name: 'Salvar alterações' }).click();
  await page.getByRole('button', { name: 'Desligar câmera' }).click();
  await page.getByRole('button', { name: 'Iniciar câmera em teste' }).waitFor();
  await page.locator('.gestures-page').evaluate(el => el.scrollTop = 0);
  await mkdir(resolve(root, 'bin/gesture-ui'), { recursive: true });
  await page.screenshot({ path: resolve(root, 'bin/gesture-ui/desktop.png') });
  await page.setViewportSize({ width: 780, height: 720 });
  await page.screenshot({ path: resolve(root, 'bin/gesture-ui/compact.png') });
  assert.equal(await page.locator('.gestures-page').evaluate(el => el.scrollWidth <= el.clientWidth + 1), true);
  assert.deepEqual(errors, []);
  console.log('PASS: test mode, arm/pause, recording, sample deletion, failed save and compact layout.');
} finally {
  await browser.close();
  await new Promise(resolve => server.close(resolve));
}
