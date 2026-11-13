import * as THREE from 'three';
import { OrbitControls } from './vendor/three/OrbitControls.js';

// 此文件只负责显示；运动位置由独立的 MotionEngine 计算。
export function createScene(canvas) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setClearColor(0xf4f7fb);
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(43, 1, 0.01, 1000);
  const controls = new OrbitControls(camera, canvas);
  controls.enableDamping = true;
  controls.maxPolarAngle = Math.PI * 0.49;
  controls.minDistance = 1.5;

  scene.add(new THREE.HemisphereLight(0xffffff, 0x9baec9, 2.5));
  const light = new THREE.DirectionalLight(0xffffff, 3.0);
  light.position.set(4, 8, 5);
  light.castShadow = true;
  light.shadow.mapSize.set(1024, 1024);
  light.shadow.camera.left = light.shadow.camera.bottom = -8;
  light.shadow.camera.right = light.shadow.camera.top = 8;
  scene.add(light);
  const plane = new THREE.Mesh(new THREE.PlaneGeometry(200, 200),
    new THREE.MeshStandardMaterial({ color: 0xf4f7fb, roughness: 1 }));
  plane.rotation.x = -Math.PI / 2;
  plane.position.y = -0.012;
  plane.receiveShadow = true;
  scene.add(plane);
  const grid = new THREE.GridHelper(20, 40, 0xa5b4ce, 0xdce4ef);
  grid.material.transparent = true;
  grid.material.opacity = 0.65;
  scene.add(grid);

  const cube = new THREE.Mesh(new THREE.BoxGeometry(0.4, 0.4, 0.4),
    new THREE.MeshStandardMaterial({ color: 0xf29242, roughness: 0.38, metalness: 0.06 }));
  cube.castShadow = true;
  cube.receiveShadow = true;
  cube.position.set(0, 0.2, 0);
  scene.add(cube);
  const edges = new THREE.LineSegments(new THREE.EdgesGeometry(cube.geometry),
    new THREE.LineBasicMaterial({ color: 0xb75f21, transparent: true, opacity: 0.45 }));
  cube.add(edges);
  const targetMarker = new THREE.Mesh(new THREE.SphereGeometry(0.075, 20, 12),
    new THREE.MeshBasicMaterial({ color: 0x3b65df, transparent: true, opacity: 0.8 }));
  targetMarker.visible = false;
  scene.add(targetMarker);
  const routeGroup = new THREE.Group();
  scene.add(routeGroup);
  const trailGeometry = new THREE.BufferGeometry();
  // 预分配缓冲区；当前 Three.js 的 setFromPoints 不会自动扩容已有属性。
  const trailPositions = new THREE.BufferAttribute(new Float32Array(2000 * 3), 3);
  trailPositions.setUsage(THREE.DynamicDrawUsage);
  trailGeometry.setAttribute('position', trailPositions);
  trailGeometry.setDrawRange(0, 0);
  const trail = new THREE.Line(trailGeometry, new THREE.LineBasicMaterial({ color: 0x27a598 }));
  trail.frustumCulled = false;
  scene.add(trail);
  let trailPoints = [];
  let routePoints = [{ x: 0, y: 0.2, z: 0 }];

  function vector(point) { return new THREE.Vector3(point.x, point.y, point.z); }

  function fitCamera() {
    const bounds = new THREE.Box3().setFromPoints(routePoints.map(vector));
    const center = bounds.getCenter(new THREE.Vector3());
    const span = Math.max(bounds.getSize(new THREE.Vector3()).length(), 3.0);
    camera.position.copy(center).add(new THREE.Vector3(span * 0.95, span * 0.95, span * 1.2));
    controls.target.copy(center);
    controls.maxDistance = span * 8;
    camera.far = Math.max(1000, span * 20);
    camera.updateProjectionMatrix();
    controls.update();
  }

  function label(text, position) {
    const surface = document.createElement('canvas');
    surface.width = surface.height = 128;
    const ctx = surface.getContext('2d');
    ctx.fillStyle = '#ffffff';
    ctx.beginPath(); ctx.arc(64, 64, 41, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = '#c5d0e2'; ctx.lineWidth = 3; ctx.stroke();
    ctx.fillStyle = '#425572'; ctx.font = '500 46px sans-serif'; ctx.textAlign = 'center';
    ctx.textBaseline = 'middle'; ctx.fillText(text, 64, 65);
    const texture = new THREE.CanvasTexture(surface);
    const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture, depthTest: false }));
    sprite.position.copy(vector(position)).add(new THREE.Vector3(0, 0.33, 0));
    sprite.scale.set(0.38, 0.38, 0.38);
    routeGroup.add(sprite);
  }

  function clearRoute() {
    for (const child of [...routeGroup.children]) {
      child.geometry?.dispose();
      child.material?.map?.dispose();
      child.material?.dispose();
      routeGroup.remove(child);
    }
  }

  function setRoute(route) {
    clearRoute();
    routePoints = [route.initial_position, ...route.segments.map(segment => segment.target)];
    const geometry = new THREE.BufferGeometry().setFromPoints(routePoints.map(vector));
    const line = new THREE.Line(geometry, new THREE.LineDashedMaterial({ color: 0x7892d7, dashSize: 0.11, gapSize: 0.065 }));
    line.computeLineDistances(); routeGroup.add(line);
    routePoints.forEach((position, index) => {
      const dot = new THREE.Mesh(new THREE.SphereGeometry(0.045, 12, 8), new THREE.MeshBasicMaterial({ color: 0x6481ca }));
      dot.position.copy(vector(position)); routeGroup.add(dot);
      // 闭合路径的末点与起点重合，避免两个编号标签叠在一起。
      if (index === routePoints.length - 1 && vector(position).distanceTo(vector(routePoints[0])) < 1e-6) return;
      label(String(index), position);
    });
    trailPoints = [];
    trailGeometry.setDrawRange(0, 0);
    targetMarker.visible = false;
    fitCamera();
  }

  function setPosition(position, record = false) {
    cube.position.copy(vector(position));
    if (record && (!trailPoints.length || trailPoints.at(-1).distanceTo(cube.position) > 0.025)) {
      trailPoints.push(cube.position.clone());
      if (trailPoints.length > 2000) trailPoints.shift();
      trailPoints.forEach((value, index) => trailPositions.setXYZ(index, value.x, value.y + 0.006, value.z));
      trailPositions.needsUpdate = true;
      trailGeometry.setDrawRange(0, trailPoints.length);
    }
  }

  const observer = new ResizeObserver(() => {
    const { width, height } = canvas.getBoundingClientRect();
    if (width < 1 || height < 1) return;
    renderer.setSize(width, height, false);
    camera.aspect = width / height; camera.updateProjectionMatrix();
  });
  observer.observe(canvas);
  fitCamera();
  return {
    setRoute, setPosition, resetCamera: fitCamera,
    setTarget(position) { targetMarker.visible = Boolean(position); if (position) targetMarker.position.copy(vector(position)); },
    render() { controls.update(); renderer.render(scene, camera); },
    dispose() { observer.disconnect(); controls.dispose(); renderer.dispose(); clearRoute(); },
  };
}
