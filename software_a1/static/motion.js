// 纯数学模块：不依赖浏览器、Three.js 或服务端，便于独立测试。
export function point(value) {
  if (!value || ![value.x, value.y, value.z].every(v => typeof v === 'number' && Number.isFinite(v))) {
    throw new Error('坐标必须包含有限的 x、y、z 数值');
  }
  return { x: value.x, y: value.y, z: value.z };
}

export function distance(a, b) {
  return Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z);
}

export function advanceTowards(position, target, speed, deltaSeconds) {
  const from = point(position), to = point(target);
  if (!Number.isFinite(speed) || speed <= 0) throw new Error('速度必须有限且大于零');
  if (!Number.isFinite(deltaSeconds) || deltaSeconds < 0) throw new Error('时间差必须有限且非负');
  const remaining = distance(from, to);
  if (!Number.isFinite(remaining)) throw new Error('目标距离超出了有限数值范围');
  if (remaining === 0) return { position: to, arrived: true, moved: 0, usedSeconds: 0 };
  const step = Math.min(speed * deltaSeconds, remaining);
  const arrived = step >= remaining;
  const ratio = step / remaining;
  return {
    position: arrived ? to : {
      x: from.x + (to.x - from.x) * ratio,
      y: from.y + (to.y - from.y) * ratio,
      z: from.z + (to.z - from.z) * ratio,
    },
    arrived, moved: step, usedSeconds: step / speed,
  };
}

export class MotionEngine {
  constructor(initial) { this.reset(initial); }

  get busy() { return this.phase === 'moving' || this.phase === 'paused'; }

  reset(position) {
    this.position = point(position);
    this.command = null;
    this.phase = 'idle';
    this.elapsed = 0;
    this.reason = '';
    this.pauseReasons = new Set();
  }

  start(command) {
    if (this.busy) throw new Error('上一条命令尚未完成');
    if (typeof command.command_id !== 'string' || !command.command_id) throw new Error('缺少命令编号');
    const target = point(command.target);
    if (!Number.isFinite(command.speed) || command.speed <= 0) throw new Error('速度无效');
    this.command = { command_id: command.command_id, target, speed: command.speed, start: point(this.position) };
    this.elapsed = 0;
    this.reason = '';
    this.pauseReasons.clear();
    this.phase = 'moving';
  }

  tick(deltaSeconds) {
    if (this.phase !== 'moving') return;
    const step = advanceTowards(this.position, this.command.target, this.command.speed, deltaSeconds);
    this.position = step.position;
    this.elapsed += step.usedSeconds;
    if (step.arrived) this.phase = 'arrived';
  }

  pause(reason = 'manual') {
    if (!this.busy) return;
    this.pauseReasons.add(reason);
    this.phase = 'paused';
    this.reason = this.pauseReasons.has('hidden') ? '页面位于后台，已暂停' : '手动暂停';
  }

  resume(reason = 'manual') {
    this.pauseReasons.delete(reason);
    if (this.phase !== 'paused') return;
    if (this.pauseReasons.size === 0) { this.phase = 'moving'; this.reason = ''; }
    else this.reason = this.pauseReasons.has('hidden') ? '页面位于后台，已暂停' : '手动暂停';
  }

  cancel(reason = '运动已停止') {
    if (!this.busy) return;
    this.phase = 'cancelled';
    this.reason = reason;
    this.pauseReasons.clear();
  }

  snapshot() {
    const total = this.command ? distance(this.command.start, this.command.target) : 0;
    const remaining = this.command ? distance(this.position, this.command.target) : 0;
    return { command_id: this.command?.command_id ?? null, phase: this.phase,
      position: point(this.position), target: this.command ? point(this.command.target) : null,
      speed: this.command?.speed ?? 0, elapsed_s: this.elapsed, reason: this.reason,
      progress: this.command ? (total === 0 ? (this.phase === 'arrived' ? 1 : 0) : Math.max(0, Math.min(1, 1 - remaining / total))) : 0 };
  }
}
