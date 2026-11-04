#!/usr/bin/env python3
"""Nova Calc - a calculator that thinks alongside you.

Run:  python nova_calc.py          (GUI)
      python nova_calc.py --test   (engine self-test)

Features: live results, named variables, history tape, unit/currency
conversion, natural-language input, Explain steps, graphing (y = ...),
finance functions, hex/bin, Deg/Rad, light/dark theme.
"""
import calendar
import datetime as dt
import json
import math
import re
import sys
import time
import urllib.error
import urllib.request

# --------------------------------------------------------------------------
# Engine
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
            t = m.group(1)
            if t.lower().startswith("0x"):
                val = float(int(t, 16))
            elif t.lower().startswith("0b"):
                val = float(int(t, 2))
            else:
                val = float(t)
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
            return ("bin", "^", base, self.unary())  # right-assoc
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


# ---- units -----------------------------------------------------------------
UNITS = {  # name: (group, factor to base)
    **{u: ("len", f) for u, f in {
        "mm": .001, "cm": .01, "m": 1, "km": 1000, "in": .0254, "inch": .0254,
        "ft": .3048, "feet": .3048, "yd": .9144, "mile": 1609.344,
        "miles": 1609.344, "mi": 1609.344}.items()},
    **{u: ("mass", f) for u, f in {
        "mg": 1e-6, "g": .001, "kg": 1, "lb": .45359237, "lbs": .45359237,
        "oz": .028349523}.items()},
    **{u: ("vol", f) for u, f in {
        "ml": .001, "l": 1, "litre": 1, "liter": 1, "gal": 3.785411784,
        "cup": .2365882365}.items()},
    **{u: ("time", f) for u, f in {
        "sec": 1, "s": 1, "min": 60, "hr": 3600, "h": 3600, "day": 86400,
        "days": 86400, "week": 604800}.items()},
}
TEMPS = {"c", "f", "k"}
# Offline fallback rates per 1 USD. Live rates are fetched and cached on demand.
RATES = {"usd": 1.0, "inr": 83.0, "eur": 0.92, "gbp": 0.79, "jpy": 150.0,
         "aud": 1.52, "cad": 1.36, "aed": 3.67}
CURRENCY_CACHE = {}
CURRENCY_LAST_ATTEMPT = {}
CURRENCY_CACHE_TTL = 6 * 60 * 60


def currency_rate(base, quote):
    """Return a recent reference rate, falling back to the bundled estimates offline."""
    base, quote = base.lower(), quote.lower()
    if base == quote:
        return 1.0, None
    now = time.time()
    cached = CURRENCY_CACHE.get((base, quote))
    if cached and now - cached[1] < CURRENCY_CACHE_TTL:
        return cached[0], cached[2]

    # Avoid repeating a failed request on each keystroke in the GUI.
    last_attempt = CURRENCY_LAST_ATTEMPT.get((base, quote), 0)
    if now - last_attempt > 60:
        CURRENCY_LAST_ATTEMPT[(base, quote)] = now
        if re.fullmatch(r"[a-z]{3}", base) and re.fullmatch(r"[a-z]{3}", quote):
            url = "https://api.frankfurter.dev/v2/rate/%s/%s" % (base, quote)
            request = urllib.request.Request(url, headers={"User-Agent": "NovaCalc/1.0"})
            try:
                with urllib.request.urlopen(request, timeout=1.5) as response:
                    data = json.loads(response.read().decode("utf-8"))
                rate = float(data["rate"])
                if math.isfinite(rate) and rate > 0:
                    CURRENCY_CACHE[(base, quote)] = (rate, now, data.get("date"))
                    return rate, data.get("date")
            except (OSError, ValueError, KeyError, TypeError, urllib.error.URLError):
                pass

    if base in RATES and quote in RATES:
        return RATES[quote] / RATES[base], None
    raise CalcError("No rate available for %s to %s (check your connection and currency codes)" %
                    (base.upper(), quote.upper()))


def convert(value, a, b):
    a, b = a.lower().rstrip("°"), b.lower().rstrip("°")
    if a in TEMPS and b in TEMPS:
        c = {"c": value, "f": (value - 32) * 5 / 9, "k": value - 273.15}[a]
        return {"c": c, "f": c * 9 / 5 + 32, "k": c + 273.15}[b]
    if (a in RATES and b in RATES) or (re.fullmatch(r"[a-z]{3}", a) and
                                       re.fullmatch(r"[a-z]{3}", b)):
        rate, _rate_date = currency_rate(a, b)
        return value * rate
    if a in UNITS and b in UNITS:
        if UNITS[a][0] != UNITS[b][0]:
            raise CalcError("Cannot convert %s to %s" % (a, b))
        return value * UNITS[a][1] / UNITS[b][1]
    return None


# ---- finance ---------------------------------------------------------------
def emi(p, annual_rate, years):
    r, n = annual_rate / 1200, years * 12
    if r == 0:
        return p / n
    return p * r * (1 + r) ** n / ((1 + r) ** n - 1)


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


def shift_months(day, months):
    """Add calendar months, clamping to the last valid day of the target month."""
    month_index = day.year * 12 + day.month - 1 + months
    year, month0 = divmod(month_index, 12)
    month = month0 + 1
    return day.replace(year=year, month=month,
                       day=min(day.day, calendar.monthrange(year, month)[1]))


def parse_date(value):
    value = value.strip().lower()
    today = dt.date.today()
    named = {"today": today, "tomorrow": today + dt.timedelta(days=1),
             "yesterday": today - dt.timedelta(days=1)}
    if value in named:
        return named[value]
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise CalcError("Use a date like YYYY-MM-DD, today, tomorrow, or yesterday")


def date_text(day):
    return "%s, %s" % (day.strftime("%A"), day.isoformat())


def age_text(birthday, today):
    if birthday > today:
        raise CalcError("Birth date cannot be in the future")
    months = (today.year - birthday.year) * 12 + today.month - birthday.month
    anchor = shift_months(birthday, months)
    if anchor > today:
        months -= 1
        anchor = shift_months(birthday, months)
    years, remaining_months = divmod(months, 12)
    days = (today - anchor).days
    return "%d years, %d months, %d days" % (years, remaining_months, days)


class Calc:
    def __init__(self):
        self.vars = {}
        self.ans = 0.0
        self.deg = True
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
            "emi": emi, "compound": compound,
            "gst": lambda amt, rate: amt * rate / 100,
            "hex": lambda x: hex(int(x)), "bin": lambda x: bin(int(x)),
            "min": min, "max": max,
        }

    def _a(self, x):
        return math.radians(x) if self.deg else x

    def _r(self, x):
        return math.degrees(x) if self.deg else x

    # -- evaluation ----------------------------------------------------------
    def ev(self, n, env, steps):
        k = n[0]
        if k == "num":
            return n[1]
        if k == "var":
            name = n[1].lower()
            if name in env:
                return env[name]
            if name == "pi":
                return math.pi
            if name == "e":
                return math.e
            if name == "ans":
                return self.ans
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
                r = {"+": lambda: a + b, "-": lambda: a - b,
                     "*": lambda: a * b, "/": lambda: a / b,
                     "mod": lambda: a % b, "^": lambda: a ** b}[op]()
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
            except (ValueError, TypeError, ZeroDivisionError):
                raise CalcError("Invalid input for %s()" % n[1])
            steps.append("%s(%s) = %s" % (n[1], ", ".join(map(fmt, args)), fmt(r)))
            return r
        if k == "assign":
            v = self.ev(n[2], env, steps)
            env[n[1].lower()] = v
            steps.append("%s := %s" % (n[1], fmt(v)))
            return v
        raise CalcError("Bad expression")

    # -- natural language ----------------------------------------------------
    @staticmethod
    def date_expression(text):
        """Evaluate the calculator's plain-language date commands."""
        source = text.strip()
        m = re.fullmatch(r"(today|tomorrow|yesterday)\s*([+-])\s*(\d+)\s*"
                         r"(days?|weeks?|months?|years?)", source, re.I)
        if m:
            day = parse_date(m[1])
            amount = int(m[3]) * (-1 if m[2] == "-" else 1)
            unit = m[4].lower().rstrip("s")
            if unit == "day":
                day += dt.timedelta(days=amount)
            elif unit == "week":
                day += dt.timedelta(weeks=amount)
            else:
                day = shift_months(day, amount * (12 if unit == "year" else 1))
            return date_text(day), "%s %s %s %s -> %s" % (m[1], m[2], m[3], m[4], date_text(day))

        m = re.fullmatch(r"days\s+between\s+(.+?)\s+and\s+(.+)", source, re.I)
        if m:
            start, end = parse_date(m[1]), parse_date(m[2])
            count = abs((end - start).days)
            return "%d days" % count, "Days between %s and %s = %d days" % (
                start.isoformat(), end.isoformat(), count)

        m = re.fullmatch(r"age\s+of\s+(.+)", source, re.I)
        if m:
            birthday = parse_date(m[1])
            result = age_text(birthday, dt.date.today())
            return result, "Age on %s = %s" % (birthday.isoformat(), result)

        m = re.fullmatch(r"weekday\s+of\s+(.+)", source, re.I)
        if m:
            day = parse_date(m[1])
            return day.strftime("%A"), "%s is a %s" % (day.isoformat(), day.strftime("%A"))

        if re.fullmatch(r"today|tomorrow|yesterday", source, re.I):
            day = parse_date(source)
            return date_text(day), date_text(day)
        return None

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

    def run(self, text, commit=True):
        """Returns (result_string, steps). Raises CalcError."""
        date_result = self.date_expression(text)
        if date_result is not None:
            return date_result[0], [date_result[1]]
        s = self.normalize(text)
        if not s:
            raise CalcError("")
        steps = []
        m = re.match(r"^(.+?)\s*([A-Za-z°]+)\s+(?:to|in|into)\s+([A-Za-z°]+)$", s)
        if m:
            try:
                val = self.ev(Parser(tokenize(m[1])).parse(), dict(self.vars), steps)
            except CalcError:
                val = None
            out = convert(val, m[2], m[3]) if val is not None else None
            if out is not None:
                steps.append("%s %s -> %s %s" % (fmt(val), m[2], fmt(out), m[3]))
                rate_info = CURRENCY_CACHE.get((m[2].lower(), m[3].lower()))
                if rate_info and rate_info[2]:
                    steps.append("Reference exchange rate dated %s (Frankfurter)" % rate_info[2])
                elif m[2].lower() in RATES and m[3].lower() in RATES:
                    steps.append("Using bundled offline exchange-rate estimate")
                if commit:
                    self.ans = out
                return "%s %s" % (fmt(out), m[3]), steps
        env = self.vars if commit else dict(self.vars)
        val = self.ev(Parser(tokenize(s)).parse(), env, steps)
        res = fmt(val)
        if commit and not isinstance(val, str):
            self.ans = val
        return res, steps

    def plot_expr(self, text):
        m = re.match(r"^\s*(?:y|f\(x\))\s*=\s*(.+)$", text, re.I)
        return m[1] if m else None

    def sample(self, expr, lo=-10, hi=10, n=400):
        ast = Parser(tokenize(self.normalize(expr))).parse()
        pts = []
        for i in range(n + 1):
            x = lo + (hi - lo) * i / n
            try:
                y = self.ev(ast, {**self.vars, "x": x}, [])
                pts.append((x, y if isinstance(y, float) and abs(y) < 1e9 else None))
            except (CalcError, ValueError):
                pts.append((x, None))
        return pts


# --------------------------------------------------------------------------
# GUI
# --------------------------------------------------------------------------
THEMES = {
    "dark": dict(bg="#12141a", panel="#1b1e27", fg="#e8eaf0", accent="#6c8cff",
                 dim="#8a90a2", key="#272b37", op="#2f3650", clr="#4a2a31",
                 clr_fg="#ff8f9b", err="#ff7b8a"),
    "light": dict(bg="#f2f3f8", panel="#ffffff", fg="#1b1e27", accent="#3b5bdb",
                  dim="#6b7185", key="#e4e7f0", op="#d3dbf6", clr="#fbdfe3",
                  clr_fg="#c92a3d", err="#d6336c"),
}
BASE_KEYS = [["C", "⌫", "(", ")", "÷"], ["7", "8", "9", "×", "^"],
             ["4", "5", "6", "−", "!"], ["1", "2", "3", "+", "%"],
             ["0", ".", "π", "Ans", "="]]
MODES = {
    "Standard": [["√", "mod", "y="]],
    "Scientific": [["sin", "cos", "tan", "ln", "log"],
                   ["asin", "acos", "atan", "sqrt", "exp"]],
    "Finance": [["emi", "compound", "gst", "round"]],
    "Programmer": [["hex", "bin", "0x", "0b"]],
    "Dates": [["today", "tomorrow", "yesterday", "days between", "age of"],
              ["weekday of", "+ days", "+ weeks", "+ months", "+ years"]],
}
INSERT = {"÷": "/", "×": "*", "−": "-", "√": "sqrt(", "Ans": "ans",
          "π": "pi", "mod": " mod ", "y=": "y = ",
          "days between": "days between ", "age of": "age of ",
          "weekday of": "weekday of ", "+ days": "today + 30 days",
          "+ weeks": "today + 4 weeks", "+ months": "today + 3 months",
          "+ years": "today + 1 year"}


def blend(c1, c2, amount):
    """Mix two #rrggbb colours."""
    rgb = lambda c: [int(c[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(
        round(a * (1 - amount) + b * amount)
        for a, b in zip(rgb(c1), rgb(c2)))


def launch():
    import platform
    import tkinter as tk
    from tkinter import messagebox

    system = platform.system()
    ui_font = {"Darwin": "Helvetica Neue", "Windows": "Segoe UI"}.get(system, "DejaVu Sans")
    mono_font = {"Darwin": "Menlo", "Windows": "Consolas"}.get(system, "DejaVu Sans Mono")
    shortcut_mod = "Command" if system == "Darwin" else "Control"
    calc, history = Calc(), []
    cfg = {"theme": "dark", "mode": "Standard", "history_pos": None}
    memory = {"value": None}

    root = tk.Tk()
    root.title("Nova Calc")
    root.geometry("960x660")
    root.minsize(800, 560)
    right = tk.Frame(root)
    right.pack(side="right", fill="both", expand=True, padx=(0, 14), pady=14)
    left = tk.Frame(root)
    left.pack(side="left", fill="both", expand=True, padx=14, pady=14)
    fixed_buttons, pad_buttons = [], []

    modebar = tk.Frame(left)
    modebar.pack(fill="x", pady=(0, 10))
    entry = tk.Entry(left, font=(mono_font, 22), bd=0, relief="flat", highlightthickness=2)
    entry.pack(fill="x", ipady=10)
    liveframe = tk.Frame(left, height=64)
    liveframe.pack(fill="x")
    liveframe.pack_propagate(False)
    live = tk.Label(liveframe, anchor="e", text="0")
    live.pack(fill="both", expand=True)
    keys = tk.Frame(left)
    keys.pack(fill="both", expand=True)
    status = tk.Label(left, anchor="w", font=(ui_font, 10),
                      text="Enter evaluates · ↑/↓ history · Esc clear · F1 help")
    status.pack(fill="x", pady=(8, 0))

    tabbar = tk.Frame(right)
    tabbar.pack(fill="x", pady=(0, 8))
    history_panel = tk.Frame(right)
    graph_panel = tk.Frame(right)
    history_panel.pack(fill="both", expand=True)

    tk.Label(history_panel, anchor="w", font=(ui_font, 10),
             text="TAPE   double-click: edit   |   right-click: use result").pack(fill="x", pady=(0, 4))
    tape = tk.Listbox(history_panel, width=40, height=16, bd=0, font=(mono_font, 12),
                      activestyle="none", highlightthickness=0)
    tape.pack(fill="both", expand=True)
    memorybar = tk.Frame(history_panel)
    memorybar.pack(fill="x", pady=(8, 0))
    memory_status = tk.Label(memorybar, text="Memory: empty", anchor="w", font=(mono_font, 10))
    memory_status.pack(fill="x", pady=(0, 4))
    memory_buttons = tk.Frame(memorybar)
    memory_buttons.pack(fill="x")
    varlbl = tk.Label(history_panel, text="Variables: none", justify="left", anchor="w",
                      wraplength=330, font=(mono_font, 10))
    varlbl.pack(fill="x", pady=10)
    toolbar = tk.Frame(history_panel)
    toolbar.pack(fill="x")

    def paint(button, state="normal"):
        t = THEMES[cfg["theme"]]
        bg, fg = ((t["accent"], "#fff") if button.kind == "eq" or
                  (button.kind == "mode" and button.on) else
                  (t["clr"], t["clr_fg"]) if button.kind == "clear" else
                  (t["op"], t["fg"]) if button.kind == "op" else (t["key"], t["fg"]))
        if state == "hover":
            bg = blend(bg, "#ffffff" if cfg["theme"] == "dark" else "#000000", .10)
        elif state == "down":
            bg = blend(bg, t["accent"], .35)
        button.config(bg=bg, fg=fg)

    def mkbtn(parent, text, command, kind="key", font=None, **kw):
        button = tk.Label(parent, text=text, font=font or (ui_font, 14), cursor="hand2", **kw)
        button.kind, button.command, button.on = kind, command, False
        button.bind("<Enter>", lambda _e: paint(button, "hover"))
        button.bind("<Leave>", lambda _e: paint(button))
        button.bind("<Button-1>", lambda _e: paint(button, "down"))
        def released(event):
            paint(button, "hover")
            if 0 <= event.x < button.winfo_width() and 0 <= event.y < button.winfo_height():
                button.command()
        button.bind("<ButtonRelease-1>", released)
        paint(button)
        return button

    tab_buttons = {}
    def show_panel(name):
        history_panel.pack_forget()
        graph_panel.pack_forget()
        (history_panel if name == "History" else graph_panel).pack(fill="both", expand=True)
        for tab_name, button in tab_buttons.items():
            button.on = tab_name == name
            paint(button)
        if name == "Graph" and graph_state["expr"] is not None:
            draw_graph()

    for tab_name in ("History", "Graph"):
        button = mkbtn(tabbar, tab_name, lambda n=tab_name: show_panel(n), "mode",
                       font=(ui_font, 11), padx=14, pady=7)
        button.pack(side="left", padx=(0, 5))
        tab_buttons[tab_name] = button
        fixed_buttons.append(button)

    graph_controls = tk.Frame(graph_panel, padx=8, pady=8)
    graph_controls.pack(fill="x")
    tk.Label(graph_controls, text="x min", font=(ui_font, 10)).pack(side="left")
    x_min = tk.Entry(graph_controls, width=8)
    x_min.insert(0, "-10")
    x_min.pack(side="left", padx=(4, 9))
    tk.Label(graph_controls, text="x max", font=(ui_font, 10)).pack(side="left")
    x_max = tk.Entry(graph_controls, width=8)
    x_max.insert(0, "10")
    x_max.pack(side="left", padx=(4, 8))
    graph_status = tk.Label(graph_controls, text="Enter y = expression", anchor="w",
                            font=(ui_font, 9))
    graph_status.pack(side="left", fill="x", expand=True, padx=4)
    plot_button = mkbtn(graph_controls, "Plot", lambda: draw_graph(),
                        font=(ui_font, 10), padx=9, pady=4)
    plot_button.pack(side="right")
    fixed_buttons.append(plot_button)
    graph_canvas = tk.Canvas(graph_panel, width=480, height=440, highlightthickness=0)
    graph_canvas.pack(fill="both", expand=True, padx=4, pady=(0, 4))
    graph_state = {"expr": None, "points": [], "xlo": -10.0, "xhi": 10.0,
                   "readout": None, "redraw_id": None}

    def show(text, kind="ok"):
        t = THEMES[cfg["theme"]]
        live.config(text=text, fg={"ok": t["accent"], "err": t["err"], "hint": t["dim"]}[kind],
                    font=(mono_font, 27, "bold") if kind == "ok" else (ui_font, 13))

    def say(text):
        status.config(text=text)

    def refresh_vars():
        values = ", ".join("%s=%s" % (k, fmt(v)) for k, v in calc.vars.items())
        varlbl.config(text="Variables: " + (values or "none"))

    def update_live(_event=None):
        text = entry.get()
        if not text.strip():
            show("0", "hint")
            return
        try:
            graph_expr = calc.plot_expr(text)
            if graph_expr:
                show("Graph ready · press Enter", "hint")
                if graph_state["expr"] is not None:
                    if not graph_panel.winfo_manager():
                        show_panel("Graph")
                    if graph_state["redraw_id"]:
                        root.after_cancel(graph_state["redraw_id"])
                    graph_state["redraw_id"] = root.after(120, draw_graph)
            else:
                show("= " + calc.run(text, commit=False)[0])
        except CalcError as exc:
            message = str(exc)
            incomplete = message == "Unexpected end" or message.startswith("Expected")
            show("…" if incomplete else message, "hint" if incomplete else "err")

    def put(text):
        entry.insert(entry.index("insert"), text)
        entry.focus_set()
        update_live()

    def clear(_event=None):
        entry.delete(0, "end")
        update_live()

    def back():
        pos = entry.index("insert")
        if pos:
            entry.delete(pos - 1)
        update_live()

    def draw_graph(_event=None):
        graph_state["redraw_id"] = None
        source = entry.get()
        expression = calc.plot_expr(source) if source.strip() else None
        expression = expression or graph_state["expr"]
        if expression is None:
            graph_status.config(text="Enter y = expression")
            return
        try:
            xlo, xhi = float(x_min.get()), float(x_max.get())
            if not math.isfinite(xlo) or not math.isfinite(xhi) or xlo >= xhi:
                raise ValueError
            points = calc.sample(expression, xlo, xhi)
        except ValueError:
            graph_status.config(text="Enter finite x limits with min < max")
            return
        except CalcError as exc:
            graph_status.config(text="Expression: " + str(exc))
            return

        graph_state.update(expr=expression, xlo=xlo, xhi=xhi, points=points)
        graph_status.config(text="")
        t = THEMES[cfg["theme"]]
        graph_canvas.config(bg=t["panel"])
        graph_canvas.delete("all")
        graph_state["readout"] = None
        width = max(graph_canvas.winfo_width(), 320)
        height = max(graph_canvas.winfo_height(), 280)
        margin = 48
        ys = [y for _, y in points if y is not None]
        if not ys:
            graph_canvas.create_text(width / 2, height / 2, text="Nothing to plot", fill=t["dim"])
            graph_state["readout"] = graph_canvas.create_text(
                width - margin, 14, anchor="e", fill=t["fg"], font=(mono_font, 10),
                text="Move over the graph for coordinates")
            return
        ylo, yhi = min(ys), max(ys)
        if yhi - ylo < 1e-9:
            ylo, yhi = ylo - 1, yhi + 1
        else:
            pad = (yhi - ylo) * .08
            ylo, yhi = ylo - pad, yhi + pad
        sx = lambda x: margin + (x - xlo) / (xhi - xlo) * (width - 2 * margin)
        sy = lambda y: height - margin - (y - ylo) / (yhi - ylo) * (height - 2 * margin)
        for i in range(6):
            gx = xlo + (xhi - xlo) * i / 5
            gy = ylo + (yhi - ylo) * i / 5
            graph_canvas.create_line(sx(gx), margin, sx(gx), height - margin, fill=t["key"])
            graph_canvas.create_line(margin, sy(gy), width - margin, sy(gy), fill=t["key"])
            graph_canvas.create_text(sx(gx), height - margin + 14, text="%.3g" % gx, fill=t["dim"])
            graph_canvas.create_text(margin - 7, sy(gy), text="%.3g" % gy,
                                     fill=t["dim"], anchor="e")
        if ylo < 0 < yhi:
            graph_canvas.create_line(margin, sy(0), width - margin, sy(0), fill=t["dim"], width=2)
        if xlo < 0 < xhi:
            graph_canvas.create_line(sx(0), margin, sx(0), height - margin, fill=t["dim"], width=2)
        previous = None
        for x, y in points:
            if y is None or not ylo <= y <= yhi:
                previous = None
                continue
            point = (sx(x), sy(y))
            if previous:
                graph_canvas.create_line(*previous, *point, fill=t["accent"], width=2)
            previous = point
        graph_state["readout"] = graph_canvas.create_text(
            width - margin, 14, anchor="e", fill=t["fg"], font=(mono_font, 10),
            text="Move over the graph for coordinates")

    def show_coordinates(event):
        width = max(graph_canvas.winfo_width(), 320)
        margin = 48
        if (not graph_state["points"] or graph_state["readout"] is None or
                not margin <= event.x <= width - margin):
            return
        ratio = (event.x - margin) / (width - 2 * margin)
        index = round(ratio * (len(graph_state["points"]) - 1))
        x, y = graph_state["points"][index]
        value = "undefined" if y is None else "%.5g" % y
        graph_canvas.itemconfig(graph_state["readout"], text="x = %.5g    y = %s" % (x, value))

    graph_canvas.bind("<Motion>", show_coordinates)
    for field in (x_min, x_max):
        field.bind("<Return>", draw_graph)
    graph_canvas.bind("<Configure>", lambda _e: draw_graph() if graph_state["expr"] else None)

    def commit(_event=None):
        text = entry.get()
        if not text.strip():
            return
        graph = calc.plot_expr(text)
        if graph:
            graph_state["expr"] = graph
            show_panel("Graph")
            draw_graph()
            return
        try:
            result, _steps = calc.run(text)
        except CalcError as exc:
            show(str(exc), "err")
            return
        history.append((text, result))
        tape.insert("end", "%s  =  %s" % (text, result))
        tape.see("end")
        entry.delete(0, "end")
        cfg["history_pos"] = None
        show(result)
        refresh_vars()

    def set_memory(value):
        memory["value"] = value
        memory_status.config(text="Memory: " + ("empty" if value is None else fmt(value)))

    def memory_recall():
        if memory["value"] is None:
            say("Memory is empty")
            return "break"
        put(fmt(memory["value"]))
        return "break"

    def memory_clear():
        set_memory(None)
        say("Memory cleared")
        return "break"

    def memory_adjust(sign):
        source = entry.get().strip()
        if not source:
            say("Enter a number before using M+ or M−")
            return "break"
        try:
            result = calc.run(source, commit=False)[0]
            value = float(result)
            if not math.isfinite(value):
                raise ValueError
        except (CalcError, TypeError, ValueError):
            say("M+ and M− need a finite numeric result")
            return "break"
        current = memory["value"] or 0.0
        set_memory(current + sign * value)
        say("Added to memory" if sign > 0 else "Subtracted from memory")
        return "break"

    def recall(direction):
        if not history:
            return "break"
        pos = cfg["history_pos"]
        pos = len(history) - 1 if pos is None and direction < 0 else len(history) if pos is None else min(max(pos + direction, 0), len(history))
        cfg["history_pos"] = pos
        entry.delete(0, "end")
        if pos < len(history):
            entry.insert(0, history[pos][0])
        update_live()
        return "break"

    def edit_history(_event=None):
        selected = tape.curselection()
        if selected:
            entry.delete(0, "end")
            entry.insert(0, history[selected[0]][0])
            update_live()

    def use_result(event):
        index = tape.nearest(event.y)
        if 0 <= index < len(history):
            put(history[index][1].split()[0])

    tape.bind("<Double-Button-1>", edit_history)
    tape.bind("<Button-2>", use_result)
    tape.bind("<Button-3>", use_result)

    def explain():
        source = entry.get() or (history[-1][0] if history else "")
        try:
            steps = calc.run(source, commit=False)[1]
        except CalcError as exc:
            steps = [str(exc)]
        messagebox.showinfo("Explain", "\n".join("%d. %s" % (i + 1, step)
                                                  for i, step in enumerate(steps)) or "Nothing to explain.")

    def toggle_deg():
        calc.deg = not calc.deg
        deg_button.config(text="DEG" if calc.deg else "RAD")
        update_live()

    mode_buttons = {}
    def build_keys():
        for widget in keys.winfo_children():
            widget.destroy()
        pad_buttons.clear()
        rows = MODES[cfg["mode"]] + BASE_KEYS
        for row, values in enumerate(rows):
            keys.rowconfigure(row, weight=1, uniform="rows")
            for col, key in enumerate(values):
                keys.columnconfigure(col, weight=1, uniform="cols")
                if key == "C":
                    command, kind = clear, "clear"
                elif key == "⌫":
                    command, kind = back, "clear"
                elif key == "=":
                    command, kind = commit, "eq"
                else:
                    text = INSERT.get(key, key + "(" if key in calc.funcs else key)
                    command = lambda value=text: put(value)
                    kind = "op" if key in ("÷", "×", "−", "+", "^", "!", "%", "(", ")") else "key"
                button = mkbtn(keys, key, command, kind,
                               font=(ui_font, 15 if len(key) < 3 else 11))
                button.grid(row=row, column=col, sticky="nsew", padx=3, pady=3)
                pad_buttons.append(button)

    def set_mode(name):
        cfg["mode"] = name
        build_keys()
        apply_theme()
        say(name + " mode")

    for name in MODES:
        button = mkbtn(modebar, name, lambda n=name: set_mode(n), "mode",
                       font=(ui_font, 10), padx=10, pady=6)
        button.pack(side="left", padx=(0, 4))
        mode_buttons[name] = button
        fixed_buttons.append(button)

    def tool(text, command):
        button = mkbtn(toolbar, text, command, font=(ui_font, 10), padx=8, pady=6)
        button.pack(side="left", padx=(0, 4))
        fixed_buttons.append(button)
        return button

    def memory_tool(text, command):
        button = mkbtn(memory_buttons, text, command, font=(ui_font, 10), padx=8, pady=6)
        button.pack(side="left", fill="x", expand=True, padx=(0, 4))
        fixed_buttons.append(button)
        return button

    memory_tool("MC", memory_clear)
    memory_tool("MR", memory_recall)
    memory_tool("M−", lambda: memory_adjust(-1))
    memory_tool("M+", lambda: memory_adjust(1))

    tool("Explain", explain)
    deg_button = tool("DEG", toggle_deg)
    def toggle_theme():
        cfg["theme"] = "light" if cfg["theme"] == "dark" else "dark"
        apply_theme()
    tool("Theme", toggle_theme)
    tool("Clear tape", lambda: (history.clear(), tape.delete(0, "end"), refresh_vars()))

    def apply_theme():
        t = THEMES[cfg["theme"]]
        root.config(bg=t["bg"])
        for widget in (left, right, keys, modebar, liveframe, toolbar, memorybar,
                       memory_buttons, tabbar, history_panel, graph_panel, graph_controls):
            widget.config(bg=t["bg"])
        entry.config(bg=t["panel"], fg=t["fg"], insertbackground=t["fg"],
                     highlightbackground=t["panel"], highlightcolor=t["accent"])
        live.config(bg=t["bg"])
        tape.config(bg=t["panel"], fg=t["fg"], selectbackground=t["accent"], selectforeground="#fff")
        varlbl.config(bg=t["bg"], fg=t["dim"])
        memory_status.config(bg=t["bg"], fg=t["dim"])
        status.config(bg=t["bg"], fg=t["dim"])
        graph_status.config(bg=t["bg"], fg=t["dim"])
        for parent in (right, history_panel, graph_panel, graph_controls):
            for widget in parent.winfo_children():
                if isinstance(widget, tk.Label):
                    widget.config(bg=t["bg"], fg=t["dim"])
        for field in (x_min, x_max):
            field.config(bg=t["panel"], fg=t["fg"], insertbackground=t["fg"])
        for button in fixed_buttons + pad_buttons:
            button.on = ((button in mode_buttons.values() and mode_buttons.get(cfg["mode"]) is button)
                         or (button in tab_buttons.values() and
                             tab_buttons.get("Graph" if graph_panel.winfo_manager() else "History") is button))
            paint(button)
        if graph_state["expr"] is not None and graph_panel.winfo_manager():
            draw_graph()
        update_live()

    entry.bind("<KeyRelease>", update_live)
    entry.bind("<Return>", commit)
    entry.bind("<KP_Enter>", commit)
    entry.bind("<Escape>", clear)
    entry.bind("<Up>", lambda _e: recall(-1))
    entry.bind("<Down>", lambda _e: recall(1))
    root.bind("<%s-l>" % shortcut_mod, clear)
    root.bind("<%s-d>" % shortcut_mod, lambda _e: (toggle_deg(), "break")[1])
    root.bind("<%s-m>" % shortcut_mod, lambda _e: memory_recall())
    root.bind("<%s-Shift-m>" % shortcut_mod, lambda _e: memory_clear())
    root.bind("<%s-Shift-equal>" % shortcut_mod, lambda _e: memory_adjust(1))
    root.bind("<%s-Shift-minus>" % shortcut_mod, lambda _e: memory_adjust(-1))
    root.bind("<F1>", lambda _e: messagebox.showinfo(
        "Nova Calc help", "Enter expressions or assignments such as rent = 12000.\n"
        "Use y = expression to graph, and value unit to unit to convert.\n"
        "Right-click a tape entry to reuse its result.\n\n"
        "Esc clears input · %s+L clears · %s+D toggles DEG/RAD\n"
        "%s+M recalls memory · %s+Shift+M clears memory\n"
        "%s+Shift+= adds to memory · %s+Shift+- subtracts from memory" %
        ("⌘" if shortcut_mod == "Command" else "Ctrl",) * 6))

    build_keys()
    apply_theme()
    entry.focus_set()
    root.mainloop()


# --------------------------------------------------------------------------
def self_test():
    c = Calc()
    cases = [
        ("0.1 + 0.2", "0.3"), ("2 + 3 * 4", "14"), ("(2+3)*4", "20"),
        ("2^3^2", "512"), ("-2^2", "-4"), ("10 mod 3", "1"), ("5!", "120"),
        ("sin(30)", "0.5"), ("sqrt(16)", "4"), ("200 + 10%", "200.1"),
        ("20% of 850", "170"), ("15 more than 230", "245"),
        ("rent = 12000", "12000"), ("rent * 2", "24000"),
        ("tax = 18%", "0.18"), ("1000 * (1 + tax)", "1180"),
        ("5 km to miles", "3.10685596119 miles"), ("100 c to f", "212 f"),
        ("hex(255)", "0xff"), ("0b101 + 0x10", "21"), ("2pi", "6.28318530718"),
        ("emi(100000, 12, 1)", "8884.87886783"),
    ]
    bad = 0
    for expr, want in cases:
        got = c.run(expr)[0]
        ok = got == want
        bad += not ok
        print("%s  %-24s -> %s%s" % ("ok " if ok else "BAD", expr, got,
                                      "" if ok else "   (want %s)" % want))
    for expr in ("1/0", "sqrt(-1)", "2 +", "foo + 1", "$"):
        try:
            c.run(expr)
            print("BAD  no error for", expr)
            bad += 1
        except CalcError as e:
            print("ok   %-24s -> error: %s" % (expr, e))
    print("explain:", c.run("(120*1.18)-15", commit=False)[1])
    print("FAILED" if bad else "ALL PASSED")
    return bad


if __name__ == "__main__":
    sys.exit(self_test()) if "--test" in sys.argv else launch()
