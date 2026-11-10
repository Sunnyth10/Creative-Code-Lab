<p align="center"><img src="banner.svg" alt="Crazy Physics Playground" width="100%"></p>

<p align="center">
  <img alt="TypeScript" src="https://img.shields.io/badge/TypeScript-strict-3178c6?logo=typescript&logoColor=white">
  <img alt="Canvas 2D" src="https://img.shields.io/badge/Canvas-2D-ff6ec7">
  <img alt="Runtime dependencies" src="https://img.shields.io/badge/runtime%20deps-0-7dff9f">
  <img alt="Balls" src="https://img.shields.io/badge/balls-up%20to%20600-7df9ff">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-ffd166">
</p>

<p align="center"><b>A neon sandbox where hundreds of glowing balls collide, orbit gravity wells, get blasted across the screen and change colour on every hit.</b><br>Pure TypeScript + Canvas 2D. No framework, no physics library, no runtime dependencies.</p>

<p align="center"><img src="demo.svg" alt="Animated preview" width="720"></p>

## Visual demo

<video src="visual-demo.mp4" controls playsinline preload="metadata" width="720">
  Your browser cannot play the embedded video. [Open the visual demo](visual-demo.mp4).
</video>

---

## 📚 Table of contents

[About](#about) · [Visual demo](#visual-demo) · [Demo](#-demo) · [Features](#-features) · [Quick start](#-quick-start) · [Controls](#-controls) · [Tech stack](#-tech-stack) · [What you can learn](#-what-you-can-learn-from-this-project) · [How it works](#-how-it-works) · [Project layout](#-project-layout) · [Configuration](#-configuration) · [Troubleshooting](#-troubleshooting) · [Roadmap](#-roadmap) · [License](#-license)

## About

Crazy Physics Playground is a small, dependency-free physics sandbox built to explore collision response, force fields, and real-time canvas rendering.

## 🎬 Demo


| | |
|---|---|
| ▶️ **Play instantly** | Open [`preview.html`](preview.html), the self-contained version of the app. |
| 🎥 **Visual demo** | [Watch the screen recording](visual-demo.mp4). |
| 🖼️ **Animated preview** | The SVG above is a stylised preview, not a recording. |

<details>
<summary><b>🎥 How to record the demo video / GIF (20 to 30 seconds)</b></summary>

**Shot list**

1. 0–5 s: the page loads, balls tumble. Drag to spawn and attract a swarm.
2. 5–10 s: right-click drag to repel, then double-click to drop a gravity well.
3. 10–15 s: press **C** to cycle colour modes while balls collide.
4. 15–22 s: push **Gravity** negative so everything floats up, then slam it back.
5. 22–30 s: hit **Space** for a blast (shockwave ring), then **B** to spawn a burst.

**Recording**

- macOS: `Shift + Cmd + 5` → *Record Selected Portion*. Windows: `Win + G` (Xbox Game Bar). Cross-platform: [OBS Studio](https://obsproject.com/).
- Record the browser at about 1280×720 for clean text.

**Make a README-friendly GIF** (needs [ffmpeg](https://ffmpeg.org/)):

```bash
ffmpeg -i demo.mp4 -vf "fps=20,scale=800:-1:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse" demo.gif
```

Then replace the animated preview with `<img src="demo.gif" width="720">`, or paste your video link in the table above.

</details>

## ✨ Features

- 🎱 **Up to 600 balls** with mass-aware collisions: heavy balls shove light ones around
- ⚡ **Spatial-hash collision detection**: roughly O(n) instead of O(n²)
- ⏱️ **Fixed 120 Hz physics step**, so it behaves identically at 60, 120 or 144 fps
- 🕳️ **Gravity wells**: attracting (cyan) or repelling (pink), fading over time
- 💥 **Blast** with distance falloff and an expanding shockwave ring
- 🎨 **Three colour modes**: *Flow* (hues drift and shift on impact), *Speed* (blue → red), *Size*
- 🖐️ **Mouse, touch and pen** via pointer events
- 🪄 Motion trails, pause, live FPS counter, and a compact control bar with a shortcuts dropdown

## 🚀 Quick start

### Requirements

| Need | Version | Why |
|---|---|---|
| A modern browser | Chrome, Edge, Firefox, Safari (any current version) | Canvas 2D + ES modules |
| **Just to play** | nothing else | open `preview.html` |
| Node.js *(only to build or serve)* | 18 or newer | runs TypeScript and a local server |

### Option A: just play (no install)

Open **`preview.html`** in your browser. It is the whole app inlined into one file.

### Option B: run the full project

```bash
npm install        # installs TypeScript (dev only)
npm run build      # compiles main.ts -> main.js
npm run serve      # http://localhost:8080
```

> `index.html` loads `main.js` as an ES module, so it must be served over HTTP. Double-clicking it will not work (`npm run serve` handles this). The compiled `main.js` is committed, so you can also skip `npm install` and run `npx http-server .` directly.

Use `npm run watch` to recompile automatically while you edit.

### 🌍 Deploy for free

Push this project to a GitHub repository, then enable Pages in the repository settings to publish the static app.

## 🎮 Controls

| Input | Action |
|---|---|
| **Drag** | Spawn balls and attract them |
| **Right-click drag** / **Shift + drag** | Repel |
| **Double-click** or **W** | Drop a gravity well at the cursor |
| **Shift + double-click** / **Shift + W** | Drop a repelling well |
| **Space** | Blast from the cursor |
| **B** | Burst of 40 balls at the cursor |
| **C** | Cycle colour mode (Flow / Speed / Size) |
| **T** | Toggle trails |
| **P** | Pause / resume |
| **R** | Reset |

**Sliders:** **Gravity** (negative floats upward) · **Bounce** (above 1.0 adds energy on wall hits) · **Chaos** (wobbly wind, and the strength of pulls, wells and blasts). Double-click any slider to reset it.

The **Blast** button explodes from the screen centre; the **Space** key explodes from your cursor.

## 🧰 Tech stack

| Layer | Choice | Notes |
|---|---|---|
| Language | **TypeScript 5** (strict mode) | the only dev dependency |
| Rendering | **HTML5 Canvas 2D** | additive blending (`lighter`) for the glow |
| Physics | **Hand-written Verlet engine** | no physics library |
| Spatial index | **Uniform grid / spatial hash** | typed arrays, no allocations per frame |
| Input | **Pointer Events API** | one code path for mouse, touch and pen |
| UI | **Plain HTML + CSS** | custom range sliders, glassmorphism, CSS variables |
| Build | `tsc` | compiles to ES2020 modules |
| Dev server | `http-server` via `npx` | optional |
| Runtime deps | **none** | |

## 🎓 What you can learn from this project

Each topic points to the place in `main.ts` to read first.

| Concept | Where to look | What it teaches |
|---|---|---|
| **Verlet integration** | `integrate()` | velocity is implicit (`pos − prevPos`), which makes constraints and collisions stable |
| **Fixed timestep + accumulator** | `frame()` | decoupling physics from rendering; why variable `dt` breaks simulations |
| **Spatial hashing** | `collideBalls()` | turning O(n²) into ~O(n) with a grid and linked lists in typed arrays |
| **Impulse-based collisions** | `resolve()` | mass-weighted separation, restitution, relative velocity along the normal |
| **Force fields** | `applyForces()` | inverse-square attractors with softening so they never blow up |
| **Speed limiting** | `collideWalls()` | keeping a chaotic system numerically stable |
| **Pointer Events** | input section | unified mouse/touch/pen handling, pointer capture, preventing context menus |
| **Canvas tricks** | `draw()` | trail effect via translucent clears, additive glow, HiDPI scaling with `devicePixelRatio` |
| **Allocation-free hot loops** | whole file | reusing arrays and typed arrays to avoid GC hitches |
| **TypeScript in the browser** | `tsconfig.json` | strict typing, ES modules, a zero-bundler setup |
| **CSS craft** | `style.css` | custom range inputs, backdrop blur, CSS Grid/Flex layout, `<details>` popovers with no JS |

**Try these experiments to learn faster**

1. Set `STEP` to `1/30` and watch the simulation fall apart. Then you know why fixed, small steps matter.
2. Remove the `+ 300` softening in the well force and see what happens when a ball passes through the centre.
3. Swap the spatial hash for a double `for` loop and compare the FPS at 600 balls.
4. Make `m` constant instead of `r * r` and see how collisions feel without mass.
5. Try drag (`damp`) values of `1.0`, `0.998` and `0.98`.

## 🧠 How it works

```
requestAnimationFrame
        │
        ▼
 accumulate real dt ──► while (acc ≥ STEP) {          // STEP = 1/120 s
                            applyForces()    gravity, chaos wind, mouse, wells
                            integrate()      Verlet: x += (x − prevX)·damp + a·dt²
                            collideBalls()   spatial hash → impulse resolve
                            collideWalls()   bounce + speed limit
                        }
        │
        ▼
      draw()   translucent clear (trails) → wells → shockwaves → additive-blended balls
```

1. **Verlet integration**: each ball stores its current and previous position; velocity is the difference.
2. **Fixed timestep**: physics always advances in 1/120 s steps; slow frames are capped instead of spiralling.
3. **Spatial hash**: balls are bucketed into 48 px cells; only neighbouring cells are tested for overlaps.
4. **Collisions**: balls are pushed apart in proportion to the other ball's mass, then an impulse along the contact normal applies restitution. Every hit also shifts both balls' hues and makes them flash.
5. **Rendering**: a translucent rectangle each frame leaves trails; `globalCompositeOperation = "lighter"` makes overlapping balls glow.

## 🗂️ Project layout

```
index.html       page + control bar
style.css        neon UI styling
main.ts          source code (edit this)
main.js          compiled output (generated by `npm run build`)
preview.html     everything inlined: open this to play instantly
banner.svg       README banner
demo.svg         animated README preview
tsconfig.json    strict TypeScript config
developer.md     detailed architecture and contribution guide
package.json     scripts + metadata
LICENSE          MIT
```

## 🔧 Configuration

Tweak the constants at the top of `main.ts`, then run `npm run build`:

| Constant | Default | Effect |
|---|---|---|
| `MAX_BALLS` | 600 | ball cap (try 1000 on a fast machine) |
| `STEP` | 1/120 | physics step; smaller is more accurate but costs more CPU |
| `MAX_V` | 20 | speed limit per step (px) |
| `CELL` | 48 | grid cell size; keep it at least the largest ball diameter |
| `WELL_LIFE` | 420 | how long gravity wells last |
| `WAVE_LIFE` | 40 | how long the blast shockwave ring lasts |

## 🩹 Troubleshooting

| Problem | Fix |
|---|---|
| Blank page when opening `index.html` | Browsers block ES modules from `file://`. Use `npm run serve`, or open `preview.html` |
| `main.js` not found / old behaviour | Run `npm run build` after editing `main.ts` |
| Low FPS | Lower `MAX_BALLS`, turn off trails (**T**), or close other heavy tabs |
| Balls pile up at the bottom | Gravity is high, so lower it or drag the slider negative and press **Space** |
| Touch device scrolls the page | The canvas uses `touch-action: none`; make sure your own CSS doesn't override it |

## 🗺️ Roadmap

- [ ] Obstacles and bumpers (draw walls with the mouse)
- [ ] Springs and ropes between balls
- [ ] Black holes that swallow and re-emit balls
- [ ] Save and share scenes as a URL
- [ ] GIF / WebM recording button
- [ ] Slow-motion and time-scale slider
- [ ] Optional sound effects

## 🤝 Contributing

Ideas and pull requests are welcome. Fork, create a branch, run `npm run build`, make sure it type-checks with no errors, and open a PR with a short GIF of the change.

## 📄 License

[MIT](LICENSE)

---

<p align="center">Made for fun. Break the physics. 🌌</p>
