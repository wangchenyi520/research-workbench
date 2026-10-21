import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

// 本地日期字符串（YYYY-MM-DD）。注意：不要用 toISOString().slice(0,10)，
// 那会按 UTC 计算，凌晨 0-8 点（UTC+8）日期会回退一天。
export const todayStr = () => {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

// 全局错误提示：仅网络错误 / 5xx 由拦截器统一 toast（4xx 交给页面自行处理）
api.interceptors.response.use(
  r => r,
  err => {
    const status = err.response?.status
    if (!err.response || status >= 500) {
      window.dispatchEvent(
        new CustomEvent('api-error', {
          detail: { status, msg: err.response?.data?.detail || (err.code === 'ECONNABORTED' ? '请求超时' : '网络错误，请确认后端已启动') },
        })
      )
    }
    return Promise.reject(err)
  }
)

export default api