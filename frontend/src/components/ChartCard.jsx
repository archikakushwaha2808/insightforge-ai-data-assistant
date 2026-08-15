import { Component } from 'react'
import { motion } from 'framer-motion'
import Plot from 'react-plotly.js'
import { BarChart3 } from 'lucide-react'

// Catches errors thrown *during* Plotly's render (bad/edge-case figure data,
// browser quirks, etc.) so one broken chart can't blank out its card — or
// take the rest of the dashboard down with it.
class ChartErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false }
  }
  static getDerivedStateFromError() {
    return { hasError: true }
  }
  componentDidCatch(error) {
    console.error('Chart render failed, showing fallback:', error)
  }
  render() {
    return this.state.hasError ? this.props.fallback : this.props.children
  }
}

// Same size/style as the real chart area, so swapping to this never changes
// the card's footprint or causes layout jumps.
function ChartFallback({ chart }) {
  const isHeatmap = chart.type === 'heatmap'
  const items = chart.fallback?.items

  return (
    <div className="flex-1 min-h-[260px] rounded-xl bg-white p-4 flex flex-col items-center justify-center text-center">
      <BarChart3 size={22} className="text-muted mb-2" />
      <p className="text-sm font-medium text-ink">
        {isHeatmap ? 'Heatmap unavailable' : 'Chart unavailable'}
      </p>
      <p className="text-xs text-muted mt-1 mb-3">
        {isHeatmap
          ? 'Showing correlation summary instead of a blank chart.'
          : 'Showing a quick summary instead of a blank chart.'}
      </p>
      {items && items.length > 0 && (
        <ul className="w-full max-w-xs text-left space-y-1.5">
          {items.map((it) => (
            <li
              key={it.label}
              className="flex items-center justify-between gap-3 text-xs text-ink/80 border-b border-border/60 pb-1"
            >
              <span className="truncate">{it.label}</span>
              <span className="font-mono tabular-nums text-muted shrink-0">
                {it.value > 0 ? '+' : ''}
                {it.value}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default function ChartCard({ chart, index = 0 }) {
  const figure = chart.figure || chart
  const hasValidFigure = !!(figure && Array.isArray(figure.data) && figure.data.length > 0)
  const fallback = <ChartFallback chart={chart} />

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-40px' }}
      transition={{ duration: 0.4, delay: (index % 6) * 0.05 }}
      className="rounded-2xl border border-border bg-surface/40 p-5 flex flex-col"
    >
      <h3 className="font-display font-medium text-sm mb-3">{chart.title}</h3>
      {/* White card wrapper: charts use a clean plotly_white style with their
          own fonts/colors baked in server-side (Colab-quality look), so we
          give them a white surface to sit on rather than overriding colors. */}
      {hasValidFigure ? (
        <ChartErrorBoundary fallback={fallback}>
          <div className="flex-1 min-h-[260px] rounded-xl overflow-hidden bg-white p-1">
            <Plot
              data={figure.data}
              layout={{ ...figure.layout, autosize: true }}
              useResizeHandler
              style={{ width: '100%', height: '100%', minHeight: '260px' }}
              config={{
                displayModeBar: false,
                responsive: true,
              }}
            />
          </div>
        </ChartErrorBoundary>
      ) : (
        fallback
      )}
      {chart.description && (
        <p className="text-xs text-muted leading-relaxed mt-3 pt-3 border-t border-border">
          {chart.description}
        </p>
      )}
    </motion.div>
  )
}
