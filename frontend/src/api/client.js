import axios from 'axios'

// In local dev, Vite's proxy (vite.config.js) forwards '/api' to the local
// backend and strips the prefix, so '/api' works as a relative baseURL.
// In production (Vercel) there is no such proxy, so '/api' would just hit
// the Vercel domain itself and get the SPA's index.html back instead of
// JSON. VITE_API_URL (set in Vercel project settings) must point directly
// at the deployed backend's root URL, e.g. https://insightforge-backend.onrender.com
const client = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api',
  timeout: 90000,
})

client.interceptors.request.use((config) => {
  const token = localStorage.getItem('insightforge-token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// Render's free tier puts the backend to sleep after idle time, and warns
// cold starts can take "50 seconds or more." The request that wakes it up
// often fails outright (500/502/503, or a bare network error with no
// response at all if the connection is refused while the container is
// still booting) rather than just being slow. A single quick retry isn't
// enough to reliably survive that window, so this retries up to 3 times
// with increasing delays (5s, 15s, 30s — ~50s total, matching Render's own
// stated worst case) before finally surfacing an error to the user.
const COLD_START_RETRY_DELAYS_MS = [5000, 15000, 30000]

function looksLikeColdStart(err) {
  const status = err.response?.status
  // No response at all (network error / connection refused) OR a gateway-
  // level error status are both consistent with the backend being asleep.
  return !err.response || status === 500 || status === 502 || status === 503
}

client.interceptors.response.use(
  (res) => res,
  async (err) => {
    const config = err.config
    if (config && looksLikeColdStart(err)) {
      config._coldStartRetryCount = config._coldStartRetryCount || 0
      if (config._coldStartRetryCount < COLD_START_RETRY_DELAYS_MS.length) {
        const delay = COLD_START_RETRY_DELAYS_MS[config._coldStartRetryCount]
        config._coldStartRetryCount += 1
        await new Promise((resolve) => setTimeout(resolve, delay))
        return client(config)
      }
    }
    if (err.response?.status === 401) {
      localStorage.removeItem('insightforge-token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export default client