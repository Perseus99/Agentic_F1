# TwinTrack — Digital Twin Economic Simulator

## What It Does

TwinTrack lets a small business owner register their business as a **digital twin** — a structured snapshot of their financials, costs, and sales profile — and then run **what-if simulations** before making real decisions.

Each simulation runs a full pipeline:
1. Pulls live economic data (CPI, unemployment, GDP, consumer spending, local market density, news sentiment)
2. Computes price elasticity and market context using a local LLM agent
3. Models the financial outcome under the proposed change
4. Returns OP1 (control baseline) and OP2 (experiment result) with a plain-English recommendation

**Three use cases:**
- **Pricing changes** — raise or lower average price; models demand response via price elasticity derived from CPI trends
- **Target audience** — shift to a new demographic segment; models ticket size, footfall, and marketing cost impact
- **Franchise expansion** — open new locations; models upfront costs, amortized over 36 months, with break-even projection

---

## Architecture

```
twintrack/          ← React + Vite frontend (port 5173)
backend/
  server.py         ← ThreadingHTTPServer (port 8765)
  agents/           ← Multi-agent system (Ollama-backed)
    base.py         ← Shared Ollama client + agentic tool-use loop
    data_agent.py   ← NAICS/MSA resolution + news sentiment
    enrichment_agent.py  ← NL parameter extraction from user descriptions
    simulation_agent.py  ← Demographic resolution + recommendation generation
    orchestrator.py ← Python coordinator sequencing the agents
  ml/               ← Market data + forecasting layer
    fetcher.py      ← FRED, BLS, BEA, Census, NewsAPI
    context.py      ← NAICS/MSA resolver (agent-backed)
    elasticity.py   ← Price/labor/market elasticity
    forecaster.py   ← ARIMA 12-month projections
    sentiment.py    ← News sentiment scoring (agent-backed)
    ms_builder.py   ← Builds MS (market snapshot) JSON
    main.py         ← ML pipeline entry point
  sim/
    sim_bridge.py   ← Translates frontend form → IP1/IP2
    sim_layer.py    ← Financial simulation engine
  data/
    base/           ← Enrollment JSON files
    ms/             ← Market snapshot outputs
    op/             ← Simulation outputs (OP1 + OP2)
    cache/          ← API response cache (by date)
```

**Request flow for a simulation:**
```
Frontend → Run simulation engine (UI)
  → load twin layer from disk
  → NL enrichment agent (if description provided)
  → ml_run()         → ms/ms_exp_<bizid>_<date>.json
  → run_simulation() → {op1, op2}
  → write_op()       → op/op_<usecase>_<bizid>_<date>.json
  → recommendation agent
  → return {op1, op2, recommendation}
```

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

| Key | Get it from |
|-----|-------------|
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
Go to **Register business** in the sidebar. Enter your financials, cost breakdown, loan details, sales channel, and product info. The server assigns a `business_id` (integer, starting at 1) and writes:
- `backend/data/base/input_newbusiness_<date>.json`

### Step 2 — Run a simulation
Go to **Run simulation**. Select your registered business, pick a use case, and optionally describe your decision in plain English. The enrichment agent will extract and merge structured parameters from your description — no need to fill in every numeric field.

Click **Run simulation engine** to execute the full pipeline. Results appear as OP1 (control) and OP2 (experiment) with an Ollama-generated recommendation.

### Step 3 — View results
The dashboard shows:
- Revenue, margin, and footfall delta (OP2 vs OP1)
- 6-month revenue projection chart (ARIMA)
- Confidence score
- News sentiment (from local market news)
- Plain-English recommendation

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Server health check |
| `GET` | `/api/enrollments` | List all enrolled businesses |
| `POST` | `/api/save-twin-layer` | Register a new business |
| `POST` | `/api/update-twin-layer` | Update business financials (versioned) |

> Simulations are run through the UI only — there is no scripted `/api/simulate` endpoint.

---

## Data Sources

| Source | What it provides |
|--------|-----------------|
| **FRED** (St. Louis Fed) | CPI, interest rates, GDP |
| **BLS** (Bureau of Labor Statistics) | Unemployment by metro area |
| **BEA** (Bureau of Economic Analysis) | Consumer spending by sector |
| **Census** | Business density by NAICS + metro |
| **NewsData.io** | Local news sentiment for the business category |

All API responses are cached to `backend/data/cache/` by date. Repeat runs on the same day reuse the cache.

---

## LLM / Agent Integration

Three local Ollama (`qwen2.5:7b`) agent calls in the pipeline:

1. **Data Agent** — resolves `business_type + city + state` → `naics_code + msa_code`; also handles news sentiment analysis
2. **Enrichment Agent** — extracts structured simulation parameters from the optional plain-English description on step 3; only overrides keys explicitly mentioned
3. **Simulation Agent** — writes a 2–3 sentence recommendation grounded in the actual OP delta numbers (revenue, margin, footfall, confidence score)

All three calls degrade gracefully — if Ollama is unavailable, the pipeline continues without LLM output.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 19, Vite 5 |
| Backend | Python 3 `http.server.ThreadingHTTPServer` |
| Forecasting | `statsmodels` ARIMA, `pmdarima` auto-ARIMA |
| LLM | Ollama `qwen2.5:7b` via OpenAI-compatible API |
| Agent framework | Custom tool-use loop (`backend/agents/base.py`) |
| Data | `pandas`, `requests` |
| Config | `python-dotenv` |

---

## File Naming Convention

| Layer | Pattern |
|-------|---------|
| Enrollment | `input_newbusiness_<date>.json` |
| Market snapshot | `ms_exp_<bizid>_<date>.json` |
| Simulation output | `op_<usecase>_<bizid>_<date>.json` |

---

*Built at WEHack UTD · April 2026*
