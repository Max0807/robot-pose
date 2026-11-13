import test from 'node:test';
import assert from 'node:assert/strict';
import { advanceTowards, distance, MotionEngine } from '../static/motion.js';

const origin = { x: 0, y: 0.2, z: 0 };
const target = { x: 2, y: 0.2, z: 0 };
const command = () => ({ command_id: 'test-1', target: { ...target }, speed: 0.5 });
const near = (a, b, epsilon = 1e-10) => assert.ok(Math.abs(a - b) < epsilon, `${a} != ${b}`);

test('axis motion uses speed times elapsed seconds', () => {
  const step = advanceTowards(origin, target, 0.5, 0.1);
  near(step.position.x, 0.05); near(step.moved, 0.05); assert.equal(step.arrived, false);
});

test('diagonal motion normalizes the direction', () => {
  const result = advanceTowards({ x: 0, y: 0, z: 0 }, { x: 3, y: 4, z: 0 }, 2, 1);
  near(result.position.x, 1.2); near(result.position.y, 1.6); near(result.moved, 2);
});

test('large delta clamps at target and counts only consumed motion time', () => {
  const step = advanceTowards(origin, target, 0.5, 100);
  assert.deepEqual(step.position, target); assert.equal(step.arrived, true); near(step.usedSeconds, 4);
});

test('already at target never divides by zero', () => {
  const step = advanceTowards(target, target, 0.5, 0);
  assert.equal(step.arrived, true); assert.equal(step.usedSeconds, 0); assert.deepEqual(step.position, target);
});

test('zero delta cannot move a nonzero distance', () => {
  assert.deepEqual(advanceTowards(origin, target, 1, 0).position, origin);
});

test('invalid coordinates, speed and delta are rejected', () => {
  for (const speed of [0, -1, NaN, Infinity]) assert.throws(() => advanceTowards(origin, target, speed, 1));
  for (const delta of [-1, NaN, Infinity]) assert.throws(() => advanceTowards(origin, target, 1, delta));
  for (const point of [{}, { x: '1', y: 0, z: 0 }, { x: NaN, y: 0, z: 0 }]) assert.throws(() => advanceTowards(point, target, 1, 1));
});

test('overflowing distance is rejected', () => {
  assert.throws(() => advanceTowards({ x: -1e308, y: 0, z: 0 }, { x: 1e308, y: 0, z: 0 }, 1, 1));
});

test('30, 60 and 144 fps cover the same distance over two seconds', () => {
  for (const fps of [30, 60, 144]) {
    let position = { x: 0, y: 0, z: 0 };
    for (let frame = 0; frame < fps * 2; frame++) position = advanceTowards(position, { x: 100, y: 0, z: 0 }, 0.75, 1 / fps).position;
    near(position.x, 1.5);
  }
});

test('irregular frame timing still preserves speed', () => {
  const deltas = [0.01, 0.043, 0.016, 0.07, 0.021];
  let position = { ...origin };
  for (const dt of deltas) position = advanceTowards(position, target, 0.5, dt).position;
  near(distance(position, origin), 0.5 * deltas.reduce((a, b) => a + b, 0));
});

test('busy engine rejects silently overwriting the active command', () => {
  const engine = new MotionEngine(origin); engine.start(command());
  assert.throws(() => engine.start({ ...command(), command_id: 'another' }));
});

test('pause freezes position and excludes paused time', () => {
  const engine = new MotionEngine(origin); engine.start(command()); engine.tick(1);
  engine.pause(); engine.tick(50); near(engine.position.x, 0.5); near(engine.elapsed, 1);
  engine.resume(); engine.tick(1); near(engine.position.x, 1); near(engine.elapsed, 2);
});

test('manual and hidden pause reasons are independent', () => {
  const engine = new MotionEngine(origin); engine.start(command());
  engine.pause('manual'); engine.pause('hidden'); engine.resume('hidden');
  assert.equal(engine.phase, 'paused'); engine.tick(10); assert.deepEqual(engine.position, origin);
  engine.resume('manual'); assert.equal(engine.phase, 'moving');
});

test('stop preserves position and cannot continue advancing', () => {
  const engine = new MotionEngine(origin); engine.start(command()); engine.tick(1); engine.cancel(); engine.tick(20);
  assert.equal(engine.phase, 'cancelled'); near(engine.position.x, 0.5);
});

test('reset clears command and sets a new start', () => {
  const engine = new MotionEngine(origin); engine.start(command()); engine.cancel(); engine.reset(target);
  assert.equal(engine.command, null); assert.equal(engine.phase, 'idle'); assert.deepEqual(engine.position, target);
});

test('zero length command completes with zero motion time', () => {
  const engine = new MotionEngine(origin); engine.start({ ...command(), target: origin }); engine.tick(0);
  assert.equal(engine.phase, 'arrived'); assert.equal(engine.snapshot().progress, 1); near(engine.elapsed, 0);
});

test('final position and total motion time remain exact after overshooting frame', () => {
  const engine = new MotionEngine(origin); engine.start(command());
  for (let frame = 0; frame < 100; frame++) engine.tick(0.07);
  assert.equal(engine.phase, 'arrived'); assert.deepEqual(engine.position, target); near(engine.elapsed, 4);
});

test('caller objects are not mutated or retained by reference', () => {
  const start = { ...origin }, request = command();
  const engine = new MotionEngine(start); engine.start(request); request.target.x = 999;
  engine.tick(1); assert.deepEqual(start, origin); near(engine.position.x, 0.5); assert.equal(engine.command.target.x, 2);
});
