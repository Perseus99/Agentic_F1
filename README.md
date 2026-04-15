# TwinTrack — Digital Twin Economic Simulator

TwinTrack lets a small business owner register their business as a **digital twin** — a structured snapshot of their financials, costs, and sales profile — and then run **what-if simulations** before making real decisions.

Each simulation runs a full pipeline:
1. Pulls live economic data (CPI, unemployment, GDP, consumer spending, local market density, news sentiment)
2. Resolves industry codes and computes elasticity modifiers using a local LLM agent
3. Models the financial outcome under the proposed change
4. Returns **OP1** (control baseline) and **OP2** (experiment result) with a plain-English recommendation and a confidence score

---

## Simulation Use Cases

| Use case | What it models |
|----------|---------------|
| **Pricing changes** | Raise or lower average price; demand response via price elasticity derived from live YoY CPI trends |
| **Target audience** | Shift to a new demographic segment; models ticket size, footfall, and marketing cost impact weighted by actual census income distribution |
| **Franchise expansion** | Open new locations; distinguishes franchisee-operated (royalty only) vs. company-owned (full revenue); amortises upfront costs over 36 months |

---

## Architecture

```
twintrack/          ← React 19 + Vite frontend (port 5173)
backend/
  server.py         ← ThreadingHTTPServer (port 8765)
  agents/           ← Multi-agent system (Ollama-backed)
    base.py               ← Shared Ollama client + tool-use loop
    sim_state.py          ← Shared pipeline state object (passed between agents)
    orchestrator.py       ← Python coordinator sequencing the agents
    data_agent.py         ← NAICS/MSA resolution + news sentiment scoring
    enrichment_agent.py   ← NL parameter extraction from user descriptions
    elasticity_agent.py   ← Calibrates formula elasticity values with business context
    critique_agent.py     ← ReAct loop: checks OP1→OP2 vs market snapshot, applies confidence penalty
    simulation_agent.py   ← Generates plain-English recommendation from final OP delta
    scenario_agent.py     ← Proposes 2–3 ranked simulation scenarios from market + business signals
  ml/               ← Market data + forecasting layer
    fetcher.py      ← FRED, BLS, BEA, Census, NewsData.io
    context.py      ← NAICS/MSA resolver (agent-backed)
    elasticity.py   ← Formula-based price / labor / demand / market elasticity
    forecaster.py   ← ARIMA 2-month projections (pmdarima auto-ARIMA or statsmodels fallback)
    sentiment.py    ← Thin wrapper delegating news scoring to data_agent
    ms_builder.py   ← Builds the market snapshot (MS) JSON
    main.py         ← ML pipeline entry point
  sim/
    sim_bridge.py   ← Translates frontend form → IP1/IP2
    sim_layer.py    ← Financial simulation engine + confidence score
  data/
    base/           ← Enrollment JSON files
    ms/             ← Market snapshot outputs
    op/             ← Simulation outputs (OP1 + OP2)
    cache/          ← API response cache (by date)
```

### Request flow

```
Frontend → POST /api/simulate { business_id, sim }
  → server.py: load twin from disk, recompute IP1
  → orchestrator.run_simulate_pipeline()
      → ui_sim_to_ip2()              build IP2 from sim params
      → build_market_snapshot()      fetch live data (FRED/BLS/BEA/Census/News)
          → elasticity_agent (Ollama)  calibrate formula elasticity with business context
                                     → ms/ms_base_<bizid>_<date>.json
      → enrichment_agent (Ollama)    extract NL params (if description provided)
      → sim_layer.run_simulation()   rules-based financial engine → {op1, op2}
      → critique_agent (Ollama)      ReAct loop: flag contradictions, apply confidence penalty
      → simulation_agent (Ollama)    generate plain-English recommendation
  → return {ok, result: {op1, op2, recommendation, use_case, agent_log}}

Frontend → POST /api/suggest-scenarios { business_id }
  → server.py: load twin + latest market snapshot
  → scenario_agent (Ollama)         propose 2–3 ranked simulation scenarios
  → return {ok, scenarios: [...]}
```

---

## Simulation Engine Details

### Elasticity modifiers (`ml/elasticity.py`)

Four modifiers are computed from live data and applied to the simulation:

| Modifier | Inputs | Notes |
|----------|--------|-------|
| `price_elasticity` | FRED CPI (YoY rate), BEA sector spending | Uses YoY growth rate, not absolute CPI level; thresholds: >6% = high inflation |
| `labor_elasticity` | BLS unemployment, BLS wage trend | Low unemployment → expensive, hard-to-hire market |
| `demand_elasticity` | BEA sector spending, FRED GDP trend | Ranges −1.0 (contracting) to +1.0 (growing) |
| `market_elasticity` | Census CBP establishment count | Summed across all 50 states, normalised per 100k US population |

### Confidence score (`sim/sim_layer.py`)

Three components, each 0–1, weighted into a final 0–100% score:

```
score = 0.30 × input_plausibility
      + 0.40 × assumption_alignment
      + 0.30 × forecast_quality
```

- **Input plausibility** — checks that revenue > 0, margin is within 0–90%, and that any proposed price change or franchise margin are physically reasonable
- **Assumption alignment** — checks whether the proposed decision conflicts with market conditions (e.g. raising prices during high CPI and falling consumer spending)
- **Forecast quality** — ARIMA forecast uncertainty band width (upper − lower / mean); defaults to 0.35 (penalised) when insufficient data for ARIMA
- A **critique agent** (ReAct loop) applies an additional −0.05 to −0.30 penalty after reviewing the OP1→OP2 delta against the market snapshot

### Metric explanations (`sim/sim_layer.py`)

`_build_explanations()` runs after the use-case formula and produces a plain-English sentence for each output metric, referencing the exact parameter values that drove it — no LLM involved.  The result is attached to `op2.explanations` and rendered in the dashboard under each KPI card.

| Use case | What each explanation cites |
|---|---|
| **pricing** | Price elasticity value used, % volume change, fixed vs variable cost split, sentiment label |
| **target_audience** | Demographic segment (18–34 / 35–54 / 55+), reach increase %, marketing spend %, income tier |
| **franchising** | Location count, trade-zone overlap rule (70%), ownership model (royalty % vs company-owned), saturation discount, amortisation period |

### Revenue projections

OP1 and OP2 revenue projections use an **exponential decay** to converge over time:

```python
decayed_ratio = 1.0 + (decision_ratio - 1.0) × 0.92^month
```

This prevents the simulation from projecting a permanent fixed gap between control and experiment — the uplift (or decline) gradually fades toward baseline as market forces re-equilibrate.

### News relevance

News articles are fetched via **NewsData.io** using NAICS-keyed search terms (e.g. NAICS 722515 → `"coffee cafe beverage"`). The sentiment agent is instructed to exclude articles unrelated to the specific business type and local market, returning an empty flags list when fewer than 2 articles are genuinely relevant.

---

## Setup

### Prerequisites
- Python 3.10+
- Node.js 18+
- [Ollama](https://ollama.com) with `qwen2.5:7b` pulled

### 1. Clone and install

```bash
# Python dependencies (from repo root)
pip install -r requirements.txt

# Frontend dependencies
cd twintrack
npm install
```

### 2. Pull the LLM model

```bash
ollama pull qwen2.5:7b
```

### 3. Environment variables

Copy `.env.example` to `.env` and fill in your API keys:

```env
FRED_API_KEY=...
BLS_API_KEY=...
BEA_API_KEY=...
CENSUS_API_KEY=...
NEWSDATA_API_KEY=...
```

| Key | Where to get it |
|-----|----------------|
| `FRED_API_KEY` | [fred.stlouisfed.org/docs/api](https://fred.stlouisfed.org/docs/api/api_key.html) |
| `BLS_API_KEY` | [data.bls.gov/registrationEngine](https://data.bls.gov/registrationEngine/) |
| `BEA_API_KEY` | [apps.bea.gov/API/signup](https://apps.bea.gov/API/signup/) |
| `CENSUS_API_KEY` | [api.census.gov/data/key_signup.html](https://api.census.gov/data/key_signup.html) |
| `NEWSDATA_API_KEY` | [newsdata.io](https://newsdata.io) |

> No cloud LLM keys required — all AI runs locally via Ollama.

### 4. Run

**Terminal 1 — Ollama (if not already running):**
```bash
ollama serve
```

**Terminal 2 — backend:**
```bash
python backend/server.py
# Listening on http://127.0.0.1:8765
```

**Terminal 3 — frontend:**
```bash
cd twintrack
npm run dev
# Running on http://localhost:5173
```

Open **http://localhost:5173** in your browser.

---

## Usage

### Step 1 — Register your business
Go to **Register business** in the sidebar. Enter your financials, cost breakdown, loan details, sales channel, and product info. The server assigns a `business_id` (integer, starting at 1) and writes a JSON twin to `backend/data/base/`.

### Step 2 — Run a simulation
Go to **Run simulation**. Select your registered business, pick a use case, fill in the parameters, and optionally describe your decision in plain English. The enrichment agent extracts and merges structured parameters from your description — no need to fill in every numeric field.

Click **Run simulation engine** to execute the full pipeline.

### Step 3 — View results
The dashboard shows:
- Revenue, margin, profit, foot traffic, and COGS delta (OP2 vs OP1)
- Per-metric causal explanations — rules-based text stating exactly why each figure changed (e.g. elasticity value used, volume shift %, cost drivers)
- Revenue projection line chart with shared "Now" anchor and convergence decay
- Confidence score (model trustworthiness, not environment favorability)
- News sentiment with relevant flags for your business type and market
- Plain-English recommendation from the simulation agent, opening with a clear verdict: **PROCEED**, **PROCEED WITH CAUTION**, or **DO NOT PROCEED**

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Server health check |
| `GET` | `/api/enrollments` | List all enrolled businesses |
| `POST` | `/api/save-twin-layer` | Register a new business |
| `POST` | `/api/update-twin-layer` | Update business financials (versioned) |
| `POST` | `/api/simulate` | Run a what-if simulation, returns OP1 + OP2 (with `explanations` block) + recommendation + agent_log |
| `POST` | `/api/suggest-scenarios` | Returns 2–3 ranked simulation scenarios generated by the Scenario Agent |

---

## Data Sources

| Source | What it provides |
|--------|-----------------|
| **FRED** (St. Louis Fed) | CPI (YoY rate), interest rates, GDP |
| **BLS** (Bureau of Labor Statistics) | Unemployment rate and labor force by metro area |
| **BEA** (Bureau of Economic Analysis) | Personal consumption expenditure by sector (quarterly) |
| **Census CBP** | Business establishment counts by NAICS sector across all states |
| **Census ACS** | Local demographics — population, median income, age, income distribution |
| **NewsData.io** | Recent news for the business category, filtered by NAICS-keyed search terms |

All API responses are cached to `backend/data/cache/` by date. Repeat runs on the same day reuse the cache.

---

## LLM / Agent Integration

Six local Ollama (`qwen2.5:7b`) agents, each with a specific role:

| Agent | When it runs | What it does |
|-------|-------------|--------------|
| **Data Agent** | ML layer (every run) | Resolves `business_type + city + state` → `naics_code + msa_code`; scores and filters news sentiment |
| **Elasticity Agent** | ML layer (every run) | Takes formula-derived elasticity values, adjusts them using business type and local market reasoning |
| **Enrichment Agent** | Before simulation (if NL description provided) | Extracts structured IP2 parameters from plain-English description; only overrides keys explicitly mentioned |
| **Critique Agent** | After simulation (every run) | ReAct loop: flags contradictions between OP1→OP2 projections and market context; applies −0.05 to −0.30 confidence penalty |
| **Simulation Agent** | After critique (every run) | Writes a 2–3 sentence verdict grounded in the final OP delta numbers; opens with **PROCEED**, **PROCEED WITH CAUTION**, or **DO NOT PROCEED** based on profit direction, margin change (>5pp threshold), break-even length, and confidence score |
| **Scenario Agent** | On-demand via `/api/suggest-scenarios` | Reads market snapshot + business financials and proposes 2–3 ranked simulation scenarios with pre-filled parameters |

All agents degrade gracefully — if Ollama is unavailable, the pipeline continues with rule-based fallbacks.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 19, Vite 5 |
| Backend | Python 3 `http.server.ThreadingHTTPServer` |
| Forecasting | `pmdarima` auto-ARIMA (falls back to `statsmodels` ARIMA(1,1,1)) |
| LLM | Ollama `qwen2.5:7b` via OpenAI-compatible API |
| Agent framework | Custom tool-use loop (`backend/agents/base.py`) |
| Data | `pandas`, `requests` |
| Config | `python-dotenv` |

---

## File Naming Convention

| Layer | Pattern |
|-------|---------|
| Enrollment | `input_newbusiness_<date>.json` |
| Market snapshot | `ms_base_<bizid>_<date>.json` (base) / `ms_<usecase>_<bizid>_<date>.json` (experiment) |
| Simulation output | `op_<usecase>_<bizid>_<date>.json` |
| API cache | `<source>_<suffix>_<date>.json` |
