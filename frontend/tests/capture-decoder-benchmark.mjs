// Run through test_stream_native.ps1 -DecoderBenchmark. Synthetic pixels only.
import assert from 'node:assert/strict';
import { chromium } from 'playwright';
const browser = await chromium.connectOverCDP('http://127.0.0.1:9236');
try {
  let page;
  for (let attempt = 0; attempt < 40 && !page; attempt++) {
    page = browser.contexts()[0].pages().find(page => page.url().includes('appassets'));
    if (!page) await new Promise(resolve => setTimeout(resolve, 250));
  }
  assert(page, 'Isolated WebView2 exists');
  const measurements = await page.evaluate(async () => {
    const results = [];
    for (const [width, height] of [[1280, 720], [1920, 1080]]) {
      const source = document.createElement('canvas'); source.width = width; source.height = height;
      const paint = source.getContext('2d');
      for (let y = 0; y < height; y += 20) for (let x = 0; x < width; x += 20) {
        paint.fillStyle = `rgb(${x % 255},${y % 255},${(x + y) % 255})`; paint.fillRect(x, y, 20, 20);
      }
      paint.fillStyle = '#ea2010'; paint.fillRect(0, 0, width / 4, height / 4);
      const blob = await new Promise(resolve => source.toBlob(resolve, 'image/jpeg', .85));
      const data = await blob.arrayBuffer();
      const canvas = document.createElement('canvas'); canvas.width = width; canvas.height = height;
      const context = canvas.getContext('2d', { alpha: false });
      const available = typeof ImageDecoder !== 'undefined' && await ImageDecoder.isTypeSupported('image/jpeg');
      const samples = { bitmap: [], webcodecs: [] };
      const run = async path => {
        const begin = performance.now(); let decoder, frame;
        try {
          if (path === 'bitmap') frame = await createImageBitmap(blob);
          else { decoder = new ImageDecoder({ data, type: 'image/jpeg' }); frame = (await decoder.decode()).image; }
          context.drawImage(frame, 0, 0);
        } finally { frame?.close(); decoder?.close(); }
        return performance.now() - begin;
      };
      for (let i = 0; i < 32; i++) {
        for (const path of i % 2 ? ['bitmap', 'webcodecs'] : ['webcodecs', 'bitmap']) {
          if (path === 'webcodecs' && !available) continue;
          const elapsed = await run(path); if (i >= 6) samples[path].push(elapsed);
          const pixel = context.getImageData(20, 20, 1, 1).data;
          if (pixel[0] < 200 || pixel[1] > 65 || pixel[2] > 65) throw new Error('Decoded color mismatch');
        }
      }
      const summary = values => values.length ? { meanMs: values.reduce((a, b) => a + b, 0) / values.length,
        p95Ms: [...values].sort((a, b) => a - b)[Math.ceil(values.length * .95) - 1] } : null;
      results.push({ width, height, bytes: data.byteLength, bitmap: summary(samples.bitmap), webcodecs: summary(samples.webcodecs) });
    }
    return results;
  });
  for (const measurement of measurements) console.log('MEASURE JPEG decode/draw in WebView2:', JSON.stringify(measurement));
} finally { await browser.close(); }
