<div align="center">

# InsightForge — AI Data Analyst

**Upload any dataset. Get a full data-analytics platform back — automatically.**

Cleaning · EDA with auto-generated charts · KPI dashboard · Automated ML ·
GenAI-written business insights · A chat assistant that writes real SQL
against your data

**Live site:** https://insightforge-ai-data-assistant-enhb.vercel.app

[**Live Demo**](https://insightforge-ai-data-assistant-enhb.vercel.app) · [Report a Bug](#) · [Request a Feature](#)

</div>

---

## What it does

Most "AI data analyst" demos are hardcoded to one sample dataset. InsightForge
isn't — upload *any* CSV, TSV, XLSX, or JSON, and every part of the app
adapts to that file's actual columns, types, and data quality:

| | |
|---|---|
| 📊 **Dashboard** | Auto-selected charts (histograms, bar charts, correlation heatmap, boxplots, time series) with plain-English, numbers-backed captions |
| 🧠 **AI Insights** | A GenAI-written executive summary + business recommendations, grounded in real statistics — not a generic caption |
| 🤖 **Machine Learning** | Pick a target column and it auto-detects classification vs. regression, trains and compares 2–3 models, and reports feature importance. No target? It runs KMeans clustering + PCA instead |
| 📈 **KPI view** | Business-relevant metrics (sales, revenue, cost, etc.) surfaced automatically by column-name detection, plus full stats for every other column |
| 💬 **Chat Assistant** | Ask questions in plain English — it writes and runs real SQL queries against your data (via DuckDB) and can draw new charts on request, with full multi-turn conversation history |

Everything is dataset-agnostic by design — none of it is hardcoded to any
particular schema.

---

## Tech stack

**Backend** — FastAPI · pandas · scikit-learn · Plotly · DuckDB · SQLAlchemy · JWT auth · Groq (Llama)
**Frontend** — React + Vite · Tailwind CSS · Framer Motion · react-three-fiber (3D) · Plotly.js
**Database** — Neon (serverless Postgres, free tier)
**File storage** — Supabase Storage
**Hosting** — Render (backend) · Vercel (frontend)
**Uptime** — UptimeRobot (keeps the free-tier backend warm)

---

## Getting started (local development)

### 1. Get a free Groq API key
Go to **[console.groq.com/keys](https://console.groq.com/keys)**, sign in, create a key.
Groq's free tier serves open models (Llama) extremely fast.

### 2. Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# fill in the values below

uvicorn main:app --reload --port 8000
```

API live at `http://localhost:8000` (interactive docs at `/docs`).

#### Environment variables

| Variable | Purpose | Required locally? |
|---|---|---|
| `GROQ_API_KEY` | Groq LLM access | ✅ |
| `SECRET_KEY` | JWT signing — any random string | ✅ |
| `DATABASE_URL` | Postgres connection string. Falls back to local SQLite if unset. | Optional locally, **required in production** |
| `SUPABASE_URL` | Your Supabase project URL | **Required in production** |
| `SUPABASE_SERVICE_KEY` | Supabase `service_role` secret key | **Required in production** |
| `SUPABASE_BUCKET` | Storage bucket name for uploaded datasets | **Required in production** |

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Vite proxies `/api/*` to the backend on port
8000 in dev — both need to be running.

For production, set `VITE_API_URL` in your host's environment to your
deployed backend's root URL.

### 4. Try it

1. Sign up (password: 8+ chars, upper, lower, number, special character — instant account, no email step).
2. Upload any CSV/XLSX/JSON in **Workspace**.
3. Explore **Dashboard**, **AI Insights**, and **Machine Learning**.
4. Open **Assistant** and ask something specific — e.g. *"what's the average revenue by region?"* or *"write me a SQL query for the top 5 products by revenue"*.

---

## How it works under the hood

- **Cleaning** (`profiler.py`) — strips whitespace, drops duplicates, coerces
  numeric/datetime columns stored as text, imputes missing values.
- **Profiling** — infers a semantic type per column (numeric, categorical,
  datetime, boolean, identifier, text), computes stats, skew, IQR outliers,
  and a correlation matrix.
- **EDA** (`eda.py`) — auto-selects the right chart per situation and writes
  a one-line, numbers-backed caption under each. One shared style function
  keeps every chart visually consistent.
- **ML** (`ml_pipeline.py`) — auto-detects classification vs. regression,
  validates the target column actually has enough class diversity to train
  on (returns a clear message instead of crashing if not), trains multiple
  candidate models, and reports the best one with feature importance.
- **GenAI layer** (`groq_service.py`) — the chat assistant has two tools:
  `generate_chart` and `run_sql_query` (real, read-only SQL via DuckDB —
  destructive statements are blocked). It does a full two-step tool-calling
  round trip: the tool result is fed back to the model before it writes its
  final answer, so replies are grounded in actual numbers.
- **AI Insights** — a separate, stateless one-shot Groq call built from a
  compact statistical summary (never the full dataset or chat history), so
  it can't grow unbounded regardless of dataset size.

---

## Real engineering challenges solved

Building the demo is the easy part — running it reliably on free-tier
infrastructure surfaced a few genuine production problems worth documenting:

- **Ephemeral file storage** — Render's free-tier filesystem wipes on every
  restart/redeploy. Uploaded dataset files were silently disappearing.
  Fixed by moving file storage from local disk to Supabase Storage.
- **Database persistence** — same root issue for the SQLite database itself
  (accounts and datasets vanishing after a redeploy). Fixed by migrating to
  Neon Postgres.
- **CORS across ephemeral preview URLs** — Vercel gives every deploy a
  different subdomain. Fixed with a regex-based CORS policy on the backend
  instead of a hardcoded origin list.
- **Cold-start failures** — Render's free tier sleeps after ~15 minutes
  idle, and cold starts can take 50+ seconds; the waking request often
  fails outright rather than just being slow. Fixed with an automatic
  retry-with-backoff interceptor on the frontend, plus an UptimeRobot
  monitor to reduce how often it happens at all.
- **Unhandled ML edge cases** — an imbalanced or constant target column
  would crash the ML endpoint with a raw scikit-learn error. Fixed by
  validating class diversity up front, stratifying the train/test split,
  and wrapping each candidate model in its own try/except so one model
  failing doesn't take down the whole comparison.
- **Slow model training on limited CPU** — training multiple models on
  larger datasets could exceed the frontend's request timeout on Render's
  free-tier CPU. Fixed by reducing estimator counts, parallelizing Random
  Forest training, and extending the client-side timeout to a realistic
  window.

---

## Extending it further

- **Swap or add an LLM provider** — `groq_service.py` is isolated by design;
  mirror its two functions with another SDK (OpenAI, Anthropic, etc.).
- **Streaming chat** — switch to a `StreamingResponse` + Groq's streaming
  completions for token-by-token replies.
- **Time-series forecasting** — `ml_pipeline.py` already detects datetime
  columns; Prophet/ARIMA would slot in naturally.
- **Multi-column dashboard filters** and category → subcategory drill-down,
  reusing the existing `run_sql_query` machinery.
- **Dataset management UI** — the backend already has a DELETE endpoint for
  datasets; the frontend doesn't expose it yet.

---

<div align="center">

Built as a full-stack portfolio project — feedback and PRs welcome.

</div>


