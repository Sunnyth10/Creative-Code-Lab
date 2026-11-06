# Nova Calc Developer Guide

This guide describes the implementation in [`nova_calc.py`](nova_calc.py), how a calculation travels through the app, and where to make common changes. Nova Calc is intentionally a single-file Python application with no third-party dependencies.

## Project overview

| Area | Implementation |
|---|---|
| Language/runtime | Python 3.9+; standard library only |
| Desktop UI | Tkinter, imported inside `launch()` |
| Math input | Custom regular-expression tokenizer, recursive-descent parser, and AST evaluator |
| Dates and conversions | Python `datetime`, calendar arithmetic, built-in conversion tables |
| Saved state | JSON session and rate cache in the user's home directory |
| Graphs | Sample expression values and draw them with Tkinter Canvas |
| Self-check | Built-in `self_test()` invoked with `--test` |

```text
nova_calc/
├── nova_calc.py          # engine, UI, persistence, graphing, self-test
├── readme.md             # user documentation
├── DEVELOPERS.md         # this guide
└── assets/screenshots/   # screenshots referenced by the readme
```

## Run and inspect

From this folder:

```sh
python3 nova_calc.py
python3 nova_calc.py --test
```

From the repository root:

```sh
python3 nova_calc/nova_calc.py
```

The app requires a graphical desktop for normal use. Linux installations may need the operating system's Tkinter package (often named `python3-tk`). The calculation engine itself can be imported and used without starting the UI.

## Main code areas

The file is arranged in functional sections, in roughly the order a developer should read them:

1. **Imports and paths** — standard-library modules and the two user-level JSON paths: `SESSION_FILE` and `RATES_FILE`.
2. **Formatting and errors** — `CalcError` is the expected user-facing calculation error; `fmt()` renders numbers consistently and rejects non-finite results.
3. **Tokenizer and parser** — `TOKEN_RE`, `tokenize()`, and `Parser` turn allowed input into a small tuple-based syntax tree.
4. **Conversions and rates** — `UNITS`, `TEMPS`, `RATES`, `convert()`, and rate cache/network helpers.
5. **Dates and math helpers** — date parsing/arithmetic and standalone finance/math functions.
6. **Calculation engine** — `Calc` owns variables, angle mode, function table, evaluation, normalization, date handling, graph sampling, and state serialization.
7. **Exports and UI configuration** — tape export functions plus help, themes, keypad, modes, and key insertion mappings.
8. **Tkinter application** — `launch()` constructs widgets and binds UI actions to the engine.
9. **Self-test and entry point** — `self_test()` and the `if __name__ == "__main__"` argument dispatch.

## Calculation pipeline

For a normal expression, `Calc.run()` coordinates these steps:

```text
user text
  ├─ normalize()     symbols and supported natural-language phrases
  ├─ try_date()      recognized date requests return early
  ├─ conversion path  parse numeric expression, then convert units/currency
  └─ tokenize() → Parser.parse() → Calc.ev() → fmt()
```

`run(text, commit=True)` returns `(result_string, steps)`. The `steps` list is used by the Explain feature. With `commit=True`, assignments update `Calc.vars` and successful numeric results update `Calc.ans`. With `commit=False`, the evaluator receives a copy of the variable environment, which is useful for live previews and explanation without committing a new answer.

### Safe expression language

Nova Calc deliberately does not use Python `eval()`. The tokenizer accepts numeric literals (including `0x` and `0b`), identifiers, and a fixed set of operators/punctuation. The parser builds nodes such as `("num", value)`, `("bin", op, left, right)`, `("call", name, args)`, and `("assign", name, expression)`. `Calc.ev()` interprets only those nodes.

The parser methods encode precedence from low to high:

| Parser method | Operators/forms |
|---|---|
| `expr()` | `+`, `-` |
| `term()` | `*`, `/`, `mod`, implicit multiplication such as `2pi` |
| `unary()` | unary `+` and `-` |
| `power()` | `^` (right-associative) |
| `postfix()` | factorial `!` and percent `%` |
| `primary()` | literals, variables, function calls, parentheses |

For example, `2 + 3 * 4` becomes addition whose right child is multiplication, so it evaluates to `14`. Power calls `unary()` for its exponent, which makes `2^3^2` right-associative. The tree evaluator reports controlled `CalcError`s for unknown names/functions, divide-by-zero, invalid domains, complex answers, and malformed input.

### Variables, functions, and answer memory

`Calc.__init__()` initializes `vars`, `ans`, angle mode (`deg`), and `funcs`. Variables are assigned with syntax like `rent = 12000`; names are normalized to lowercase when evaluated. Built-in constants are `pi`, `e`, and `ans`.

To add a calculator function, add a callable to `self.funcs` in `Calc.__init__()`. It will then be reachable through the parser's function-call syntax, for example `myfunc(2, 3)`. Keep argument validation and errors predictable: `Calc.ev()` translates common Python math/type exceptions to `CalcError("Invalid input for name()")`. Add an explicit check and raise `CalcError` when a clearer message is useful.

Function groups currently include:

- **Scientific:** `sqrt`, `sin`, `cos`, `tan`, inverse trig, `ln`, `log`, `exp`, `abs`, `floor`, `ceil`, `round`, factorial, combinations/permutations.
- **Finance:** `emi`, `compound`, `gst`, `pctchange`.
- **Statistics:** `sum`, `mean`, `median`, `stdev`, `min`, `max`.
- **Programmer:** `hex`, `bin`, `oct`, `band`, `bor`, `bxor`, `shl`, `shr`, plus binary/hex literals.
- **Integer helpers:** `gcd`, `lcm`.

Angle conversion is centralized in `_a()` and `_r()`: forward trig converts degrees to radians when `deg` is enabled, and inverse trig converts back for display.

## Natural language, dates, and conversions

`Calc.normalize()` handles input symbols and a small, explicit vocabulary: “what is”, “calculate”, percentage-of phrases, “more/less than”, and word operators such as “plus” and “divided by”. It is not a general language model; new phrases should be added as narrow, tested transformations.

`Calc.try_date()` recognizes date-only requests before expression parsing. The regex constants `D` and `UNIT_RE` define accepted dates and intervals. `_date()` resolves ISO dates and relative words against `self.today()`. `self.today` is injectable, which makes date behavior deterministic in the self-test. `add_months()` clamps to the final valid day of the destination month (for example, January 31 plus one month becomes the last day of February).

Unit conversions use a base-unit factor and a category in `UNITS`; temperature conversion is handled separately in `convert()`. Currency values are rates relative to USD. `fetch_rates()` downloads rates from `RATES_URL`, updates the in-memory table and cache, while `load_cached_rates()` is best-effort. Offline defaults are approximate. The UI launches the network fetch on a background thread so the window remains responsive.

To add a unit, add its lowercase alias and `(category, factor-to-base)` entry in `UNITS`. Aliases in the same physical category can convert to each other. To add a currency fallback, add it to `RATES`. Temperature aliases and formulas belong in `convert()`.

## Graphing

`Calc.plot_spec()` recognizes `y = ...` or `f(x) = ...`, optionally with `for x in low..high`. `Calc.sample()` parses the expression once and evaluates it at evenly spaced x values with `x` added to a temporary variable environment. Undefined or excessively large points are represented as `None`, allowing the graph to break across discontinuities. `show_graph()` in `launch()` draws axes, grid, curve, and hover coordinates on a Canvas.

To support another graph syntax, update `plot_spec()` and its self-test cases. Keep graph evaluation routed through `Parser` and `Calc.ev()` so graph expressions obey the same safe expression rules.

## UI and interaction model

`launch()` imports Tkinter locally, constructs the `Calc`, restores saved state, loads cached currency rates, then builds the window. Nested functions inside `launch()` are UI callbacks. The most relevant ones are:

| Callback | Responsibility |
|---|---|
| `update_live()` | Evaluate the current entry without committing state and update the live result |
| `commit()` | Run and append an expression/result pair to the tape |
| `recall()` | Navigate previous expressions with Up/Down |
| `set_mode()` / `build_keys()` | Rebuild mode buttons and keypad |
| `explain()` | Show evaluation steps for the current expression or selected tape item |
| `do_export()` | Save tape as text or CSV |
| `save_sheet()` / `open_sheet()` | Save or restore a JSON sheet |
| `do_rates()` | Start a background rates refresh and update UI status |
| `show_graph()` | Render sampled points in a graph window |
| `on_close()` | Persist session state before closing |

Mode layouts live in `MODES`; common keys live in `BASE_KEYS`; display-to-input translations live in `INSERT`. If a keypad item should insert special syntax, add its mapping to `INSERT` and make sure the callback handles it as expected. The text entry remains the primary interface, so features should also work when typed directly.

Theme colors are in `THEMES`. UI code reads the selected theme and applies colors through `apply_theme()`; add keys matching the existing palette structure when creating a theme.

## Persistence and file formats

The current session is stored at `~/.nova_calc_session.json`; cached currency rates are stored at `~/.nova_calc_rates.json`. These paths are formed from `Path.home()` near the top of the file.

`Calc.export_state(history, **extra)` serializes variables, history, angle mode, answer memory, and optional UI configuration. `Calc.import_state()` restores engine state and returns history as tuples. The session file also carries UI values such as theme and mode. Sheet Save/Open uses the same state representation. Tape-only exports are handled by `export_text()` and `export_csv()`.

When changing persisted fields, preserve defaults in `import_state()` and in the session restore code so older JSON files remain loadable. File reads/writes should continue to handle expected `OSError` and malformed JSON gracefully.

## Error-handling conventions

- Raise `CalcError` for expected input and calculation failures.
- Do not let malformed user input escape as a traceback in the UI.
- Catch only the anticipated exceptions at each boundary; the engine currently translates common math/function exceptions in `Calc.ev()`.
- Keep `fmt()` as the shared numeric output formatter so tape, live display, Explain steps, and exports stay consistent.
- Network failures should leave cached/offline rates available and surface a status message rather than blocking the UI.

## Extending the app: quick recipes

### Add a function

1. Implement or select a callable, preferably as a small named helper for nontrivial logic.
2. Register it in `Calc.__init__()` under a lowercase name.
3. If users should discover it in the GUI, update `HELP` and the relevant `MODES` row.
4. Add representative success and failure cases to `self_test()`.

### Add a unit

1. Pick the base unit for the category (the existing factors use meters, kilograms, liters, and seconds).
2. Add unit aliases and their factor in `UNITS`.
3. Add self-test cases for conversion and category mismatch if relevant.

### Add a date phrase

1. Add a specific pattern to `Calc.try_date()` before its final date-only fallback.
2. Use `_date()`, `shift()`, and `describe()` where appropriate.
3. Add a deterministic test using the injected `c.today` function.

### Add a mode or keypad action

1. Define the layout in `MODES` or `BASE_KEYS`.
2. Add special insertion text to `INSERT`, if needed.
3. Update `HELP` and check that `set_mode()` / `build_keys()` display it correctly.

## Self-test guidance

The built-in self-test is a lightweight executable specification for the engine. It checks precedence, formatting, errors, conversions, dates, statistics, finance functions, graphing, exports, state round-tripping, and rate parsing. Run it with:

```sh
python3 nova_calc.py --test
```

The test fixes the current date through `Calc.today`, so date expectations do not change every day. When changing behavior, update/add a focused case alongside the implementation. A GUI launch can be checked separately with `python3 nova_calc.py --smoke` in an environment with Tkinter and a display.

## Current design constraints

- The app is one Python file; keep sections ordered and use the existing section dividers.
- No third-party packages are required; UI and graphics are Tkinter/Canvas.
- The expression language is intentionally smaller than Python and must remain data-only.
- The live currency request needs internet access; the rest of the calculator works offline.
- GUI callbacks are nested inside `launch()`, so extracting or reusing them requires a deliberate refactor.
