// Run against a local UFHOB server: node admissions/check_funnel_browser.cjs
const { spawn } = require('node:child_process');
const { mkdtempSync, writeFileSync } = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

async function main() {
  const profile = mkdtempSync(path.join(process.cwd(), 'tmp', 'admission-browser-'));
  const browser = spawn(process.env.UFHOB_BROWSER_EXECUTABLE || path.join(process.env['ProgramFiles(x86)'], 'Microsoft', 'Edge', 'Application', 'msedge.exe'), [
    '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
    '--remote-debugging-port=9876', `--user-data-dir=${profile}`, 'about:blank',
  ], { windowsHide: true, stdio: 'ignore' });
  let ws;
  try {
    let tabs;
    for (let i = 0; i < 80; i++) {
      try { tabs = await (await fetch('http://127.0.0.1:9876/json')).json(); break; }
      catch { await delay(250); }
    }
    assert(tabs, 'Browser did not start');
    ws = new WebSocket(tabs.find(tab => tab.type === 'page').webSocketDebuggerUrl);
    await new Promise(resolve => ws.addEventListener('open', resolve, { once: true }));
    let sequence = 0;
    const pending = new Map();
    const errors = [], requests = [];
    ws.addEventListener('message', event => {
      const message = JSON.parse(event.data);
      if (message.id) {
        const task = pending.get(message.id);
        pending.delete(message.id);
        if (message.error) task.reject(message.error); else task.resolve(message.result);
      }
      if (message.method === 'Runtime.exceptionThrown') errors.push(JSON.stringify(message.params.exceptionDetails));
      if (message.method === 'Runtime.consoleAPICalled' && message.params.type === 'error') errors.push(JSON.stringify(message.params));
      if (message.method === 'Network.requestWillBeSent' && message.params.request.url.includes('/partials/step3/')) requests.push(message.params.request.url);
    });
    const send = (method, params = {}) => new Promise((resolve, reject) => {
      const id = ++sequence; pending.set(id, { resolve, reject });
      ws.send(JSON.stringify({ id, method, params }));
    });
    const evaluate = async expression => {
      const result = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
      if (result.exceptionDetails) throw new Error(result.exceptionDetails.text);
      return result.result.value;
    };
    const waitFor = async (expression, description) => {
      for (let i = 0; i < 120; i++) {
        if (await evaluate(expression)) return;
        await delay(250);
      }
      console.error('Browser diagnostics', await evaluate("({ready:document.readyState, state:window.Alpine&&document.querySelector('form[x-data]')?JSON.stringify(Alpine.$data(document.querySelector('form[x-data]'))):null, campuses:document.querySelector('#step3-campuses-list')?.innerHTML})"), errors);
      throw new Error(`Timed out: ${description}`);
    };
    await send('Runtime.enable'); await send('Network.enable'); await send('Page.enable');
    await send('Page.navigate', { url: 'http://127.0.0.1:8765/admissions/' });
    await waitFor("Boolean(document.readyState === 'complete' && window.htmx && window.Alpine && document.querySelector('[data-field=school_code] button'))", 'page initialized');
    await evaluate("document.querySelector('#cookie-reject-all')?.click()");
    await evaluate("window.funnel = Alpine.$data(document.querySelector('form[x-data]')); Array.from(document.querySelectorAll('.admission-shell button')).find(b=>b.innerText.includes('Commencer ma candidature')).click()");
    await evaluate("for(const [key,value] of Object.entries({last_name:'Recette',first_name:'UFHOB',city:'Test'})){const input=document.querySelector('input[data-field='+key+']');input.value=value;input.dispatchEvent(new Event('input',{bubbles:true}));}");
    await evaluate("funnel.goTo(2)");
    await evaluate("for(const [key,value] of Object.entries({email:'recette@example.invalid',phone:'00000000',birth_date:'2000-01-01'})){const input=document.querySelector('input[data-field='+key+']');input.value=value;input.dispatchEvent(new Event('input',{bubbles:true}));} funnel.formData.gender='female'; funnel.goTo(3)");
    await delay(300);
    await evaluate("document.querySelector('[data-field=school_code] button').click()");
    await waitFor("document.querySelector('#step3-campuses-list button')", 'campuses displayed');
    assert.equal(await evaluate('funnel.formData.branch_id'), '', 'Campus must be chosen explicitly');
    await evaluate("document.querySelector('#step3-campuses-list button').click()");
    await delay(300);
    await waitFor("funnel.step3Phase === 'cycle' && document.querySelector('#step3-cycles-list button')", 'cycles displayed');
    await evaluate("document.querySelector('#step3-cycles-list button').click()");
    await delay(300);
    await waitFor("funnel.step3Phase === 'program' && document.querySelector('#step3-formations-list button')", 'programmes displayed');
    await evaluate("document.querySelector('#step3-formations-list button').click()");
    await waitFor("funnel.step3Phase === 'documents' && !document.querySelector('#step3-documents-list').innerText.includes('Choisissez une formation')", 'documents displayed');
    await waitFor("document.querySelector('#step3-documents-list [data-documents-ready]')", 'document inputs ready');
    await evaluate("funnel.goTo(4)");
    if (await evaluate('funnel.requiredDocumentsTotal() > 0')) assert.equal(await evaluate('funnel.step'), 3, 'Missing documents require consent');
    await evaluate("document.querySelector('#documents-deferred').click()");
    await evaluate("(()=>{const input=document.querySelector('#step3-documents-list input[type=file]');if(input){const dt=new DataTransfer();dt.items.add(new File(['%PDF-1.4 test'], 'piece-recette.pdf', {type:'application/pdf'}));input.files=dt.files;input.dispatchEvent(new Event('change',{bubbles:true}));}})()");
    const files = await evaluate('funnel.uploadedDocumentsCount()');
    await evaluate("funnel.goTo(4)");
    assert.equal(await evaluate('funnel.step'), 4);
    await evaluate('funnel.goTo(3)'); await delay(300);
    assert.equal(await evaluate('funnel.uploadedDocumentsCount()'), files, 'Files survive recap and back');
    assert.equal(await evaluate('funnel.documentsDeferred'), true, 'Partial upload does not silently remove consent');
    const chosen = await evaluate('({school:funnel.formData.school_code, campus:funnel.formData.branch_name, programme:funnel.formData.formation, slug:funnel.formData.formation_slug})');
    await evaluate("funnel.step3Phase='school'"); await delay(250);
    await evaluate("document.querySelectorAll('[data-field=school_code] button')[1].click()");
    await waitFor("document.querySelector('#step3-campuses-list').innerText.includes('Campus proposés pour ' + funnel.formData.school_name)", 'campuses for second school');
    assert.equal(await evaluate('funnel.formData.branch_id'), '');
    assert.equal(await evaluate('funnel.formData.formation_slug'), '');
    const changed = await evaluate("({school:funnel.formData.school_code, campuses:document.querySelector('#step3-campuses-list').innerText})");
    const screenshots = [];
    for (const width of [1920,1440,1366,1024,768,390]) {
      await send('Emulation.setDeviceMetricsOverride', {width,height:1000,deviceScaleFactor:1,mobile:false});
      await delay(300);
      assert(await evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'), `No horizontal overflow at ${width}px`);
      const result = await send('Page.captureScreenshot', {format:'png', captureBeyondViewport:true});
      const target = path.join(profile, `funnel-${width}.png`);
      writeFileSync(target, Buffer.from(result.data,'base64')); screenshots.push(target);
    }
    await evaluate("funnel.step3Phase='school'"); await delay(200);
    await evaluate("Array.from(document.querySelectorAll('[data-field=school_code] button')).find(b=>b.innerText.includes('FATEC')).click()");
    await waitFor("document.querySelector('#step3-campuses-list').innerText.includes('Campus proposés pour FATEC')", 'FATEC campuses');
    await evaluate("document.querySelector('#step3-campuses-list button').click()");
    await delay(300);
    await waitFor("document.querySelector('#step3-cycles-list button') && !document.querySelector('#step3-cycles-list').classList.contains('htmx-request')", 'FATEC cycles');
    const fatecCycles = await evaluate("document.querySelector('#step3-cycles-list').innerText");
    assert(fatecCycles.includes('DUT') && fatecCycles.includes('Licence') && fatecCycles.includes('Master'), 'FATEC cycles match actual programmes');
    assert(!fatecCycles.includes('Doctorat'), 'No ESMED cycle left on FATEC');
    await evaluate("document.querySelector('#step3-cycles-list button').click()");
    await delay(300);
    await waitFor("document.querySelector('#step3-formations-list button') && !document.querySelector('#step3-formations-list').classList.contains('htmx-request')", 'FATEC programmes');
    const fatec = await evaluate("document.querySelector('#step3-formations-list').innerText");
    assert(!fatec.includes('Chirurgie'), 'No ESMED programme on FATEC');
    assert(fatec.includes('DUT'), 'FATEC programme selection uses its selected cycle');
    for (const width of [1920,1440,1366,1024,768,390]) {
      await send('Emulation.setDeviceMetricsOverride', {width,height:1000,deviceScaleFactor:1,mobile:false});
      await delay(600);
      await waitFor("document.querySelector('.funnel-programme')", 'responsive programmes');
      assert(await evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'), `Programme grid fits ${width}px`);
      assert(await evaluate("Array.from(document.querySelectorAll('.tunnel-nav button')).filter(b=>b.offsetParent).every(b=>b.getBoundingClientRect().left>=0 && b.getBoundingClientRect().right<=window.innerWidth)"), `Navigation buttons fit ${width}px`);
    }
    await evaluate("document.querySelector('#step3-formations-list button').click()");
    await waitFor("document.querySelector('#step3-documents-list [data-documents-ready]')", 'FATEC documents');
    await evaluate("if (!funnel.documentsDeferred) document.querySelector('#documents-deferred').click(); funnel.goTo(4)");
    assert.equal(await evaluate('funnel.step'), 4);
    for (const width of [1920,1440,1366,1024,768,390]) {
      await send('Emulation.setDeviceMetricsOverride', {width,height:1000,deviceScaleFactor:1,mobile:false});
      await delay(300);
      assert(await evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'), `Recap fits ${width}px`);
      const result = await send('Page.captureScreenshot', {format:'png',captureBeyondViewport:true});
      const target = path.join(profile, `recap-${width}.png`);
      writeFileSync(target,Buffer.from(result.data,'base64')); screenshots.push(target);
    }
    await evaluate("funnel.step=3");
    await evaluate("funnel.step3Phase='campus'"); await delay(300);
    const beforeReload = requests.length;
    await send('Page.reload');
    await waitFor("document.readyState === 'complete' && window.Alpine && document.querySelector('#step3-campuses-list button')", 'campuses restored after reload');
    assert(requests.length > beforeReload, 'Restored draft must refresh compatible campuses');
    await send('Page.navigate', {url:'http://127.0.0.1:8765/admissions/?formation=' + encodeURIComponent(chosen.slug)});
    await waitFor("document.readyState === 'complete' && window.Alpine && document.querySelector('form[x-data]')", 'direct programme entry');
    await evaluate("window.funnel=Alpine.$data(document.querySelector('form[x-data]'))");
    assert.equal(await evaluate('funnel.formData.formation_slug'), chosen.slug);
    assert.equal(await evaluate('funnel.formData.current_level'), 'doctorat');
    assert.equal(await evaluate('funnel.step'), 1, 'Direct link still collects candidate identity');
    await evaluate('funnel.startDiscovery()');
    await waitFor("document.querySelector('#step3-campuses-list button')", 'direct entry campus choice');
    await evaluate("document.querySelector('#step3-campuses-list button').click()");
    await waitFor("document.querySelector('#step3-documents-list [data-documents-ready]')", 'preselected programme documents');
    assert.equal(await evaluate('funnel.formData.formation_slug'), chosen.slug, 'Campus selection keeps the preselected programme');
    assert.deepEqual(errors, [], 'No JavaScript errors in the admission journey');
    console.log(JSON.stringify({ result: 'PASS', chosen, changed, fatecCycles, fatec, screenshots, requests }, null, 2));
    await send('Browser.close');
  } finally {
    if (ws) ws.close();
    browser.kill();
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
