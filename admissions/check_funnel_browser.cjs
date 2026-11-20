// Run against a local UFHOB server: node admissions/check_funnel_browser.cjs
const { spawn } = require('node:child_process');
const { mkdirSync, mkdtempSync, writeFileSync } = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

async function main() {
  mkdirSync(path.join(process.cwd(), 'tmp'), {recursive:true});
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
    await send('Emulation.setDeviceMetricsOverride', {width:375,height:812,deviceScaleFactor:1,mobile:true});
    await send('Page.addScriptToEvaluateOnNewDocument', {source:"window.pixelEvents=[]; window.fbq=function(){pixelEvents.push(Array.from(arguments));}; window.fbq.loaded=true;"});
    const origin = process.env.UFHOB_TEST_ORIGIN || 'http://127.0.0.1:8765';
    const screenshot = async name => {
      const result=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
      const target=path.join(profile,name+'.png'); writeFileSync(target,Buffer.from(result.data,'base64')); return target;
    };
    const screenshots=[];
    for (const code of ['FATEC','ESGA']) {
      await send('Page.navigate',{url:origin+'/formations/tunnel-'+code.toLowerCase()+'/?utm_source=mobile-test'});
      await waitFor("document.readyState==='complete' && document.querySelector('.programme-mobile-apply a')",'mobile programme '+code);
      await evaluate("document.querySelector('#cookie-reject-all')?.click()");
      const bounds=await evaluate("(()=>{const e=document.querySelector('.programme-mobile-apply'); const r=e.getBoundingClientRect();return {bottom:r.bottom,top:r.top,position:getComputedStyle(e).position,width:innerWidth,overflow:document.documentElement.scrollWidth};})()");
      assert.equal(bounds.position,'fixed'); assert(bounds.bottom<=813 && bounds.top>650); assert(bounds.overflow<=376);
      assert(await evaluate("Array.from(document.querySelectorAll('a')).some(a=>a.textContent.trim()==='Candidater' && a.getBoundingClientRect().top<innerHeight)"),'Top CTA visible');
      screenshots.push(await screenshot(code+'-fiche-375'));
      await evaluate("window.scrollTo(0,document.body.scrollHeight)");
      assert(await evaluate("document.querySelector('.programme-mobile-apply').getBoundingClientRect().bottom<=innerHeight+1"));
      await evaluate("document.querySelector('.programme-mobile-apply a').click()");
      await waitFor("document.readyState==='complete' && window.Alpine && document.querySelector('form[x-data]')",'tunnel');
      await evaluate("window.funnel=Alpine.$data(document.querySelector('form[x-data]'))");
      assert.equal(await evaluate('funnel.formData.school_code'),code);
      assert.equal(await evaluate('funnel.formData.formation_slug'),'tunnel-'+code.toLowerCase());
      assert.equal(await evaluate("document.querySelectorAll('input[type=file],input[name=documents_deferred]').length"),0);
      assert.equal(await evaluate("pixelEvents.filter(e=>e[1]==='InitiateCheckout').length"),1);
      await evaluate("Array.from(document.querySelectorAll('.admission-shell button')).find(b=>b.innerText.includes('Commencer ma candidature')).click()");
      await evaluate("for(const [key,value] of Object.entries({last_name:'Recette',first_name:'UFHOB',city:'Test'})){const input=document.querySelector('input[data-field='+key+']');input.value=value;input.dispatchEvent(new Event('input',{bubbles:true}));} funnel.goTo(2)");
      await evaluate("for(const [key,value] of Object.entries({email:'mobile-'+Date.now()+'@example.invalid',phone:'00000000',birth_date:'2000-01-01'})){const input=document.querySelector('input[data-field='+key+']');input.value=value;input.dispatchEvent(new Event('input',{bubbles:true}));} funnel.formData.gender='female'; funnel.goTo(3)");
      await waitFor("document.querySelector('#step3-campuses-list button')",'campus');
      await evaluate("document.querySelector('#step3-campuses-list button').click()");
      await waitFor("document.querySelector('#step3-formations-list button')",'preselected programme');
      await evaluate("document.querySelector('#step3-formations-list button').click()");
      await waitFor('funnel.step===4','recap');
      assert.equal(await evaluate("document.querySelector('[x-show=\"step === 4\"]').innerText.toLowerCase().includes('pièce')"),false);
      await delay(350);
      await evaluate("document.querySelector('[x-show=\"step === 4\"]').scrollIntoView({block:'start'})");
      await delay(200);
      screenshots.push(await screenshot(code+'-recap-375'));
      await evaluate("document.querySelector('button[type=submit]').scrollIntoView({block:'center'})");
      await delay(250);
      const submitPoint=await evaluate("(()=>{const e=document.querySelector('button[type=submit]');const r=e.getBoundingClientRect();const x=r.left+r.width/2,y=r.top+r.height/2;return {x,y,reachable:e.contains(document.elementFromPoint(x,y))};})()");
      assert(submitPoint.reachable,'Submit button can be clicked at 375px');
      await send('Input.dispatchMouseEvent',{type:'mousePressed',x:submitPoint.x,y:submitPoint.y,button:'left',clickCount:1});
      await send('Input.dispatchMouseEvent',{type:'mouseReleased',x:submitPoint.x,y:submitPoint.y,button:'left',clickCount:1});
      await waitFor("location.pathname.includes('/done/') && document.readyState==='complete'",'confirmation');
      assert(await evaluate("document.body.innerText.includes('+223 76 88 24 79')"));
      assert.equal(await evaluate("pixelEvents.filter(e=>e[1]==='Lead').length"),1);
      screenshots.push(await screenshot(code+'-confirmation-375'));
      await send('Page.reload');
      await waitFor("document.readyState==='complete' && document.body.innerText.includes('Votre candidature')",'confirmation reload');
      assert.equal(await evaluate("pixelEvents.filter(e=>e[1]==='Lead').length"),0);
    }
    // Migrate the old documents phase without restoring files or waiting on HTMX.
    await send('Page.navigate',{url:origin+'/admissions/?formation=tunnel-fatec'});
    await waitFor("document.readyState==='complete' && window.Alpine && document.querySelector('form[x-data]')",'draft preparation');
    await evaluate("(()=>{const state=Alpine.$data(document.querySelector('form[x-data]')); sessionStorage.setItem(state.draftKey,JSON.stringify({step:3,step3Phase:'documents',formData:{...state.formData,branch_id:'1',email:'draft@example.invalid'},documentsDeferred:true,hadFiles:true}));})()");
    await send('Page.navigate',{url:origin+'/admissions/'});
    await waitFor("document.readyState==='complete' && window.Alpine && document.querySelector('form[x-data]')",'old draft restored');
    assert.equal(await evaluate("Alpine.$data(document.querySelector('form[x-data]')).step"),4);
    assert.equal(await evaluate("Alpine.$data(document.querySelector('form[x-data]')).step3Phase"),'program');
    assert.equal(requests.some(url=>url.includes('/documents/')),false,'No document fragment request');
    assert.deepEqual(errors,[],'No JavaScript errors');
    console.log(JSON.stringify({result:'PASS',viewport:375,schools:['FATEC','ESGA'],oldDraft:true,uniqueLead:true,screenshots,requests},null,2));
    await send('Browser.close');
  } finally {
    if (ws) ws.close();
    browser.kill();
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
