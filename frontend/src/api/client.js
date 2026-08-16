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

// Render's free tier puts the backend to sleep after idle time. The request
// that wakes it back up sometimes fails outright with a 500/502/503 before
// the server is actually ready, rather than just being slow. Rather than
// surfacing that as a real error to the user, silently retry once after a
// short delay — by then the backend is awake and the retry succeeds.
client.interceptors.response.use(
  (res) => res,
  async (err) => {
    const status = err.response?.status
    const isColdStartLikely = status === 500 || status === 502 || status === 503
    const config = err.config
    if (isColdStartLikely && config && !config._retriedAfterColdStart) {
      config._retriedAfterColdStart = true
      await new Promise((resolve) => setTimeout(resolve, 3000))
      return client(config)
    }
    if (err.response?.status === 401) {
      localStorage.removeItem('insightforge-token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export default client