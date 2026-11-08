// Launched only by scripts/tests/test_assets_native.ps1 against an isolated publish.
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

(async () => {
  let browser;
  for (let attempt = 0; attempt < 50; attempt++) {
    try { browser = await chromium.connectOverCDP('http://127.0.0.1:9232', { timeout: 1000 }); break; }
    catch { await new Promise(resolve => setTimeout(resolve, 250)); }
  }
  if (!browser) throw Error('Native WebView debugger unavailable');
  const page = browser.contexts()[0].pages().find(value => value.url().startsWith('https://appassets/')) || browser.contexts()[0].pages()[0];
  try {
    await page.waitForURL('https://appassets/**');
    await page.waitForFunction(() => !!window.chrome?.webview?.hostObjects?.api);
    await page.getByTitle('Biblioteca', { exact: true }).dispatchEvent('click');
    await page.locator('.assets-workspace').waitFor();
    await page.getByText('native-art.png', { exact: true }).waitFor();
    await page.locator('.assets-card').first().scrollIntoViewIfNeeded();
    await page.screenshot({ path: require('node:path').resolve(__dirname, '../../bin/assets-native.png') });
    await page.waitForFunction(() => { const img = document.querySelector('.assets-card img'); return img?.complete && img.naturalWidth > 0; });
    const info = await page.evaluate(async phase => {
      const api = window.chrome.webview.hostObjects.api;
      const roots = JSON.parse(await api.GetAssetRoots());
      const page = JSON.parse(await api.QueryAssets(JSON.stringify({ rootId: roots[0].id, imagesOnly: true, includeDescendants: true, limit: 10 })));
      const item = page.items[0];
      if (phase === 'write') {
        await api.EditAsset(JSON.stringify({ id: item.id, favorite: true, notes: 'Teste nativo', addTag: 'Nativo' }));
        const collection = JSON.parse(await api.AddAssetCollection('Teste nativo'));
        await api.SetAssetCollectionItem(collection.id, item.id, true);
      }
      const tags = JSON.parse(await api.GetAssetTagOverview(JSON.stringify({ source: 'manual', search: 'Nativo', limit: 10 })));
      const request = { type: 'rename', assetIds: [item.id], conflictPolicy: 'ask', choices: [],
        naming: { baseName: 'denia', pattern: '{base}_{number}', scope: 'all', autoContinue: false, startNumber: 23, digits: 3 } };
      const naming = JSON.parse(await api.PlanAssetFileOperation(JSON.stringify(request)));
      const conflict = JSON.parse(await api.PlanAssetFileOperation(JSON.stringify({ type: 'copy', assetIds: [item.id],
        destinationRootId: roots[0].id, destinationFolder: '', conflictPolicy: 'ask', choices: [] })));
      return { rootCount: roots.length, itemCount: page.items.length, item: JSON.parse(await api.GetAssetDetails(item.id)), tags, naming, conflict };
    }, process.argv[2]);
    assert.equal(info.rootCount, 1);
    assert.equal(info.itemCount, 1);
    assert.equal(info.item.favorite, true);
    assert.equal(info.item.notes, 'Teste nativo');
    assert(info.item.tags.includes('Nativo'));
    assert(info.tags.items.some(value => value.term === 'Nativo' && value.manual === 1));
    assert.equal(info.naming.canExecute, true);
    assert.equal(info.naming.startNumber, 23);
    assert(info.naming.items[0].destinationPath.endsWith('denia_023.png'));
    assert.equal(info.conflict.canExecute, false);
    assert.equal(info.conflict.items[0].conflict, true);
    console.log('PASS native assets ' + process.argv[2] + ': COM, SQLite, thumbnail, naming preview and persistence');
  } finally {
    await page.evaluate(() => window.chrome.webview.hostObjects.api.Shutdown()).catch(() => {});
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
