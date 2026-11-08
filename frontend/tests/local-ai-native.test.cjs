// Real WebView2/COM + local HTTP fixture. No model weights or personal Data are used.
const assert = require('node:assert/strict');
const { createServer } = require('node:http');
const { mkdir } = require('node:fs/promises');
const { resolve } = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const phase = process.argv[2] || 'write';
const port = Number(process.argv[3] || 9232);
const root = resolve(__dirname, '../..');
let generationCount = 0;
const server = createServer(async (request, response) => {
  if (request.url === '/api/tags' || request.url === '/api/ps') {
    response.setHeader('Content-Type', 'application/json');
    response.end(JSON.stringify({ models: [{ name: 'fixture-local-model', digest: 'fixture-digest', size: 4294967296, size_vram: 4294967296, context_length: 4096 }] })); return;
  }
  if (request.url === '/api/show') {
    response.setHeader('Content-Type', 'application/json');
    response.end(JSON.stringify({ capabilities: ['completion'], model_info: {} })); return;
  }
  if (request.url === '/api/chat') {
    let raw = ''; for await (const part of request) raw += part;
    const payload = JSON.parse(raw);
    assert.equal(payload.options.num_ctx, 4096); assert.equal(payload.keep_alive, 60);
    response.setHeader('Content-Type', 'application/x-ndjson');
    response.end(JSON.stringify({ message: { content: 'Resposta nativa validada.' }, done: true }) + '\n'); return;
  }
  if (request.url === '/v1/models') {
    response.setHeader('Content-Type', 'application/json');
    response.end(JSON.stringify({ data: [{ id: 'fixture-local-model' }] })); return;
  }
  if (request.url !== '/v1/chat/completions') { response.writeHead(404).end(); return; }
  let body = ''; for await (const part of request) body += part;
  const payload = JSON.parse(body);
  assert.equal(payload.model, 'fixture-local-model'); assert.equal(payload.stream, true);
  generationCount++;
  response.writeHead(200, { 'Content-Type': 'text/event-stream' });
  response.write('data: ' + JSON.stringify({ choices: [{ delta: { content: 'Resposta parcial de teste. ' } }] }) + '\n\n');
  const timer = setTimeout(() => {
    if (response.destroyed) return;
    response.end('data: ' + JSON.stringify({ choices: [{ delta: { content: 'Conexão local validada.' } }] }) + '\n\ndata: [DONE]\n\n');
  }, 2500);
  response.on('close', () => clearTimeout(timer));
});
let browser;
try {
  awaitMain().catch(error => { console.error(error); process.exitCode = 1; });
} catch (error) { console.error(error); process.exitCode = 1; }
async function awaitMain() {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  try {
    for (let attempt = 0; attempt < 50; attempt++) {
      try { browser = await chromium.connectOverCDP('http://127.0.0.1:' + port); break; }
      catch { await new Promise(resolve => setTimeout(resolve, 200)); }
    }
    assert.ok(browser, 'WebView2 debugging port available');
    const page = browser.contexts()[0].pages()[0];
    await page.waitForURL('https://appassets/**');
    await page.evaluate(async () => {
      const api = window.chrome.webview.hostObjects.api;
      await api.SetAutoHideSidebar(false);
      await api.SetAutoHideTitlebar(false);
      if (await api.IsSidebarMode()) await api.ToggleSidebar();
    });
    await page.reload();
    await page.waitForURL('https://appassets/**');
    await page.setViewportSize({ width: 1440, height: 1000 });
    const errors = []; page.on('pageerror', error => errors.push(error.message));
    await page.getByTitle('IA local', { exact: true }).click();
    await page.getByRole('heading', { name: 'Recursos e fila' }).waitFor();
    if (phase === 'read') {
      await page.getByRole('button', { name: /Teste de persistência/ }).click();
      await page.getByText('Resposta parcial de teste. Conexão local validada.', { exact: true }).waitFor();
      const restored = await page.evaluate(async () => JSON.parse(await window.chrome.webview.hostObjects.api.GetAiState()));
      assert.equal(restored.jobs.length, 0, 'No job replay on restart');
      assert.ok(restored.chats.length >= 2, 'Chats restored');
    } else {
      await page.getByRole('button', { name: 'Conexão e orçamento', exact: true }).click();
      await page.getByLabel('Endereço local').fill(`http://127.0.0.1:${server.address().port}/v1`);
      await page.getByLabel('Reserva adicional de RAM (GiB)').fill('0.25');
      await page.getByLabel('Reserva adicional de VRAM (GiB)').fill('0.25');
      await page.getByLabel('Limite total de memória (%)').fill('85');
      await page.getByRole('button', { name: 'Salvar configuração' }).click();
      await page.getByRole('button', { name: 'Consultar modelos no endereço salvo' }).click();
      await page.getByText('1 modelo(s) encontrado(s). Selecione o identificador e salve.', { exact: true }).waitFor();
      await page.getByLabel('Modelo', { exact: true }).fill('fixture-local-model');
      await page.getByRole('button', { name: 'Salvar configuração' }).click();
      await page.getByRole('button', { name: 'Conexão e orçamento', exact: true }).click();
      await page.getByLabel('Mensagem', { exact: true }).fill('Teste de persistência');
      await page.getByRole('button', { name: 'Enviar', exact: true }).click();
      await page.getByText('Resposta parcial de teste.', { exact: true }).waitFor();
      await page.getByTitle('Jogos', { exact: true }).click();
      await page.getByTitle('IA local', { exact: true }).click();
      await page.getByText('Resposta parcial de teste. Conexão local validada.', { exact: true }).waitFor();
      const downloadPromise = page.waitForEvent('download');
      await page.getByTitle('Exportar conversa', { exact: true }).click();
      const download = await downloadPromise;
      const { readFile } = require('node:fs/promises');
      const exported = JSON.parse(await readFile(await download.path(), 'utf8'));
      assert.equal(exported.messages[1].status, 'complete');
      await page.getByRole('button', { name: 'Nova conversa', exact: true }).click();
      await page.getByRole('button', { name: 'Conexão e orçamento', exact: true }).click();
      await page.getByLabel('Reserva adicional de RAM (GiB)').fill('128');
      await page.getByRole('button', { name: 'Salvar configuração' }).click();
      await page.getByRole('button', { name: 'Conexão e orçamento', exact: true }).click();
      await page.getByLabel('Mensagem', { exact: true }).fill('Fila por orçamento');
      await page.getByRole('button', { name: 'Enviar', exact: true }).click();
      await page.getByRole('status').filter({ hasText: 'não cabe no orçamento' }).waitFor();
      assert.equal(generationCount, 1, 'Oversized task never reaches HTTP server');
      await mkdir(resolve(root, 'bin/local-ai-ui'), { recursive: true });
      await page.screenshot({ path: resolve(root, 'bin/local-ai-ui/native-queue.png'), fullPage: true });
      await page.getByRole('button', { name: 'Cancelar tarefa', exact: true }).click();
      await page.getByText('Cancelado', { exact: true }).waitFor();
      await page.getByRole('button', { name: 'Priorizar meu PC' }).click();
      await page.getByRole('button', { name: 'Retomar fila' }).waitFor();
      await page.getByLabel('Mensagem', { exact: true }).fill('Rascunho preservado');
      await page.getByTitle('Dashboard', { exact: true }).click();
      await page.getByTitle('IA local', { exact: true }).click();
      assert.equal(await page.getByLabel('Mensagem', { exact: true }).inputValue(), 'Rascunho preservado');
      const telemetry = await page.evaluate(async () => JSON.parse(await window.chrome.webview.hostObjects.api.RefreshAiResources()));
      assert.ok(telemetry.ramTotalGb > 0); assert.ok(telemetry.vramTotalGb > 0); assert.ok(telemetry.vramUsedGb >= 0);
      console.log('Native telemetry:', JSON.stringify(telemetry));
      await page.setViewportSize({ width: 650, height: 880 });
      assert.equal(await page.locator('.local-ai-tab').evaluate(el => el.scrollWidth > el.clientWidth + 2), false, 'No compact overflow');
      await page.waitForTimeout(650); // Wait for the existing tab entrance animation.
      await page.screenshot({ path: resolve(root, 'bin/local-ai-ui/native-compact.png'), fullPage: true });
      await page.setViewportSize({ width: 1440, height: 1000 });
      await page.getByRole('button', { name: 'Conexão e orçamento', exact: true }).click();
      await page.getByRole('button', { name: 'Detectar Ollama', exact: true }).click();
      const modelCard = page.locator('.ai-model-card').filter({ hasText: 'fixture-local-model' });
      await modelCard.waitFor(); await modelCard.click();
      assert.equal(await page.getByLabel('Tipo de conexão').inputValue(), 'ollama');
      assert.equal(await page.getByLabel('Orçamento por modelo').inputValue(), 'auto');
      assert.equal(await page.getByRole('button', { name: 'Liberar modelos da memória' }).isDisabled(), true, 'Cannot unload external server from UI');
      await page.getByRole('button', { name: 'Salvar configuração' }).click();
      await page.waitForTimeout(700);
      await page.locator('.ai-settings h3').scrollIntoViewIfNeeded();
      await page.screenshot({ path: resolve(root, 'bin/local-ai-ui/native-ollama.png'), fullPage: true });
      await page.setViewportSize({ width: 650, height: 880 });
      assert.equal(await page.locator('.local-ai-tab').evaluate(el => el.scrollWidth > el.clientWidth + 2), false, 'Ollama settings fit compact layout');
      await page.locator('.ai-settings h3').scrollIntoViewIfNeeded();
      await page.screenshot({ path: resolve(root, 'bin/local-ai-ui/native-ollama-compact.png'), fullPage: true });
      await page.getByRole('button', { name: 'Conexão e orçamento', exact: true }).click();
      await page.getByRole('button', { name: 'Retomar fila' }).click();
      await page.getByRole('button', { name: 'Nova conversa', exact: true }).click();
      await page.getByLabel('Mensagem', { exact: true }).fill('Teste Ollama nativo');
      await page.getByRole('button', { name: 'Enviar', exact: true }).click();
      await page.getByText('Resposta nativa validada.', { exact: true }).waitFor();
      const nativeState = await page.evaluate(async () => JSON.parse(await window.chrome.webview.hostObjects.api.GetAiState()));
      assert.equal(nativeState.jobs.at(-1).demand.alreadyLoaded, true, 'Native COM admission uses loaded model metadata');
      assert.deepEqual(errors, []);
    }
    console.log('Local AI native ' + phase + ': PASS');
    await page.evaluate(() => { void window.chrome.webview.hostObjects.api.Shutdown(); });
  } finally { if (browser) await browser.close(); await new Promise(resolve => server.close(resolve)); }
}
