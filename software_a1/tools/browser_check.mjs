// 可选浏览器集成检查：需要先启动 server.py，并安装 Playwright 和 Chrome。
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';

const root = fileURLToPath(new URL('..', import.meta.url));
const output = path.join(root, 'output');
const base = (process.argv[2] ?? 'http://127.0.0.1:8000').replace(/\/$/, '');
const { chromium } = await import(process.env.A1_PLAYWRIGHT_MODULE ?? 'playwright');
const python = process.env.A1_PYTHON ?? path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const checks = [];
const errors = [];
const runTag = Date.now().toString(36);
let browser, child;

async function api(endpoint, payload) {
  const response = await fetch(base + endpoint, payload ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) } : {});
  const result = await response.json();
  assert.ok(response.ok, JSON.stringify(result));
  return result;
}

async function eventually(read, accept, label, timeout = 10000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const value = await read();
    if (accept(value)) return value;
    await delay(30);
  }
  throw new Error(`等待超时：${label}`);
}

function watch(page) {
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', item => {
    if (item.type() === 'error' || (item.type() === 'warning' && item.text().includes('Buffer size'))) errors.push(item.text());
  });
  page.on('request', request => {
    if (!request.url().startsWith(base) && !request.url().startsWith('data:')) errors.push(`页面访问外部资源：${request.url()}`);
  });
}

await fs.mkdir(output, { recursive: true });
try {
  browser = await chromium.launch({ channel: 'chrome', headless: true, args: ['--enable-unsafe-swiftshader'] });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 }, deviceScaleFactor: 1 });
  const page = await context.newPage(); watch(page);
  await page.goto(base);
  await page.locator('#connection').filter({ hasText: '已连接' }).waitFor();
  checks.push('Three.js 页面就绪，依赖全部来自本地');

  child = spawn(python, [path.join(root, 'controller.py'), '--url', base], { cwd: root, windowsHide: true });
  let stdout = '', stderr = '';
  child.stdout.setEncoding('utf8'); child.stderr.setEncoding('utf8');
  child.stdout.on('data', data => { stdout += data; }); child.stderr.on('data', data => { stderr += data; });
  const completed = new Promise((resolve, reject) => {
    child.on('error', reject); child.on('close', code => resolve(code));
  });
  await page.locator('#phase').filter({ hasText: '运动中' }).waitFor();
  await delay(250);
  await page.screenshot({ path: path.join(output, 'preview-moving.png'), fullPage: true });
  await page.getByRole('button', { name: '暂停', exact: true }).click();
  await page.locator('#phase').filter({ hasText: '已暂停' }).waitFor();
  const paused = await eventually(() => api('/api/state'), state => state.phase === 'paused', '暂停回执');
  await delay(450);
  const stillPaused = await api('/api/state');
  assert.deepEqual(stillPaused.position, paused.position);
  await page.getByRole('button', { name: '继续', exact: true }).click();
  checks.push('页面真实暂停 / 继续，暂停期间位置不变');

  assert.equal(await completed, 0, stderr || stdout);
  assert.match(stdout, /全部路段已到达：PASS/);
  const run = JSON.parse(await fs.readFile(path.join(output, 'last_run.json'), 'utf8'));
  assert.equal(run.status, 'completed'); assert.equal(run.commands.length, 4);
  for (const command of run.commands) {
    assert.equal(command.status, 'arrived');
    assert.ok(Math.abs(command.motion_elapsed_s - command.expected_motion_s) < 1e-6);
    assert.deepEqual(command.position, command.target);
  }
  await fs.writeFile(path.join(output, 'controller-demo.txt'), stdout + stderr, 'utf8');
  checks.push('独立 Python 进程通过 HTTP 逐段下发，四段到达后才完成');
  checks.push('每段最终坐标及运动时间与目标、路程 / 速度一致');
  await page.locator('#scene-note').filter({ hasText: '全部路段已完成' }).waitFor();
  await page.screenshot({ path: path.join(output, 'preview-desktop.png'), fullPage: true });

  await page.setViewportSize({ width: 390, height: 844 });
  await delay(150);
  const size = await page.evaluate(() => ({ content: document.documentElement.scrollWidth, viewport: window.innerWidth }));
  assert.ok(size.content <= size.viewport, JSON.stringify(size));
  await page.screenshot({ path: path.join(output, 'preview-mobile.png'), fullPage: true });
  checks.push('390px 窄屏布局无横向溢出');
  await page.setViewportSize({ width: 1440, height: 1100 });

  const stopId = `browser-stop-${runTag}`;
  await api('/api/move', { command_id: stopId, target: { x: 3, y: 0.2, z: 3 }, speed: 0.5 });
  await page.locator('#phase').filter({ hasText: '运动中' }).waitFor();
  await page.getByRole('button', { name: '停止', exact: true }).click();
  const stopped = await eventually(() => api(`/api/commands/${stopId}`), value => value.status === 'cancelled', '停止回执');
  assert.notDeepEqual(stopped.position, stopped.target);
  checks.push('停止产生 cancelled，不被误报为到达');

  const disconnectId = `browser-disconnect-${runTag}`;
  await api('/api/move', { command_id: disconnectId, target: { x: 4, y: 0.2, z: 0 }, speed: 0.5 });
  await page.locator('#phase').filter({ hasText: '运动中' }).waitFor();
  await page.close();
  await eventually(() => api(`/api/commands/${disconnectId}`), value => value.status === 'cancelled', '断线取消');
  const reconnected = await context.newPage(); watch(reconnected);
  await reconnected.goto(base);
  await reconnected.locator('#connection').filter({ hasText: '已连接' }).waitFor();
  assert.equal((await api('/api/state')).active_command_id, null);
  checks.push('关闭页面会取消未完成命令，重连后不自动续跑旧命令');
  assert.deepEqual(errors, []);
  checks.push('浏览器无脚本错误或外部资源请求');
  await fs.writeFile(path.join(output, 'browser_check.json'), JSON.stringify({ status: 'passed', checks, browser_errors: errors }, null, 2) + '\n');
  console.log(JSON.stringify({ status: 'passed', checks, output }, null, 2));
} catch (error) {
  await fs.writeFile(path.join(output, 'browser_check.json'), JSON.stringify({ status: 'failed', checks, error: error.stack, browser_errors: errors }, null, 2) + '\n');
  throw error;
} finally {
  if (child && child.exitCode === null) child.kill();
  await browser?.close();
}
