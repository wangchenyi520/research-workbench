import React, { createContext, useContext, useCallback, useState } from 'react'

const ToastCtx = createContext(null)

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])

  const push = useCallback((msg, type = 'info') => {
    // 容错：422 校验错误的 detail 是数组/对象，直接渲染会触发 React #31 崩溃
    const text = typeof msg === 'string' ? msg : (msg && typeof msg === 'object' ? JSON.stringify(msg) : String(msg ?? ''))
    const id = Date.now() + Math.random()
    setToasts(t => [...t, { id, msg: text, type }])
    setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), 3000)
  }, [])

  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toast-wrap">
        {toasts.map(t => (
          <div key={t.id} className={`toast ${t.type === 'error' ? 'error' : ''}`}>{t.msg}</div>
        ))}
      </div>
    </ToastCtx.Provider>
  )
}

export const useToast = () => useContext(ToastCtx)
