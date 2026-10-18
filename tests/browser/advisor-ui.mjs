// Run against a Docker gateway using an existing Playwright installation.
import { createRequire } from 'node:module';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_PACKAGE || 'playwright');
const base = process.env.UI_BASE_URL || 'http://localhost:38000';
const out = process.env.UI_OUTPUT || '.scratch/final-ui-interaction-qa';
const mutate = process.env.UI_MUTATIONS === '1';
const feedbackSubmit = process.env.UI_FEEDBACK === '1';
await fs.mkdir(out, { recursive: true });
const browser = await chromium.launch({ headless: process.env.UI_HEADLESS === '1' });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, permissions: ['clipboard-read', 'clipboard-write'], locale: 'en-GB', timezoneId: 'UTC' });
const audit = { base, started: new Date().toISOString(), interactions: [], responses: [], console: [], failed: [], navigation: [], geometry: [] };
let expectedValidation = false;
context.on('page', p => {
  p.on('console', m => audit.console.push({ page: p.url(), type: m.type(), text: m.text(), expectedValidation }));
  p.on('pageerror', e => audit.console.push({ page: p.url(), type: 'pageerror', text: e.message }));
});
context.on('requestfailed', r => audit.failed.push({ url: r.url(), method: r.method(), error: r.failure()?.errorText }));
context.on('response', r => {
  const h = r.headers();
  audit.responses.push({ url: r.url(), origin: new URL(r.url()).origin, method: r.request().method(), type: r.request().resourceType(), status: r.status(), redirectFrom: r.request().redirectedFrom()?.url(), contentType: h['content-type'], cacheControl: h['cache-control'], etag: h.etag, location: h.location, cors: h['access-control-allow-origin'], expectedValidation });
});
const page = await context.newPage();
page.setDefaultTimeout(15000);
async function check(screen, element, action, expected, fn) {
  const start = audit.responses.length, consoleStart = audit.console.length;
  try {
    const actual = await fn();
    audit.interactions.push({ screen, element, action, expected, actual: actual ?? 'As expected', pass: true, requests: audit.responses.slice(start), console: audit.console.slice(consoleStart) });
    console.log(`PASS ${screen}: ${element}`);
  } catch (error) {
    audit.interactions.push({ screen, element, action, expected, actual: error.message, pass: false, requests: audit.responses.slice(start), console: audit.console.slice(consoleStart) });
    throw error;
  }
}
async function shot(name, fullPage = true) { await page.screenshot({ path: `${out}/${name}.png`, fullPage }); }
async function noOverflow(label) {
  const geometry = await page.evaluate(() => ({ width: innerWidth, document: document.documentElement.scrollWidth }));
  audit.geometry.push({ label, ...geometry });
  assert.ok(geometry.document <= geometry.width + 1, `${label} overflows: ${JSON.stringify(geometry)}`);
}
async function dropdown(width) {
  const button = page.getByRole('button', { name: 'Observability' });
  const menu = page.locator('.dropdown-menu');
  await check(`Header ${width}`, 'Observability mouse/Escape', 'Click, Escape', 'Open then close; focus on toggle', async () => {
    await button.click(); assert.ok(await menu.isVisible());
    const box = await menu.boundingBox(); assert.ok(box.x >= 0 && box.x + box.width <= width + 1);
    await page.keyboard.press('Escape'); assert.ok(!(await menu.isVisible())); assert.ok(await button.evaluate(e => e === document.activeElement));
  });
  await check(`Header ${width}`, 'Observability keyboard/outside', 'Enter, ArrowDown, Escape; open and click outside', 'Keyboard focus enters menu, outside closes', async () => {
    await button.focus(); await page.keyboard.press('Enter'); assert.ok(await menu.isVisible());
    await page.keyboard.press('ArrowDown'); assert.ok(await menu.locator('a').evaluateAll(es => es.includes(document.activeElement)));
    await page.keyboard.press('Escape'); await button.click(); await page.locator('h1').first().click(); assert.ok(!(await menu.isVisible()));
  });
}
let reports = {};
try {
  await check('Public', 'Root redirect', 'Navigate /', '/advisor/ 200', async () => {
    const r = await page.goto(base + '/'); assert.equal(new URL(page.url()).pathname, '/advisor/'); assert.equal(r.status(), 200);
  });
  await check('Landing', 'Manual/developer forms', 'Inspect and focus target', 'All forms visible and labelled', async () => {
    assert.ok(await page.getByRole('heading', { name: 'Manual analysis' }).isVisible());
    assert.ok(await page.getByRole('heading', { name: 'Developer tools' }).isVisible());
    await page.getByLabel('Target', { exact: true }).fill('orders-api');
    for (const label of ['Start', 'End']) assert.ok(await page.getByLabel(label, { exact: true }).isVisible());
  });
  await check('Header', 'Recent analyses', 'Click', 'History anchor scrolls into view', async () => {
    await page.getByRole('link', { name: 'Recent analyses', exact: true }).click(); assert.equal(new URL(page.url()).hash, '#recent-analyses');
    await page.waitForFunction(() => document.querySelector('#recent-analyses').getBoundingClientRect().y < 200);
  });
  await check('Recent', 'View all', 'Expand/collapse', 'Additional rows become visible', async () => {
    const history = page.locator('.advisor-history-details');
    if (!await history.count()) return 'Not present: fewer than six reports';
    await history.locator('summary').click(); assert.ok(await history.evaluate(e => e.open));
    assert.ok(await history.locator('a').first().isVisible()); await shot('recent-analyses-expanded', false);
    await history.locator('summary').click(); assert.ok(!(await history.evaluate(e => e.open)));
  });
  await check('Header', 'Home', 'Click product', 'Advisor landing', async () => { await page.getByRole('link', { name: 'DB Reliability Advisor', exact: true }).click(); assert.equal(new URL(page.url()).pathname, '/advisor/'); });
  for (const [width, height] of [[1920,1080],[1440,1000],[1280,800],[1024,768],[768,1024],[390,844]]) {
    await page.setViewportSize({ width, height });
    await check(`Landing ${width}`, 'Responsive layout', 'Inspect geometry and visible forms', 'No page overflow or clipped fields', async () => {
      await noOverflow('landing');
      for (const selector of ['#target', '#startTime', '#endTime']) { const b = await page.locator(selector).boundingBox(); assert.ok(b.width > 80 && b.x >= 0 && b.x + b.width <= width + 1); }
      if (width >= 1280) {
        const row = page.locator('.advisor-report-row').first();
        const box = await row.boundingBox(), arrow = await row.locator('.advisor-row-link .bi').boundingBox();
        assert.ok(box.height < 190);
        assert.ok(box.x + box.width - arrow.x - arrow.width < 50, 'Open affordance stays at the row end even without metrics');
      }
    });
    if ([1440,768,390].includes(width)) await dropdown(width);
    if ([1440,1024,390].includes(width)) await shot(`advisor-${width}`);
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
  for (const [name, path, text] of [['Grafana','/grafana/d/dbadv-mvp-overview/','DB Reliability Advisor'],['Prometheus','/prometheus/','Prometheus'],['Alertmanager','/alertmanager/','Alertmanager'],['Docs','/advisor/docs','Database Reliability Advisor']]) {
    await check('Navigation', name, 'Click actual new-tab link', 'Working same-origin destination with safe rel', async () => {
      if (name !== 'Docs') await page.getByRole('button', { name: 'Observability' }).click();
      const link = page.getByRole('link', { name, exact: true });
      assert.ok((await link.getAttribute('href')).startsWith(path)); assert.match(await link.getAttribute('rel'), /noopener/);
      const open = context.waitForEvent('page'); await link.click(); const dest = await open; await dest.waitForLoadState();
      await dest.getByText(text, { exact: false }).filter({ visible: true }).first().waitFor({ timeout: 30000 });
      if (name === 'Grafana') { await dest.getByText('Scrape targets up', { exact: true }).waitFor(); await dest.getByRole('button', { name: 'Cancel', exact: true }).waitFor({ state: 'hidden', timeout: 60000 }); }
      assert.equal(new URL(dest.url()).origin, base); audit.navigation.push({ name, url: dest.url(), text: (await dest.locator('body').innerText()).slice(0,800) });
      await dest.evaluate(() => document.fonts.ready);
      await dest.screenshot({ path: `${out}/${name.toLowerCase()}.png` }); await page.bringToFront(); await page.keyboard.press('Escape');
    });
  }
  await check('Manual', 'Empty target/dates', 'Clear fields then submit', 'Native required validation; no POST', async () => {
    const before = audit.responses.filter(r => r.method === 'POST').length;
    await page.getByLabel('Target', { exact: true }).fill(''); await page.getByRole('button', { name: 'Run analysis', exact: true }).click();
    assert.ok(!(await page.locator('#target').evaluate(e => e.validity.valid)));
    await page.locator('#target').fill('orders-api'); await page.getByRole('button', { name: 'Run analysis', exact: true }).click();
    assert.ok(!(await page.locator('#startTime').evaluate(e => e.validity.valid)));
    assert.equal(audit.responses.filter(r => r.method === 'POST').length, before);
  });
  for (const [label, start, end, message] of [['reversed','2026-10-18T12:00','2026-10-18T11:00','startTime must be earlier'],['equal','2026-10-18T12:00','2026-10-18T12:00','startTime must be earlier'],['over maximum','2026-10-10T12:00','2026-10-18T12:00','exceeds configured maximum']]) {
    await check('Manual', label, 'Submit invalid dates', '422 HTML with readable error and retained values', async () => {
      expectedValidation = true; await page.locator('#startTime').fill(start); await page.locator('#endTime').fill(end);
      const response = page.waitForResponse(r => r.request().method() === 'POST');
      await page.getByRole('button', { name: 'Run analysis', exact: true }).click(); const r = await response; await page.waitForLoadState();
      assert.equal(r.status(), 422); assert.match(await page.locator('[role=alert]').innerText(), new RegExp(message));
      assert.ok(!(await page.locator('[role=alert]').innerText()).includes('input_value')); assert.equal(await page.locator('#startTime').inputValue(), start);
      expectedValidation = false;
    });
  }
  await page.goto(base + '/advisor/');
  if (mutate) {
    for (const [kind, name] of [['query','Run query regression demo'],['connection','Run connection pressure demo']]) {
      await check('Developer', kind, 'Click once and observe in-flight state', 'One POST, disabled controls, 303 to mock report', async () => {
        const before = audit.responses.length;
        await page.getByRole('button', { name, exact: true }).click({ noWaitAfter: true });
        assert.ok(await page.getByRole('button', { name: 'Running analysis…', exact: true }).isDisabled());
        assert.equal(await page.locator('[data-analysis-form] button:enabled').count(), 0);
        await page.waitForURL(/\/analyses\/AN-.*\/report$/, { timeout: 180000 });
        assert.ok(await page.locator('.context-bar').getByText('Mock data', { exact: true }).isVisible());
        reports[kind] = page.url();
        const posts = audit.responses.slice(before).filter(r => r.method === 'POST'); assert.equal(posts.length, 1); assert.equal(posts[0].status, 303);
        await page.getByRole('link', { name: 'Run another analysis' }).click();
      });
    }
    await check('Manual', 'Valid window', 'Submit valid target/start/end', '303 to rendered report', async () => {
      await page.locator('#startTime').fill('2026-10-18T07:00'); await page.locator('#endTime').fill('2026-10-18T07:10');
      await page.getByRole('button', { name: 'Run analysis', exact: true }).click({ noWaitAfter: true });
      await page.waitForURL(/\/analyses\/AN-.*\/report$/, { timeout: 180000 }); assert.ok(await page.locator('.context-bar').isVisible());
      reports.manual = page.url(); await page.getByRole('link', { name: 'Run another analysis' }).click();
    });
  }
  const recent = await page.locator('.advisor-report-row h3 a').evaluateAll(es => es.slice(0,5).map(e => e.href));
  reports.query ||= process.env.UI_QUERY_URL || recent[0];
  reports.connection ||= process.env.UI_CONNECTION_URL || recent[1];
  reports.fallback = process.env.UI_FALLBACK_URL;
  for (const selector of ['.advisor-report-row h3 a', '.advisor-row-link']) {
    await check('Recent', selector, 'Click report link/chevron', 'Rendered report, then return', async () => {
      await page.locator(selector).first().click(); assert.ok(await page.locator('.context-bar').isVisible()); await page.getByRole('link', { name: 'Run another analysis' }).click();
    });
  }
  for (const [kind, url] of Object.entries(reports).filter(([kind,url]) => kind !== 'manual' && url)) {
    await page.goto(url);
    if (kind === 'fallback') await check('Fallback', 'AI unavailable', 'Inspect hypothesis', 'No confidence for unavailable AI', async () => { assert.ok(await page.getByRole('heading', { name: 'AI interpretation unavailable' }).isVisible()); assert.equal(await page.locator('.confidence').count(), 0); });
    for (const [width,height] of [[1920,1080],[1440,1000],[1280,800],[1024,768],[768,1024],[390,844]]) {
      await page.setViewportSize({width,height});
      await check(`${kind} ${width}`, 'Context and overflow', 'Measure rendered layout', 'Compact horizontal desktop, safe mobile', async () => {
        await noOverflow(kind); const b = await page.locator('.context-bar').boundingBox(); audit.geometry.push({label:kind,width,context:b});
        if (width >= 1280) { assert.ok(b.height < 150); const fields = await page.locator('.context-bar>div').evaluateAll(es=>es.map(e=>e.getBoundingClientRect().x)); assert.ok(new Set(fields).size > 2); }
      });
      if (width === 1440 || (kind === 'query' && width === 390)) await shot(`${kind}-${width}`);
      await check(`${kind} ${width}`, 'Disclosures and copy', 'Open both sequences and copy each query', 'Independent heights, real clipboard matches', async () => {
        const verify = page.locator('details').filter({ has: page.locator('summary', { hasText: 'Verify the evidence' }) });
        const detail = page.locator('details').filter({ has: page.locator('summary', { hasText: 'Detailed evidence' }) });
        assert.ok(!(await verify.evaluate(e => e.open))); assert.ok(!(await detail.evaluate(e => e.open)));
        await verify.locator('summary').click(); assert.ok(await verify.evaluate(e => e.open)); assert.ok((await detail.boundingBox()).height < 150);
        if (kind === 'query' && width === 1440) await shot('report-verification-open');
        await page.bringToFront();
        const copies = verify.getByRole('button', { name: 'Copy query', exact: true });
        for (let i=0;i<await copies.count();i++) { await copies.nth(i).click(); assert.equal(await page.evaluate(()=>navigator.clipboard.readText()), await copies.nth(i).getAttribute('data-query')); assert.equal(await copies.nth(i).locator('..').locator('.copy-status').innerText(), 'Copied'); }
        await detail.locator('summary').click(); assert.ok(await detail.evaluate(e => e.open)); await verify.locator('summary').click(); assert.ok((await verify.boundingBox()).height < 150);
        if (kind === 'query' && width === 1440) await shot('report-detailed-open');
        await verify.locator('summary').click(); assert.ok(await verify.evaluate(e=>e.open));
        await noOverflow(`${kind} expanded`); await detail.locator('summary').click(); await verify.locator('summary').click();
      });
    }
  }
  await page.setViewportSize({width:1440,height:1000}); await page.goto(reports.query);
  await dropdown(1440); await page.getByRole('button',{name:'Observability'}).click(); await page.evaluate(()=>scrollTo(0,0)); await shot('report-observability-open',false); await page.keyboard.press('Escape');
  await check('Feedback', 'Required verdict and all options', 'Submit empty; select every verdict; type comment', 'Native required validation, exclusive selection', async () => {
    await page.getByRole('button',{name:'Submit feedback'}).click(); assert.ok(!(await page.locator('#verdict-correct').evaluate(e=>e.validity.valid)));
    for(const name of ['Correct','Partially correct','Incorrect']) { await page.getByRole('radio',{name,exact:true}).check(); assert.equal(await page.locator('[name=verdict]:checked').count(),1); }
    await page.getByRole('radio',{name:'Correct',exact:true}).check(); await page.getByLabel('Optional comment').fill('Local browser QA: mock report interaction verified.');
  });
  if(feedbackSubmit) await check('Feedback','One submission','Click Submit once','201, inline confirmation, no duplicate submit',async()=>{
    const response=page.waitForResponse(r=>r.url().endsWith('/feedback')&&r.request().method()==='POST');
    await page.getByRole('button',{name:'Submit feedback'}).click(); assert.equal((await response).status(),201);
    await page.getByText('Feedback recorded. Thank you.',{exact:true}).waitFor(); assert.ok(await page.getByRole('button',{name:'Submitted',exact:true}).isDisabled());
    assert.equal(audit.responses.filter(r=>r.method==='POST'&&r.url.endsWith('/feedback')).length,1);
  });
  await check('Network','Application requests/assets','Review all recorded browser requests','Same origin, correct MIME, no unexpected failures',async()=>{
    const app=audit.responses.filter(r=>new URL(r.url).pathname.startsWith('/advisor/'));
    assert.ok(app.every(r=>r.origin===base));
    assert.deepEqual(app.filter(r=>r.status>=400&&!r.expectedValidation),[]);
    assert.deepEqual(audit.failed.filter(r=>new URL(r.url).pathname.startsWith('/advisor/')),[]);
    const required=[['bootstrap.min.css','text/css'],['bootstrap-icons.min.css','text/css'],['bootstrap-icons.woff2','font/woff2'],['report.css','text/css'],['bootstrap.bundle.min.js','javascript'],['advisor.js','javascript'],['favicon.svg','image/svg+xml']];
    for(const [suffix,mime] of required) assert.ok(app.some(r=>r.url.split('?')[0].endsWith(suffix)&&r.status===200&&r.contentType.includes(mime)),`Missing asset ${suffix}`);
    assert.deepEqual(audit.console.filter(m=>m.page.startsWith(base+'/advisor/')&&['error','pageerror'].includes(m.type)&&!m.expectedValidation),[]);
    assert.deepEqual(audit.console.filter(m=>/CORS|Mixed Content|blocked by|Failed to fetch|Cross-Origin|preflight/i.test(m.text)),[]);
  });
} finally {
  audit.reports=reports; audit.finished=new Date().toISOString();
  await fs.writeFile(`${out}/browser-audit.json`,JSON.stringify(audit,null,2));
  const esc=v=>String(v??'').replaceAll('|','/').replaceAll('\n',' ');
  const matrix=['# Browser interaction matrix','','| Screen | Element | Action | Expected behavior | Actual behavior | Network request | Console output | PASS/FAIL | Defect ID |','|---|---|---|---|---|---|---|---|---|',...audit.interactions.map(i=>`| ${[i.screen,i.element,i.action,i.expected,i.actual,i.requests.map(r=>`${r.method} ${new URL(r.url).pathname} ${r.status}`).join('; ')||'None',i.console.map(m=>m.text).join('; ')||'None',i.pass?'PASS':'FAIL',i.pass?'':'See actual'].map(esc).join(' | ')} |`)];
  await fs.writeFile(`${out}/INTERACTION-MATRIX.md`,matrix.join('\n')+'\n');
  console.log(JSON.stringify({passed:audit.interactions.filter(i=>i.pass).length,failed:audit.interactions.filter(i=>!i.pass).length,reports}));
  await browser.close();
}
