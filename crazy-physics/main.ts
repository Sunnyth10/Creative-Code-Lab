type Vec = { x: number; y: number };

type Ball = {
  x: number; y: number;
  px: number; py: number;
  ax: number; ay: number;
  r: number;
  m: number;
  hue: number;
  life: number;
};

const canvas = document.getElementById("c") as HTMLCanvasElement;
const ctx = canvas.getContext("2d")!;
const gInput = document.getElementById("g") as HTMLInputElement;
const bInput = document.getElementById("b") as HTMLInputElement;
const chInput = document.getElementById("ch") as HTMLInputElement;
const stats = document.getElementById("stats")!;

let W = 0, H = 0, DPR = Math.max(1, Math.min(2, window.devicePixelRatio || 1));
let balls: Ball[] = [];
let wells: { x: number; y: number; t: number }[] = [];
let mouse: Vec & { down: boolean; px: number; py: number } = { x: 0, y: 0, px: 0, py: 0, down: false };
let tPrev = performance.now();
let hueBase = 180;

function resize() {
  W = Math.floor(window.innerWidth);
  H = Math.floor(window.innerHeight);
  canvas.width = Math.floor(W * DPR);
  canvas.height = Math.floor(H * DPR);
  canvas.style.width = W + "px";
  canvas.style.height = H + "px";
  ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
}
window.addEventListener("resize", resize);
resize();

function rand(a: number, b: number) { return a + Math.random() * (b - a); }

function addBall(x: number, y: number, vx = rand(-2, 2), vy = rand(-2, 2), r = rand(5, 22)): void {
  balls.push({
    x, y,
    px: x - vx,
    py: y - vy,
    ax: 0, ay: 0,
    r,
    m: r * r,
    hue: (hueBase + rand(-40, 40) + 360) % 360,
    life: rand(0.8, 1.4),
  });
  if (balls.length > 220) balls.splice(0, balls.length - 220);
}

function seed(n = 90) {
  balls = [];
  wells = [];
  for (let i = 0; i < n; i++) addBall(rand(40, W - 40), rand(40, H - 40), rand(-3, 3), rand(-3, 3));
}
seed();

canvas.addEventListener("mousemove", (e) => {
  mouse.px = mouse.x; mouse.py = mouse.y;
  mouse.x = e.clientX; mouse.y = e.clientY;
  if (mouse.down) {
    for (let i = 0; i < 2; i++) addBall(mouse.x + rand(-6, 6), mouse.y + rand(-6, 6), (mouse.x - mouse.px) * 0.25 + rand(-1.5, 1.5), (mouse.y - mouse.py) * 0.25 + rand(-1.5, 1.5), rand(3, 10));
  }
});
canvas.addEventListener("mousedown", () => { mouse.down = true; });
window.addEventListener("mouseup", () => { mouse.down = false; });
canvas.addEventListener("dblclick", (e) => {
  wells.push({ x: e.clientX, y: e.clientY, t: 420 });
  for (let i = 0; i < 24; i++) addBall(e.clientX, e.clientY, Math.cos(i) * rand(1, 5), Math.sin(i) * rand(1, 5), rand(4, 12));
});
window.addEventListener("keydown", (e) => {
  if (e.code === "Space") {
    e.preventDefault();
    const cx = mouse.x || W / 2, cy = mouse.y || H / 2;
    for (const b of balls) {
      const dx = b.x - cx, dy = b.y - cy;
      const d = Math.hypot(dx, dy) + 12;
      const f = (2200 * Number(chInput.value)) / d;
      b.px -= (dx / d) * f * 0.016;
      b.py -= (dy / d) * f * 0.016;
    }
    hueBase = (hueBase + 47) % 360;
  }
  if (e.key.toLowerCase() === "r") seed();
});

function applyForces(dt: number) {
  const g = Number(gInput.value) * 1200;
  const chaos = Number(chInput.value);
  for (const b of balls) {
    b.ax = 0; b.ay = g;
    b.ax += Math.sin((b.y + performance.now() * 0.02) * 0.01) * 40 * chaos;
    b.ay += Math.cos((b.x + performance.now() * 0.017) * 0.01) * 25 * chaos;
    if (mouse.down) {
      const dx = mouse.x - b.x, dy = mouse.y - b.y;
      const d2 = dx * dx + dy * dy + 600;
      const f = (180000 * chaos) / d2;
      b.ax += dx * f; b.ay += dy * f;
    }
    for (const w of wells) {
      const dx = w.x - b.x, dy = w.y - b.y;
      const d2 = dx * dx + dy * dy + 300;
      const f = (260000 * (w.t / 420) * chaos) / d2;
      b.ax += dx * f; b.ay += dy * f;
    }
  }
  wells = wells.map(w => ({ ...w, t: w.t - dt * 60 })).filter(w => w.t > 0);
}

function integrate(dt: number) {
  const damp = 0.996;
  for (const b of balls) {
    const vx = (b.x - b.px) * damp;
    const vy = (b.y - b.py) * damp;
    b.px = b.x;
    b.py = b.y;
    b.x += vx + b.ax * dt * dt;
    b.y += vy + b.ay * dt * dt;
  }
}

function collideWalls() {
  const bounce = Number(bInput.value);
  for (const b of balls) {
    let vx = b.x - b.px, vy = b.y - b.py;
    if (b.x - b.r < 0) { b.x = b.r; b.px = b.x + vx * bounce; }
    if (b.x + b.r > W) { b.x = W - b.r; b.px = b.x + vx * bounce; }
    if (b.y - b.r < 0) { b.y = b.r; b.py = b.y + vy * bounce; }
    if (b.y + b.r > H) { b.y = H - b.r; b.py = b.y + vy * bounce; }
    vx = b.x - b.px; vy = b.y - b.py;
    if (Math.abs(vx) > 40) b.px = b.x - Math.sign(vx) * 40;
    if (Math.abs(vy) > 40) b.py = b.y - Math.sign(vy) * 40;
  }
}

function collideBalls() {
  for (let i = 0; i < balls.length; i++) {
    for (let j = i + 1; j < balls.length; j++) {
      const a = balls[i], b = balls[j];
      let dx = b.x - a.x, dy = b.y - a.y;
      let dist = Math.hypot(dx, dy);
      const min = a.r + b.r;
      if (dist === 0 || dist >= min) continue;
      if (dist < 0.001) { dx = rand(-1, 1); dy = rand(-1, 1); dist = Math.hypot(dx, dy); }
      const nx = dx / dist, ny = dy / dist;
      const overlap = (min - dist) * 0.5;
      a.x -= nx * overlap; a.y -= ny * overlap;
      b.x += nx * overlap; b.y += ny * overlap;
      const rvx = (b.x - b.px) - (a.x - a.px);
      const rvy = (b.y - b.py) - (a.y - a.py);
      const vn = rvx * nx + rvy * ny;
      if (vn < 0) {
        const impulse = vn * 0.9;
        a.px -= nx * impulse; a.py -= ny * impulse;
        b.px += nx * impulse; b.py += ny * impulse;
      }
    }
  }
}

function draw() {
  ctx.fillStyle = "rgba(7, 8, 22, 0.22)";
  ctx.fillRect(0, 0, W, H);

  for (const w of wells) {
    const r = 30 + (1 - w.t / 420) * 120;
    const g = ctx.createRadialGradient(w.x, w.y, 0, w.x, w.y, r);
    g.addColorStop(0, `rgba(125,249,255,${0.18 * (w.t / 420)})`);
    g.addColorStop(1, "rgba(125,249,255,0)");
    ctx.fillStyle = g;
    ctx.beginPath(); ctx.arc(w.x, w.y, r, 0, Math.PI * 2); ctx.fill();
  }

  ctx.globalCompositeOperation = "lighter";
  for (const b of balls) {
    const v = Math.hypot(b.x - b.px, b.y - b.py);
    const glow = Math.min(1, 0.18 + v * 0.04);
    ctx.fillStyle = `hsla(${b.hue} 95% 62% / ${glow})`;
    ctx.beginPath();
    ctx.arc(b.x, b.y, b.r + Math.min(10, v * 1.2), 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = `hsla(${b.hue} 100% 72% / 0.95)`;
    ctx.beginPath();
    ctx.arc(b.x, b.y, b.r, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.globalCompositeOperation = "source-over";

  stats.textContent = `balls: ${balls.length} | wells: ${wells.length} | drag to attract/spawn | dbl-click well | space blast | R reset`;
}

function frame(now: number) {
  const dt = Math.min(0.033, Math.max(0.001, (now - tPrev) / 1000));
  tPrev = now;
  applyForces(dt);
  integrate(dt);
  for (let i = 0; i < 2; i++) { collideBalls(); collideWalls(); }
  draw();
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
