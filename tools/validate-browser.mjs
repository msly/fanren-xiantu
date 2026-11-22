#!/usr/bin/env node
// Node 20+ and Playwright: node tools/validate-browser.mjs [report.json] [screenshots-dir]
// FANREN_CHROMIUM_PATH selects an installed browser; otherwise Playwright's Chromium is used.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const root = fs.realpathSync(path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..'));
const reportPath = path.resolve(root, process.argv[2] || 'docs/browser-verification.json');
const screenshotDir = path.resolve(root, process.argv[3] || path.join(path.dirname(reportPath), 'browser-verification-screenshots', new Date().toISOString().replace(/[:.]/g, '-')));
const inputFiles = ['game3d.html', 'web3d/main.js', 'web3d/style.css', 'web3d/environment.js', 'assets/3d/hanli.glb', 'assets/3d/mojiao.glb', 'tools/validate-browser.mjs'];
assert(!inputFiles.some(file => path.resolve(root, file) === reportPath), 'Report path must not replace a source or model input');
const sha256 = file => createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const report = {
  status: 'RUNNING', startedAt: new Date().toISOString(), stage: 'inputs',
  scope: 'Real Chromium, exported GLB loading, WebGL rendering, browser controls and measured DOM layout; mobile viewport is emulated.',
  webgl_verified: false, css_layout_verified: false, fps_measured: false, mobile_performance_verified: false,
  inputs: {}, checks: [], screenshots: [], pageErrors: [], consoleErrors: [], networkErrors: [],
};
const servedFiles = new Set();
let server, browser, navigationStarted = false;
function check(name, evidence, test) {
  const record = { name, status: 'FAIL', evidence };
  report.checks.push(record);
  try { test(); record.status = 'PASS'; } catch (error) { record.error = error.message; throw error; }
}
const insideRoot = target => {
  const relative = path.relative(root, target);
  return !path.isAbsolute(relative) && relative !== '..' && !relative.startsWith('..' + path.sep);
};
const hasDotSegment = relative => relative.split(/[\\/]/).some(part => part.startsWith('.'));
function serve(req, res) {
  try {
    if (!['GET', 'HEAD'].includes(req.method)) { res.writeHead(405, { Allow: 'GET, HEAD' }).end(); return; }
    const raw = (req.url || '').split('?')[0];
    const pathname = decodeURIComponent(raw);
    if (!pathname.startsWith('/') || pathname.startsWith('//') || /[\\\x00-\x1f\x7f]/.test(pathname) || hasDotSegment(pathname)) {
      res.writeHead(404).end(); return;
    }
    if (pathname === '/favicon.ico') { res.writeHead(204).end(); return; }
    const candidate = path.resolve(root, '.' + (pathname === '/' ? '/game3d.html' : pathname));
    if (!insideRoot(candidate)) { res.writeHead(404).end(); return; }
    const real = fs.realpathSync(candidate), relative = path.relative(root, real);
    if (!insideRoot(real) || hasDotSegment(relative)) { res.writeHead(404).end(); return; }
    const stat = fs.statSync(real);
    if (!stat.isFile()) { res.writeHead(404).end(); return; }
    const mime = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.json': 'application/json', '.glb': 'model/gltf-binary', '.png': 'image/png', '.jpg': 'image/jpeg' }[path.extname(real)] || 'application/octet-stream';
    res.writeHead(200, { 'Content-Type': mime, 'Content-Length': stat.size, 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' });
    servedFiles.add(relative.split(path.sep).join('/'));
    if (req.method === 'HEAD') res.end();
    else fs.createReadStream(real).on('error', () => res.destroy()).pipe(res);
  } catch { if (!res.headersSent) res.writeHead(404); res.end(); }
}
async function settle(page) {
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
}
async function screenshot(page, name) {
  fs.mkdirSync(screenshotDir, { recursive: true });
  const file = path.join(screenshotDir, name + '.png');
  await page.screenshot({ path: file });
  report.screenshots.push({ name, file: path.relative(path.dirname(reportPath), file).split(path.sep).join('/'), sha256: sha256(file) });
}
async function openPage(context, label, origin) {
  const page = await context.newPage();
  page.setDefaultTimeout(15000);
  page.on('pageerror', error => report.pageErrors.push({ context: label, message: error.message }));
  page.on('console', message => { if (message.type() === 'error') report.consoleErrors.push({ context: label, message: message.text() }); });
  page.on('requestfailed', request => report.networkErrors.push({ context: label, url: request.url(), error: request.failure()?.errorText }));
  page.on('response', response => { if (response.status() >= 400) report.networkErrors.push({ context: label, url: response.url(), status: response.status() }); });
  report.stage = label + '-navigation'; navigationStarted = true;
  const response = await page.goto(origin + '/game3d.html', { waitUntil: 'domcontentloaded', timeout: 30000 });
  assert.equal(response?.status(), 200, label + ': HTML must return 200');
  await page.waitForFunction(() => window.__xiantu3d?.getStatus().ready && window.__xiantu3d.renderer.info.render.triangles > 0, null, { timeout: 45000 });
  const loaded = await page.evaluate(() => window.__xiantu3d.getStatus());
  check(label + '-models-loaded-and-rendered', loaded, () => {
    assert(loaded.drawCalls > 0 && loaded.triangles > 0);
    for (const clips of [loaded.heroClips, loaded.beastClips]) for (const clip of ['Idle', 'Walk', 'Attack']) assert(clips.includes(clip));
    assert(servedFiles.has('assets/3d/hanli.glb') && servedFiles.has('assets/3d/mojiao.glb'));
  });
  return page;
}
async function layout(page, name, mode, touch = false) {
  const evidence = await page.evaluate(({ mode, touch }) => {
    const selectors = ['#scene', '#topbar', '.brand', '#topbar nav', '#quality', '#footer'];
    if (mode === 'viewer') selectors.push('#viewer');
    else selectors.push('#hero-hud', '#boss-hud', '#combat-actions', '#pause');
    if (touch) selectors.push('#touch-pad');
    const rects = {};
    for (const selector of selectors) {
      const el = document.querySelector(selector), style = getComputedStyle(el);
      rects[selector] = { ...el.getBoundingClientRect().toJSON(), display: style.display, visibility: style.visibility };
    }
    const controls = [...document.querySelectorAll('#topbar button, #topbar a, #viewer button, #combat-actions button, #pause, #touch-pad button')]
      .filter(el => el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden')
      .map(el => { const r = el.getBoundingClientRect(), hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2); return { label: el.id || el.dataset.frame || el.dataset.pose || el.dataset.key || el.textContent.trim(), ...r.toJSON(), reachable: hit === el || el.contains(hit) }; });
    return { viewport: { width: innerWidth, height: innerHeight }, scrollWidth: document.documentElement.scrollWidth, scrollHeight: document.documentElement.scrollHeight, coarsePointer: matchMedia('(pointer:coarse)').matches, rects, controls };
  }, { mode, touch });
  check(name, evidence, () => {
    const { width, height } = evidence.viewport;
    assert(evidence.scrollWidth <= width + 1 && evidence.scrollHeight <= height + 1, 'document overflow');
    const within = (rect, label) => {
      assert(rect.width > 0 && rect.height > 0, label + ': empty rectangle');
      assert(rect.left >= -1 && rect.top >= -1 && rect.right <= width + 1 && rect.bottom <= height + 1, label + ': outside viewport');
    };
    for (const [label, rect] of Object.entries(evidence.rects)) { assert(rect.display !== 'none' && rect.visibility !== 'hidden', label + ': hidden'); within(rect, label); }
    for (const control of evidence.controls) { within(control, control.label); assert(control.reachable, control.label + ': covered at center'); }
    const separated = (a, b) => a.right <= b.left + 1 || b.right <= a.left + 1 || a.bottom <= b.top + 1 || b.bottom <= a.top + 1;
    for (const [a, b] of [['.brand', '#topbar nav'], ['#topbar nav', '#quality']]) assert(separated(evidence.rects[a], evidence.rects[b]), a + ' overlaps ' + b);
    if (mode === 'viewer') {
      assert(separated(evidence.rects['#viewer'], evidence.rects['#topbar']), 'viewer overlaps header');
      assert(separated(evidence.rects['#viewer'], evidence.rects['#footer']), 'viewer overlaps footer');
    } else {
      assert(separated(evidence.rects['#hero-hud'], evidence.rects['#boss-hud']), 'health displays overlap');
      assert(separated(evidence.rects['#combat-actions'], evidence.rects['#pause']), 'pause overlaps actions');
      if (touch) assert(separated(evidence.rects['#combat-actions'], evidence.rects['#touch-pad']), 'touch controls overlap');
    }
    if (touch) assert(evidence.coarsePointer, 'touch viewport must use coarse pointer emulation');
  });
}
async function snapshot(page) {
  return page.evaluate(() => {
    const g = window.__xiantu3d;
    return { state: { ...g.state }, hero: g.hero.root.position.toArray(), beast: g.beast.root.position.toArray(), mixers: [g.hero.mixer.time, g.beast.mixer.time], dialog: document.querySelector('#result').open };
  });
}
try {
  for (const file of inputFiles) report.inputs[file] = sha256(path.join(root, file));
  report.stage = 'runtime'; assert(Number(process.versions.node.split('.')[0]) >= 20, 'Node 20+ is required');
  report.stage = 'dependencies'; const { chromium } = createRequire(import.meta.url)('playwright');
  report.stage = 'http-listen'; server = http.createServer(serve);
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  const origin = 'http://127.0.0.1:' + server.address().port;
  report.httpServer = { bind: '127.0.0.1', port: server.address().port };
  report.stage = 'chromium-launch';
  browser = await chromium.launch({ headless: true, ...(process.env.FANREN_CHROMIUM_PATH ? { executablePath: process.env.FANREN_CHROMIUM_PATH } : {}), timeout: 20000 });
  report.browserVersion = browser.version(); report.stage = 'browser-context';
  const desktop = await browser.newContext({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
  const page = await openPage(desktop, 'desktop', origin);
  report.stage = 'desktop-checks';
  report.webgl = await page.evaluate(() => {
    const g = window.__xiantu3d, gl = g.renderer.getContext(), debug = gl.getExtension('WEBGL_debug_renderer_info');
    const renderer = gl.getParameter(debug ? debug.UNMASKED_RENDERER_WEBGL : gl.RENDERER);
    const vendor = gl.getParameter(debug ? debug.UNMASKED_VENDOR_WEBGL : gl.VENDOR);
    const software = /swiftshader|llvmpipe|softpipe|software|lavapipe|swrast/i.test(renderer + ' ' + vendor);
    return { version: gl.getParameter(gl.VERSION), renderer, vendor, debugRendererAvailable: !!debug, classification: software ? 'software' : debug ? 'reported-hardware' : 'unknown', contextLost: gl.isContextLost(), error: gl.getError(), drawingBuffer: [gl.drawingBufferWidth, gl.drawingBufferHeight], render: { ...g.renderer.info.render } };
  });
  check('webgl-context-and-draw', report.webgl, () => { assert(!report.webgl.contextLost); assert.equal(report.webgl.error, 0); assert(report.webgl.render.triangles > 0); });
  report.webgl_verified = true;
  report.renderingNote = report.webgl.classification === 'software' ? 'Software WebGL rendering; this run does not validate hardware GPU performance.' : 'Renderer information is reported by WebGL; no frame-rate or device-performance claim is made.';
  await page.click('#view-hero');
  for (const frame of ['full', 'portrait', 'head']) {
    await page.click('[data-frame="' + frame + '"]'); await settle(page);
    const status = await page.evaluate(() => window.__xiantu3d.getStatus());
    check('hero-' + frame, status, () => { assert.equal(status.mode, 'hero'); assert.equal(status.frame, frame); assert(status.triangles > 0); });
    await layout(page, 'desktop-hero-' + frame + '-layout', 'viewer'); await screenshot(page, 'desktop-hero-' + frame);
  }
  await page.click('#view-beast'); await page.click('[data-frame="head"]'); await settle(page);
  const beastStatus = await page.evaluate(() => window.__xiantu3d.getStatus());
  check('beast-head', beastStatus, () => { assert.equal(beastStatus.mode, 'beast'); assert.equal(beastStatus.frame, 'head'); });
  await layout(page, 'desktop-beast-head-layout', 'viewer'); await screenshot(page, 'desktop-beast-head');
  await page.click('#view-scene'); await page.click('#begin');
  const beforeMove = await snapshot(page); await page.keyboard.down('KeyW');
  await page.waitForFunction(before => Math.hypot(...window.__xiantu3d.hero.root.position.toArray().map((v, i) => v - before[i])) > .35, beforeMove.hero, { timeout: 8000 });
  await page.keyboard.up('KeyW'); const afterMove = await snapshot(page);
  check('keyboard-movement', { before: beforeMove, after: afterMove }, () => assert(Math.hypot(...afterMove.hero.map((v, i) => v - beforeMove.hero[i])) > .35));
  await page.click('#view-scene'); const activeScene = await snapshot(page);
  check('active-scene-does-not-reset-battle', activeScene, () => { assert.equal(activeScene.state.phase, 'battle'); assert.deepEqual(activeScene.hero, afterMove.hero); });
  await page.click('#pause'); const frozen = await snapshot(page);
  await page.keyboard.down('KeyW'); await page.keyboard.press('KeyJ'); await page.keyboard.press('KeyQ'); await page.keyboard.press('Space');
  await page.waitForTimeout(250); await page.keyboard.up('KeyW'); const stillFrozen = await snapshot(page);
  check('pause-freezes-state-input-and-animation', { before: frozen, after: stillFrozen }, () => { assert(frozen.state.paused); assert.deepEqual(stillFrozen, frozen); });
  await layout(page, 'desktop-battle-layout', 'battle'); await screenshot(page, 'desktop-paused-battle');
  await page.click('#pause'); await page.waitForFunction(time => !window.__xiantu3d.state.paused && window.__xiantu3d.state.time > time, frozen.state.time);
  const resumed = await snapshot(page);
  check('resume-advances-simulation', resumed, () => { assert(!resumed.state.paused); assert(resumed.state.time > frozen.state.time); });
  // Explicit deterministic fixture: use a real click/attack/finish path, without waiting for a full boss fight.
  await page.evaluate(() => { const g = window.__xiantu3d; g.state.bossHP = 31; g.state.bossCD = 10; g.state.bossWind = g.state.bossLunge = 0; g.beast.root.position.set(g.hero.root.position.x, 0, g.hero.root.position.z - 2); });
  await page.click('#strike'); await page.waitForFunction(() => window.__xiantu3d.state.phase === 'victory' && document.querySelector('#result').open);
  const victory = await snapshot(page);
  const hudWidth = await page.locator('#boss-hp').evaluate(el => el.style.width);
  check('victory-dialog', { fixture: 'boss HP set to 31 and positioned two meters ahead; normal strike resolves the victory', snapshot: victory, hudWidth }, () => { assert.equal(victory.state.bossHP, 0); assert(victory.dialog); assert.equal(hudWidth, '0%', 'final health HUD must show zero'); });
  await screenshot(page, 'desktop-victory'); await page.click('#retry'); const retried = await snapshot(page);
  check('retry-resets-battle', retried, () => { assert.equal(retried.state.phase, 'battle'); assert.equal(retried.state.hp, 100); assert.equal(retried.state.qi, 100); assert.equal(retried.state.bossHP, 360); assert(!retried.dialog && !retried.state.paused); assert.deepEqual(retried.hero, [-1.25, 0, 3.1]); });
  await desktop.close();
  report.stage = 'mobile-emulation-checks';
  const mobile = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1, isMobile: true, hasTouch: true });
  const phone = await openPage(mobile, 'mobile-emulation', origin);
  for (const [actor, frame] of [['hero', 'portrait'], ['hero', 'head'], ['beast', 'head']]) {
    await phone.tap('#view-' + actor); await phone.tap('[data-frame="' + frame + '"]'); await settle(phone);
    await layout(phone, 'mobile-' + actor + '-' + frame + '-layout', 'viewer'); await screenshot(phone, 'mobile-' + actor + '-' + frame);
  }
  await phone.tap('#view-scene'); await phone.tap('#begin'); await phone.tap('#pause');
  await layout(phone, 'mobile-battle-touch-layout', 'battle', true); await screenshot(phone, 'mobile-paused-battle');
  report.css_layout_verified = true;
  await settle(phone); await mobile.close();
  report.stage = 'final-checks';
  check('no-browser-or-network-errors', { pageErrors: report.pageErrors, consoleErrors: report.consoleErrors, networkErrors: report.networkErrors }, () => { assert.equal(report.pageErrors.length, 0); assert.equal(report.consoleErrors.length, 0); assert.equal(report.networkErrors.length, 0); });
  check('runtime-files-served', [...servedFiles].sort(), () => { for (const file of inputFiles.filter(file => !file.startsWith('tools/'))) assert(servedFiles.has(file), file + ' was not requested'); });
  report.inputsAfter = Object.fromEntries(inputFiles.map(file => [file, sha256(path.join(root, file))]));
  check('inputs-unchanged-during-run', report.inputsAfter, () => assert.deepEqual(report.inputsAfter, report.inputs));
  report.status = 'PASS'; report.stage = 'complete';
} catch (error) {
  const environmentStage = ['runtime', 'dependencies', 'http-listen', 'chromium-launch', 'browser-context'].includes(report.stage);
  report.status = !navigationStarted && environmentStage ? 'BLOCKED' : 'FAIL';
  report.error = String(error.stack || error);
} finally {
  if (browser) await browser.close().catch(error => { report.cleanupError = String(error); if (report.status === 'PASS') report.status = 'FAIL'; });
  if (server?.listening) { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
  report.finishedAt = new Date().toISOString();
  fs.mkdirSync(path.dirname(reportPath), { recursive: true });
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2) + '\n');
  process.exitCode = report.status === 'PASS' ? 0 : report.status === 'BLOCKED' ? 2 : 1;
  console.log(JSON.stringify({ status: report.status, stage: report.stage, report: reportPath, screenshots: report.screenshots.length, error: report.error?.split('\n')[0] || null }, null, 2));
}
