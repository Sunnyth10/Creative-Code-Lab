"use strict";
const MAX_BALLS = 600;
const WELL_LIFE = 420;
const STEP = 1 / 120; // fixed physics step (seconds)
const MAX_V = 20; // max displacement per step (px)
const CELL = 48; // spatial-hash cell size (>= largest ball diameter)
const $ = (id) => document.getElementById(id);
const canvas = $("c");
const ctx = canvas.getContext("2d");
const gInput = $("g");
const bInput = $("b");
const chInput = $("ch");
const stats = $("stats");
const panel = $("ui");
let W = 0, H = 0;
const DPR = Math.max(1, Math.min(2, window.devicePixelRatio || 1));
let balls = [];
let wells = [];
const mouse = { x: -1, y: -1, px: -1, py: -1, down: false, repel: false, inside: false };
let colorMode = 0;
let waves = [];
const WAVE_LIFE = 40;
const MODES = ["Flow", "Speed", "Size"];
let hueBase = 180, simT = 0, paused = false, trails = true;
let head = new Int32Array(0), next = new Int32Array(MAX_BALLS), cols = 0, rows = 0;
function resize() {
    W = window.innerWidth;
    H = window.innerHeight;
    canvas.width = Math.floor(W * DPR);
    canvas.height = Math.floor(H * DPR);
    canvas.style.width = W + "px";
    canvas.style.height = H + "px";
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    cols = Math.ceil(W / CELL) + 1;
    rows = Math.ceil(H / CELL) + 1;
    head = new Int32Array(cols * rows);
}
window.addEventListener("resize", resize);
resize();
const rand = (a, b) => a + Math.random() * (b - a);
function onHit(a, b, imp) {
    const s = Math.min(1, imp / 8), shift = imp * 9;
    a.hue = (a.hue + shift) % 360;
    b.hue = (b.hue - shift + 360) % 360; // colour shifts on impact
    a.flash = Math.max(a.flash, s);
    b.flash = Math.max(b.flash, s);
}
/** vx/vy are in px per 60fps-frame (kept from the original API). */
function addBall(x, y, vx = rand(-2, 2), vy = rand(-2, 2), r = rand(5, 22)) {
    if (balls.length >= MAX_BALLS)
        balls.shift();
    balls.push({
        x, y, px: x - vx * 0.5, py: y - vy * 0.5, ax: 0, ay: 0, r, m: r * r,
        hue: (hueBase + rand(-40, 40) + 360) % 360, flash: 0,
    });
}
function seed(n = 90) {
    balls = [];
    wells = [];
    waves = [];
    for (let i = 0; i < n; i++)
        addBall(rand(40, W - 40), rand(40, H - 40), rand(-3, 3), rand(-3, 3));
}
seed();
function addWell(x, y, repel = false) {
    wells.push({ x, y, t: WELL_LIFE, repel });
    for (let i = 0; i < 24; i++) {
        const a = (i / 24) * Math.PI * 2;
        addBall(x, y, Math.cos(a) * rand(1, 5), Math.sin(a) * rand(1, 5), rand(4, 12));
    }
}
function explode(cx, cy) {
    const power = 0.5 + Number(chInput.value) * 0.5;
    for (const b of balls) {
        const dx = b.x - cx, dy = b.y - cy;
        const d = Math.hypot(dx, dy) || 1;
        const dv = (16 * power * Math.exp(-d / 450)) / (1 + b.r / 40); // px/step, lighter balls fly further
        const ux = d > 1 ? dx / d : Math.cos(rand(0, 6.28)), uy = d > 1 ? dy / d : Math.sin(rand(0, 6.28));
        b.px -= ux * dv;
        b.py -= uy * dv;
        b.flash = 1;
    }
    waves.push({ x: cx, y: cy, t: WAVE_LIFE });
    hueBase = (hueBase + 47) % 360;
}
function setPaused(p) { paused = p; $("pause").textContent = p ? "Resume" : "Pause"; }
function setColor(m) { colorMode = m % MODES.length; $("color").textContent = "Colour: " + MODES[colorMode]; }
function setTrails(t) { trails = t; $("trails").textContent = "Trails: " + (t ? "on" : "off"); }
// ---------- Input (pointer events: mouse + touch + pen) ----------
canvas.addEventListener("contextmenu", (e) => e.preventDefault());
canvas.addEventListener("pointermove", (e) => {
    mouse.px = mouse.inside ? mouse.x : e.clientX;
    mouse.py = mouse.inside ? mouse.y : e.clientY;
    mouse.x = e.clientX;
    mouse.y = e.clientY;
    mouse.inside = true;
    if (mouse.down && !mouse.repel) {
        for (let i = 0; i < 2; i++)
            addBall(mouse.x + rand(-6, 6), mouse.y + rand(-6, 6), (mouse.x - mouse.px) * 0.25 + rand(-1.5, 1.5), (mouse.y - mouse.py) * 0.25 + rand(-1.5, 1.5), rand(3, 10));
    }
});
canvas.addEventListener("pointerdown", (e) => {
    canvas.setPointerCapture(e.pointerId);
    mouse.x = mouse.px = e.clientX;
    mouse.y = mouse.py = e.clientY;
    mouse.inside = true;
    mouse.down = true;
    mouse.repel = e.button === 2 || e.shiftKey;
});
const release = () => { mouse.down = false; };
canvas.addEventListener("pointerup", release);
canvas.addEventListener("pointercancel", release);
canvas.addEventListener("pointerleave", (e) => { if (e.pointerType === "mouse")
    mouse.inside = false; });
canvas.addEventListener("dblclick", (e) => addWell(e.clientX, e.clientY, e.shiftKey));
window.addEventListener("keydown", (e) => {
    if (e.target instanceof HTMLInputElement)
        return;
    const cx = mouse.inside ? mouse.x : W / 2, cy = mouse.inside ? mouse.y : H / 2;
    switch (e.key.toLowerCase()) {
        case " ":
            e.preventDefault();
            explode(cx, cy);
            break;
        case "r":
            seed();
            break;
        case "p":
            setPaused(!paused);
            break;
        case "t":
            setTrails(!trails);
            break;
        case "c":
            setColor(colorMode + 1);
            break;
        case "w":
            addWell(cx, cy, e.shiftKey);
            break;
        case "b":
            for (let i = 0; i < 40; i++)
                addBall(cx + rand(-20, 20), cy + rand(-20, 20), rand(-6, 6), rand(-6, 6));
            break;
    }
});
$("pause").addEventListener("click", () => setPaused(!paused));
$("color").addEventListener("click", () => setColor(colorMode + 1));
$("trails").addEventListener("click", () => setTrails(!trails));
$("reset").addEventListener("click", () => seed());
$("burst").addEventListener("click", (e) => { explode(W / 2, H / 2); e.currentTarget.blur(); });
$("fold").addEventListener("click", () => {
    const c = panel.classList.toggle("collapsed");
    $("fold").textContent = c ? "+" : "–";
});
// ---------- Physics ----------
function applyForces() {
    const g = Number(gInput.value) * 1200;
    const chaos = Number(chInput.value);
    const tA = simT * 20, tB = simT * 17;
    const pull = mouse.down && mouse.inside;
    const sign = mouse.repel ? -1 : 1;
    for (const b of balls) {
        b.ax = Math.sin((b.y + tA) * 0.01) * 40 * chaos;
        b.ay = g + Math.cos((b.x + tB) * 0.01) * 25 * chaos;
        if (pull) {
            const dx = mouse.x - b.x, dy = mouse.y - b.y;
            const f = (sign * 180000 * chaos) / (dx * dx + dy * dy + 600);
            b.ax += dx * f;
            b.ay += dy * f;
        }
        for (const w of wells) {
            const dx = w.x - b.x, dy = w.y - b.y;
            const f = ((w.repel ? -1 : 1) * 260000 * (w.t / WELL_LIFE) * chaos) / (dx * dx + dy * dy + 300);
            b.ax += dx * f;
            b.ay += dy * f;
        }
    }
    for (let i = waves.length - 1; i >= 0; i--) {
        waves[i].t -= STEP * 60;
        if (waves[i].t <= 0)
            waves.splice(i, 1);
    }
    for (let i = wells.length - 1; i >= 0; i--) {
        wells[i].t -= STEP * 60;
        if (wells[i].t <= 0)
            wells.splice(i, 1);
    }
}
function integrate() {
    const damp = 0.998, dt2 = STEP * STEP;
    for (const b of balls) {
        const vx = (b.x - b.px) * damp, vy = (b.y - b.py) * damp;
        b.hue = (b.hue + 10 * STEP) % 360;
        b.flash *= 0.985;
        b.px = b.x;
        b.py = b.y;
        b.x += vx + b.ax * dt2;
        b.y += vy + b.ay * dt2;
    }
}
function collideWalls() {
    const bounce = Number(bInput.value);
    for (const b of balls) {
        let vx = b.x - b.px, vy = b.y - b.py;
        if (b.x - b.r < 0) {
            b.x = b.r;
            b.px = b.x + vx * bounce;
        }
        else if (b.x + b.r > W) {
            b.x = W - b.r;
            b.px = b.x + vx * bounce;
        }
        if (b.y - b.r < 0) {
            b.y = b.r;
            b.py = b.y + vy * bounce;
        }
        else if (b.y + b.r > H) {
            b.y = H - b.r;
            b.py = b.y + vy * bounce;
        }
        vx = b.x - b.px;
        vy = b.y - b.py;
        const s = Math.hypot(vx, vy);
        if (s > MAX_V) {
            b.px = b.x - (vx / s) * MAX_V;
            b.py = b.y - (vy / s) * MAX_V;
        }
    }
}
function resolve(a, b, e) {
    let dx = b.x - a.x, dy = b.y - a.y;
    let dist = Math.hypot(dx, dy);
    const min = a.r + b.r;
    if (dist >= min)
        return;
    if (dist < 0.001) {
        dx = rand(-1, 1);
        dy = rand(-1, 1);
        dist = Math.hypot(dx, dy) || 1;
    }
    const nx = dx / dist, ny = dy / dist, inv = 1 / (a.m + b.m);
    const overlap = min - dist;
    a.x -= nx * overlap * b.m * inv;
    a.y -= ny * overlap * b.m * inv; // lighter ball moves more
    b.x += nx * overlap * a.m * inv;
    b.y += ny * overlap * a.m * inv;
    const vn = ((b.x - b.px) - (a.x - a.px)) * nx + ((b.y - b.py) - (a.y - a.py)) * ny;
    if (vn < 0) {
        const j = (-(1 + e) * vn) / (1 / a.m + 1 / b.m);
        a.px += (nx * j) / a.m;
        a.py += (ny * j) / a.m;
        b.px -= (nx * j) / b.m;
        b.py -= (ny * j) / b.m;
        onHit(a, b, -vn);
    }
}
/** Spatial hash: ~O(n) instead of O(n²) pair checks. */
function collideBalls() {
    const e = Math.min(1, Number(bInput.value)) * 0.92;
    head.fill(-1);
    const n = balls.length;
    for (let i = 0; i < n; i++) {
        const b = balls[i];
        const cx = Math.min(cols - 1, Math.max(0, (b.x / CELL) | 0));
        const cy = Math.min(rows - 1, Math.max(0, (b.y / CELL) | 0));
        const c = cy * cols + cx;
        next[i] = head[c];
        head[c] = i;
    }
    for (let cy = 0; cy < rows; cy++) {
        for (let cx = 0; cx < cols; cx++) {
            for (let i = head[cy * cols + cx]; i !== -1; i = next[i]) {
                for (let oy = 0; oy <= 1; oy++) {
                    for (let ox = -1; ox <= 1; ox++) {
                        if (oy === 0 && ox < 0)
                            continue; // forward neighbours only
                        const nx = cx + ox, ny = cy + oy;
                        if (nx < 0 || nx >= cols || ny >= rows)
                            continue;
                        let j = head[ny * cols + nx];
                        if (ox === 0 && oy === 0)
                            j = next[i]; // same cell: only later entries
                        for (; j !== -1; j = next[j])
                            resolve(balls[i], balls[j], e);
                    }
                }
            }
        }
    }
}
// ---------- Rendering ----------
function draw() {
    ctx.globalCompositeOperation = "source-over";
    ctx.fillStyle = trails ? "rgba(7, 8, 22, 0.22)" : "rgb(7, 8, 22)";
    ctx.fillRect(0, 0, W, H);
    for (const w of wells) {
        const k = w.t / WELL_LIFE, r = 30 + (1 - k) * 120;
        const rgb = w.repel ? "255,110,199" : "125,249,255";
        const g = ctx.createRadialGradient(w.x, w.y, 0, w.x, w.y, r);
        g.addColorStop(0, `rgba(${rgb},${0.22 * k})`);
        g.addColorStop(1, `rgba(${rgb},0)`);
        ctx.fillStyle = g;
        ctx.beginPath();
        ctx.arc(w.x, w.y, r, 0, Math.PI * 2);
        ctx.fill();
    }
    for (const w of waves) {
        const k = w.t / WAVE_LIFE, r = 20 + (1 - k) * Math.max(W, H) * 0.7;
        ctx.strokeStyle = `rgba(255,255,255,${0.6 * k})`;
        ctx.lineWidth = 2 + 8 * k;
        ctx.beginPath();
        ctx.arc(w.x, w.y, r, 0, Math.PI * 2);
        ctx.stroke();
    }
    ctx.globalCompositeOperation = "lighter";
    for (const b of balls) {
        const v = Math.hypot(b.x - b.px, b.y - b.py) * 2; // px per 60fps frame
        const h = colorMode === 1 ? 240 - Math.min(1, v / 8) * 240 : colorMode === 2 ? ((b.r - 3) / 19) * 300 : b.hue;
        ctx.fillStyle = `hsla(${h} 95% 62% / ${Math.min(1, 0.18 + v * 0.04 + b.flash * 0.5)})`;
        ctx.beginPath();
        ctx.arc(b.x, b.y, b.r + Math.min(14, v * 1.2 + b.flash * 8), 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = `hsla(${h} 100% ${72 + b.flash * 22} / 0.95)`;
        ctx.beginPath();
        ctx.arc(b.x, b.y, b.r, 0, Math.PI * 2);
        ctx.fill();
    }
    ctx.globalCompositeOperation = "source-over";
}
// ---------- Main loop ----------
let tPrev = performance.now(), acc = 0, fps = 60, statT = 0;
function frame(now) {
    const dt = Math.min(0.05, Math.max(0.0001, (now - tPrev) / 1000));
    tPrev = now;
    fps += (1 / dt - fps) * 0.05;
    if (!paused) {
        acc += dt;
        for (let s = 0; acc >= STEP && s < 6; s++, acc -= STEP) {
            applyForces();
            integrate();
            collideBalls();
            collideWalls();
            simT += STEP;
        }
        if (acc > STEP)
            acc = 0; // drop backlog instead of spiralling
    }
    draw();
    if (now - statT > 250) {
        statT = now;
        stats.textContent = `balls ${balls.length}/${MAX_BALLS} · wells ${wells.length} · ${fps.toFixed(0)} fps${paused ? " · paused" : ""}`;
    }
    requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
