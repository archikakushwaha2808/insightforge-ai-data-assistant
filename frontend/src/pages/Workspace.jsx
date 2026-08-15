import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Sparkles, TrendingUp, BrainCog, LayoutDashboard, AlertTriangle, FileClock, Gauge, Filter, X } from 'lucide-react'
import client from '../api/client'
import UploadDropzone from '../components/UploadDropzone'
import KpiCard from '../components/KpiCard'
import ChartCard from '../components/ChartCard'

const TABS = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'insights', label: 'AI Insights', icon: Sparkles },
  { id: 'ml', label: 'Machine Learning', icon: BrainCog },
  { id: 'kpi', label: 'KPI', icon: Gauge },
]

function extractErrorMessage(err) {
  return err?.response?.data?.detail || err?.message || 'Something went wrong. Please try again.'
}

export default function Workspace() {
  const [dataset, setDataset] = useState(null)
  const [recentDatasets, setRecentDatasets] = useState([])
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState('')
  const [tab, setTab] = useState('dashboard')

  const [dashboardData, setDashboardData] = useState(null)
  const [insights, setInsights] = useState(null)
  const [mlResult, setMlResult] = useState(null)
  const [targetCol, setTargetCol] = useState('')

  // Power BI-style slicer: pick a categorical/date column + value, and the
  // KPI cards + charts below recompute over just the matching rows.
  const [filterColumn, setFilterColumn] = useState('')
  const [filterValue, setFilterValue] = useState('')

  const [loadingDashboard, setLoadingDashboard] = useState(false)
  const [loadingInsights, setLoadingInsights] = useState(false)
  const [loadingMl, setLoadingMl] = useState(false)
  const [insightsError, setInsightsError] = useState('')
  const [mlError, setMlError] = useState('')

  // Restore the last-used dataset on mount, and fetch the list of previously
  // uploaded datasets so re-analysis never requires a fresh upload.
  useEffect(() => {
    const savedId = localStorage.getItem('insightforge-last-dataset-id')
    const savedName = localStorage.getItem('insightforge-last-dataset-name')
    if (savedId && savedName) {
      setDataset({ dataset_id: Number(savedId), filename: savedName })
    }
    client.get('/datasets/').then((res) => setRecentDatasets(res.data)).catch(() => {})
  }, [])

  const selectDataset = (id, filename) => {
    localStorage.setItem('insightforge-last-dataset-id', String(id))
    localStorage.setItem('insightforge-last-dataset-name', filename)
    setDataset({ dataset_id: id, filename })
    setDashboardData(null)
    setInsights(null)
    setMlResult(null)
    setInsightsError('')
    setMlError('')
    setFilterColumn('')
    setFilterValue('')
  }

  const handleUpload = async (file) => {
    setUploading(true)
    setUploadError('')
    const formData = new FormData()
    formData.append('file', file)
    try {
      const res = await client.post('/datasets/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      selectDataset(res.data.dataset_id, res.data.filename)
    } catch (err) {
      setUploadError(extractErrorMessage(err))
    } finally {
      setUploading(false)
    }
  }

  // Dashboard/profile data loads as soon as a dataset is selected — not only
  // when the Dashboard tab is opened — because the ML tab's target-column
  // dropdown depends on this same profile data.
  const loadDashboard = useCallback(async () => {
    if (!dataset) return
    setLoadingDashboard(true)
    try {
      const params = {}
      if (filterColumn && filterValue) {
        params.filter_column = filterColumn
        params.filter_value = filterValue
      }
      const res = await client.get(`/analysis/${dataset.dataset_id}/dashboard`, { params })
      setDashboardData(res.data)
    } catch (err) {
      setUploadError(extractErrorMessage(err))
    } finally {
      setLoadingDashboard(false)
    }
  }, [dataset, filterColumn, filterValue])

  useEffect(() => {
    if (dataset) loadDashboard()
  }, [dataset, filterColumn, filterValue, loadDashboard])

  const loadInsights = useCallback(async () => {
    if (!dataset) return
    setLoadingInsights(true)
    setInsightsError('')
    try {
      const res = await client.get(`/analysis/${dataset.dataset_id}/insights`)
      setInsights(res.data)
    } catch (err) {
      setInsightsError(extractErrorMessage(err))
    } finally {
      setLoadingInsights(false)
    }
  }, [dataset])

  const runMl = useCallback(async (target) => {
    if (!dataset) return
    setLoadingMl(true)
    setMlError('')
    try {
      const res = await client.post(`/analysis/${dataset.dataset_id}/ml`, null, {
        params: target ? { target_column: target } : {},
        timeout: 60000, // model training can legitimately take longer than the default
      })
      setMlResult(res.data)
    } catch (err) {
      setMlError(extractErrorMessage(err))
    } finally {
      setLoadingMl(false)
    }
  }, [dataset])

  useEffect(() => {
    if (!dataset) return
    if (tab === 'insights' && !insights && !insightsError) loadInsights()
    if (tab === 'ml' && !mlResult && !mlError) runMl(null)
  }, [tab, dataset])

  const startOver = () => {
    localStorage.removeItem('insightforge-last-dataset-id')
    localStorage.removeItem('insightforge-last-dataset-name')
    setDataset(null)
    setDashboardData(null)
    setInsights(null)
    setMlResult(null)
    setInsightsError('')
    setMlError('')
  }

  if (!dataset) {
    return (
      <div className="max-w-3xl mx-auto px-6 py-20">
        <h1 className="font-display text-3xl font-semibold mb-2 text-center">Bring your dataset</h1>
        <p className="text-muted text-center mb-10">
          It'll be cleaned, profiled, and visualized automatically — no setup needed.
        </p>

        {recentDatasets.length > 0 && (
          <div className="mb-8">
            <p className="text-xs font-mono uppercase tracking-wider text-muted mb-3 flex items-center gap-2">
              <FileClock size={13} /> Continue with a previous upload
            </p>
            <div className="flex flex-wrap gap-2">
              {recentDatasets.map((d) => (
                <button
                  key={d.id}
                  onClick={() => selectDataset(d.id, d.filename)}
                  className="px-4 py-2 rounded-full border border-border hover:border-signal-cyan text-sm transition-colors"
                >
                  {d.filename} <span className="text-muted">· {d.row_count.toLocaleString()} rows</span>
                </button>
              ))}
            </div>
          </div>
        )}

        <UploadDropzone onUpload={handleUpload} uploading={uploading} />
        {uploadError && (
          <p className="mt-4 text-sm text-signal-magenta flex items-center gap-2 justify-center">
            <AlertTriangle size={14} /> {uploadError}
          </p>
        )}
      </div>
    )
  }

  return (
    <div className="max-w-7xl mx-auto px-6 py-10">
      <div className="flex flex-wrap items-center justify-between gap-4 mb-8">
        <div>
          <h1 className="font-display text-2xl font-semibold">{dataset.filename}</h1>
          {dashboardData?.profile && (
            <p className="text-sm text-muted">
              {dashboardData.profile.n_rows.toLocaleString()} rows · {dashboardData.profile.n_cols} columns
            </p>
          )}
        </div>
        <button
          onClick={startOver}
          className="text-sm px-4 py-2 rounded-full border border-border hover:border-signal-cyan transition-colors"
        >
          Upload a different file
        </button>
      </div>

      <div className="flex gap-2 mb-8 border-b border-border">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors
              ${tab === t.id ? 'border-signal-cyan text-ink' : 'border-transparent text-muted hover:text-ink'}`}
          >
            <t.icon size={15} /> {t.label}
          </button>
        ))}
      </div>

      <AnimatePresence mode="wait">
        {tab === 'dashboard' && (
          <motion.div key="dashboard" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            {dashboardData?.filterable_columns?.length > 0 && (
              <div className="flex flex-wrap items-center gap-3 mb-6 p-4 rounded-2xl border border-border bg-surface/30">
                <span className="flex items-center gap-1.5 text-xs font-mono uppercase tracking-wider text-muted">
                  <Filter size={13} /> Filter
                </span>
                <select
                  value={filterColumn}
                  onChange={(e) => { setFilterColumn(e.target.value); setFilterValue('') }}
                  className="px-3 py-2 rounded-lg bg-surface/50 border border-border text-sm outline-none focus:border-signal-cyan"
                >
                  <option value="">All data</option>
                  {dashboardData.filterable_columns.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
                {filterColumn && (
                  <select
                    value={filterValue}
                    onChange={(e) => setFilterValue(e.target.value)}
                    className="px-3 py-2 rounded-lg bg-surface/50 border border-border text-sm outline-none focus:border-signal-cyan"
                  >
                    <option value="">Choose a value…</option>
                    {(dashboardData.profile.columns.find((c) => c.name === filterColumn)?.top_values
                      ? Object.keys(dashboardData.profile.columns.find((c) => c.name === filterColumn).top_values)
                      : []
                    ).map((v) => <option key={v} value={v}>{v}</option>)}
                  </select>
                )}
                {filterColumn && filterValue && (
                  <button
                    onClick={() => { setFilterColumn(''); setFilterValue('') }}
                    className="flex items-center gap-1 text-xs text-muted hover:text-signal-magenta transition-colors"
                  >
                    <X size={12} /> Clear
                  </button>
                )}
                {dashboardData.filters_applied && (
                  <span className="text-xs text-muted ml-auto">
                    Showing {dashboardData.filtered_row_count.toLocaleString()} of {dashboardData.profile.n_rows.toLocaleString()} rows
                  </span>
                )}
              </div>
            )}
            {loadingDashboard && (
              <div className="py-24 text-center text-muted">
                <div className="inline-block w-8 h-8 border-2 border-signal-cyan border-t-transparent rounded-full animate-spin mb-4" />
                <p>Crunching the numbers…</p>
              </div>
            )}
            {!loadingDashboard && dashboardData && (
              <>
                <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8">
                  {dashboardData.kpis.map((k, i) => <KpiCard key={k.label} {...k} index={i} />)}
                </div>
                <div className="grid md:grid-cols-2 gap-5">
                  {dashboardData.charts.map((c, i) => <ChartCard key={c.title} chart={c} index={i} />)}
                </div>
              </>
            )}
            {!loadingDashboard && !dashboardData && (
              <p className="text-signal-magenta text-sm flex items-center gap-2 py-12 justify-center">
                <AlertTriangle size={14} /> Couldn't load the dashboard. Try uploading again.
              </p>
            )}
          </motion.div>
        )}

        {tab === 'insights' && (
          <motion.div key="insights" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="space-y-8 max-w-3xl">
            {loadingInsights && (
              <div className="py-24 text-center text-muted">
                <div className="inline-block w-8 h-8 border-2 border-signal-cyan border-t-transparent rounded-full animate-spin mb-4" />
                <p>Asking the AI analyst…</p>
              </div>
            )}
            {!loadingInsights && insightsError && (
              <div className="py-12 text-center">
                <p className="text-signal-magenta text-sm flex items-center gap-2 justify-center mb-3">
                  <AlertTriangle size={14} /> {insightsError}
                </p>
                <button onClick={loadInsights} className="text-sm text-signal-cyan hover:underline">Try again</button>
                <p className="text-xs text-muted mt-4 max-w-md mx-auto">
                  This usually means the backend's GROQ_API_KEY in .env is missing, still the
                  placeholder value, or invalid — check the terminal running uvicorn for the
                  actual error message.
                </p>
              </div>
            )}
            {!loadingInsights && insights && (
              <>
                <div className="p-6 rounded-2xl border border-border bg-surface/40">
                  <h3 className="font-display font-medium mb-2 flex items-center gap-2"><Sparkles size={16} className="text-signal-cyan" /> Executive Summary</h3>
                  <p className="text-sm text-muted leading-relaxed">{insights.executive_summary}</p>
                </div>
                <div>
                  <h3 className="font-display font-medium mb-3">Key Insights</h3>
                  <ul className="space-y-2">
                    {insights.key_insights?.map((ins, i) => (
                      <li key={i} className="flex gap-3 text-sm p-4 rounded-xl border border-border bg-surface/30">
                        <span className="font-mono text-signal-cyan">{String(i + 1).padStart(2, '0')}</span>
                        <span className="text-muted">{ins}</span>
                      </li>
                    ))}
                  </ul>
                </div>
                <div>
                  <h3 className="font-display font-medium mb-3 flex items-center gap-2"><TrendingUp size={16} className="text-signal-violet" /> Business Recommendations</h3>
                  <ul className="space-y-2">
                    {insights.business_recommendations?.map((rec, i) => (
                      <li key={i} className="text-sm p-4 rounded-xl border border-signal-violet/20 bg-signal-violet/5 text-muted">{rec}</li>
                    ))}
                  </ul>
                </div>
                {insights.risk_flags?.length > 0 && (
                  <div>
                    <h3 className="font-display font-medium mb-3 flex items-center gap-2 text-signal-magenta"><AlertTriangle size={16} /> Risk Flags</h3>
                    <ul className="space-y-2">
                      {insights.risk_flags.map((r, i) => (
                        <li key={i} className="text-sm p-4 rounded-xl border border-signal-magenta/20 bg-signal-magenta/5 text-muted">{r}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </>
            )}
          </motion.div>
        )}

        {tab === 'ml' && (
          <motion.div key="ml" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="space-y-6">
            <div className="flex flex-wrap items-center gap-3">
              <select
                value={targetCol}
                onChange={(e) => setTargetCol(e.target.value)}
                disabled={!dashboardData}
                className="px-4 py-2.5 rounded-xl bg-surface/50 border border-border text-sm outline-none focus:border-signal-cyan disabled:opacity-50"
              >
                <option value="">No target — find clusters</option>
                {dashboardData?.profile.columns.map((c) => (
                  <option key={c.name} value={c.name}>{c.name}</option>
                ))}
              </select>
              <button
                onClick={() => runMl(targetCol || null)}
                disabled={loadingMl}
                className="px-5 py-2.5 rounded-xl bg-signal-gradient text-black text-sm font-medium hover:opacity-90 disabled:opacity-50"
              >
                Run model
              </button>
              {!dashboardData && !loadingDashboard && (
                <span className="text-xs text-muted">Column list loads with the Dashboard — one moment.</span>
              )}
            </div>

            {loadingMl && (
              <div className="py-24 text-center text-muted">
                <div className="inline-block w-8 h-8 border-2 border-signal-cyan border-t-transparent rounded-full animate-spin mb-4" />
                <p>Training and comparing models…</p>
              </div>
            )}

            {!loadingMl && mlError && (
              <p className="text-signal-magenta text-sm flex items-center gap-2">
                <AlertTriangle size={14} /> {mlError}
              </p>
            )}

            {!loadingMl && mlResult && !mlResult.error && (
              <>
                <div className="p-6 rounded-2xl border border-border bg-surface/40">
                  <p className="font-display font-medium mb-2 capitalize">{mlResult.task_type} result</p>
                  <p className="text-sm text-muted">{mlResult.summary}</p>
                </div>

                {mlResult.models_compared && (
                  <div className="grid md:grid-cols-3 gap-4">
                    {Object.entries(mlResult.models_compared).map(([name, metrics]) => (
                      <div key={name} className={`p-5 rounded-2xl border ${name === mlResult.best_model ? 'border-signal-cyan bg-signal-cyan/5' : 'border-border bg-surface/30'}`}>
                        <p className="font-medium text-sm mb-2">{name} {name === mlResult.best_model && '★'}</p>
                        {Object.entries(metrics).map(([k, v]) => (
                          <p key={k} className="text-xs text-muted font-mono">{k}: {v}</p>
                        ))}
                      </div>
                    ))}
                  </div>
                )}

                {mlResult.feature_importance_chart && (
                  <ChartCard chart={{ title: 'Feature Importance', figure: mlResult.feature_importance_chart }} />
                )}
                {mlResult.cluster_chart && (
                  <ChartCard chart={{ title: 'Clusters (PCA projection)', figure: mlResult.cluster_chart }} />
                )}
              </>
            )}
          </motion.div>
        )}

        {tab === 'kpi' && (
          <motion.div key="kpi" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="space-y-8">
            {!dashboardData && !loadingDashboard && (
              <p className="text-muted text-sm py-12 text-center">Column stats load with the Dashboard — one moment.</p>
            )}
            {dashboardData && <KpiSection profile={dashboardData.profile} />}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// Dynamic, dataset-agnostic KPI page — built entirely from the statistical
// profile (never hard-coded to any particular dataset/columns). Numeric
// columns whose name suggests a business metric (sales, revenue, profit,
// price, cost, amount, expense, margin, quantity...) surface as headline
// "business KPI" cards up top; every other numeric/categorical column gets
// a detailed stat card below.
const BUSINESS_KEYWORDS = /sales|revenue|profit|price|cost|amount|expense|margin|quantity|spend|budget|income/i

function formatNumber(n) {
  if (n === null || n === undefined) return '—'
  return Math.abs(n) >= 1000 ? n.toLocaleString(undefined, { maximumFractionDigits: 2 }) : n.toFixed(2)
}

function KpiSection({ profile }) {
  const numericCols = profile.columns.filter((c) => c.type === 'numeric')
  const categoricalCols = profile.columns.filter((c) => c.type === 'categorical' || c.type === 'boolean')
  const businessCols = numericCols.filter((c) => BUSINESS_KEYWORDS.test(c.name))
  const otherNumeric = numericCols.filter((c) => !businessCols.includes(c))

  return (
    <>
      <div>
        <h3 className="font-display font-medium mb-3 flex items-center gap-2"><Gauge size={16} className="text-signal-cyan" /> Overview</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <KpiCard label="Total Rows" value={profile.n_rows.toLocaleString()} />
          <KpiCard label="Total Columns" value={String(profile.n_cols)} />
          <KpiCard label="Numeric Columns" value={String(profile.numeric_columns.length)} />
          <KpiCard label="Categorical Columns" value={String(profile.categorical_columns.length)} />
          <KpiCard label="Missing Values" value={profile.total_missing_cells.toLocaleString()}
                   sub={profile.n_rows && profile.n_cols ? `${(profile.total_missing_cells / (profile.n_rows * profile.n_cols) * 100).toFixed(1)}% of data` : ''} />
          <KpiCard label="Duplicate Rows" value={profile.duplicate_rows.toLocaleString()} />
        </div>
      </div>

      {businessCols.length > 0 && (
        <div>
          <h3 className="font-display font-medium mb-3 flex items-center gap-2"><TrendingUp size={16} className="text-signal-violet" /> Business KPIs</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {businessCols.map((c) => (
              <div key={c.name} className="rounded-2xl border border-signal-violet/20 bg-signal-violet/5 p-5">
                <p className="text-xs font-mono uppercase tracking-wider text-muted mb-2">Total {c.name}</p>
                <p className="font-display text-2xl font-semibold text-gradient">{formatNumber(c.sum)}</p>
                <p className="text-xs text-muted mt-1">Avg {formatNumber(c.mean)} · Median {formatNumber(c.median)}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {otherNumeric.length > 0 && (
        <div>
          <h3 className="font-display font-medium mb-3">Numeric Column Stats</h3>
          <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-4">
            {otherNumeric.map((c) => (
              <div key={c.name} className="rounded-2xl border border-border bg-surface/30 p-5">
                <p className="font-medium text-sm mb-3 truncate">{c.name}</p>
                <div className="grid grid-cols-3 gap-y-1.5 text-xs">
                  <span className="text-muted">Mean</span><span className="col-span-2 font-mono">{formatNumber(c.mean)}</span>
                  <span className="text-muted">Median</span><span className="col-span-2 font-mono">{formatNumber(c.median)}</span>
                  <span className="text-muted">Min / Max</span><span className="col-span-2 font-mono">{formatNumber(c.min)} / {formatNumber(c.max)}</span>
                  <span className="text-muted">Std Dev</span><span className="col-span-2 font-mono">{formatNumber(c.std)}</span>
                  <span className="text-muted">Sum</span><span className="col-span-2 font-mono">{formatNumber(c.sum)}</span>
                  {c.outlier_count > 0 && (
                    <><span className="text-signal-magenta">Outliers</span><span className="col-span-2 font-mono text-signal-magenta">{c.outlier_count}</span></>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {categoricalCols.length > 0 && (
        <div>
          <h3 className="font-display font-medium mb-3">Category Breakdown</h3>
          <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-4">
            {categoricalCols.map((c) => {
              const top = c.top_values ? Object.entries(c.top_values)[0] : null
              return (
                <div key={c.name} className="rounded-2xl border border-border bg-surface/30 p-5">
                  <p className="font-medium text-sm mb-3 truncate">{c.name}</p>
                  <div className="grid grid-cols-3 gap-y-1.5 text-xs">
                    <span className="text-muted">Unique values</span><span className="col-span-2 font-mono">{c.unique_count}</span>
                    <span className="text-muted">Missing</span><span className="col-span-2 font-mono">{c.missing_count} ({c.missing_pct}%)</span>
                    {top && (
                      <><span className="text-muted">Most common</span><span className="col-span-2 font-mono truncate">{top[0]} ({top[1]})</span></>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </>
  )
}
