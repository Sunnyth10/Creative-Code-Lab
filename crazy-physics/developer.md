# Developer guide

This guide explains how the Crazy Physics Playground is structured and how to make changes without breaking the simulation, the standalone preview, or the compiled app.

## Project at a glance

The app is a browser-only Canvas 2D simulation. The runtime has no dependencies or bundler. TypeScript is the source, `tsc` compiles it to the JavaScript module loaded by `index.html`, and `preview.html` is a separate self-contained copy for quick play.

| File | Purpose |
|---|---|
| `index.html` | Main page structure and controls. Loads `style.css` and `main.js`. |
| `style.css` | Responsive control bar, sliders, buttons, stats, and visual styling. |
| `main.ts` | Authoritative TypeScript application and physics source. Edit this for app logic. |
| `main.js` | Compiled ES2020 JavaScript produced from `main.ts`. |
| `preview.html` | Standalone HTML with CSS and JavaScript inlined. It does not load the other app files. |
| `demo.svg` | Animated illustration shown in the README. It is not a recording of the simulation. |
| `visual-demo.mp4` | Compressed screen recording linked from the README. |
| `banner.svg` | README banner. |
| `README.md` | Project overview, quick start, controls, and learning notes. |
| `package.json` | Build, watch, and local server scripts. |
| `tsconfig.json` | Strict TypeScript compiler settings. |
| `LICENSE` | MIT license. |

## Set up and run

Use Node.js 18 or newer. From the project directory:

```bash
npm install
npm run build
npm run serve
```

Open the local address printed by the server, usually `http://localhost:8080`. The main page uses an ES module, so opening `index.html` directly with `file://` may be blocked by the browser. For a no-install preview, open `preview.html` directly.

During development, `npm run watch` keeps compiling `main.ts` as it changes. The TypeScript compiler writes `main.js` into the project root because `tsconfig.json` sets `outDir` to `.`.

## Runtime startup and data flow

`main.ts` starts by finding the canvas, its 2D context, the three range inputs, the stats area, and the control panel. It measures the viewport, configures the HiDPI canvas and collision grid, seeds 90 balls, registers input and button listeners, installs slider readouts, and starts the animation-frame loop.

Each rendered frame follows this flow:

```text
requestAnimationFrame
  ├─ clamp elapsed wall-clock time
  ├─ add elapsed time to the accumulator
  ├─ run up to six fixed physics steps
  │    ├─ apply gravity, wind, pointer force, and well forces
  │    ├─ integrate positions
  │    ├─ resolve ball collisions using the spatial hash
  │    └─ resolve wall collisions and cap speed
  ├─ draw wells, shockwaves, balls, and trails
  ├─ refresh stats about four times per second
  └─ request the next frame
```

Physics runs at `STEP = 1 / 120` seconds independently of the display refresh rate. The accumulator catches up after a slow frame, but runs no more than six steps in one frame. If it is still behind, the remaining backlog is dropped to prevent a long frame from causing an ever-growing update loop.

## Simulation model

### Balls and Verlet positions

A ball stores current position (`x`, `y`), previous position (`px`, `py`), acceleration (`ax`, `ay`), radius, mass, hue, and a short-lived impact flash. Its velocity is implicit: the displacement from the previous position to its current position represents motion. `integrate()` applies damping and acceleration, then moves the previous position forward.

Mass is `radius²`. Bigger balls therefore move less during collision separation and transfer momentum according to their mass. `addBall()` accepts initial velocity values in the legacy API's approximate pixels-per-60-fps-frame units and converts them into the 120 Hz position representation.

`MAX_BALLS` is 600. When adding a ball at capacity, the oldest array entry is removed before the new one is appended. The `next` typed array used by the spatial hash is sized to this cap.

### Forces

`applyForces()` rebuilds each ball's acceleration every physics step:

- **Gravity:** the Gravity slider value is multiplied by 1200 and added to vertical acceleration. Negative values pull upward.
- **Wind / Chaos:** two smooth sine and cosine fields vary by position and simulation time. Chaos scales their strength.
- **Pointer:** while the pointer is held down, a softened inverse-square force attracts balls. Right-click or Shift changes its sign and repels instead.
- **Gravity wells:** each well applies a softened inverse-square force. The force fades with the well's remaining lifetime. Shift-clicked wells repel.

The denominators include small softening constants so force does not become infinite when a ball is at the force centre. Setting Chaos to zero disables wind and pointer/well force strength; gravity remains controlled independently.

### Blasts, wells, and shockwaves

`explode()` changes each ball's previous position to add an outward displacement. The force falls off exponentially with distance and is slightly weaker for larger balls. A wave record is added for the expanding ring, and the base hue advances for subsequently created balls.

`addWell()` creates a finite-life attractor or repeller and spawns a ring of 24 small balls around it. Wells and waves age in simulation time, so they pause with the simulation. `WELL_LIFE` and `WAVE_LIFE` are counted in 60 Hz style ticks: the code subtracts `STEP * 60` on every 120 Hz step. This makes a 420-life well last about seven seconds and a 40-life wave about two-thirds of a second.

### Ball collisions and spatial hashing

`collideBalls()` assigns every ball to a uniform grid cell. Each cell has a linked list represented by two typed arrays:

- `head[cell]` points to the first ball index in that cell.
- `next[ballIndex]` points to the next ball in the same cell.

The simulation tests pairs within the same cell and a set of forward neighboring cells. This checks every nearby pair once and avoids testing every possible pair across the whole scene. `CELL` is 48 px. Keep it at least as large as the maximum ball diameter (currently 44 px for radius 22); otherwise collisions can cross more than one cell and be missed.

`resolve()` first separates overlapping balls in proportion to their masses. If they are moving toward one another along the contact normal, it applies an impulse using the selected restitution. Exact overlap is given a small random direction so the normal is defined. Successful impacts also shift both hues and increase their flash values.

Ball-to-ball restitution is `min(1, Bounce) * 0.92`, so it tops out below 1 even if the slider goes higher. Wall restitution uses the Bounce slider directly; values above 1 add energy on wall impacts. Wall collision also clamps displacement magnitude to `MAX_V`.

### Resizing and pixels

The simulation uses CSS pixel coordinates. The canvas backing store is multiplied by `DPR`, capped at 2 to limit memory use, while `ctx.setTransform()` keeps drawing coordinates in CSS pixels. Resizing also recreates the spatial hash grid dimensions. The current DPR is captured at startup.

## Rendering

`draw()` clears the canvas with a solid background when trails are off. With trails on, it paints a translucent background instead, so earlier frames fade gradually. Wells use radial gradients and shockwaves use stroked circles. Balls are drawn under additive (`lighter`) compositing: a larger, translucent glow is drawn first, then a bright solid core. The composite mode is reset to `source-over` at the end of the function.

The three color modes are selected by the Color button or **C**:

- **Flow:** each ball's hue drifts over time and shifts after collisions.
- **Speed:** hue maps from blue to red as the ball's displacement increases.
- **Size:** hue maps to radius.

The FPS display is a smoothed estimate based on the time between animation frames. Ball and well counts plus FPS are refreshed every 250 ms rather than on every frame.

## Input and controls

Canvas pointer events provide one input path for mouse, touch, and pen. Pointer capture keeps a drag active after the pointer leaves the canvas. A normal drag spawns small balls and attracts the existing ones; a right-button or Shift drag repels. Double-click adds an attracting well, and Shift + double-click adds a repelling well. The browser context menu is suppressed on the canvas so right-drag works.

Keyboard shortcuts use the pointer location when it is inside the canvas, or the viewport centre otherwise:

| Input | Action |
|---|---|
| Drag | Spawn balls and attract |
| Right-drag or Shift + drag | Repel |
| Double-click or **W** | Add an attracting well |
| Shift + double-click or Shift + **W** | Add a repelling well |
| **Space** | Blast at the pointer (or centre if outside) |
| **B** | Add 40 balls |
| **C** | Cycle Flow, Speed, and Size |
| **T** | Toggle trails |
| **P** | Pause or resume |
| **R** | Reset to 90 random balls |

The Gravity, Bounce, and Chaos sliders update live. Their matching `<output>` elements show two decimal places; the range fill uses the CSS custom property `--p`. Double-clicking a slider restores its HTML default value.

The control buttons and keyboard shortcuts call the same small state-changing functions (`setPaused`, `setColor`, and `setTrails`). Keep those functions as the single place to update both simulation state and active UI styling.

## Interface and styling

`index.html` contains the controls and the canvas. `main.ts` refers to controls by their IDs (`g`, `b`, `ch`, `pause`, `color`, `trails`, `burst`, `reset`, and `fold`), so changing an ID requires updating the TypeScript lookup too. Slider outputs are named by adding `v` to the slider ID (`gv`, `bv`, `chv`).

`style.css` provides the dark neon palette, glass-like panel, slider appearance, active button states, shortcut popover, and responsive layout. At narrower widths the controls stack and buttons wrap. The `prefers-reduced-motion` rule removes the logo pulse and UI transitions.

## Build and source-of-truth rules

- Make behavior changes in `main.ts`, then run `npm run build` to regenerate `main.js`.
- Make page structure changes in `index.html`; update selectors in `main.ts` if an ID changes.
- Make visual changes in `style.css`.
- `preview.html` is a separate inlined copy. There is no script that regenerates it, so changes to app markup, CSS, or JavaScript need to be mirrored there if the standalone preview must stay current.
- `main.js` is committed so the project can be served without building first. Commit it together with its matching `main.ts` source.
- `demo.svg` and `visual-demo.mp4` are README media assets. Updating either asset may require changing its README link or description.

## Configuration reference

The main constants are near the top of `main.ts`:

| Constant | Default | Meaning |
|---|---:|---|
| `MAX_BALLS` | 600 | Maximum number of balls in the scene. |
| `WELL_LIFE` | 420 ticks | Gravity-well lifetime, in the simulation's 60 Hz style ticks. |
| `STEP` | 1/120 s | Fixed physics step. Smaller steps cost more CPU. |
| `MAX_V` | 20 px/step | Maximum displacement after wall handling. |
| `CELL` | 48 px | Spatial-hash cell size; keep it at least the largest ball diameter. |
| `WAVE_LIFE` | 40 ticks | Shockwave ring lifetime. |
| `DPR` | 1–2 | Canvas pixel ratio, capped at 2. |

The slider ranges and defaults live in `index.html`. Gravity ranges from -2 to 3, Bounce from 0.2 to 1.2, and Chaos from 0 to 2.

## Troubleshooting and performance

- **Blank page from `index.html`:** serve the directory over HTTP; ES modules may not load from `file://`.
- **Old behavior after editing TypeScript:** run `npm run build` and reload the page.
- **Slow simulation:** reduce `MAX_BALLS`, disable trails with **T**, or reduce the number of active wells. The spatial hash reduces collision work, but force calculations still visit every ball and every well.
- **Touch scrolling instead of drawing:** the canvas sets `touch-action: none`; check that another stylesheet has not overridden it.
- **Preview differs from the main app:** update the inlined source in `preview.html` as well. It is maintained separately.

## Safe extension points

- Add a new color style by extending `MODES`, the button label logic, and the hue selection in `draw()`.
- Add a new force by accumulating into `b.ax` and `b.ay` inside `applyForces()`; preserve the fixed-step units.
- Add a new control by creating its markup in `index.html`, styling it in `style.css`, looking it up in `main.ts`, and wiring both pointer and keyboard behavior where appropriate.
- Add an obstacle or constraint by integrating it into the fixed-step update path, not only into rendering. Draw-only shapes do not participate in collisions.

Keep hot-loop work allocation-light: `applyForces()`, `integrate()`, collision handling, and `draw()` run many times per second. Reuse typed arrays where practical and avoid adding per-ball objects each frame.
