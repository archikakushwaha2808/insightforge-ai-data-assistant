import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ArrowRight, Database, BrainCircuit, MessageSquareText, BarChart3 } from 'lucide-react'
import DataConstellation from '../components/DataConstellation'

const capabilities = [
  {
    icon: Database,
    title: 'Feed it anything',
    body: 'Drop in CSV, TSV, TXT, JSON, or Excel. It sniffs delimiters, encodings, and column types on its own — no setup.',
  },
  {
    icon: BarChart3,
    title: 'Clean, explore, visualize',
    body: 'Missing values, duplicates, and outliers get handled automatically. Every chart ships with a plain-English read of what it shows.',
  },
  {
    icon: BrainCircuit,
    title: 'Modeling, auto-selected',
    body: 'Give it a target and it benchmarks classifiers or regressors and reports the winner. No target? It clusters and finds structure on its own.',
  },
  {
    icon: MessageSquareText,
    title: 'An analyst that talks back',
    body: 'Ask follow-up questions in plain language. It remembers the conversation and can sketch a brand-new chart mid-reply.',
  },
]

export default function Landing() {
  return (
    <div className="overflow-hidden">
      {/* HERO */}
      <section className="relative max-w-7xl mx-auto px-6 pt-16 pb-24 grid md:grid-cols-2 gap-12 items-center">
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, ease: 'easeOut' }}
        >
          <span className="inline-block font-mono text-xs uppercase tracking-[0.2em] text-signal-cyan mb-5">
            Data in → Decisions out
          </span>
          <h1 className="font-display text-5xl md:text-6xl font-semibold leading-[1.05] tracking-tight mb-6">
            Your dataset,
            <br />
            <span className="text-gradient">fully understood</span>
            <br />
            in minutes.
          </h1>
          <p className="text-muted text-lg leading-relaxed max-w-md mb-9">
            Upload any file. InsightForge cleans it, explores it, models it, and
            builds you a live dashboard — then sticks around to answer whatever
            you ask next.
          </p>
          <div className="flex items-center gap-4">
            <Link
              to="/dashboard"
              className="group flex items-center gap-2 px-6 py-3.5 rounded-full bg-signal-gradient text-black font-medium hover:opacity-90 transition-all shadow-glow"
            >
              Analyze your data
              <ArrowRight size={16} className="group-hover:translate-x-1 transition-transform" />
            </Link>
            <Link to="/chat" className="px-6 py-3.5 rounded-full border border-border hover:border-signal-cyan font-medium transition-colors">
              Talk to the assistant
            </Link>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 1, ease: 'easeOut', delay: 0.2 }}
          className="relative h-[420px] md:h-[520px]"
        >
          <DataConstellation className="absolute inset-0" />
        </motion.div>
      </section>

      {/* CAPABILITIES */}
      <section className="max-w-7xl mx-auto px-6 pb-28">
        <div className="grid md:grid-cols-4 gap-6">
          {capabilities.map((cap, i) => (
            <motion.div
              key={cap.title}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5, delay: i * 0.08 }}
              className="p-6 rounded-2xl border border-border bg-surface/40 hover:border-signal-cyan/50 transition-colors"
            >
              <cap.icon size={22} className="text-signal-cyan mb-4" />
              <h3 className="font-display font-medium text-base mb-2">{cap.title}</h3>
              <p className="text-sm text-muted leading-relaxed">{cap.body}</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* CTA STRIP */}
      <section className="max-w-7xl mx-auto px-6 pb-28">
        <div className="rounded-3xl border border-border bg-gradient-to-br from-surface to-transparent p-12 text-center relative overflow-hidden">
          <div className="absolute inset-0 bg-signal-gradient opacity-[0.06]" />
          <h2 className="font-display text-3xl font-semibold mb-3 relative">Stop analyzing manually.</h2>
          <p className="text-muted mb-8 relative">What used to take a notebook and an afternoon now takes one upload.</p>
          <Link
            to="/dashboard"
            className="inline-flex items-center gap-2 px-7 py-3.5 rounded-full bg-signal-gradient text-black font-medium hover:opacity-90 transition-opacity relative"
          >
            Get started free <ArrowRight size={16} />
          </Link>
        </div>
      </section>
    </div>
  )
}
