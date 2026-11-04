#!/usr/bin/env python3
"""Nova Calc - a calculator that thinks alongside you.

    python nova_calc.py           launch the GUI
    python nova_calc.py --test    run the engine self-test
    python nova_calc.py --smoke   open the GUI for a moment, then close (CI check)

Standard + scientific functions, live results, named variables, history tape,
unit / temperature / live-currency conversion, natural-language input, a Date
calculator, Programmer + Finance + Stats functions, Explain steps, graphing,
export (txt / csv), save/load sheets, auto-saved session, light/dark theme.
Only the Python standard library is used. Expressions are parsed by a custom
parser (no eval), so nothing you type can run code.
"""
import calendar
import csv
import datetime as dt
import io
import json
import math
import re
import statistics
import sys
import threading
import urllib.request
from pathlib import Path

HOME = Path.home()
SESSION_FILE = HOME / ".nova_calc_session.json"
RATES_FILE = HOME / ".nova_calc_rates.json"
RATES_URL = "https://open.er-api.com/v6/latest/USD"

# --------------------------------------------------------------------------
# Formatting + errors
# --------------------------------------------------------------------------


class CalcError(Exception):
    pass


def fmt(v):
    if isinstance(v, str):
        return v
    if isinstance(v, bool):
        return str(v)
    if v != v or v in (math.inf, -math.inf):
        raise CalcError("Result is not a finite number")
    if float(v).is_integer() and abs(v) < 1e15:
        return str(int(v))
    return "%.12g" % v


# --------------------------------------------------------------------------
# Tokenizer + parser
# --------------------------------------------------------------------------
TOKEN_RE = re.compile(
    r"\s*(?:(0x[0-9a-fA-F]+|0b[01]+|\d+\.?\d*(?:[eE][+-]?\d+)?|\.\d+)"
    r"|([A-Za-z_]\w*)|([-+*/^()!,%=]))"
)


def tokenize(s):
    out, pos = [], 0
    s = s.rstrip()
    while pos < len(s):
        m = TOKEN_RE.match(s, pos)
        if not m or m.end() == pos:
            raise CalcError("Unexpected character: %r" % s[pos:].strip()[:1])
        pos = m.end()
        if m.group(1):
            t = m.group(1).lower()
            val = float(int(t, 16)) if t.startswith("0x") else \
                float(int(t, 2)) if t.startswith("0b") else float(t)
            out.append(("num", val))
        elif m.group(2):
            out.append(("id", m.group(2)))
        else:
            out.append(("op", m.group(3)))
    return out


class Parser:
    def __init__(self, toks):
        self.t, self.i = toks, 0

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else (None, None)

    def eat(self, val=None):
        tok = self.peek()
        if tok[0] is None or (val and tok[1] != val):
            raise CalcError("Expected %r" % val if val else "Unexpected end")
        self.i += 1
        return tok

    def parse(self):
        if (len(self.t) > 1 and self.t[0][0] == "id"
                and self.t[1] == ("op", "=")):
            name = self.t[0][1]
            self.i = 2
            node = ("assign", name, self.expr())
        else:
            node = self.expr()
        if self.i != len(self.t):
            raise CalcError("Unexpected %r" % (self.peek()[1],))
        return node

    def expr(self):
        node = self.term()
        while self.peek() in (("op", "+"), ("op", "-")):
            op = self.eat()[1]
            node = ("bin", op, node, self.term())
        return node

    def term(self):
        node = self.unary()
        while True:
            tok = self.peek()
            if tok in (("op", "*"), ("op", "/")) or tok == ("id", "mod"):
                op = self.eat()[1]
                node = ("bin", op, node, self.unary())
            elif tok[0] in ("num", "id") or tok == ("op", "("):
                node = ("bin", "*", node, self.unary())  # implicit: 2pi, 3(4)
            else:
                return node

    def unary(self):
        if self.peek() == ("op", "-"):
            self.eat()
            return ("neg", self.unary())
        if self.peek() == ("op", "+"):
            self.eat()
            return self.unary()
        return self.power()

    def power(self):
        base = self.postfix()
        if self.peek() == ("op", "^"):
            self.eat()
            return ("bin", "^", base, self.unary())  # right-associative
        return base

    def postfix(self):
        node = self.primary()
        while self.peek() in (("op", "!"), ("op", "%")):
            node = ("fact" if self.eat()[1] == "!" else "pct", node)
        return node

    def primary(self):
        kind, val = self.peek()
        if kind == "num":
            self.eat()
            return ("num", val)
        if kind == "id":
            self.eat()
            if self.peek() == ("op", "("):
                self.eat()
                args = []
                if self.peek() != ("op", ")"):
                    args.append(self.expr())
                    while self.peek() == ("op", ","):
                        self.eat()
                        args.append(self.expr())
                self.eat(")")
                return ("call", val.lower(), args)
            return ("var", val)
        if (kind, val) == ("op", "("):
            self.eat()
            node = self.expr()
            self.eat(")")
            return node
        raise CalcError("Unexpected end" if kind is None else "Unexpected %r" % val)


# --------------------------------------------------------------------------
# Units + currency
# --------------------------------------------------------------------------
UNITS = {
    **{u: ("len", f) for u, f in {
        "mm": .001, "cm": .01, "m": 1, "km": 1000, "in": .0254, "inch": .0254,
        "inches": .0254, "ft": .3048, "feet": .3048, "yd": .9144,
        "mile": 1609.344, "miles": 1609.344, "mi": 1609.344}.items()},
    **{u: ("mass", f) for u, f in {
        "mg": 1e-6, "g": .001, "kg": 1, "lb": .45359237, "lbs": .45359237,
        "oz": .028349523, "tonne": 1000}.items()},
    **{u: ("vol", f) for u, f in {
        "ml": .001, "l": 1, "litre": 1, "liter": 1, "gal": 3.785411784,
        "cup": .2365882365}.items()},
    **{u: ("time", f) for u, f in {
        "sec": 1, "s": 1, "seconds": 1, "min": 60, "minutes": 60, "hr": 3600,
        "h": 3600, "hours": 3600, "day": 86400, "days": 86400,
        "week": 604800, "weeks": 604800}.items()},
}
TEMPS = {"c", "f", "k"}
# Offline fallback (approximate, per 1 USD). "Rates" button fetches live ones.
RATES = {"usd": 1.0, "inr": 83.0, "eur": 0.92, "gbp": 0.79, "jpy": 150.0,
         "aud": 1.52, "cad": 1.36, "aed": 3.67}
RATES_META = {"source": "offline defaults", "updated": None}


def convert(value, a, b):
    a, b = a.lower().rstrip("°"), b.lower().rstrip("°")
    if a in TEMPS and b in TEMPS:
        c = {"c": value, "f": (value - 32) * 5 / 9, "k": value - 273.15}[a]
        return {"c": c, "f": c * 9 / 5 + 32, "k": c + 273.15}[b]
    if a in UNITS and b in UNITS:
        if UNITS[a][0] != UNITS[b][0]:
            raise CalcError("Cannot convert %s to %s" % (a, b))
        return value * UNITS[a][1] / UNITS[b][1]
    if a in RATES and b in RATES:
        return value / RATES[a] * RATES[b]
    return None


def parse_rates(data):
    if data.get("result") != "success" or "rates" not in data:
        raise CalcError("Rate service returned an error")
    return {k.lower(): float(v) for k, v in data["rates"].items()}


def fetch_rates(timeout=8, url=RATES_URL):
    """Download live USD-based rates; updates RATES and caches to disk."""
    with urllib.request.urlopen(url, timeout=timeout) as r:
        rates = parse_rates(json.loads(r.read().decode("utf-8")))
    RATES.update(rates)
    RATES_META.update(source="live", updated=dt.datetime.now().isoformat(" ", "minutes"))
    try:
        RATES_FILE.write_text(json.dumps({"meta": RATES_META, "rates": rates}))
    except OSError:
        pass
    return len(rates)


def load_cached_rates():
    try:
        d = json.loads(RATES_FILE.read_text())
        RATES.update({k: float(v) for k, v in d["rates"].items()})
        RATES_META.update(d.get("meta", {}))
        RATES_META["source"] = "cached"
    except (OSError, ValueError, KeyError):
        pass


# --------------------------------------------------------------------------
# Dates
# --------------------------------------------------------------------------
D = r"(\d{4}-\d{2}-\d{2}|today|tomorrow|yesterday)"
UNIT_RE = r"(day|week|month|year)s?"


def add_months(d, n):
    y, m = divmod(d.year * 12 + d.month - 1 + n, 12)
    m += 1
    return d.replace(year=y, month=m, day=min(d.day, calendar.monthrange(y, m)[1]))


def shift(d, n, unit):
    if unit == "day":
        return d + dt.timedelta(days=n)
    if unit == "week":
        return d + dt.timedelta(weeks=n)
    return add_months(d, n if unit == "month" else 12 * n)


def describe(d):
    return "%s (%s)" % (d.isoformat(), d.strftime("%A"))


def age_between(b, t):
    if b > t:
        raise CalcError("Date is in the future")
    y, m, d = t.year - b.year, t.month - b.month, t.day - b.day
    if d < 0:
        m -= 1
        py, pm = (t.year, t.month - 1) if t.month > 1 else (t.year - 1, 12)
        d += calendar.monthrange(py, pm)[1]
    if m < 0:
        y, m = y - 1, m + 12
    return y, m, d


# --------------------------------------------------------------------------
# Math helpers
# --------------------------------------------------------------------------
def emi(p, annual_rate, years):
    r, n = annual_rate / 1200, years * 12
    return p / n if r == 0 else p * r * (1 + r) ** n / ((1 + r) ** n - 1)


def compound(p, rate, years, n=1):
    return p * (1 + rate / 100 / n) ** (n * years)


def fact(x):
    if x < 0:
        raise CalcError("Factorial of negative number")
    if float(x).is_integer():
        if x > 170:
            raise CalcError("Number too large")
        return float(math.factorial(int(x)))
    return math.gamma(x + 1)


def _bits(f):
    return lambda a, b: float(f(int(a), int(b)))


# --------------------------------------------------------------------------
# Calculator engine
# --------------------------------------------------------------------------
class Calc:
    def __init__(self):
        self.vars = {}
        self.ans = 0.0
        self.deg = True
        self.today = dt.date.today  # injectable for tests
        self.funcs = {
            "sqrt": math.sqrt, "abs": abs, "ln": math.log, "log": math.log10,
            "exp": math.exp, "round": lambda x, n=0: round(x, int(n)),
            "floor": math.floor, "ceil": math.ceil, "fact": fact,
            "sin": lambda x: math.sin(self._a(x)),
            "cos": lambda x: math.cos(self._a(x)),
            "tan": lambda x: math.tan(self._a(x)),
            "asin": lambda x: self._r(math.asin(x)),
            "acos": lambda x: self._r(math.acos(x)),
            "atan": lambda x: self._r(math.atan(x)),
            "ncr": lambda n, r: math.comb(int(n), int(r)),
            "npr": lambda n, r: math.perm(int(n), int(r)),
            "gcd": _bits(math.gcd), "lcm": _bits(math.lcm),
            # finance
            "emi": emi, "compound": compound,
            "gst": lambda amt, rate: amt * rate / 100,
            "pctchange": lambda a, b: (b - a) / a * 100,
            # stats
            "sum": lambda *a: math.fsum(a), "mean": lambda *a: statistics.mean(a),
            "median": lambda *a: statistics.median(a),
            "stdev": lambda *a: statistics.stdev(a),
            "min": min, "max": max,
            # programmer
            "hex": lambda x: hex(int(x)), "bin": lambda x: bin(int(x)),
            "oct": lambda x: oct(int(x)),
            "band": _bits(lambda a, b: a & b), "bor": _bits(lambda a, b: a | b),
            "bxor": _bits(lambda a, b: a ^ b),
            "shl": _bits(lambda a, b: a << b), "shr": _bits(lambda a, b: a >> b),
        }

    def _a(self, x):
        return math.radians(x) if self.deg else x

    def _r(self, x):
        return math.degrees(x) if self.deg else x

    # -- evaluator -------------------------------------------------------------
    def ev(self, n, env, steps):
        k = n[0]
        if k == "num":
            return n[1]
        if k == "var":
            name = n[1].lower()
            if name in env:
                return env[name]
            consts = {"pi": math.pi, "e": math.e, "ans": self.ans}
            if name in consts:
                return consts[name]
            raise CalcError("Unknown name: %s" % n[1])
        if k == "neg":
            return -self.ev(n[1], env, steps)
        if k == "pct":
            a = self.ev(n[1], env, steps)
            steps.append("%s%% = %s" % (fmt(a), fmt(a / 100)))
            return a / 100
        if k == "fact":
            a = self.ev(n[1], env, steps)
            r = fact(a)
            steps.append("%s! = %s" % (fmt(a), fmt(r)))
            return r
        if k == "bin":
            a, b = self.ev(n[2], env, steps), self.ev(n[3], env, steps)
            op = n[1]
            try:
                r = {"+": lambda: a + b, "-": lambda: a - b, "*": lambda: a * b,
                     "/": lambda: a / b, "mod": lambda: a % b,
                     "^": lambda: a ** b}[op]()
            except ZeroDivisionError:
                raise CalcError("Cannot divide by zero")
            except OverflowError:
                raise CalcError("Number too large")
            if isinstance(r, complex):
                raise CalcError("Result is not a real number")
            steps.append("%s %s %s = %s" % (fmt(a), op, fmt(b), fmt(r)))
            return r
        if k == "call":
            f = self.funcs.get(n[1])
            if not f:
                raise CalcError("Unknown function: %s" % n[1])
            args = [self.ev(a, env, steps) for a in n[2]]
            try:
                r = f(*args)
            except (ValueError, TypeError, ZeroDivisionError, OverflowError,
                    statistics.StatisticsError):
                raise CalcError("Invalid input for %s()" % n[1])
            steps.append("%s(%s) = %s" % (n[1], ", ".join(map(fmt, args)), fmt(r)))
            return r
        if k == "assign":
            v = self.ev(n[2], env, steps)
            env[n[1].lower()] = v
            steps.append("%s := %s" % (n[1], fmt(v)))
            return v
        raise CalcError("Bad expression")

    # -- natural language ------------------------------------------------------
    @staticmethod
    def normalize(s):
        s = s.strip().replace("×", "*").replace("÷", "/").replace("−", "-")
        s = s.replace("π", "pi").replace("√", "sqrt")
        s = re.sub(r"^(what is|what's|calculate)\s+", "", s, flags=re.I)
        m = re.match(r"^(.+?)%\s+of\s+(.+)$", s, re.I)
        if m:
            return "(%s/100)*(%s)" % (m[1], m[2])
        m = re.match(r"^(.+?)\s+(more|less)\s+than\s+(.+)$", s, re.I)
        if m:
            return "(%s)%s(%s)" % (m[3], "+" if m[2].lower() == "more" else "-", m[1])
        for w, o in (("plus", "+"), ("minus", "-"), ("times", "*"),
                     ("divided by", "/"), ("to the power of", "^")):
            s = re.sub(r"\b%s\b" % w, o, s, flags=re.I)
        return s

    # -- dates -----------------------------------------------------------------
    def _date(self, t):
        t = t.lower()
        base = self.today()
        if t == "today":
            return base
        if t == "tomorrow":
            return base + dt.timedelta(days=1)
        if t == "yesterday":
            return base - dt.timedelta(days=1)
        try:
            return dt.date.fromisoformat(t)
        except ValueError:
            raise CalcError("Invalid date: %s" % t)

    def try_date(self, s):
        I = re.I
        m = re.match(r"^days?\s+between\s+%s\s+and\s+%s$" % (D, D), s, I)
        if m:
            n = abs((self._date(m[2]) - self._date(m[1])).days)
            return "%d days" % n, ["%s to %s = %d days" % (m[1], m[2], n)]
        m = re.match(r"^%s\s*([+-])\s*(\d+)\s*%s$" % (D, UNIT_RE), s, I)
        if m:
            n = int(m[3]) * (1 if m[2] == "+" else -1)
            r = shift(self._date(m[1]), n, m[4].lower())
            return describe(r), ["%s %s %s %ss" % (m[1], m[2], m[3], m[4])]
        m = re.match(r"^(\d+)\s*%s\s+(from\s+now|from\s+today|ago)$" % UNIT_RE, s, I)
        if m:
            n = int(m[1]) * (-1 if m[3].lower() == "ago" else 1)
            return describe(shift(self.today(), n, m[2].lower())), []
        m = re.match(r"^age(?:\s+of)?\s+%s$" % D, s, I)
        if m:
            y, mo, d = age_between(self._date(m[1]), self.today())
            return "%d years, %d months, %d days" % (y, mo, d), []
        m = re.match(r"^(?:weekday|day)\s+of\s+%s$" % D, s, I)
        if m:
            return self._date(m[1]).strftime("%A"), []
        m = re.match(r"^%s$" % D, s, I)
        if m:
            return describe(self._date(m[1])), []
        return None

    # -- main entry ------------------------------------------------------------
    def run(self, text, commit=True):
        """Returns (result_string, steps). Raises CalcError."""
        s = self.normalize(text)
        if not s:
            raise CalcError("")
        d = self.try_date(s)
        if d:
            return d
        steps = []
        m = re.match(r"^(.+?)\s*([A-Za-z°]+)\s+(?:to|in|into)\s+([A-Za-z°]+)$", s)
        if m:
            try:
                val = self.ev(Parser(tokenize(m[1])).parse(), dict(self.vars), steps)
                out = convert(val, m[2], m[3])
            except CalcError:
                out = None
            if out is not None:
                steps.append("%s %s -> %s %s" % (fmt(val), m[2], fmt(out), m[3]))
                if commit:
                    self.ans = out
                return "%s %s" % (fmt(out), m[3]), steps
        env = self.vars if commit else dict(self.vars)
        val = self.ev(Parser(tokenize(s)).parse(), env, steps)
        if commit and not isinstance(val, str):
            self.ans = val
        return fmt(val), steps

    # -- graphing --------------------------------------------------------------
    @staticmethod
    def plot_spec(text):
        """'y = x^2 for x in -5..5' -> ('x^2', -5.0, 5.0); None if not a plot."""
        m = re.match(r"^\s*(?:y|f\(x\))\s*=\s*(.+?)"
                     r"(?:\s+for\s+x\s+in\s+(-?\d+(?:\.\d+)?)\s*\.\.\s*(-?\d+(?:\.\d+)?))?\s*$",
                     text, re.I)
        if not m:
            return None
        lo, hi = (float(m[2]), float(m[3])) if m[2] else (-10.0, 10.0)
        if lo >= hi:
            raise CalcError("Range start must be below its end")
        return m[1], lo, hi

    def sample(self, expr, lo=-10.0, hi=10.0, n=400):
        ast = Parser(tokenize(self.normalize(expr))).parse()
        pts = []
        for i in range(n + 1):
            x = lo + (hi - lo) * i / n
            try:
                y = self.ev(ast, {**self.vars, "x": x}, [])
                pts.append((x, float(y) if not isinstance(y, str) and abs(y) < 1e9 else None))
            except (CalcError, ValueError):
                pts.append((x, None))
        if all(p[1] is None for p in pts):  # surface the real error
            self.ev(ast, {**self.vars, "x": lo + (hi - lo) / 2}, [])
        return pts

    # -- persistence -------------------------------------------------------------
    def export_state(self, history, **extra):
        return {"vars": self.vars, "history": [list(h) for h in history],
                "deg": self.deg, "ans": self.ans, **extra}

    def import_state(self, d):
        self.vars = dict(d.get("vars", {}))
        self.deg = bool(d.get("deg", True))
        self.ans = d.get("ans", 0.0)
        return [tuple(h) for h in d.get("history", [])]


def export_text(history):
    return "\n".join("%s = %s" % h for h in history) + ("\n" if history else "")


def export_csv(history):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["expression", "result"])
    w.writerows(history)
    return buf.getvalue()


HELP = """NOVA CALC - things you can type

Basics       2+3*4   (2+3)^2   5!   10 mod 3   20%   2pi   sqrt(16)
Natural      20% of 850    15 more than 230    what is 5 plus 3
Variables    rent = 12000     tax = 18%     rent * (1 + tax)
Ans          ans * 2  (last result)
Convert      5 km to miles   100 c to f   100 usd to inr   3 hours to min
Graph        y = x^2 - 3x     y = sin(x) for x in -6.28..6.28
Dates        today + 30 days      days between 2026-01-01 and 2026-12-25
             age of 1990-05-14    weekday of 2026-12-25    3 weeks ago
Finance      emi(100000, 12, 1)  (loan, annual %, years)
             compound(1000, 7, 10, 12)   gst(2500, 18)   pctchange(50, 75)
Stats        mean(1,2,3)   median(...)   stdev(...)   sum(...)   ncr(5,2)
Programmer   hex(255)  bin(5)  oct(8)  0xFF  0b101  band bor bxor shl shr

Keys         Enter = save to tape      Up/Down = recall      Esc = clear
             Ctrl+E export   Ctrl+S save sheet   Ctrl+O open sheet   F1 help
Tape         double-click = edit expression, right-click = insert result
Rates        'Rates' button fetches live currency rates (needs internet);
             otherwise approximate offline rates are used."""


# --------------------------------------------------------------------------
# GUI
# --------------------------------------------------------------------------
THEMES = {
    "dark": dict(bg="#14161c", panel="#1d2029", fg="#e8eaf0", accent="#6c8cff",
                 key="#272b37", dim="#8a90a2"),
    "light": dict(bg="#f4f5f9", panel="#ffffff", fg="#1b1e27", accent="#3b5bdb",
                  key="#e6e8f0", dim="#6b7185"),
}
BASE_KEYS = [["C", "⌫", "(", ")", "÷"], ["7", "8", "9", "×", "^"],
             ["4", "5", "6", "−", "!"], ["1", "2", "3", "+", "%"],
             ["0", ".", ",", "Ans", "="]]
MODES = {
    "Standard": [["√", "π", "mod", "x", "y="]],
    "Scientific": [["sin", "cos", "tan", "ln", "log"],
                   ["asin", "acos", "atan", "sqrt", "exp"],
                   ["π", "e", "ncr", "mod", "abs"]],
    "Finance": [["emi", "compound", "gst", "pctchange", "round"]],
    "Programmer": [["hex", "bin", "oct", "0x", "0b"],
                   ["band", "bor", "bxor", "shl", "shr"]],
    "Dates": [["today", "tomorrow", "yesterday", "days between", "age of"],
              ["+ days", "+ weeks", "+ months", "+ years", "weekday of"]],
}
INSERT = {"÷": "/", "×": "*", "−": "-", "√": "sqrt(", "Ans": "ans", "π": "pi",
          "mod": " mod ", "y=": "y = ", "days between": "days between today and ",
          "age of": "age of ", "weekday of": "weekday of ", "+ days": " + 30 days",
          "+ weeks": " + 4 weeks", "+ months": " + 3 months", "+ years": " + 1 years"}


def launch(smoke=False):
    import tkinter as tk
    from tkinter import filedialog, messagebox

    calc = Calc()
    history = []
    cfg = {"theme": "dark", "mode": "Standard", "hpos": None}
    try:
        saved = json.loads(SESSION_FILE.read_text())
        history = calc.import_state(saved)
        cfg["theme"] = saved.get("theme", "dark")
        cfg["mode"] = saved.get("mode", "Standard")
    except (OSError, ValueError):
        pass
    load_cached_rates()

    root = tk.Tk()
    root.title("Nova Calc")
    root.geometry("920x620")
    left = tk.Frame(root)
    left.pack(side="left", fill="both", expand=True, padx=12, pady=12)
    right = tk.Frame(root)
    right.pack(side="right", fill="y", padx=(0, 12), pady=12)

    modebar = tk.Frame(left)
    modebar.pack(fill="x", pady=(0, 8))
    entry = tk.Entry(left, font=("Consolas", 20), bd=0, relief="flat")
    entry.pack(fill="x", ipady=10)
    live = tk.Label(left, font=("Consolas", 22, "bold"), anchor="e", text="0")
    live.pack(fill="x", pady=(6, 10))
    keys = tk.Frame(left)
    keys.pack(fill="both", expand=True)
    status = tk.Label(left, anchor="w", font=("Segoe UI", 9), text="Press F1 for help")
    status.pack(fill="x", pady=(6, 0))
    buttons, modebtns = [], {}

    def say(t):
        status.config(text=t)

    # ---- core actions -------------------------------------------------------
    def update_live(_=None):
        txt = entry.get()
        if not txt.strip():
            live.config(text="0")
            return
        try:
            if calc.plot_spec(txt):
                live.config(text="graph ready - press Enter")
            else:
                live.config(text="= " + calc.run(txt, commit=False)[0])
        except CalcError as e:
            live.config(text=str(e))

    def refresh_vars():
        v = ", ".join("%s=%s" % (k, fmt(x)) for k, x in calc.vars.items())
        varlbl.config(text="Variables: " + (v or "none"))

    def commit(_=None):
        txt = entry.get()
        if not txt.strip():
            return
        try:
            spec = calc.plot_spec(txt)
            if spec:
                show_graph(*spec)
                return
            res, _steps = calc.run(txt)
        except CalcError as e:
            live.config(text=str(e))
            return
        history.append((txt, res))
        tape.insert("end", "%s  =  %s" % (txt, res))
        tape.see("end")
        entry.delete(0, "end")
        live.config(text=res)
        cfg["hpos"] = None
        refresh_vars()

    def put(t):
        entry.insert(entry.index("insert"), t)
        entry.focus_set()
        update_live()

    def clear(_=None):
        entry.delete(0, "end")
        update_live()

    def back():
        i = entry.index("insert")
        if i:
            entry.delete(i - 1)
        update_live()

    def recall(step):
        if not history:
            return "break"
        n = len(history)
        p = n - 1 if cfg["hpos"] is None and step < 0 else \
            (cfg["hpos"] if cfg["hpos"] is not None else n)
        p = min(max(p + (step if cfg["hpos"] is not None else 0), 0), n)
        cfg["hpos"] = p
        entry.delete(0, "end")
        if p < n:
            entry.insert(0, history[p][0])
        update_live()
        return "break"

    # ---- keypad ---------------------------------------------------------------
    def cmd_for(k):
        if k == "C":
            return clear
        if k == "⌫":
            return back
        if k == "=":
            return commit
        return lambda: put(INSERT.get(k, k + "(" if k in calc.funcs else k))

    def build_keys():
        for w in keys.winfo_children():
            w.destroy()
        for r in range(12):
            keys.rowconfigure(r, weight=0)
        buttons.clear()
        for r, row in enumerate(MODES[cfg["mode"]] + BASE_KEYS):
            keys.rowconfigure(r, weight=1)
            for c, k in enumerate(row):
                keys.columnconfigure(c, weight=1)
                b = tk.Button(keys, text=k, command=cmd_for(k), bd=0, relief="flat",
                              font=("Segoe UI", 12), cursor="hand2")
                b.grid(row=r, column=c, sticky="nsew", padx=3, pady=3)
                buttons.append((b, k == "="))

    def set_mode(name):
        cfg["mode"] = name
        build_keys()
        apply_theme()
        say("%s mode" % name)

    for name in MODES:
        b = tk.Button(modebar, text=name, bd=0, relief="flat", cursor="hand2",
                      font=("Segoe UI", 10), padx=8, pady=3,
                      command=lambda n=name: set_mode(n))
        b.pack(side="left", padx=2)
        modebtns[name] = b

    # ---- right panel ------------------------------------------------------------
    tape_lbl = tk.Label(right, text="TAPE   (double-click: edit  |  right-click: use result)",
                        font=("Segoe UI", 8))
    tape_lbl.pack(anchor="w")
    tape = tk.Listbox(right, width=38, height=15, bd=0, font=("Consolas", 11),
                      activestyle="none", highlightthickness=0)
    tape.pack(fill="x")
    varlbl = tk.Label(right, text="Variables: none", justify="left", anchor="w",
                      wraplength=310, font=("Consolas", 10))
    varlbl.pack(fill="x", pady=8)
    bar1, bar2 = tk.Frame(right), tk.Frame(right)
    bar1.pack(fill="x")
    bar2.pack(fill="x", pady=(4, 0))

    def load_tape():
        tape.delete(0, "end")
        for e, r in history:
            tape.insert("end", "%s  =  %s" % (e, r))
        tape.see("end")
        refresh_vars()

    def on_edit(_=None):
        s = tape.curselection()
        if s:
            entry.delete(0, "end")
            entry.insert(0, history[s[0]][0])
            update_live()

    def on_result(ev):
        i = tape.nearest(ev.y)
        if 0 <= i < len(history):
            put(history[i][1].split()[0])

    tape.bind("<Double-Button-1>", on_edit)
    tape.bind("<Button-3>", on_result)
    tape.bind("<Button-2>", on_result)

    # ---- features ---------------------------------------------------------------
    def explain():
        src = entry.get() or (history[-1][0] if history else "")
        try:
            steps = calc.run(src, commit=False)[1]
        except CalcError as e:
            steps = [str(e)]
        messagebox.showinfo("Explain", "\n".join(
            "%d. %s" % (i + 1, s) for i, s in enumerate(steps)) or "Nothing to explain.")

    def toggle_deg():
        calc.deg = not calc.deg
        degbtn.config(text="DEG" if calc.deg else "RAD")
        update_live()

    def toggle_theme():
        cfg["theme"] = "light" if cfg["theme"] == "dark" else "dark"
        apply_theme()

    def do_export(_=None):
        if not history:
            say("Nothing to export yet")
            return
        p = filedialog.asksaveasfilename(defaultextension=".txt", initialfile="nova_tape",
                                         filetypes=[("Text", "*.txt"), ("CSV", "*.csv")])
        if p:
            data = export_csv(history) if p.lower().endswith(".csv") else export_text(history)
            with open(p, "w", encoding="utf-8", newline="") as f:
                f.write(data)
            say("Exported to " + p)

    def save_sheet(_=None):
        p = filedialog.asksaveasfilename(defaultextension=".json", initialfile="sheet",
                                         filetypes=[("Nova sheet", "*.json")])
        if p:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(calc.export_state(history, theme=cfg["theme"], mode=cfg["mode"]), f)
            say("Sheet saved: " + p)

    def open_sheet(_=None):
        p = filedialog.askopenfilename(filetypes=[("Nova sheet", "*.json")])
        if not p:
            return
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
            history[:] = calc.import_state(data)
        except (OSError, ValueError):
            say("Could not open that file")
            return
        load_tape()
        say("Sheet loaded: " + p)

    def do_rates():
        say("Fetching live rates...")
        box = {}

        def work():
            try:
                box["n"] = fetch_rates()
            except Exception as e:  # network errors are expected offline
                box["err"] = str(e)

        threading.Thread(target=work, daemon=True).start()

        def poll():
            if "n" in box:
                say("Live rates updated (%d currencies)" % box["n"])
                update_live()
            elif "err" in box:
                say("Offline - using %s rates" % RATES_META["source"])
            else:
                root.after(200, poll)

        poll()

    def show_help(_=None):
        w = tk.Toplevel(root)
        w.title("Nova Calc help")
        t = tk.Text(w, width=84, height=28, font=("Consolas", 10), bd=0, padx=12, pady=12)
        t.insert("1.0", HELP)
        t.config(state="disabled", bg=THEMES[cfg["theme"]]["panel"],
                 fg=THEMES[cfg["theme"]]["fg"])
        t.pack()

    def show_graph(expr, lo, hi):
        try:
            pts = calc.sample(expr, lo, hi)
        except CalcError as e:
            live.config(text=str(e))
            return
        t = THEMES[cfg["theme"]]
        win = tk.Toplevel(root)
        win.title("y = %s" % expr)
        W, H, M = 640, 440, 36
        cv = tk.Canvas(win, width=W, height=H, bg=t["panel"], highlightthickness=0)
        cv.pack()
        ys = [y for _, y in pts if y is not None]
        if not ys:
            cv.create_text(W / 2, H / 2, text="Nothing to plot", fill=t["dim"])
            return
        ylo, yhi = max(min(ys), -1e4), min(max(ys), 1e4)
        if yhi - ylo < 1e-9:
            ylo, yhi = ylo - 1, yhi + 1
        pad = (yhi - ylo) * .08
        ylo, yhi = ylo - pad, yhi + pad
        sx = lambda x: M + (x - lo) / (hi - lo) * (W - 2 * M)
        sy = lambda y: H - M - (y - ylo) / (yhi - ylo) * (H - 2 * M)
        for i in range(6):  # grid + tick labels
            gx, gy = lo + (hi - lo) * i / 5, ylo + (yhi - ylo) * i / 5
            cv.create_line(sx(gx), M, sx(gx), H - M, fill=t["key"])
            cv.create_line(M, sy(gy), W - M, sy(gy), fill=t["key"])
            cv.create_text(sx(gx), H - M + 12, text="%.3g" % gx, fill=t["dim"], font=("Segoe UI", 8))
            cv.create_text(M - 4, sy(gy), text="%.3g" % gy, fill=t["dim"], anchor="e", font=("Segoe UI", 8))
        if ylo < 0 < yhi:
            cv.create_line(M, sy(0), W - M, sy(0), fill=t["dim"], width=2)
        if lo < 0 < hi:
            cv.create_line(sx(0), M, sx(0), H - M, fill=t["dim"], width=2)
        prev = None
        for x, y in pts:
            if y is None or not ylo <= y <= yhi:
                prev = None
                continue
            p = (sx(x), sy(y))
            if prev:
                cv.create_line(*prev, *p, fill=t["accent"], width=2)
            prev = p
        read = cv.create_text(W - M, 14, anchor="e", fill=t["fg"], font=("Consolas", 10), text="")

        def hover(ev):
            x = lo + (ev.x - M) / (W - 2 * M) * (hi - lo)
            if lo <= x <= hi:
                y = pts[round((x - lo) / (hi - lo) * (len(pts) - 1))][1]
                cv.itemconfig(read, text="x=%.3g   y=%s" % (x, "-" if y is None else "%.4g" % y))

        cv.bind("<Motion>", hover)

    def mk(parent, text, cmd):
        b = tk.Button(parent, text=text, command=cmd, bd=0, relief="flat", cursor="hand2",
                      font=("Segoe UI", 9), padx=7, pady=4)
        b.pack(side="left", padx=2)
        return b

    mk(bar1, "Explain", explain)
    degbtn = mk(bar1, "DEG" if calc.deg else "RAD", toggle_deg)
    mk(bar1, "Theme", toggle_theme)
    mk(bar1, "Help", show_help)
    mk(bar2, "Export", do_export)
    mk(bar2, "Save", save_sheet)
    mk(bar2, "Open", open_sheet)
    mk(bar2, "Rates", do_rates)
    mk(bar2, "Clear", lambda: (history.clear(), load_tape()))

    def apply_theme():
        t = THEMES[cfg["theme"]]
        root.config(bg=t["bg"])
        for w in (left, right, keys, bar1, bar2, modebar):
            w.config(bg=t["bg"])
        entry.config(bg=t["panel"], fg=t["fg"], insertbackground=t["fg"])
        live.config(bg=t["bg"], fg=t["accent"])
        tape.config(bg=t["panel"], fg=t["fg"], selectbackground=t["accent"])
        varlbl.config(bg=t["bg"], fg=t["dim"])
        status.config(bg=t["bg"], fg=t["dim"])
        tape_lbl.config(bg=t["bg"], fg=t["dim"])
        for bar in (bar1, bar2):
            for w in bar.winfo_children():
                w.config(bg=t["key"], fg=t["fg"], activebackground=t["accent"])
        for n, b in modebtns.items():
            on = n == cfg["mode"]
            b.config(bg=t["accent"] if on else t["key"], fg="white" if on else t["fg"],
                     activebackground=t["accent"])
        for b, is_eq in buttons:
            b.config(bg=t["accent"] if is_eq else t["key"],
                     fg="white" if is_eq else t["fg"], activebackground=t["accent"])

    def on_close():
        try:
            SESSION_FILE.write_text(json.dumps(
                calc.export_state(history, theme=cfg["theme"], mode=cfg["mode"])))
        except OSError:
            pass
        root.destroy()

    entry.bind("<KeyRelease>", update_live)
    entry.bind("<Return>", commit)
    entry.bind("<Escape>", clear)
    entry.bind("<Up>", lambda e: recall(-1))
    entry.bind("<Down>", lambda e: recall(1))
    for seq, fn in (("<Control-e>", do_export), ("<Control-s>", save_sheet),
                    ("<Control-o>", open_sheet), ("<F1>", show_help)):
        root.bind(seq, fn)
    root.protocol("WM_DELETE_WINDOW", on_close)
    build_keys()
    load_tape()
    apply_theme()
    entry.focus_set()
    if smoke:
        entry.insert(0, "20% of 850")
        update_live()
        root.update()
        assert live.cget("text") == "= 170", live.cget("text")
        commit()
        set_mode("Dates")
        root.after(300, root.destroy)
    root.mainloop()


# --------------------------------------------------------------------------
# Self-test
# --------------------------------------------------------------------------
def self_test():
    c = Calc()
    c.today = lambda: dt.date(2026, 11, 4)
    cases = [
        ("0.1 + 0.2", "0.3"), ("2 + 3 * 4", "14"), ("(2+3)*4", "20"),
        ("2^3^2", "512"), ("-2^2", "-4"), ("10 mod 3", "1"), ("5!", "120"),
        ("sin(30)", "0.5"), ("sqrt(16)", "4"), ("200 + 10%", "200.1"),
        ("20% of 850", "170"), ("15 more than 230", "245"), ("what is 5 plus 3", "8"),
        ("rent = 12000", "12000"), ("rent * 2", "24000"),
        ("tax = 18%", "0.18"), ("1000 * (1 + tax)", "1180"), ("ans + 1", "1181"),
        ("5 km to miles", "3.10685596119 miles"), ("100 c to f", "212 f"),
        ("100 usd to inr", "8300 inr"), ("3 hours to min", "180 min"),
        ("hex(255)", "0xff"), ("0b101 + 0x10", "21"), ("2pi", "6.28318530718"),
        ("emi(100000, 12, 1)", "8884.87886783"), ("compound(1000, 10, 2)", "1210"),
        ("gst(2500, 18)", "450"), ("pctchange(50, 75)", "50"),
        ("mean(1,2,3,4)", "2.5"), ("median(5,1,3)", "3"), ("sum(1,2,3)", "6"),
        ("stdev(2,4,4,4,5,5,7,9)", "2.1380899353"), ("ncr(5,2)", "10"),
        ("gcd(12,18)", "6"), ("band(12,10)", "8"), ("bxor(5,1)", "4"), ("shl(1,4)", "16"),
        ("today + 30 days", "2026-12-04 (Friday)"),
        ("days between 2026-01-01 and 2026-12-25", "358 days"),
        ("2026-01-31 + 1 month", "2026-02-28 (Saturday)"),
        ("3 weeks ago", "2026-10-14 (Wednesday)"),
        ("age of 1990-05-14", "36 years, 5 months, 21 days"),
        ("weekday of 2026-12-25", "Friday"), ("tomorrow", "2026-11-05 (Thursday)"),
    ]
    bad = 0
    for expr, want in cases:
        got = c.run(expr)[0]
        ok = got == want
        bad += not ok
        print("%s  %-40s -> %s%s" % ("ok " if ok else "BAD", expr, got,
                                      "" if ok else "   (want %s)" % want))
    for expr in ("1/0", "sqrt(-1)", "2 +", "foo + 1", "$", "stdev(1)", "age of 2999-01-01",
                 "days between 2026-13-01 and today"):
        try:
            c.run(expr)
            print("BAD  no error for", expr)
            bad += 1
        except CalcError as e:
            print("ok   %-40s -> error: %s" % (expr, e))

    def check(name, cond):
        nonlocal bad
        print("%s  %s" % ("ok " if cond else "BAD", name))
        bad += not cond

    check("plot spec default", Calc.plot_spec("y = x^2") == ("x^2", -10.0, 10.0))
    check("plot spec range", Calc.plot_spec("y = x^2 for x in -5..5") == ("x^2", -5.0, 5.0))
    check("plot spec ignores normal math", Calc.plot_spec("2+3") is None)
    pts = c.sample("x^2", -2, 2, 4)
    check("graph samples", [round(p[1]) for p in pts] == [4, 1, 0, 1, 4])
    h = [("1+1", "2"), ("x = 5", "5")]
    check("export txt", export_text(h) == "1+1 = 2\nx = 5 = 5\n")
    check("export csv", export_csv(h).splitlines()[1] == "1+1,2")
    c2 = Calc()
    got = c2.import_state(json.loads(json.dumps(c.export_state(h))))
    check("session roundtrip", got == h and c2.vars == c.vars)
    check("parse_rates", parse_rates({"result": "success", "rates": {"USD": 1, "INR": 80.5}})
          == {"usd": 1.0, "inr": 80.5})
    try:
        parse_rates({"result": "error"})
        check("parse_rates rejects errors", False)
    except CalcError:
        check("parse_rates rejects errors", True)
    print("explain:", c.run("(120*1.18)-15", commit=False)[1])
    print("FAILED (%d)" % bad if bad else "ALL PASSED")
    return bad


if __name__ == "__main__":
    if "--test" in sys.argv:
        sys.exit(self_test())
    launch(smoke="--smoke" in sys.argv)