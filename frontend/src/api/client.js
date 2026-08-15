import axios from 'axios'

const client = axios.create({
  baseURL: '/api',
  timeout: 90000,
})

client.interceptors.request.use((config) => {
  const token = localStorage.getItem('insightforge-token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

client.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('insightforge-token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export default client
