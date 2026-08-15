import { motion } from 'framer-motion'

export default function KpiCard({ label, value, sub, index = 0 }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: index * 0.06 }}
      className="rounded-2xl border border-border bg-surface/40 p-5"
    >
      <p className="text-xs font-mono uppercase tracking-wider text-muted mb-2">{label}</p>
      <p className="font-display text-2xl font-semibold text-gradient">{value}</p>
      {sub && <p className="text-xs text-muted mt-1">{sub}</p>}
    </motion.div>
  )
}
