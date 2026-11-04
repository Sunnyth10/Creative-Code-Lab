```
 ███╗   ██╗ ██████╗ ██╗   ██╗ █████╗      ██████╗ █████╗ ██╗      ██████╗
 ████╗  ██║██╔═══██╗██║   ██║██╔══██╗    ██╔════╝██╔══██╗██║     ██╔════╝
 ██╔██╗ ██║██║   ██║██║   ██║███████║    ██║     ███████║██║     ██║
 ██║╚██╗██║██║   ██║╚██╗ ██╔╝██╔══██║    ██║     ██╔══██║██║     ██║
 ██║ ╚████║╚██████╔╝ ╚████╔╝ ██║  ██║    ╚██████╗██║  ██║███████╗╚██████╗
 ╚═╝  ╚═══╝ ╚═════╝   ╚═══╝  ╚═╝  ╚═╝     ╚═════╝╚═╝  ╚═╝╚══════╝ ╚═════╝
```

# 🧮 Nova Calc
### *The calculator that read your homework, your budget, and your calendar, and still has time to plot a parabola.*

Your phone calculator has the memory of a goldfish and the personality of a toaster.
You type `12 × 7`, it says `84`, and then it forgets you exist.

**Nova Calc remembers.** It keeps a tape, names your numbers, explains its own thinking,
converts your units, counts your days, and judges your EMI (silently, with love).

One file. Zero dependencies. No `eval()`. No subscriptions. No ads. No "Calculator Pro+ Premium Gold."

---

## ⚡ Launch it in 10 seconds

```bash
python3 nova_calc.py            # run from inside this folder
python3 nova_calc.py --test     # run the engine self-test
```

From the repository root, use `python3 nova_calc/nova_calc.py` instead.

Needs **Python 3.9+**. On Linux, if it complains about `tkinter`: `sudo apt install python3-tk`.
Windows and macOS already ship with it. Go forth.

---

## 🪄 Tricks your old calculator can't do

You type words. It does math. Try these. No quotes, no ceremony.

| You type | Nova says |
|---|---|
| `20% of 850` | `170` |
| `15 more than 230` | `245` |
| `what is 5 plus 3` | `8` |
| `5 km to miles` | `3.10685596119 miles` |
| `100 c to f` | `212 f` |
| `100 usd to inr` | *(whatever the rupee is feeling today)* |
| `today + 30 days` | the date, **plus the weekday**, so you know if it lands on a Monday |
| `days between 2026-01-01 and 2026-12-25` | `358 days` *(start the countdown)* |
| `age of 1990-05-14` | years, months **and** days. Brutal. Precise. |
| `emi(100000, 12, 1)` | `8884.87886783` *(your bank already knew)* |
| `0.1 + 0.2` | `0.3` *(yes, really. We fixed JavaScript's biggest embarrassment.)* |

---

## 🧠 It has a MEMORY (a real one)

Give your numbers names. Change one, and everything that used it is recalculated in your head... or at least in the next line.

```
rent = 12000
tax  = 18%
rent * (1 + tax)      →  14160
ans * 12              →  169920     ← "ans" is the last result
```

Everything you do lands on the **tape**:

- 🖱️ **Double-click** a line → pull the expression back and edit it
- 🖱️ **Right-click** a line → drop its *result* into what you're typing
- ⌨️ **Up / Down** → time-travel through your previous entries
- 💾 It **auto-saves on exit**, so tomorrow-you picks up where today-you left off

---

## 🔍 The "Explain" button (a calculator that shows its work)

Press **Explain** and it narrates itself, like a math teacher who finally cares:

```
(120 * 1.18) - 15

1. 120 * 1.18 = 141.6
2. 141.6 - 15 = 126.6
```

Great for learning. Greater for proving to your friend that *you* were right about the bill split.

---

## 🎛️ Five personalities (modes)

| Mode | Vibe | Toys inside |
|---|---|---|
| **Standard** | "Just add it up." | √ π mod, plus `x` and `y=` for graphs |
| **Scientific** | Lab coat on. | sin cos tan asin acos atan ln log exp abs ncr, DEG⇄RAD toggle |
| **Finance** | Suit and tie. | `emi` `compound` `gst` `pctchange` `round` |
| **Programmer** | Hoodie, 3 a.m. | `hex` `bin` `oct` `0xFF` `0b101` `band` `bor` `bxor` `shl` `shr` |
| **Dates** | Time lord. | `today` `tomorrow` `yesterday` `days between` `age of` `weekday of` |

Stats lurk in the background too: `mean(...)`, `median(...)`, `stdev(...)`, `sum(...)`, `gcd`, `lcm`.

---

## 📈 It draws. Yes, a calculator that draws.

```
y = x^2 - 3x
y = sin(x) for x in -6.28..6.28
```

Hit **Enter** and a graph window pops up with gridlines, axis labels, and
**hover-to-read**: move the mouse and it tells you the exact `x` and `y`.
Your old calculator would have said `SYNTAX ERROR` and gone to lie down.

---

## 🛡️ Why it won't blow up your computer

Most DIY calculators use `eval()`, which is like giving a stranger the keys to your house because they said they were "just checking the thermostat."

Nova Calc has its **own parser**: tokenizer → parser → evaluator, built from scratch.
It can do math and *only* math. Type `__import__('os').system('rm -rf /')` and it politely says
`Unexpected character`. Nothing runs. Your files live to see another day.

It's also clear about its feelings when you misbehave:

| You try | It says |
|---|---|
| `1/0` | `Cannot divide by zero` |
| `sqrt(-1)` | `Invalid input for sqrt()` |
| `foo + 1` | `Unknown name: foo` |
| `2 +` | `Unexpected end` |
| `age of 2999-01-01` | `Date is in the future` *(nice try, time traveler)* |

---

## 📦 Take your work with you

- **Export** → tape as `.txt` or `.csv` (hello, spreadsheet people)
- **Save / Open** → full sheets (variables + history) as `.json`
- **Rates** button → fetches live currency rates, no API key needed
- **Theme** button → dark mode for night owls, light mode for people who enjoy squinting

---

## ⌨️ Keyboard ninja cheat sheet

| Key | Does |
|---|---|
| `Enter` | commit to the tape |
| `Esc` | clear the line |
| `↑` / `↓` | recall previous entries |
| `Ctrl+E` | export |
| `Ctrl+S` / `Ctrl+O` | save / open a sheet |
| `F1` | help (the in-app list of everything you can type) |

---

## ❓ FAQ (Frequently Asked Questions, Probably)

**Is this overkill for a calculator?**
Yes. Beautifully, unapologetically yes.

**Do I need the internet?**
No. Only the **Rates** button wants it. Offline, it uses built-in approximate rates
(good for "roughly how much is this in euros," not for "sell my house").

**Are the currency numbers financial advice?**
Absolutely not. They're a convenience. Your bank's rate wins every argument.

**Where does it keep my stuff?**
`~/.nova_calc_session.json` (your tape and variables) and `~/.nova_calc_rates.json` (cached rates).
Delete them anytime for a fresh start. It will not cry. (Probably.)

**Why is it one giant file?**
So you can email it to your cousin, drop it on a USB stick, or run it from a folder named `new folder (3)`.

**Can I add my own functions?**
Yes. Open `nova_calc.py`, find the `self.funcs = {...}` dictionary in the `Calc` class, and add a line.
You're now a calculator engineer.

**Can I add my own currencies or units?**
Same energy. Look for `UNITS` and `RATES` near the top.

---

## 🔬 Under the hood (for the curious)

```
 your typing
     │
     ▼
 normalize()   ── "20% of 850" → (20/100)*(850)   (natural language)
     │
     ├── try_date()   → "today + 30 days", "age of ..."
     ├── convert()    → "5 km to miles"
     ▼
 tokenize() → Parser (recursive descent) → ev()  ── also records the Explain steps
     │
     ▼
 fmt()  → tidy output (no 0.30000000000000004 nonsense)
```

Operator precedence is respected (`2 + 3 * 4 = 14`), powers are right-associative (`2^3^2 = 512`),
and `-2^2 = -4`, exactly as your math teacher intended.

---

## 🗺️ Where it could go next

- 🌐 A web version for your phone
- 🧮 Equation solving (`solve x^2 = 16`)
- 🎨 More themes (a "Retro Green Phosphor" one is calling my name)

---

<p align="center"><b>Built to answer "what's 18% of this bill?" and also "what day of the week is Christmas?"</b><br>
<i>Press <code>F1</code>. Type something silly. Enjoy.</i> 🚀</p>
