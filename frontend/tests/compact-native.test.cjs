// Real WPF + WebView2 + COM, isolated Data/skins; no emulated viewport.
const assert = require('node:assert/strict');
const { mkdir } = require('node:fs/promises');
const { resolve } = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async () => {
  let browser, page;
  const output = resolve(__dirname, '../../bin/compact-ui');
  await mkdir(output, { recursive: true });
  try {
    for (let i = 0; i < 50; i++) {
      try { browser = await chromium.connectOverCDP('http://127.0.0.1:' + (process.argv[2] || 9235)); break; }
      catch { await new Promise(r => setTimeout(r, 200)); }
    }
    assert.ok(browser, 'WebView2 CDP');
    page = browser.contexts()[0].pages()[0];
    const errors = [];
    page.on('pageerror', e => errors.push(e.stack || e.message));
    await page.waitForURL('https://appassets/**');
    await page.locator('#app-container').waitFor();
    await page.evaluate(async () => {
      const api = window.chrome.webview.hostObjects.api;
      await api.SetSidebarPosition('TopLeft');
      await api.SetSidebarPlacement(160, 0);
      await api.SetSidebarCollapseEdge('Auto');
      await api.ToggleSidebar();
      await api.SetSidebarPinned(true);
    });
    await page.waitForFunction(() => document.querySelector('.sidebar-mode.collapse-top') && innerWidth === 360 && innerHeight > 300);
    const size = await page.evaluate(() => ({ width: innerWidth, height: innerHeight }));
    await page.getByRole('button', { name: 'Aparência', exact: true }).click();
    await page.getByRole('button', { name: 'Editar skin no compacto', exact: true }).click();
    await page.waitForFunction(() => !document.querySelector('.skin-dock fieldset').disabled);
    await page.getByRole('button', { name: 'Cores', exact: true }).click();
    await page.getByLabel('Cor principal', { exact: true }).fill('#14aacc');
    await page.waitForFunction(() => getComputedStyle(document.documentElement).getPropertyValue('--primary').trim() === '#14aacc');
    await page.getByLabel('Salvar como skin pessoal', { exact: true }).fill('Compact native test');
    await page.getByRole('button', { name: 'Criar e aplicar cópia', exact: true }).click();
    await page.getByText('Skin salva e aplicada.', { exact: true }).waitFor();
    const saved = await page.evaluate(async () => JSON.parse(await window.chrome.webview.hostObjects.api.GetSkinConfig('Compact native test')));
    assert.equal(saved.primaryColor, '#14aacc');
    const bounds = await page.locator('.skin-dock').boundingBox();
    assert.ok(bounds.x >= 0 && bounds.y >= 0 && bounds.x + bounds.width <= size.width + 1 && bounds.y + bounds.height <= size.height + 1);
    await page.screenshot({ path: resolve(output, 'editor-native.png') });
    await page.getByTitle('Fechar editor', { exact: true }).click();
    assert.equal(await page.locator('#compact-skin-select').inputValue(), 'Compact native test');
    await page.getByRole('button', { name: 'Editar skin no compacto', exact: true }).click();
    await page.waitForFunction(() => !document.querySelector('.skin-dock fieldset').disabled);
    for (const [edge, fps] of [['Top', 0], ['Left', 60], ['Right', 120], ['Top', 30]]) {
      await page.evaluate(async fps => await window.chrome.webview.hostObjects.api.SetSidebarAnimationFps(fps), fps);
      assert.equal(await page.evaluate(async () => await window.chrome.webview.hostObjects.api.GetSidebarAnimationFps()), fps);
      await page.evaluate(async edge => {
        const api = window.chrome.webview.hostObjects.api;
        await api.SetSidebarCollapseEdge(edge);
        window.compactFrameSamples = [];
        window.compactFrameSampleStop?.();
        let active = true, width = innerWidth, height = innerHeight;
        window.compactFrameSampleStop = () => { active = false; };
        const sample = now => {
          if (!active) return;
          if (innerWidth !== width || innerHeight !== height) {
            window.compactFrameSamples.push({ now, width: innerWidth, height: innerHeight });
            width = innerWidth; height = innerHeight;
          }
          requestAnimationFrame(sample);
        };
        requestAnimationFrame(sample);
        await api.SetCompactInteracting(false);
        await api.SetSidebarPinned(false);
      }, edge);
      await page.waitForFunction(edge => edge === 'Top' ? innerHeight <= 17 : innerWidth <= 17, edge);
      const samples = await page.evaluate(() => { window.compactFrameSampleStop(); return window.compactFrameSamples; });
      const intervals = samples.slice(1).map((s, i) => s.now - samples[i].now);
      console.log('Observed viewport frames ' + edge + ' target=' + fps + ': ' + JSON.stringify({ frames: samples.length, spanMs: Math.round(samples.at(-1)?.now - samples[0]?.now), maxGapMs: Math.round(Math.max(0, ...intervals)) }));
      const canvas = await page.locator('.main-window').boundingBox();
      assert.equal(Math.round(canvas.width), size.width);
      assert.equal(Math.round(canvas.height), size.height);
      const editorSize = await page.locator('.skin-dock').evaluate(el => ({ width: el.getBoundingClientRect().width, height: el.getBoundingClientRect().height }));
      assert.equal(editorSize.width, bounds.width, 'editor width must not reflow while hiding');
      assert.equal(editorSize.height, bounds.height, 'editor height must not reflow while hiding');
      const handle = await page.locator('.compact-edge-handle').boundingBox();
      assert.ok(handle.x >= -1 && handle.y >= -1, 'handle anchored to visible native viewport');
      await page.evaluate(async () => await window.chrome.webview.hostObjects.api.SetSidebarPinned(true));
      await page.waitForFunction(size => innerWidth === size.width && innerHeight === size.height, size);
    }
    await page.getByTitle('Fechar editor', { exact: true }).click();
    await page.getByRole('button', { name: 'Expandir Xennex', exact: true }).click();
    await page.waitForFunction(() => !document.querySelector('.sidebar-mode') && innerWidth > 360);
    assert.deepEqual(errors, []);
    console.log('PASS native compact: actual viewport, Top/Left/Right collapse, stable canvas, skin preview and saved copy, expand');
  } catch (error) {
    if (page) {
      console.error((await page.locator('body').innerText()).slice(-2500));
      await page.screenshot({ path: resolve(output, 'native-failure.png') }).catch(() => {});
    }
    throw error;
  } finally {
    if (page) await page.evaluate(async () => await window.chrome.webview.hostObjects.api.Shutdown()).catch(() => {});
    if (browser) await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
