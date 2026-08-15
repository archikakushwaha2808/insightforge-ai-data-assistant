/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        base: {
          DEFAULT: 'rgb(var(--color-base) / <alpha-value>)',
        },
        surface: {
          DEFAULT: 'rgb(var(--color-surface) / <alpha-value>)',
        },
        ink: {
          DEFAULT: 'rgb(var(--color-ink) / <alpha-value>)',
        },
        signal: {
          cyan: '#3FE0C5',
          violet: '#8C7BFF',
          magenta: '#FF6FB0',
        },
        muted: {
          DEFAULT: 'rgb(var(--color-muted) / <alpha-value>)',
        },
        border: {
          DEFAULT: 'rgb(var(--color-border) / <alpha-value>)',
        },
      },
      fontFamily: {
        display: ['"Space Grotesk"', 'sans-serif'],
        body: ['"Inter"', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace'],
      },
      backgroundImage: {
        'signal-gradient': 'linear-gradient(135deg, #3FE0C5 0%, #8C7BFF 55%, #FF6FB0 100%)',
      },
      boxShadow: {
        glow: '0 0 40px rgba(63,224,197,0.15)',
      },
    },
  },
  plugins: [],
}
