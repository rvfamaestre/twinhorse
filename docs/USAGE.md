# Setup and use

Run every command from the repository root. You need Python 3.11 and, for the 3D, Node 20 or newer.

## The data is not in the repo

The data comes from a real assembly line and was only shared for the challenge, so it is not published. The same goes for everything that carries it row by row: `data/processed/`, the CSV and JSON files in `forecast/output/`, the JSON of the 3D and the JSON of the videos.

If you have the two files, put `datos_hackaton.csv` and `config_hackaton.csv` in `data/raw/` and run the steps below in order. The figures, the videos and the `.md` reports are in the repo. They were made with the real data.

## Run it

```bash
# 1. Python environment
python -m venv .venv
.venv\Scripts\activate            # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt   # TimesFM is optional: remove it if you won't forecast

# 2. Cleaning, KPIs and EDA  ->  data/processed/<line>/ and eda/output/<line>/EDA.md
python eda/run_eda.py

# 3. Stop logic  ->  data/processed/logic/logic_state.json and robustez.md
python -m backend.logic --clean data/processed --out data/processed/logic/logic_state.json
python -m backend.logic.robustness --clean data/processed --out data/processed/logic/robustez.md

# 4. Stop type and its figures  ->  data/processed/<line>/stops.csv, stops/output/<line>/STOPS.md
python stops/classify.py
python stops/plots.py

# 5. Forecast (optional, a few minutes on CPU)  ->  forecast/output/<line>/BACKTEST.md and BENCHMARK.md
python forecast/run_forecast.py backtest
python forecast/benchmark.py

# 6. 3D twin  ->  http://localhost:5173
python frontend/scripts/build_mock.py   # joins everything above into the JSON the 3D draws
python -m backend.api                   # API on :8000: serves the line and forecasts on the spot (other terminal)
cd frontend && npm install && npm run dev
```

The 3D needs steps 2 to 5. Without them there is no JSON to draw.

Tests: `python -m pytest` from the root. There are 68. The one that downloads TimesFM only runs with `RUN_TIMESFM=1`, and the ones that read the challenge data are skipped if it is not there.

## Use the 3D twin

The interface has three languages (Español, English, Français). The names below are the English ones.

- Top bar: the engines of the day. In History they are the ones that really left the line up to the time you look at. In Now the day is not over, so the model estimates the total (TimesFM with what was known the day before, `GET /api/estimate`). It uses the day of the week, whether it is the first day after a stop or the eve of one, and the engines and the stopped, starved and blocked hours of the previous days. Click the number to see where it comes from and how far it was from the real data.
- Bottlenecks: the menu next to the bell. It lists the machines that slowed the line that day, with their own stop hours and the hours they make others lose.
- Sections: use ← →, the numbers on the bottom bar, the edges of the screen or a long mouse drag (or two fingers on the trackpad). `V` shows the whole line. The wheel, two fingers vertically or a pinch zoom towards the pointer.
- Straight or Serpentine: the selector on the left of Now and History folds the line into rows. Only the drawing changes. The simulation and the data are the same.
- Click a machine for a quick card: its state (the dot next to the name), who it waits for, how its day went and its indicators. Just data and charts, no sentences.
- Help (?): the legend of states. Each one is explained with a mini animation and the plant lights up only the machines in that state. It also says how to move around.
- Time: Now rebuilds the last day with data at the current time. History lets you choose a day on a calendar, play up to ×600 and jump to any hour.
- Dark mode: the moon button, top right. The browser remembers it.
- Language: the dropdown at the top right, with a flag for each one. It changes the whole interface, the numbers (0,6 / 0.6) and the alerts. The browser remembers it.
- Forecast: the tab at the top, or "Forecast its stops" on a machine card. Choose the series, the days of context, the horizon, the origin day and the model, and the API forecasts on the spot. If the horizon falls on days with data, it is compared with what happened. The band is a gradient (80, 60, 40 and 20 %) with no centre line. It needs `python -m backend.api`.
- Alerts: the bell opens the list, with filters by severity, type, section, station, day and read.

## Repository layout

```
data/raw/            challenge data (datos_hackaton.csv, config_hackaton.csv), not published
data/processed/      generated tables: clean data, KPIs, stop type and the output of the logic (not published)
lines/               what only the plant knows, one file per line: targets, stations out of the flow,
                     subsets and sections
backend/pipeline/    loading, cleaning and KPIs, valid for any line
backend/logic/       states, arrows rule, penalty, sentences and the robustness test
eda/                 exploratory analysis                 ->  eda/output/<line>/EDA.md
stops/               stop type of each machine and day    ->  stops/output/<line>/STOPS.md
forecast/            TimesFM forecast, backtest and benchmark  ->  forecast/output/<line>/
frontend/            the 3D twin (React + three.js), no external services. scripts/build_mock.py
                     joins everything into the JSON it draws
figures/             all the figures, by category: eda/, stops/ and forecast/ (one folder per
                     line) and slides/ (presentation, formulas and diagrams)
slides/              code of the presentation figures (Python) and formulas and diagrams (LaTeX)
tests/               tests of the whole core
docs/                this guide, the results and the first plan of the team
```

Neither the core nor the 3D has station names written in. Only the presentation figures do, and they are for L5. A new line works without touching the code, and what is specific goes in `lines/<line>.json`.

Each folder has its own README with the details.
