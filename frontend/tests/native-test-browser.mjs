import { spawn } from 'node:child_process';
import { access, mkdir, mkdtemp, readFile, realpath, rm } from 'node:fs/promises';
import { resolve, join, sep } from 'node:path';

// Own disposable Edge profile only. noDefaults prevents Playwright's separate
// CDP session from keeping a supposedly minimized document artificially visible.
export async function launchNativeTestBrowser(chromium, background, output) {
  if (!background) {
    const browser = await chromium.launch({ channel: 'msedge', headless: true,
      ignoreDefaultArgs: ['--disable-background-timer-throttling', '--disable-backgrounding-occluded-windows', '--disable-renderer-backgrounding'] });
    return { browser, page: await browser.newPage(), close: () => browser.close() };
  }
  await mkdir(output, { recursive: true });
  const profile = await mkdtemp(join(output, 'isolated-edge-'));
  const executable = [process.env['ProgramFiles(x86)'], process.env.ProgramFiles].filter(Boolean)
    .map(root => join(root, 'Microsoft', 'Edge', 'Application', 'msedge.exe'));
  let edge;
  for (const candidate of executable) { try { await access(candidate); edge = candidate; break; } catch { /* Try the other standard installation. */ } }
  if (!edge) throw new Error('Microsoft Edge installation unavailable');
  const child = spawn(edge, [`--user-data-dir=${profile}`, '--remote-debugging-port=0', '--remote-debugging-address=127.0.0.1',
    '--no-first-run', '--no-default-browser-check', '--disable-extensions', '--edge-skip-compat-layer-relaunch', 'about:blank'],
    { windowsHide: true, stdio: 'ignore' });
  let browser, startupError;
  child.once('error', error => { startupError = error; });
  const close = async () => {
    try { if (browser) await browser.close(); }
    finally {
      if (child.exitCode === null) child.kill();
      try {
        const actual = await realpath(profile), boundary = await realpath(output);
        if (!actual.toLowerCase().startsWith((boundary + sep).toLowerCase()) || !resolve(profile).toLowerCase().startsWith((resolve(output) + sep).toLowerCase()))
          throw new Error('Temporary browser profile escaped the intended test directory');
        await rm(actual, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
      } catch (error) { if (error.code !== 'EBUSY' && error.code !== 'EPERM' && error.code !== 'ENOENT') throw error; }
    }
  };
  try {
    let port;
    const deadline = Date.now() + 12000;
    while (Date.now() < deadline && !port) {
      if (startupError) throw startupError;
      try { port = Number((await readFile(join(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0]); } catch { /* File appears after the owned browser starts. */ }
      if (!port) await new Promise(done => setTimeout(done, 100));
    }
    if (!Number.isInteger(port) || port <= 0 || port > 65535) throw new Error('Owned Edge CDP endpoint did not start');
    browser = await chromium.connectOverCDP(`http://127.0.0.1:${port}`, { noDefaults: true, timeout: 10000 });
    const context = browser.contexts()[0];
    const page = context.pages()[0] || await context.newPage();
    return { browser, page, close };
  } catch (error) { await close(); throw error; }
}
