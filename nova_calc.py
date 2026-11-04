#!/usr/bin/env python3
"""Nova Calc - a calculator that thinks alongside you.

Run:  python nova_calc.py          (GUI)
      python nova_calc.py --test   (engine self-test)

Features: live results, named variables, history tape, unit/currency
conversion, natural-language input, Explain steps, graphing (y = ...),
finance functions, hex/bin, Deg/Rad, light/dark theme.
"""
import math
import re
import sys

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
# Offline, approximate rates per 1 USD - edit these or plug in a live API.
RATES = {"usd": 1.0, "inr": 83.0, "eur": 0.92, "gbp": 0.79, "jpy": 150.0,
         "aud": 1.52, "cad": 1.36, "aed": 3.67}


def convert(value, a, b):
    a, b = a.lower().rstrip("°"), b.lower().rstrip("°")
    if a in TEMPS and b in TEMPS:
        c = {"c": value, "f": (value - 32) * 5 / 9, "k": value - 273.15}[a]
        return {"c": c, "f": c * 9 / 5 + 32, "k": c + 273.15}[b]
    if a in RATES and b in RATES:
        return value / RATES[a] * RATES[b]
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
        s = self.normalize(text)
        if not s:
            raise CalcError("")
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
    "dark": dict(bg="#14161c", panel="#1d2029", fg="#e8eaf0", accent="#6c8cff",
                 key="#272b37", dim="#8a90a2"),
    "light": dict(bg="#f4f5f9", panel="#ffffff", fg="#1b1e27", accent="#3b5bdb",
                  key="#e6e8f0", dim="#6b7185"),
}


def launch():
    import tkinter as tk
    from tkinter import messagebox

    calc = Calc()
    root = tk.Tk()
    root.title("Nova Calc")
    root.geometry("860x560")
    theme = {"name": "dark"}
    history = []  # (expr, result)

    left = tk.Frame(root)
    left.pack(side="left", fill="both", expand=True, padx=12, pady=12)
    right = tk.Frame(root)
    right.pack(side="right", fill="y", padx=(0, 12), pady=12)

    entry = tk.Entry(left, font=("Consolas", 20), bd=0, relief="flat")
    entry.pack(fill="x", ipady=10)
    live = tk.Label(left, font=("Consolas", 22, "bold"), anchor="e", text="0")
    live.pack(fill="x", pady=(6, 10))
    keys = tk.Frame(left)
    keys.pack(fill="both", expand=True)

    def update_live(_=None):
        txt = entry.get()
        if not txt.strip():
            live.config(text="0")
            return
        try:
            if calc.plot_expr(txt):
                live.config(text="graph ready (press Enter)")
            else:
                live.config(text="= " + calc.run(txt, commit=False)[0])
        except CalcError as e:
            live.config(text=str(e) if str(e) else "")

    def commit(_=None):
        txt = entry.get()
        if not txt.strip():
            return
        try:
            gx = calc.plot_expr(txt)
            if gx:
                show_graph(gx)
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
        refresh_vars()

    def put(t):
        entry.insert(entry.index("insert"), t)
        entry.focus_set()
        update_live()

    def clear():
        entry.delete(0, "end")
        update_live()

    def back():
        i = entry.index("insert")
        if i:
            entry.delete(i - 1)
        update_live()

    layout = [["C", "⌫", "(", ")", "÷"],
              ["sin", "cos", "tan", "ln", "log"],
              ["7", "8", "9", "×", "^"],
              ["4", "5", "6", "−", "√"],
              ["1", "2", "3", "+", "!"],
              ["0", ".", "%", "Ans", "="]]
    ins = {"÷": "/", "×": "*", "−": "-", "√": "sqrt(", "Ans": "ans",
           "sin": "sin(", "cos": "cos(", "tan": "tan(", "ln": "ln(", "log": "log("}
    buttons = []
    for r, row in enumerate(layout):
        keys.rowconfigure(r, weight=1)
        for c, k in enumerate(row):
            keys.columnconfigure(c, weight=1)
            cmd = (clear if k == "C" else back if k == "⌫" else commit if k == "="
                   else (lambda t=ins.get(k, k): put(t)))
            b = tk.Button(keys, text=k, command=cmd, font=("Segoe UI", 14), bd=0,
                          relief="flat", cursor="hand2")
            b.grid(row=r, column=c, sticky="nsew", padx=3, pady=3)
            buttons.append((b, k == "="))

    tk.Label(right, text="TAPE  (double-click: edit, right-click: use result)",
             font=("Segoe UI", 8)).pack(anchor="w")
    tape = tk.Listbox(right, width=36, height=14, bd=0, font=("Consolas", 11),
                      activestyle="none", highlightthickness=0)
    tape.pack(fill="x")
    varlbl = tk.Label(right, text="Variables: none", justify="left",
                      anchor="w", wraplength=290, font=("Consolas", 10))
    varlbl.pack(fill="x", pady=8)
    bar = tk.Frame(right)
    bar.pack(fill="x")

    def refresh_vars():
        v = ", ".join("%s=%s" % (k, fmt(x)) for k, x in calc.vars.items())
        varlbl.config(text="Variables: " + (v or "none"))

    def sel():
        s = tape.curselection()
        return history[s[0]] if s else None

    def reuse_expr(_=None):
        h = sel()
        if h:
            entry.delete(0, "end")
            entry.insert(0, h[0])
            update_live()

    def reuse_result(ev):
        i = tape.nearest(ev.y)
        if 0 <= i < len(history):
            put(history[i][1].split()[0])

    tape.bind("<Double-Button-1>", reuse_expr)
    tape.bind("<Button-3>", reuse_result)
    tape.bind("<Button-2>", reuse_result)

    def explain():
        try:
            _, steps = calc.run(entry.get() or (history[-1][0] if history else ""),
                                commit=False)
        except CalcError as e:
            steps = [str(e)]
        messagebox.showinfo("Explain", "\n".join(
            "%d. %s" % (i + 1, s) for i, s in enumerate(steps)) or "Nothing to explain.")

    def toggle_deg():
        calc.deg = not calc.deg
        degbtn.config(text="DEG" if calc.deg else "RAD")
        update_live()

    def show_graph(expr):
        try:
            pts = calc.sample(expr)
        except CalcError as e:
            live.config(text=str(e))
            return
        win = tk.Toplevel(root)
        win.title("y = " + expr)
        W, H = 620, 420
        cv = tk.Canvas(win, width=W, height=H, bg=THEMES[theme["name"]]["panel"],
                       highlightthickness=0)
        cv.pack()
        ys = [y for _, y in pts if y is not None]
        if not ys:
            cv.create_text(W / 2, H / 2, text="Nothing to plot", fill="gray")
            return
        lo, hi = max(min(ys), -50), min(max(ys), 50)
        if hi - lo < 1e-9:
            lo, hi = lo - 1, hi + 1
        pad = (hi - lo) * .1
        lo, hi = lo - pad, hi + pad
        sx = lambda x: (x + 10) / 20 * W
        sy = lambda y: H - (y - lo) / (hi - lo) * H
        cv.create_line(0, sy(0), W, sy(0), fill="#888")
        cv.create_line(sx(0), 0, sx(0), H, fill="#888")
        prev = None
        for x, y in pts:
            if y is None or not lo <= y <= hi:
                prev = None
                continue
            p = (sx(x), sy(y))
            if prev:
                cv.create_line(*prev, *p, fill="#ff6b6b", width=2)
            prev = p
        cv.create_text(8, 8, anchor="nw", fill="#888",
                       text="x: -10..10   y: %.3g..%.3g" % (lo, hi))

    def toggle_theme():
        theme["name"] = "light" if theme["name"] == "dark" else "dark"
        apply_theme()

    def mk(text, cmd):
        b = tk.Button(bar, text=text, command=cmd, bd=0, relief="flat",
                      cursor="hand2", font=("Segoe UI", 10), padx=8, pady=4)
        b.pack(side="left", padx=2)
        return b

    mk("Explain", explain)
    degbtn = mk("DEG", toggle_deg)
    mk("Theme", toggle_theme)
    mk("Clear tape", lambda: (tape.delete(0, "end"), history.clear()))

    def apply_theme():
        t = THEMES[theme["name"]]
        root.config(bg=t["bg"])
        for w in (left, right, keys, bar):
            w.config(bg=t["bg"])
        entry.config(bg=t["panel"], fg=t["fg"], insertbackground=t["fg"])
        live.config(bg=t["bg"], fg=t["accent"])
        tape.config(bg=t["panel"], fg=t["fg"], selectbackground=t["accent"])
        varlbl.config(bg=t["bg"], fg=t["dim"])
        for w in right.winfo_children():
            if isinstance(w, tk.Label) and w is not varlbl:
                w.config(bg=t["bg"], fg=t["dim"])
        for w in bar.winfo_children():
            w.config(bg=t["key"], fg=t["fg"], activebackground=t["accent"])
        for b, is_eq in buttons:
            b.config(bg=t["accent"] if is_eq else t["key"],
                     fg="white" if is_eq else t["fg"], activebackground=t["accent"])

    entry.bind("<KeyRelease>", update_live)
    entry.bind("<Return>", commit)
    entry.bind("<Escape>", lambda e: clear())
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
