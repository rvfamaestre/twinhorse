# Results and limits

The machine that stops the most is not the one that slows the line the most. ST-2390 loses 68 h with its own stops, but it affects nobody else. ST-0260 only loses 11 h by itself, but it makes the machines next to it lose 175 h.

## What we found

The line is VLL_MONTAJE_L5.

| | |
| --- | --- |
| Data | 91 operations × 20 days (16 with production), 22 required hours a day, about 1,530 engines a day |
| Quality of the data | 4 days without production recorded as stops, 161 rows with more than 22 h, 6 broken counters, 1 sensor that bounces and 1 machine out of service. Without cleaning, the top 5 of "the one that stops the most" are all false alarms |
| Where the time goes | Own stop 643 h, starved 2,019 h, blocked 1,263 h. What the neighbours cause weighs 5 times more than what the machine does itself |
| Who slows the line | ST-0260 (186 h of penalty, on all 16 days), ST-0300, PM-2020, ST0261, ST-0830 |
| Who stops the most | ST-2390 (micro-stops of about 26 s), PM2250 (long stops), ST_0100 |
| Forecast | With 16 days, no model beats "same as always" on the exact value. TimesFM does give the best calibrated normal band (78 % of the days inside p10 to p90, the ideal is 80 %), and it is used to warn about unusual days |

All the core is deterministic Python: same input, same output, no randomness and no LLM. The 3D does not calculate anything. It draws what it receives.

## How it works

```
data/raw/datos_hackaton.csv + config_hackaton.csv
   |
   +- 1. Cleaning and KPIs ......... backend/pipeline/ + eda/
   |      8 rules, each row with its warning. Dp, Tcy, Fpm, TAI.
   +- 2. Stop logic ................ backend/logic/
   |      State of each machine and day, arrows rule, penalty index, sentences.
   +- 3. Stop type ................. stops/
   |      Micro-stop, long stop, starved, blocked, unreliable data.
   +- 4. Forecast .................. forecast/ (TimesFM 3.0)
   |      Backtest and benchmark: normal band p10 to p90.
   +- 5. 3D twin ................... frontend/
          Rebuilds the day machine by machine and shows it section by section with warnings.
```

Every machine splits the 22 hours of the day into four states: working (TBF), own stop (TAP), starved (DES, no parts arrive) and blocked (SAT, it can't release its part). Only TAP is its own fault. DES and SAT together are the induced stop (TAI).

| Step | Key formula |
| --- | --- |
| KPIs | Dp = TBF / (TBF + TAP) ≥ 90 % · Tcy = 6000 · TBF / NPR ≤ 80 cmin · Fpm = 1000 · NAP / NPR · TAI = DES + SAT |
| Arrows rule (Kuo, Lim and Meerkov) | i slows the line on day d if SAT(i−1) > DES(i) and DES(i+1) > SAT(i) |
| Penalty index | P(i) = TAP(i) + Σ over the days it slows the line of [SAT(i−1) + DES(i+1)] |
| Warning by band | the TAP of a day goes above the TimesFM p90 by 0.3 h or more |

Here NPR is the number of parts, NAP the number of own stops, and cmin hundredths of a minute. All the formulas are in [`slides/latex/formulas.tex`](../slides/latex/formulas.tex).

## Assumptions and limits

- Topology: the config only has the order of the operations. Parallel machines (ST2376 + ST-2375), side inputs, subsets and buffers are deduced from the data and shown as hypotheses, with a confidence level.
- Time of each stop: the data are daily totals. The 3D spreads the stops over the day with a fixed seed, so the own stops and the engines match the real data, but the waits between machines come from the simulation.
- Forecast: 16 days is little history. The band is good for spotting strange days, not for planning.
- Open questions for the plant: is PM2130 in by-pass? Does ST2235 have a sensor that bounces? Where are the subsets and the manipulators physically?

The first plan of the team, written when the challenge started, is in [PLAN_EQUIPO.md](PLAN_EQUIPO.md) (in Spanish).
