// Real HTMX/browser regression using Django-generated test responses only.
const {spawn} = require('node:child_process');
const {readFileSync, mkdtempSync} = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const assert = require('node:assert/strict');
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

async function main() {
  const fixturePath = process.argv[2];
  const data = JSON.parse(readFileSync(fixturePath, 'utf8'));
  const template = readFileSync('accounts/templates/accounts/dashboard/manager_dashboard.html', 'utf8');
  const managerScript = template.match(/<script>([\s\S]*?)<\/script>/)[1];
  const server = http.createServer((req, res) => {
    if (req.url === '/htmx.js') {
      res.setHeader('Content-Type', 'text/javascript');
      return res.end(readFileSync('static/vendor/htmx/htmx.min.js'));
    }
    res.setHeader('Content-Type', 'text/html; charset=utf-8');
    if (req.url === data.acceptUrl) {
      for (const [key, value] of Object.entries(data.headers)) {
        if (key.toLowerCase().startsWith('hx-')) res.setHeader(key, value);
      }
      return res.end(data.accepted);
    }
    if (req.url === data.positioningUrl) return res.end(data.positioning);
    if (req.url === '/blocked') return res.end(data.blockedPositioning);
    res.end(`<!doctype html><html><head><script src="/htmx.js"></script></head><body>
      <table><tbody><tr id="candidature-${data.candidateId}"><td>Candidate</td></tr></tbody></table>
      <div id="manager-modal-content">${data.detail}</div>
      <script>window.modalOpen=true; window.confirm=()=>true;
      window.addEventListener('ui-overlay-open',()=>window.modalOpen=true);
      window.addEventListener('ui-overlay-close',()=>window.modalOpen=false);</script>
      <script>${managerScript}</script></body></html>`);
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const profile = mkdtempSync(path.join(path.dirname(fixturePath), 'browser-'));
  const browser = spawn(process.env.UFHOB_BROWSER_EXECUTABLE || path.join(process.env['ProgramFiles(x86)'], 'Microsoft', 'Edge', 'Application', 'msedge.exe'), [
    '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
    '--remote-debugging-port=9877', `--user-data-dir=${profile}`, 'about:blank',
  ], {windowsHide: true, stdio: 'ignore'});
  let ws;
  try {
    let tabs;
    for (let i = 0; i < 80; i++) {
      try { tabs = await (await fetch('http://127.0.0.1:9877/json')).json(); break; }
      catch { await delay(250); }
    }
    assert(tabs, 'Browser did not start');
    ws = new WebSocket(tabs.find(tab => tab.type === 'page').webSocketDebuggerUrl);
    await new Promise(resolve => ws.addEventListener('open', resolve, {once: true}));
    let sequence = 0;
    const pending = new Map();
    ws.addEventListener('message', event => {
      const message = JSON.parse(event.data);
      if (message.id) {
        const task = pending.get(message.id); pending.delete(message.id);
        if (message.error) task.reject(message.error); else task.resolve(message.result);
      }
    });
    const send = (method, params = {}) => new Promise((resolve, reject) => {
      const id = ++sequence; pending.set(id, {resolve, reject}); ws.send(JSON.stringify({id, method, params}));
    });
    const evaluate = async expression => {
      const result = await send('Runtime.evaluate', {expression, returnByValue:true, awaitPromise:true});
      if (result.exceptionDetails) throw new Error(result.exceptionDetails.text);
      return result.result.value;
    };
    const waitFor = async expression => {
      for (let i=0; i<80; i++) { if (await evaluate(expression)) return; await delay(100); }
      throw new Error(`Timed out: ${expression}`);
    };
    await send('Page.navigate', {url:`http://127.0.0.1:${server.address().port}/`});
    await waitFor("document.readyState === 'complete' && typeof managerOpenModal === 'function'");
    await evaluate(`document.querySelector('[hx-post="${data.acceptUrl}"]').click()`);
    await waitFor("!!document.querySelector('select[name=academic_level]')");
    await delay(250);
    assert.equal(await evaluate('window.modalOpen'), true, 'Acceptance must leave the positioning modal open');
    await evaluate("document.querySelector('select[name=academic_level]').value='L2'; document.querySelector('select[name=academic_level]').dispatchEvent(new Event('change'))");
    assert.deepEqual(await evaluate("Array.from(document.querySelector('select[name=academic_class]').options).filter(o=>o.value).map(o=>o.dataset.level)"), ['L2'], 'Injected level selector must filter compatible classes');
    await evaluate("const field=document.querySelector('select[name=academic_class]'); field.selectedIndex=1; field.dispatchEvent(new Event('change'))");
    assert.match(await evaluate(`document.getElementById('academic-fee-${data.candidateId}').textContent`), /150000/, 'Selected class must display its fee');
    await evaluate("managerOpenModal('/blocked')");
    await waitFor("document.querySelector('#manager-modal-content').textContent.includes(\"En attente d'une classe compatible\")");
    assert.equal(await evaluate("!!document.querySelector('#manager-modal-content button[type=submit]')"), false, 'Missing classes cannot bypass academic positioning');
    await evaluate(`document.querySelector('#manager-modal-content [hx-get="${data.positioningUrl}"]').click()`);
    await waitFor("!!document.querySelector('select[name=academic_level]')");
    assert.equal(await evaluate('window.modalOpen'), true, 'Checking new classes keeps the current modal open');
    console.log('PASS: acceptance stays open; level filtering and fee display run after dynamic loading.');
    await send('Browser.close');
    await Promise.race([new Promise(resolve => browser.once('exit',resolve)), delay(3000)]);
  } finally {
    if (ws) ws.close();
    browser.kill();
    server.close();
  }
}
main().catch(error => {console.error(error); process.exitCode=1;});
