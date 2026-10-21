import { useEffect, useRef, useState } from 'react'
import { Pin, Minus, Square, Copy, X } from 'lucide-react'

// 自绘窗口标题栏（仅桌面版显示）：拖动/双击最大化用系统原生循环，缩放用四边/四角热区。
// 浏览器模式下 window.pywebview 不存在 → 整体不渲染（浏览器自带窗口框架）。
const EDGES = ['top', 'bottom', 'left', 'right', 'topleft', 'topright', 'bottomleft', 'bottomright']

export default function WindowChrome() {
  const [api, setApi] = useState(null)
  const [onTop, setOnTop] = useState(false)
  const [maximized, setMaximized] = useState(false)
  const lastDownRef = useRef(0)

  // 等待 pywebview 桥就绪（桌面版才有）
  useEffect(() => {
    const ready = () => !!(window.pywebview && window.pywebview.api && window.pywebview.api.get_state)
    if (ready()) {
      setApi(window.pywebview.api)
      return
    }
    const iv = setInterval(() => {
      if (ready()) {
        setApi(window.pywebview.api)
        clearInterval(iv)
      }
    }, 250)
    return () => clearInterval(iv)
  }, [])

  // 状态同步（置顶/最大化：贴边分屏、系统菜单等外部操作也能反映到按钮）
  useEffect(() => {
    if (!api) return
    let alive = true
    const sync = () => {
      api.get_state()
        .then(st => {
          if (!alive || !st) return
          setOnTop(!!st.on_top)
          setMaximized(!!st.maximized)
        })
        .catch(() => {})
    }
    sync()
    const iv = setInterval(sync, 2000)
    return () => {
      alive = false
      clearInterval(iv)
    }
  }, [api])

  if (!api) return null

  const togglePin = async () => {
    try {
      setOnTop(!!(await api.toggle_pin()))
    } catch (e) { /* 忽略 */ }
  }
  const toggleMax = async () => {
    try {
      setMaximized(!!(await api.toggle_maximize()))
    } catch (e) { /* 忽略 */ }
  }
  const onBarDown = e => {
    if (e.button !== 0 || e.target.closest('.titlebar-btn')) return
    // 双击最大化：原生移动循环会吞掉 mouseup（dblclick 可能不触发），用两次 mousedown 间隔判断
    const now = Date.now()
    if (now - lastDownRef.current < 400) {
      lastDownRef.current = 0
      toggleMax()
      return
    }
    lastDownRef.current = now
    try {
      api.start_drag().catch(() => {})
    } catch (e) { /* 忽略 */ }
  }

  return (
    <>
      <div className="titlebar" onMouseDown={onBarDown}>
        <div className="titlebar-left">
          <img className="titlebar-icon" src="/icon.png" alt="" />
          <span className="titlebar-title">研究生工作台</span>
        </div>
        <div className="titlebar-btns">
          <button
            className={`titlebar-btn ${onTop ? 'on' : ''}`}
            title={onTop ? '取消置顶' : '窗口置顶（保持在其他窗口前面）'}
            onClick={togglePin}
          >
            <Pin size={14} strokeWidth={1.8} />
          </button>
          <button className="titlebar-btn" title="最小化" onClick={() => api.minimize().catch(() => {})}>
            <Minus size={15} strokeWidth={1.8} />
          </button>
          <button className="titlebar-btn" title={maximized ? '向下还原' : '最大化'} onClick={toggleMax}>
            {maximized ? <Copy size={13} strokeWidth={1.8} /> : <Square size={12} strokeWidth={1.8} />}
          </button>
          <button className="titlebar-btn titlebar-close" title="关闭（最小化到托盘）" onClick={() => api.hide_to_tray().catch(() => {})}>
            <X size={15} strokeWidth={1.8} />
          </button>
        </div>
      </div>
      <div className="resize-zones">
        {EDGES.map(edge => (
          <div
            key={edge}
            className={`resize-zone rz-${edge}`}
            onMouseDown={e => {
              if (e.button !== 0) return
              e.preventDefault()
              try {
                api.start_resize(edge).catch(() => {})
              } catch (err) { /* 忽略 */ }
            }}
          />
        ))}
      </div>
    </>
  )
}
