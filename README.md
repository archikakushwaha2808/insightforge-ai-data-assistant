# InsightForge — AI Data Analyst

Upload any dataset (CSV, TSV, TXT, XLSX, XLS, JSON) and get, automatically:
data cleaning, EDA with charts + plain-English descriptions, a KPI dashboard,
automated ML (classification / regression / clustering with model comparison),
GenAI-written business insights, and a persistent multi-turn chat assistant
that can draw new charts and run real SQL queries against your data on
request. Full dark/light mode, animated 3D hero.

## Stack

- **Backend:** FastAPI, pandas, scikit-learn, Plotly, DuckDB, SQLAlchemy, JWT auth, Groq (Llama)
- **Frontend:** React + Vite, Tailwind CSS, Framer Motion, react-three-fiber (3D), Plotly.js

---

## 1. Get a free Groq API key

Go to **https://console.groq.com/keys**, sign in, and create an API key.
Groq has a generous free tier and serves open models (Llama) extremely fast.

## 2. Backend setup

```bash
cd backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# open .env and fill in GROQ_API_KEY and SECRET_KEY (any random string)

uvicorn main:app --reload --port 8000
```

The API is now live at `http://localhost:8000` (interactive docs at `/docs`).

## 3. Frontend setup

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. The Vite dev server proxies `/api/*` to the
backend on port 8000 (see `vite.config.js`), so both must be running.

## 4. Try it

1. Sign up — passwords must be 8+ characters with an uppercase letter,
   lowercase letter, number, and special character. The account is ready
   immediately, no email step required.
2. Go to **Workspace** and drop in any CSV/XLSX/JSON file.
3. Explore the **Dashboard** tab (KPIs + auto-generated, brand-colored,
   Colab/Power-BI-style charts with descriptions), the **AI Insights** tab
   (AI-written executive summary + recommendations), and the **Machine
   Learning** tab (pick a target column for classification/regression, or
   leave it blank for clustering).
4. Open **Assistant** and ask questions — try both a descriptive question
   ("what is this dataset about") and a specific one ("what's the average
   revenue by region?" or "write me a SQL query for top 5 products by
   revenue") — the assistant picks the right tool automatically and grounds
   its answer in the actual query result, not a generic caption.

---

## How the automated analysis works

- **Cleaning** (`backend/services/profiler.py`): strips whitespace, drops
  duplicates, coerces numeric/datetime columns stored as text, imputes
  missing values (median for numeric, mode for categorical).
- **Profiling**: infers a semantic type per column (numeric, categorical,
  datetime, boolean, identifier, text), computes descriptive stats, skew,
  outlier counts (IQR method), and a correlation matrix. All numeric fields
  are explicitly cast to JSON-safe Python floats (`NaN`/`Infinity` become
  `null`) since raw numpy/NaN values aren't valid JSON.
- **EDA** (`backend/services/eda.py`): auto-selects a relevant chart per
  situation (histograms for numeric spread, bar charts for top categories,
  a correlation heatmap, boxplots for outliers, a time series if a date
  column exists) and writes a one-line, numbers-backed description under
  each chart. Every chart shares one global style function — `plotly_white`
  template, the `#636EFA`/`#00CC96`/`#EF553B`/`#AB63FA`/`#FFA15A` palette,
  Inter font, labeled bars, no modebar — for a consistent, professional look
  across every chart type.
- **ML** (`backend/services/ml_pipeline.py`): with a target column, it
  detects classification vs. regression automatically, trains 2–3 candidate
  models, and reports the best one with feature importance. Without a
  target, it runs KMeans (auto-picking k via silhouette score) + PCA for a
  2D cluster visualization.
- **GenAI layer** (`backend/services/groq_service.py`): the assistant has
  two tools — `generate_chart` (draws a new Plotly chart) and `run_sql_query`
  (runs a real, read-only SQL `SELECT` against your actual uploaded data via
  DuckDB, with destructive statements like `DROP`/`DELETE`/`INSERT` blocked).
  Critically, this does the **full two-step tool-calling round trip**: when
  the model calls a tool, the result is executed and fed *back* to the model
  before it writes its final answer — so replies are grounded in real
  numbers instead of generic captions like "here's the chart you asked for."
  The LLM never sees raw dataset rows except the small result sets it
  explicitly queries — keeps token cost down and avoids dumping the whole
  dataset into every request.

---

## Deployment

**Backend** → Render, Railway, or Fly.io all work well for FastAPI:
- Set `DATABASE_URL` to a managed Postgres instance (Render/Railway both
  offer one free tier).
- Set `GROQ_API_KEY` and a strong `SECRET_KEY` as environment variables.
- Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`

**Frontend** → Vercel or Netlify:
- Build command: `npm run build`, output directory: `dist`
- Set an environment-based API URL (currently the dev proxy targets
  `localhost:8000` — for production, point `src/api/client.js`'s `baseURL`
  at your deployed backend URL instead of `/api`).
- Update the backend's CORS `allow_origins` in `main.py` to include your
  deployed frontend domain.

---

## Extending it further (great talking points for an interview)

- **Swap or add an LLM provider**: `backend/services/groq_service.py` is
  isolated by design — mirror its two functions (`generate_business_insights`,
  `chat`) with another SDK (OpenAI, Anthropic, etc.) to add a second provider.
- **Streaming chat**: switch the `/chat/{id}/message` endpoint to a
  `StreamingResponse` and Groq's streaming completions for token-by-token
  replies.
- **More ML**: add time-series forecasting (Prophet/ARIMA) when a datetime
  column + numeric target are both present — `ml_pipeline.py` already
  detects datetime columns via the profiler.
- **Dashboard filters & drill-down**: today the Dashboard tab shows a fixed
  auto-generated chart gallery. A natural next step is a filter bar (date
  range, category, region) that re-queries `/analysis/{id}/dashboard` with
  query params, plus category → subcategory drill-down using the same
  `run_sql_query` machinery already built for chat.
