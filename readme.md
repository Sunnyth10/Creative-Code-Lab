# Nova Calc

A desktop calculator with scientific expressions, variables, unit and currency
conversion, graphing, history, and plain-language date calculations.

## Run

```sh
python3 nova_calc.py
```

Choose **Dates** mode for date shortcuts, or type these directly into the
calculator:

| Input | Result |
| --- | --- |
| `100 usd to inr` | Converts using the latest available reference rate; uses a bundled estimate when offline. |
| `today + 30 days` | The resulting date and weekday. Also supports weeks, months, and years. |
| `days between 2026-01-01 and 2026-12-25` | `358 days` |
| `age of 1990-05-14` | Age in years, months, and days. |
| `weekday of 2026-12-25` | The weekday for that date. |

Currency rates are fetched from [Frankfurter](https://frankfurter.dev/) when
available and cached for six hours. If the network is unavailable, the
calculator falls back to its bundled approximate rates.
