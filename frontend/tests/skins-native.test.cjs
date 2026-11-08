// Native WebView2 and COM integration; run through test_skins_native.ps1.
const assert = require('node:assert/strict');
const { mkdir } = require('node:fs/promises');
const { resolve } = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const phase = process.argv[2] || 'write', port = process.argv[3] || 9233;
(async () => {
  let browser, page;
  try {
    for (let i=0;i<50;i++) {
      try { browser = await chromium.connectOverCDP('http://127.0.0.1:' + port); break; }
      catch { await new Promise(r=>setTimeout(r,200)); }
    }
    assert.ok(browser);
    page = browser.contexts()[0].pages()[0];
    await page.waitForURL('https://appassets/**');
    await page.evaluate(async () => {
      await window.chrome.webview.hostObjects.api.SetAutoHideSidebar(false);
      await window.chrome.webview.hostObjects.api.SetAutoHideTitlebar(false);
    });
    await page.reload(); await page.waitForURL('https://appassets/**');
    await page.setViewportSize({width:1000,height:700});
    const errors=[]; page.on('pageerror',e=>errors.push(e.message));
    const css = key => page.evaluate(key=>getComputedStyle(document.documentElement).getPropertyValue(key).trim(),key);
    const expectCss = async (key,value) => {
      await page.waitForFunction(([key,value])=>getComputedStyle(document.documentElement).getPropertyValue(key).trim()===value,[key,value]);
      assert.equal(await css(key),value);
    };
    const open = async () => {
      const trigger = page.getByTitle('Personalizar aparência',{exact:true});
      // A restarted hidden WPF window can discard injected OS input until focused.
      // Activate the DOM control in the restart phase; the write phase exercises pointer input.
      if (phase === 'read') await trigger.evaluate(button => button.click());
      else await trigger.click();
      await page.getByRole('button',{name:'Restaurar visual',exact:true}).waitFor();
      await page.waitForFunction(()=>!document.querySelector('.skin-dock fieldset').disabled);
    };
    const setColor = async value => {
      await page.getByRole('button',{name:'Cores',exact:true}).click();
      await page.getByLabel('Cor principal',{exact:true}).fill(value);
      await page.waitForFunction(v=>getComputedStyle(document.documentElement).getPropertyValue('--primary').trim()===v,value);
    };
    if (phase === 'read') {
      assert.equal(await page.evaluate(async()=>await window.chrome.webview.hostObjects.api.GetActiveSkin()),'Skin nativa teste');
      await expectCss('--primary','#3975a9');
      assert.equal(await page.locator('.app-container.skin-surface-liquid').count(),1);
      const liquid = await page.evaluate(async()=>JSON.parse(await window.chrome.webview.hostObjects.api.GetSkinConfig('Skin nativa teste')));
      assert.equal(liquid.surfaceStyle,'liquid'); assert.equal(liquid.glassHighlight,.65);
      await open();
      await page.getByRole('button',{name:'Painéis',exact:true}).evaluate(button=>button.click());
      assert.equal(await page.getByLabel('Reflexos do Liquid Glass valor',{exact:true}).inputValue(),'0.65');
      await page.getByRole('button',{name:'Layout',exact:true}).evaluate(button=>button.click());
      assert.equal(await page.getByLabel('Escala do conteúdo (%) valor',{exact:true}).inputValue(),'120');
      await page.getByTitle('Fechar editor',{exact:true}).evaluate(button=>button.click());
    } else {
      await open();
      const original = await css('--primary');
      await setColor('#c533aa');
      await page.getByTitle('Desfazer',{exact:true}).click();
      await expectCss('--primary',original);
      await page.getByTitle('Refazer',{exact:true}).click();
      await expectCss('--primary','#c533aa');
      await page.getByTitle('Recolher editor',{exact:true}).click();
      await page.getByTitle('IA local',{exact:true}).click();
      await page.getByRole('button',{name:/Editar skin/}).click();
      assert.equal(await page.getByLabel('Cor principal',{exact:true}).inputValue(),'#c533aa');
      await page.getByTitle('Fechar editor',{exact:true}).click();
      await page.getByRole('button',{name:'Descartar',exact:true}).click();
      await page.waitForFunction(v=>getComputedStyle(document.documentElement).getPropertyValue('--primary').trim()===v,original);
      await open(); await setColor('#3975a9');
      await page.getByRole('button',{name:'Fundo',exact:true}).click();
      await page.getByLabel('Tipo de fundo',{exact:true}).selectOption('gradient');
      assert.equal(await page.locator('video.main-window-bg-video').count(),0);
      assert.match(await page.locator('.main-window-bg-image').evaluate(el=>getComputedStyle(el).backgroundImage),/linear-gradient/);
      await page.getByLabel('Tipo de fundo',{exact:true}).selectOption('color');
      assert.equal(await page.locator('.main-window-bg-image').count(),0);
      await page.getByLabel('Tipo de fundo',{exact:true}).selectOption('gradient');
      await page.getByRole('button',{name:'Layout',exact:true}).click();
      await page.getByLabel('Escala do conteúdo (%) valor',{exact:true}).fill('120');
      await page.getByLabel('Reduzir animações e pausar o fundo',{exact:true}).check();
      await page.getByLabel('Salvar como skin pessoal',{exact:true}).fill('Skin nativa teste');
      await page.getByRole('button',{name:'Criar e aplicar cópia',exact:true}).click();
      await page.getByText('Skin salva e aplicada.',{exact:true}).waitFor();
      assert.equal(await page.evaluate(async()=>await window.chrome.webview.hostObjects.api.GetActiveSkin()),'Skin nativa teste');
      await expectCss('--content-scale','1.2');
      const saved=await page.evaluate(async()=>JSON.parse(await window.chrome.webview.hostObjects.api.GetSkinConfig('Skin nativa teste')));
      assert.equal(saved.contentScale,120); assert.equal(saved.primaryColor,'#3975a9');
      await page.getByRole('button',{name:'Cores',exact:true}).click();
      await page.getByRole('button',{name:'Claro',exact:true}).click();
      await page.getByTitle('Fechar editor',{exact:true}).click();
      await page.getByRole('button',{name:'Descartar',exact:true}).click();
      await expectCss('--primary','#3975a9');
      await open(); await setColor('#8b44c2');
      // Saving as an existing name must fail without changing the current saved skin.
      await page.getByLabel('Nome para salvar uma cópia',{exact:true}).fill('Skin nativa teste');
      await page.getByRole('button',{name:'Salvar cópia',exact:true}).click();
      await page.getByRole('status').filter({hasText:/existe/}).waitFor();
      await page.getByTitle('Fechar editor',{exact:true}).click();
      await page.getByRole('button',{name:'Descartar',exact:true}).click();
      await expectCss('--primary','#3975a9');
      await open();
      await page.getByRole('button',{name:'Estrutura',exact:true}).click();
      await page.getByLabel('Acabamento',{exact:true}).selectOption('liquid');
      await page.getByRole('button',{name:'Painéis',exact:true}).click();
      await page.getByLabel('Opacidade dos painéis valor',{exact:true}).fill('0.7');
      await page.getByLabel('Reflexos do Liquid Glass valor',{exact:true}).fill('.65');
      await page.getByRole('button',{name:'Salvar e aplicar',exact:true}).click();
      await page.getByText('Skin salva e aplicada.',{exact:true}).waitFor();
      assert.equal(await page.locator('.app-container.skin-surface-liquid').count(),1);
      await mkdir(resolve(__dirname,'../../bin/skins-ui'),{recursive:true});
      await page.screenshot({path:resolve(__dirname,'../../bin/skins-ui/editor-native.png'),fullPage:true});
      await page.setViewportSize({width:760,height:650});
      assert.ok(await page.getByRole('button',{name:'Salvar e aplicar',exact:true}).isVisible());
      await page.screenshot({path:resolve(__dirname,'../../bin/skins-ui/editor-small.png'),fullPage:true});
      await page.getByTitle('Fechar editor',{exact:true}).click();
    }
    assert.deepEqual(errors,[]);
    console.log('PASS native skins ' + phase + ': live preview, discard, history, saved copy, bounds and persistence');
  } catch (error) {
    if (page) {
      console.error((await page.locator('body').innerText()).slice(-5000));
      await page.screenshot({path:resolve(__dirname,'../../bin/skins-ui/failure.png'),fullPage:true});
    }
    throw error;
  } finally {
    if(page) await page.evaluate(async()=>await window.chrome.webview.hostObjects.api.Shutdown()).catch(()=>{});
    if(browser) await browser.close();
  }
})().catch(e=>{console.error(e);process.exitCode=1;});
