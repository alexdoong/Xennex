import { createRequire } from 'node:module';
import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.XENNEX_PLAYWRIGHT_PATH || 'playwright');
const base = process.env.XENNEX_TEST_URL || 'http://127.0.0.1:5179';
const output = resolve('../bin/streaming-qa'); await mkdir(output, { recursive: true });
const browser = await chromium.launch({ channel: 'msedge', headless: true });
const errors = [];
const roomCode = `XNX-QA-${Date.now().toString(36).toUpperCase()}`;
try {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const host = await context.newPage();
  host.on('pageerror', error => errors.push(error.message));
  host.on('console', message => { if (message.type() === 'error') console.log('BROWSER:', message.text()); });
  await host.goto(base);
  await host.getByRole('heading', { name: 'Xennex Live' }).waitFor();
  await host.screenshot({ path: resolve(output, 'lobby-desktop.png'), fullPage: true });
  await host.setViewportSize({ width: 390, height: 844 });
  await host.screenshot({ path: resolve(output, 'lobby-mobile.png'), fullPage: true });
  const overflow = await host.evaluate(() => document.documentElement.scrollWidth > innerWidth);
  if (overflow) throw new Error('Horizontal overflow at mobile viewport');
  await host.setViewportSize({ width: 1280, height: 900 });
  await host.getByLabel('Seu nome', { exact: true }).fill('Teste anfitrião');
  await host.getByLabel('Código ou link da sala').fill(roomCode);
  await host.getByRole('button', { name: 'Entrar na sala', exact: true }).click();
  await host.getByRole('status').filter({ hasText: 'não foi encontrada nesta versão' }).waitFor({ timeout: 15000 });
  console.log('PASS: unknown room immediately explains create/join and version compatibility');
  await host.getByRole('button', { name: 'Criar sala com este código' }).click();
  await host.getByRole('button', { name: 'Sair', exact: true }).waitFor({ timeout: 25000 });
  const guestContext = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const guest = await guestContext.newPage(); guest.on('pageerror', error => errors.push(error.message));
  await guest.goto(`${base}/?room=${roomCode}`);
  await guest.getByLabel('Seu nome', { exact: true }).fill('Teste convidado');
  await guest.getByRole('button', { name: 'Entrar na sala', exact: true }).click();
  await guest.getByRole('button', { name: 'Sair', exact: true }).waitFor({ timeout: 25000 });
  await host.getByText('Teste convidado', { exact: true }).waitFor();
  console.log('PASS: real PeerJS signaling and room presence');
  // Replace only display capture with test media, keeping real WebRTC transport.
  const fixture = async page => page.evaluate(() => {
    const synthetic = async () => {
      const canvas = document.createElement('canvas'); canvas.width = 800; canvas.height = 450;
      const ctx = canvas.getContext('2d'); let frame = 0;
      const timer = setInterval(() => { ctx.fillStyle = '#423469'; ctx.fillRect(0, 0, 800, 450); ctx.fillStyle = '#bca6ff'; ctx.font = '28px sans-serif'; ctx.fillText(`Xennex — mídia de teste ${++frame}`, 40, 180); }, 33);
      const stream = canvas.captureStream(30);
      const audio = new AudioContext(); const oscillator = audio.createOscillator();
      const gain = audio.createGain(); gain.gain.value = 0.001;
      const destination = audio.createMediaStreamDestination(); oscillator.connect(gain); gain.connect(destination); oscillator.start();
      stream.addTrack(destination.stream.getAudioTracks()[0]);
      let released = false;
      for (const track of stream.getTracks()) {
        const stop = track.stop.bind(track);
        track.stop = () => { if (!released) { released = true; clearInterval(timer); void audio.close(); } stop(); };
      }
      return stream;
    };
    navigator.mediaDevices.getDisplayMedia = synthetic;
    navigator.mediaDevices.getUserMedia = synthetic;
  });
  await fixture(host); await fixture(guest);
  const share = async (page, title, camera = false) => {
    await page.getByLabel('Título', { exact: true }).fill(title);
    await page.getByLabel('Capturar', { exact: false }).selectOption(camera ? 'camera' : 'browser');
    await page.getByRole('button', { name: camera ? 'Adicionar câmera' : 'Compartilhar tela', exact: true }).click();
    await page.getByRole('button', { name: `Parar ${title}`, exact: true }).waitFor();
  };
  await share(guest, 'Tela um'); await share(guest, 'Tela dois'); await share(guest, 'Webcam', true);
  await host.getByRole('button', { name: 'Assistir Teste convidado: Webcam', exact: true }).waitFor();
  if (await host.locator('video').count()) throw new Error('Subscriptions must be explicit');
  await host.getByRole('button', { name: 'Assistir Teste convidado: Tela um', exact: true }).click();
  await host.getByRole('button', { name: 'Assistir Teste convidado: Tela dois', exact: true }).click();
  await host.waitForFunction(() => document.querySelectorAll('video').length === 2 && [...document.querySelectorAll('video')].every(v => v.readyState >= 2));
  await host.getByRole('button', { name: 'Ouvir esta transmissão', exact: true }).first().click();
  await host.getByRole('button', { name: 'Ouvir esta transmissão', exact: true }).first().click();
  await host.waitForFunction(() => [...document.querySelectorAll('video')].filter(v => !v.muted && v.srcObject?.getAudioTracks().length === 1).length === 2);
  await host.getByRole('button', { name: 'Destacar transmissão', exact: true }).first().click();
  await host.waitForFunction(() => [...document.querySelectorAll('video')].filter(v => !v.muted && !v.paused).length === 2);
  await host.getByRole('button', { name: 'Destacar transmissão', exact: true }).first().click();
  await share(host, 'Tela host');
  const observerContext = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const observer = await observerContext.newPage(); observer.on('pageerror', error => errors.push(error.message));
  await observer.goto(`${base}/?room=${roomCode}`); await fixture(observer);
  await observer.getByLabel('Seu nome', { exact: true }).fill('Observador');
  await observer.getByRole('button', { name: 'Entrar na sala', exact: true }).click();
  await observer.getByRole('button', { name: 'Sair', exact: true }).waitFor({ timeout: 25000 });
  await observer.getByRole('button', { name: 'Assistir Teste convidado: Tela um', exact: true }).click();
  await observer.waitForFunction(() => [...document.querySelectorAll('video')].some(v => v.readyState >= 2));
  await share(observer, 'Tela observador');
  await guest.getByRole('button', { name: 'Assistir Observador: Tela observador', exact: true }).click();
  await guest.waitForFunction(() => document.querySelectorAll('video').length === 4 && [...document.querySelectorAll('video')].every(v => v.readyState >= 2));
  await host.screenshot({ path: resolve(output, 'room-multiple-streams.png'), fullPage: true });
  console.log('PASS: three simultaneous publishers, two screens plus camera, independent subscriptions and simultaneous audio during focus');
  await host.getByRole('button', { name: 'Sair', exact: true }).click();
  await observer.waitForFunction(() => document.querySelector('.room-status-connected') && !document.querySelector('.room-person-group')?.textContent.includes('Teste anfitrião'), null, { timeout: 60000 });
  await observer.waitForFunction(() => [...document.querySelectorAll('video')].length === 2 && [...document.querySelectorAll('video')].every(v => v.readyState >= 2));
  const newcomerContext = await browser.newContext();
  const newcomer = await newcomerContext.newPage(); newcomer.on('pageerror', error => errors.push(error.message));
  await newcomer.goto(`${base}/?room=${roomCode}`);
  await newcomer.getByLabel('Seu nome', { exact: true }).fill('Chegou depois');
  await newcomer.getByRole('button', { name: 'Entrar na sala', exact: true }).click();
  await newcomer.getByRole('button', { name: 'Sair', exact: true }).waitFor({ timeout: 25000 });
  await newcomer.getByRole('button', { name: 'Assistir Observador: Tela observador', exact: true }).click();
  await newcomer.waitForFunction(() => [...document.querySelectorAll('video')].some(v => v.readyState >= 2));
  console.log('PASS: coordinator departure preserves media and admits new participants');
  // Close whichever participant acquired the room coordinator, without clicking Leave.
  const guestCoordinates = await guest.getByText('COORDENANDO A SALA', { exact: true }).count();
  if (guestCoordinates) {
    await guestContext.close();
    await newcomer.waitForFunction(() => document.querySelector('.room-status-connected') && !document.body.textContent.includes('Teste convidado'), null, { timeout: 60000 });
    await newcomer.waitForFunction(() => [...document.querySelectorAll('video')].some(v => v.readyState >= 2));
  } else {
    await observerContext.close();
    await guest.waitForFunction(() => document.querySelector('.room-status-connected') && !document.body.textContent.includes('Observador'), null, { timeout: 60000 });
    await newcomer.getByRole('button', { name: 'Assistir Teste convidado: Webcam', exact: true }).click();
    await newcomer.waitForFunction(() => [...document.querySelectorAll('video')].some(v => v.readyState >= 2));
  }
  if (errors.length) throw new Error(errors.join('\n'));
  console.log('PASS: abrupt browser closure, automatic coordinator election and zero browser exceptions');
} finally { await browser.close(); }
