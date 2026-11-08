// Built UI with an explicit bridge fixture; this does not claim model cognition.
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { readFile, mkdir } from 'node:fs/promises';
import { resolve, extname, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';
const root = resolve(fileURLToPath(new URL('../../', import.meta.url)));
const web = resolve(root, 'wwwroot');
const server = createServer(async (request, response) => {
  const path = resolve(web, '.' + (new URL(request.url, 'http://localhost').pathname === '/' ? '/index.html' : new URL(request.url, 'http://localhost').pathname));
  if (!path.startsWith(web + sep)) { response.writeHead(403); response.end(); return; }
  try { response.setHeader('Content-Type', { '.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html' }[extname(path)] || 'application/octet-stream'); response.end(await readFile(path)); }
  catch { response.writeHead(404); response.end(); }
});
await new Promise(done => server.listen(0, '127.0.0.1', done));
const browser = await chromium.launch({ channel: 'msedge', headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 960 } });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(() => {
    const settings = { python: 'C:/Python/python.exe', checkpoint: 'C:/Alice/source.pt', endpoint: 'http://127.0.0.1:11436', model: 'qwen3.5:0.8b-q8_0', perceptionPython: 'C:/Perception/python.exe', perceptionModels: 'C:/Encoder', seconds: 60, ramFraction: .9, attention: 'learned' };
    const state = { settings, running: false, currentSnapshot: false, scriptsAvailable: true, directory: 'Data/ai/alice', lastError: '', exitCode: null,
      snapshot: { phase: 'running', ticks: 12, writer_commits: 2, native_state: { observations: 1, moments: 1, forgotten_moments: 0, interpretation_versions: 0 }, interaction_state: { records: [] } } };
    const control = window.aliceTest = { state, starts: 0, sends: [], files: [], texts: [], fail: false };
    const handlers = {
      GetAliceState: () => JSON.stringify(state),
      StartAliceSession: raw => { state.settings = JSON.parse(raw); state.running = true; state.currentSnapshot = true; control.starts++; },
      StopAliceSession: () => { state.running = false; },
      PickAlicePath: kind => ({ image: 'C:/Selected/foto.png', audio: 'C:/Selected/som.wav' }[kind] ?? ''),
      PerceiveAlicePair: (image, audio) => {
        control.files.push({ image, audio });
        return JSON.stringify({ stream_id: 'a'.repeat(32), sequence: 40, label: 'foto.png + som.wav', modality: 'image_audio' });
      },
      PerceiveAliceWordAudio: (path, word) => {
        control.files.push({ path, word });
        const sequence = word ? 50 : 51;
        state.snapshot.native_state.last_pronunciation = {
          status: word ? 'learned' : 'heard', word: word || 'água', source_sequence: sequence,
        };
        state.snapshot.native_state.pronunciation_examples = 1;
        return JSON.stringify({ stream_id: 'a'.repeat(32), sequence, label: 'som.wav', modality: 'audio' });
      },
      PerceiveAliceFile: (modality, path) => {
        control.files.push({ modality, path });
        state.snapshot.native_state.attention_actions = [{ id: 7, action: 'image', age_seconds: 1, frame: { stream_id: 'a'.repeat(32), sequence: 0 } }];
        state.snapshot.native_state.visual_region_moments = 1;
        state.snapshot.native_state.last_visual_detection = { status: 'detected', count: 2 };
        if (modality === 'audio') state.snapshot.native_state.last_sound_association = { name: 'maruvi', count: 1 };
        return JSON.stringify({ stream_id: 'a'.repeat(32), sequence: 0, label: 'foto.png', modality });
      },
      PerceiveAliceText: text => { control.texts.push(text); return JSON.stringify({ stream_id: 'a'.repeat(32), sequence: control.texts.length, label: 'Mensagem digitada', modality: 'text' }); },
      SendAliceMessage: raw => {
        if (control.fail) throw Error('Falha simulada ao publicar');
        const value = JSON.parse(raw); control.sends.push(value);
        if (value.kind === 'feedback') state.snapshot.native_state.attention_actions = [];
        if (value.kind === 'recall_feedback') state.snapshot.native_state.recall_feedback_actions = [];
        const id = String(control.sends.length).padStart(32, '0');
        const result = value.kind === 'talk' ? { status: 'completed', data: { proposal: { text: 'Oi! Vamos conversar.', kind: 'generated_dialogue' }, memory_text: null, evidence: {} } } : value.kind === 'recall' ? { status: 'completed', data: { proposal: { text: 'Agora: mãe.' }, evidence: { kind: 'referenced_interpretation' } } } : { status: 'completed', learning: { learned: true, kind: value.kind === 'recall_feedback' ? 'recollection_relevance' : undefined } };
        state.snapshot.interaction_state.records.push({ request: { id, action: value.kind, payload: value.payload }, status: 'completed', result, published: value.kind === 'talk' ? 0 : 1, revision: 1 });
        return JSON.stringify({ id });
      },
      GetAiState: () => JSON.stringify({ settings: { model: '', memoryLimitPercent: 75 }, chats: [], jobs: [], specialists: [], paused: false, warning: '', resources: { ramUsedGb: 10, ramTotalGb: 32, vramUsedGb: 1, vramTotalGb: 16, gpuName: 'Fixture', warning: '' } }), GetSkinConfig: () => '{}', GetActiveSkin: () => 'default', GetSidebarPosition: () => 'MiddleRight', GetStreamConfig: () => '{}',
    };
    const api = new Proxy({}, { get: (_, key) => async (...args) => key in handlers ? handlers[key](...args) : false });
    Object.defineProperty(window, 'chrome', { configurable: true, value: { webview: { hostObjects: { api }, postMessage: () => {} } } });
  });
  await page.goto('http://127.0.0.1:' + server.address().port);
  await page.getByTitle('IA local', { exact: true }).click();
  await page.getByRole('button', { name: 'Alice experimental', exact: true }).click();
  const panel = page.getByRole('region', { name: 'Alice experimental', exact: true });
  await panel.getByText('Processo parado', { exact: true }).waitFor();
  assert.equal(await page.evaluate(() => window.aliceTest.starts), 0);
  assert.equal(await panel.getByRole('button', { name: 'Enviar para Alice', exact: true }).isEnabled(), false);
  await panel.getByLabel('Modelo instalado', { exact: true }).fill('modelo-editado');
  await panel.getByLabel('Modelo de conversa (opcional)', { exact: true }).fill('qwen3.5:4b');
  const mirageFolder = panel.getByLabel('Pasta do Mirage para recortes automáticos (opcional)', { exact: true });
  assert.equal(await mirageFolder.inputValue(), '');
  await mirageFolder.fill('C:/Mirage');
  assert.equal(await panel.getByLabel('Evocação de lembranças (experimental)', { exact: true }).inputValue(), 'preserve');
  await panel.getByLabel('Evocação de lembranças (experimental)', { exact: true }).selectOption('enabled');
  await page.waitForTimeout(1700);
  assert.equal(await panel.getByLabel('Modelo instalado', { exact: true }).inputValue(), 'modelo-editado');
  assert.equal(await panel.getByLabel('Modelo de conversa (opcional)', { exact: true }).inputValue(), 'qwen3.5:4b');
  await panel.getByRole('button', { name: 'Iniciar Alice', exact: true }).click();
  await panel.getByText('Processo ativo', { exact: true }).waitFor();
  assert.equal(await page.evaluate(() => window.aliceTest.state.settings.dialogueModel), 'qwen3.5:4b');
  assert.equal(await page.evaluate(() => window.aliceTest.state.settings.model), 'modelo-editado');
  assert.equal(await page.evaluate(() => window.aliceTest.state.settings.memoryRecall), 'enabled');
  assert.equal(await page.evaluate(() => window.aliceTest.state.settings.mirageModels), 'C:/Mirage');
  await panel.getByRole('button', { name: 'Enviar imagem png', exact: true }).click();
  await page.waitForTimeout(300);
  assert.deepEqual(await page.evaluate(() => window.aliceTest.files), [{ modality: 'image', path: 'C:/Selected/foto.png' }]);
  await panel.getByText('Estado salvo da memória', { exact: true }).click();
  await panel.getByText('Mirage encontrou recortes na última imagem. 2 recortes retidos dessa imagem.', { exact: true }).waitFor();
  await panel.getByLabel('Experiência selecionada', { exact: true }).locator('option').filter({ hasText: 'foto.png' }).waitFor({ state: 'attached' });
  await panel.getByLabel('O que deseja fazer?', { exact: true }).selectOption('relate');
  const message = panel.getByLabel('Mensagem para a Alice', { exact: true });
  await message.fill('O autor dessa imagem é meu pai.');
  await panel.getByRole('button', { name: 'Enviar para Alice', exact: true }).click();
  await panel.getByText('Aprendizado registrado.', { exact: true }).waitFor();
  await panel.getByLabel('O que deseja fazer?', { exact: true }).selectOption('correct');
  await panel.getByLabel('Relato a consultar ou corrigir', { exact: true }).selectOption('00000000000000000000000000000001');
  await message.fill('Corrigindo: é minha mãe.');
  await panel.getByRole('button', { name: 'Enviar para Alice', exact: true }).click();
  await panel.getByLabel('O que deseja fazer?', { exact: true }).selectOption('recall');
  await message.fill('E agora?');
  await panel.getByRole('button', { name: 'Enviar para Alice', exact: true }).click();
  await panel.getByText('Agora: mãe.', { exact: true }).waitFor();
  const sends = await page.evaluate(() => window.aliceTest.sends);
  assert.deepEqual(sends[0].payload.frame, { stream_id: 'a'.repeat(32), sequence: 0 });
  assert.equal(sends[1].payload.reply_to, '00000000000000000000000000000001');
  assert.equal(sends[2].payload.about, '00000000000000000000000000000001');
  await panel.getByLabel('O que deseja fazer?', { exact: true }).selectOption('feedback');
  await panel.getByLabel('Escolha recente de atenção', { exact: true }).selectOption('7');
  await message.fill('Porra, gostei dessa experiência.');
  await panel.getByRole('button', { name: 'Enviar para Alice', exact: true }).click();
  await panel.getByText('Nenhuma escolha disponível.', { exact: false }).waitFor();
  assert.deepEqual(await page.evaluate(() => window.aliceTest.sends.at(-1)), { kind: 'feedback', payload: { text: 'Porra, gostei dessa experiência.', action: 7 } });
  await panel.getByLabel('O que deseja fazer?', { exact: true }).selectOption('recall');
  await message.fill('rascunho da consulta');
  await panel.getByLabel('O que deseja fazer?', { exact: true }).selectOption('meaning');
  await message.fill('O que é Hami?');
  await panel.getByLabel('O que deseja fazer?', { exact: true }).selectOption('recall');
  assert.equal(await message.inputValue(), 'rascunho da consulta');
  await page.evaluate(() => { window.aliceTest.fail = true; });
  await panel.getByRole('button', { name: 'Enviar para Alice', exact: true }).click();
  await panel.getByRole('alert').filter({ hasText: 'Falha simulada' }).waitFor();
  assert.equal(await message.inputValue(), 'rascunho da consulta');
  await page.getByRole('button', { name: 'Alice experimental', exact: true }).click();
  await page.getByRole('button', { name: 'Alice experimental', exact: true }).click();
  assert.equal(await message.inputValue(), 'rascunho da consulta');
  assert.equal(await page.evaluate(() => window.aliceTest.starts), 1);
  await page.evaluate(() => { window.aliceTest.fail = false; });
  await panel.getByLabel('O que deseja fazer?', { exact: true }).selectOption('talk');
  await panel.getByLabel('Assunto da memória (opcional)', { exact: true }).selectOption('');
  await message.fill('Oi!\nPorra, tudo bem?');
  await panel.getByRole('button', { name: 'Enviar para Alice', exact: true }).click();
  assert.equal(await panel.getByText('Oi! Vamos conversar.', { exact: true }).count(), 0, 'unconfirmed expression is not exposed as delivered');
  const talkId = await page.evaluate(() => {
    const record = window.aliceTest.state.snapshot.interaction_state.records.at(-1);
    record.result.data.evidence = { association: { evocation: { entries: [{ moment_ref: { acquired_at: 1, known: [true, false, false], source_context: { stream_id: 'a'.repeat(32), source_sequence: 0, captured_wall: 1700000000 } } }] } } };
    window.aliceTest.state.snapshot.native_state.recall_feedback_actions = [{ about: record.request.id, age_seconds: 1 }];
    return record.request.id;
  });
  assert.equal(await panel.getByRole('group', { name: 'Relevância da primeira lembrança', exact: true }).count(), 0);
  await page.evaluate(() => { window.aliceTest.state.snapshot.interaction_state.records.at(-1).published = 1; });
  await panel.getByText('Oi! Vamos conversar.', { exact: true }).waitFor();
  assert.deepEqual(await page.evaluate(() => window.aliceTest.texts), ['Oi!\nPorra, tudo bem?']);
  assert.deepEqual(await page.evaluate(() => window.aliceTest.sends.at(-1).payload.frame), { stream_id: 'a'.repeat(32), sequence: 1 });
  await panel.getByText('Expressão gerada pelo módulo de linguagem', { exact: true }).waitFor();
  await panel.getByText('foto.png (imagem)', { exact: true }).waitFor();
  await mkdir(resolve(root, 'bin/AliceMemory/panel-ui'), { recursive: true });
  await panel.locator('.alice-evocation').screenshot({ path: resolve(root, 'bin/AliceMemory/panel-ui/evocation-desktop.png') });
  await page.setViewportSize({ width: 620, height: 820 });
  assert.equal(await panel.locator('.alice-evocation').evaluate(element => element.scrollWidth <= element.clientWidth + 1), true);
  await panel.locator('.alice-evocation').screenshot({ path: resolve(root, 'bin/AliceMemory/panel-ui/evocation-narrow.png') });
  await page.setViewportSize({ width: 1280, height: 960 });
  await panel.getByRole('button', { name: 'A primeira não tem a ver', exact: true }).click();
  assert.deepEqual(await page.evaluate(() => window.aliceTest.sends.at(-1)), { kind: 'recall_feedback', payload: { about: talkId, relevance: -1 } });
  await panel.getByText('Preferência de evocação atualizada.', { exact: true }).waitFor();
  assert.equal(await panel.getByRole('group', { name: 'Relevância da primeira lembrança', exact: true }).count(), 0);
  await panel.getByRole('button', { name: 'Enviar imagem e áudio juntos', exact: true }).click();
  await page.waitForFunction(() => Boolean(window.aliceTest.files.at(-1)?.image));
  assert.deepEqual(await page.evaluate(() => window.aliceTest.files.at(-1)), {
    image: 'C:/Selected/foto.png', audio: 'C:/Selected/som.wav',
  });
  await panel.getByLabel('O que deseja fazer?', { exact: true }).selectOption('name');
  const focus = panel.getByLabel('A que se refere o nome?', { exact: true });
  assert.equal(await focus.inputValue(), 'image');
  await message.fill('Essa imagem se chama maruvi.');
  await panel.getByRole('button', { name: 'Enviar para Alice', exact: true }).click();
  await page.waitForFunction(() => window.aliceTest.sends.at(-1)?.kind === 'name');
  assert.deepEqual(await page.evaluate(() => window.aliceTest.sends.at(-1).payload), {
    text: 'Essa imagem se chama maruvi.', focus: 'image', moment: null, frame: { stream_id: 'a'.repeat(32), sequence: 40 },
  });
  await panel.getByRole('button', { name: 'Enviar áudio wav', exact: true }).click();
  const memoryDetails = panel.getByText('Estado salvo da memória', { exact: true });
  if (!(await memoryDetails.evaluate(node => node.parentElement.open))) await memoryDetails.click();
  await panel.getByText('O último áudio evocou “maruvi” a partir de 1 lembrança audiovisual.', { exact: true }).waitFor();
  await panel.getByText('Palavras faladas · experimental', { exact: true }).click();
  await panel.getByLabel('Palavra escrita', { exact: true }).fill('água');
  await panel.getByRole('button', { name: 'Ensinar pronúncia', exact: true }).click();
  await panel.getByText('Pronúncia registrada · “água”.', { exact: true }).waitFor();
  assert.deepEqual(await page.evaluate(() => window.aliceTest.files.at(-1)), { path: 'C:/Selected/som.wav', word: 'água' });
  await panel.getByRole('button', { name: 'Tentar reconhecer palavra', exact: true }).click();
  await panel.getByText('Palavra reconhecida · “água”.', { exact: true }).waitFor();
  assert.deepEqual(await page.evaluate(() => window.aliceTest.files.at(-1)), { path: 'C:/Selected/som.wav', word: '' });
  await panel.getByRole('button', { name: 'Parar e salvar Alice', exact: true }).click();
  await panel.getByText('Processo parado', { exact: true }).waitFor();
  await mkdir(resolve(root, 'bin/AliceMemory/panel-ui'), { recursive: true });
  await panel.getByRole('heading', { name: 'Alice experimental', exact: true }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: resolve(root, 'bin/AliceMemory/panel-ui/desktop.png') });
  await page.setViewportSize({ width: 620, height: 820 });
  await panel.getByRole('heading', { name: 'Alice experimental', exact: true }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: resolve(root, 'bin/AliceMemory/panel-ui/narrow.png') });
  assert.equal(await panel.evaluate(element => element.scrollWidth <= element.clientWidth + 1), true);
  assert.deepEqual(errors, []);
  console.log('PASS Alice UI: explicit start/stop, selected frame, correction/query, attention feedback, stable settings/drafts, failed publication and narrow layout.');
} finally { await browser.close(); await new Promise(done => server.close(done)); }
