import { MotionEngine } from './motion.js';

const element = id => document.getElementById(id);
const engine = new MotionEngine({ x: 0, y: 0.2, z: 0 });
const phaseNames = { idle: '待命', moving: '运动中', paused: '已暂停', arrived: '已到达', cancelled: '已停止', error: '异常' };
let view, socket, ready = false, allowReconnect = true, retryDelay = 1000;
let lastFrame = null, lastReport = 0, lastReportedPhase = '', lastUI = 0;
let route = null, completedSteps = 0, activeStep = -1;
const events = [];

function setText(id, text) { if (element(id).textContent !== text) element(id).textContent = text; }
function number(value, digits = 3) { return (Math.abs(value) < 0.5 * 10 ** -digits ? 0 : value).toFixed(digits); }

function addEvent(event, detail) {
  events.unshift({ time: new Date().toLocaleTimeString('zh-CN', { hour12: false }), event, detail });
  if (events.length > 30) events.pop();
  const rows = events.map(entry => {
    const row = document.createElement('tr');
    for (const text of [entry.time, entry.event, entry.detail]) { const cell = document.createElement('td'); cell.textContent = text; row.append(cell); }
    return row;
  });
  element('events').replaceChildren(...rows);
  setText('event-count', `${events.length} 条记录`);
}

function showError(message) {
  element('error-banner').textContent = message;
  element('error-banner').hidden = false;
  addEvent('异常', message);
}

function connection(label, online = false) {
  setText('connection', label);
  element('connection').className = `connection ${online ? 'online' : 'offline'}`;
}

function send(message) {
  if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify(message));
}

function applyRoute(value, position = value.initial_position) {
  route = value;
  completedSteps = 0; activeStep = -1; lastReportedPhase = ''; lastFrame = null;
  engine.reset(position);
  view.setRoute(route); view.setPosition(position);
  setText('route-name', route.name); setText('route-count', `${route.segments.length} 个路段`);
  element('waypoints').replaceChildren(...route.segments.map((segment, index) => {
    const item = document.createElement('li'); item.className = 'waypoint';
    const heading = document.createElement('div'); heading.className = 'waypoint-heading';
    const marker = document.createElement('span'); marker.className = 'waypoint-number'; marker.textContent = index + 1;
    heading.append(marker, document.createTextNode(`路段 ${index + 1}`));
    const coordinates = document.createElement('p'); coordinates.className = 'waypoint-coordinate';
    coordinates.textContent = `(${number(segment.target.x, 1)}, ${number(segment.target.y, 1)}, ${number(segment.target.z, 1)})`;
    const speed = document.createElement('p'); speed.className = 'waypoint-speed'; speed.textContent = `${number(segment.speed, 2)} m/s`;
    item.append(heading, coordinates, speed); return item;
  }));
  updateUI();
}

function report(force = false) {
  const state = engine.snapshot();
  if (!ready || !state.command_id) return;
  const changed = state.phase !== lastReportedPhase;
  if (!changed && ['arrived', 'cancelled', 'error'].includes(state.phase)) return;
  const now = performance.now();
  if (!force && !changed && now - lastReport < 100) return;
  if (changed) {
    if (state.phase === 'arrived') {
      if (activeStep >= 0) completedSteps = activeStep + 1;
      addEvent('到达', `${state.command_id} · ${number(state.elapsed_s, 2)} s`);
    } else if (state.phase === 'paused') addEvent('暂停', state.reason);
    else if (state.phase === 'cancelled') addEvent('停止', state.reason);
    else if (state.phase === 'moving' && lastReportedPhase === 'paused') addEvent('继续', state.command_id);
  }
  send({ type: 'telemetry', command_id: state.command_id, phase: state.phase,
    position: state.position, elapsed_s: state.elapsed_s, reason: state.reason });
  lastReportedPhase = state.phase; lastReport = now;
}

function updateUI() {
  const state = engine.snapshot();
  for (const axis of ['x', 'y', 'z']) {
    setText(`current-${axis}`, number(state.position[axis]));
    setText(`target-${axis}`, state.target ? number(state.target[axis]) : '—');
  }
  setText('command-id', state.command_id ?? '—');
  for (const [id, value, unit] of [['speed', state.speed, 'm/s'], ['elapsed', state.elapsed_s, 's']]) {
    const small = document.createElement('small'); small.textContent = unit;
    element(id).replaceChildren(document.createTextNode(number(value, 2) + ' '), small);
  }
  const percent = Math.round(state.progress * 100);
  element('progress').value = percent; setText('progress-value', `${percent}%`);
  setText('phase', ready ? phaseNames[state.phase] : '未连接');
  element('phase').className = `phase ${ready ? state.phase : ''}`;
  element('pause').disabled = !ready || state.phase !== 'moving';
  element('resume').disabled = !ready || state.phase !== 'paused' || document.hidden;
  element('stop').disabled = !ready || !engine.busy;
  element('pause-reason').hidden = state.phase !== 'paused';
  setText('pause-reason', state.reason);
  let note = '等待外部控制程序下发指令';
  if (!ready) note = '等待页面与本地服务建立连接';
  else if (state.phase === 'moving') note = activeStep >= 0 ? `正在执行第 ${activeStep + 1} / ${route.segments.length} 个路段` : '正在执行外部运动指令';
  else if (state.phase === 'paused') note = state.reason;
  else if (state.phase === 'arrived') note = completedSteps === route?.segments.length ? '全部路段已完成' : '本段已到达，等待下一条指令';
  else if (state.phase === 'cancelled') note = '运动已停止，可重新运行外部控制程序';
  setText('scene-note', note);
  [...element('waypoints').children].forEach((item, index) => {
    item.className = `waypoint ${index < completedSteps ? 'done' : (index === activeStep && engine.busy ? 'active' : '')}`;
  });
}

function connect() {
  connection('连接中');
  const current = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws`);
  socket = current;
  current.onmessage = event => {
    if (current !== socket) return;
    try {
      const message = JSON.parse(event.data);
      if (message.type === 'hello') {
        applyRoute(message.state.route, message.state.position);
        send({ type: 'ready', visible: !document.hidden });
      } else if (message.type === 'ready') {
        ready = true; retryDelay = 1000; element('error-banner').hidden = true;
        connection('已连接', true); addEvent('连接', '三维页面已就绪'); updateUI();
      } else if (message.type === 'route') {
        applyRoute(message.route); addEvent('路径', `已加载 ${message.route.name}`);
      } else if (message.type === 'move') {
        engine.start(message.command);
        activeStep = route?.segments[completedSteps] &&
          ['x', 'y', 'z'].every(axis => Math.abs(route.segments[completedSteps].target[axis] - message.command.target[axis]) < 1e-9) ? completedSteps : -1;
        view.setTarget(message.command.target);
        if (document.hidden) engine.pause('hidden');
        lastFrame = null; lastReportedPhase = '';
        addEvent('运动', `${message.command.command_id} · ${number(message.command.speed, 2)} m/s`);
        report(true); updateUI();
      } else if (message.type === 'control') {
        if (message.action === 'pause') engine.pause('manual');
        if (message.action === 'resume') { engine.resume('manual'); lastFrame = null; }
        if (message.action === 'stop') engine.cancel('收到停止指令');
        report(true); updateUI();
      } else if (message.type === 'error') {
        allowReconnect = false; showError(message.message); current.close();
      }
    } catch (error) {
      showError(`处理指令失败：${error.message}`);
      engine.cancel('指令处理失败'); report(true); allowReconnect = false; current.close();
    }
  };
  current.onclose = event => {
    if (current !== socket) return;
    ready = false; lastFrame = null; engine.cancel('服务连接已断开');
    connection('连接断开'); updateUI();
    if (event.code === 4009) allowReconnect = false;
    if (allowReconnect) {
      addEvent('连接', '连接断开，正在重连；旧命令不会自动续跑');
      setTimeout(connect, retryDelay); retryDelay = Math.min(retryDelay * 2, 8000);
    }
  };
  current.onerror = () => connection('服务未连接');
}

async function control(action) {
  const response = await fetch('/api/control', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action, command_id: engine.snapshot().command_id }) });
  const result = await response.json();
  if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : JSON.stringify(result.detail));
}

for (const action of ['pause', 'resume', 'stop']) {
  element(action).addEventListener('click', async () => {
    element(action).disabled = true;
    try { await control(action); } catch (error) { showError(error.message); }
    updateUI();
  });
}
element('reset-camera').addEventListener('click', () => view?.resetCamera());
element('copy-command').addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText('.venv\\Scripts\\python controller.py');
    element('copy-command').textContent = '已复制';
    setTimeout(() => { element('copy-command').textContent = '复制'; }, 1500);
  } catch { showError('请手动复制旁边的控制命令。'); }
});
document.addEventListener('visibilitychange', () => {
  send({ type: 'visibility', visible: !document.hidden });
  if (document.hidden) engine.pause('hidden');
  else { engine.resume('hidden'); lastFrame = null; }
  report(true); updateUI();
});
window.addEventListener('beforeunload', () => { allowReconnect = false; socket?.close(); });

try {
  const { createScene } = await import('./scene.js');
  view = createScene(element('scene'));
  element('scene').addEventListener('webglcontextlost', event => {
    event.preventDefault(); allowReconnect = false; engine.cancel('三维绘图环境已丢失'); report(true);
    socket?.close(); showError('三维绘图环境已丢失，请刷新页面。');
  });
  connect();
  function animate(timestamp) {
    const deltaSeconds = lastFrame === null ? 0 : Math.max(0, (timestamp - lastFrame) / 1000);
    lastFrame = timestamp;
    engine.tick(deltaSeconds);
    view.setPosition(engine.position, engine.phase === 'moving' || engine.phase === 'arrived');
    report();
    if (timestamp - lastUI >= 100) { updateUI(); lastUI = timestamp; }
    view.render();
    requestAnimationFrame(animate);
  }
  requestAnimationFrame(animate);
} catch (error) {
  connection('画面未就绪');
  showError(`三维画面初始化失败：${error.message}。请使用支持 WebGL2 的浏览器，并检查硬件加速。`);
}
