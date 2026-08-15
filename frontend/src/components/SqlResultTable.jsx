import { useState } from 'react'
import { Copy, Check, Database } from 'lucide-react'

export default function SqlResultTable({ table }) {
  const [copied, setCopied] = useState(false)
  if (!table || !Array.isArray(table.columns) || !Array.isArray(table.rows)) return null

  const copySql = async () => {
    try {
      await navigator.clipboard.writeText(table.sql)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      // clipboard unavailable, ignore
    }
  }

  return (
    <div className="w-full rounded-xl border border-border overflow-hidden">
      <div className="flex items-center justify-between px-3 py-2 bg-surface/60 border-b border-border">
        <span className="flex items-center gap-1.5 text-xs font-mono text-muted">
          <Database size={12} /> SQL · {table.row_count} row{table.row_count === 1 ? '' : 's'}
        </span>
        <button onClick={copySql} className="text-xs text-muted hover:text-signal-cyan flex items-center gap-1 transition-colors">
          {copied ? <Check size={12} /> : <Copy size={12} />} {copied ? 'Copied' : 'Copy SQL'}
        </button>
      </div>
      <div className="px-3 pt-2 text-[10px] font-mono uppercase tracking-wide text-muted/70">Executed query</div>
      <pre className="px-3 pb-2 pt-1 text-xs font-mono text-signal-cyan bg-base/40 overflow-x-auto whitespace-pre-wrap">{table.sql}</pre>
      <div className="px-3 pt-2 text-[10px] font-mono uppercase tracking-wide text-muted/70">Result</div>
      <div className="overflow-x-auto max-h-64 mt-1">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-surface/40">
              {table.columns.map((c) => (
                <th key={c} className="px-3 py-2 text-left font-mono text-muted border-b border-border whitespace-nowrap">{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((row, i) => (
              <tr key={i} className="border-b border-border/50 last:border-0">
                {row.map((cell, j) => (
                  <td key={j} className="px-3 py-1.5 whitespace-nowrap text-ink/90">{String(cell ?? '')}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
