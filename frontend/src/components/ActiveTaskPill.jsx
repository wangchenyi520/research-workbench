import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api'
import { useToast } from './Toast'
import { Play, Check, Pause } from 'lucide-react'

// 全局「进行中任务」悬浮胶囊：任何页面右下角显示 doing 任务，可快捷完成/暂停/跳转
// 开关：设置页「桌面胶囊 → 进行中任务」（localStorage wb_active_pill，默认显示；事件即时生效）
const pillEnabled = () => localStorage.getItem('wb_active_pill') !== '0'

export default function ActiveTaskPill() {
  const [enabled, setEnabled] = useState(pillEnabled)
  const [tasks, setTasks] = useState([])
  const [doneTarget, setDoneTarget] = useState(null)
  const [doneMin, setDoneMin] = useState('')
  const navigate = useNavigate()
  const toast = useToast()

  const load = () => {
    if (!pillEnabled()) return
    api.get('/tasks/active').then(r => setTasks(r.data.items || [])).catch(() => {})
  }
  useEffect(() => {
    const onToggle = () => {
      const on = pillEnabled()
      setEnabled(on)
      if (on) load()
    }
    window.addEventListener('wb-active-pill', onToggle)
    load()
    const iv = setInterval(load, 20000)
    return () => {
      window.removeEventListener('wb-active-pill', onToggle)
      clearInterval(iv)
    }
  }, [])

  const pause = async t => {
    await api.put(`/tasks/${t.id}`, { status: 'todo' }).catch(() => {})
    toast(`已暂停「${t.title}」（回到待办）`)
    load()
  }
  const confirmDone = async () => {
    if (!doneTarget) return
    const m = Number(doneMin)
    await api
      .put(`/tasks/${doneTarget.id}`, m > 0 ? { status: 'done', actual_minutes: m } : { status: 'done' })
      .catch(() => {})
    toast(m > 0 ? `已完成「${doneTarget.title}」（实际 ${m} 分钟）` : `已完成「${doneTarget.title}」`)
    setDoneTarget(null)
    setDoneMin('')
    load()
  }

  if (!enabled) return null
  if (tasks.length === 0) return null
  const shown = tasks.slice(0, 2)
  const more = tasks.length - shown.length

  return (
    <>
      <div className="active-task-pills">
        {shown.map(t => (
          <div key={t.id} className="active-task-pill">
            <button className="atp-title" onClick={() => navigate(`/tasks?highlight=${t.id}`)} title="点击到任务页查看">
              <Play size={12} strokeWidth={2} />
              <span className="atp-title-text">{t.title}</span>
            </button>
            <button className="atp-btn" title="标记完成（可填实际耗时）"
              onClick={() => { setDoneMin(''); setDoneTarget(t) }}>
              <Check size={13} strokeWidth={2} />
            </button>
            <button className="atp-btn" title="暂停（回到待办）" onClick={() => pause(t)}>
              <Pause size={13} strokeWidth={2} />
            </button>
          </div>
        ))}
        {more > 0 && (
          <button className="active-task-pill atp-more" onClick={() => navigate('/tasks')}>+{more} 个进行中</button>
        )}
      </div>
      {doneTarget && (
        <div className="modal-mask" onClick={() => setDoneTarget(null)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h3>标记完成：{doneTarget.title}</h3>
            <div className="form-row">
              <label className="form-label">实际耗时（分钟，可留空跳过）</label>
              <input type="number" min="1" className="input" value={doneMin} autoFocus
                onChange={e => setDoneMin(e.target.value)} placeholder="如 45" />
            </div>
            <div className="modal-actions">
              <button className="btn" onClick={() => setDoneTarget(null)}>取消</button>
              <button className="btn btn-primary" onClick={confirmDone}>
                <Check size={14} strokeWidth={1.8} /> 确认完成
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
