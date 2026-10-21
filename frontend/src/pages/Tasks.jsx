import React, { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import api, { todayStr } from '../api'
import { useToast } from '../components/Toast'
import { CheckSquare, X, Play, Pause, Check, Pencil, Trash2, ListChecks, ClipboardList, BarChart3, Map as MapIcon, Monitor } from 'lucide-react'

const TYPE_LABEL = { habit: '习惯', study: '学习', once: '一次性' }
const TYPE_BADGE = { habit: 'badge-success', study: 'badge-info', once: 'badge-primary' }

const TASK_TEMPLATES = [
  ['复现论文', { title: '复现：', task_type: 'study', tags: '复现', pomodoro_minutes: 25, break_minutes: 5, priority: 3 }],
  ['精读论文', { title: '精读：', task_type: 'study', tags: '精读', pomodoro_minutes: 25, break_minutes: 5, priority: 2 }],
  ['写综述章节', { title: '写综述：', task_type: 'study', tags: '写作', pomodoro_minutes: 35, break_minutes: 5, priority: 2 }],
  ['准备组会', { title: '准备组会', task_type: 'once', tags: '组会', priority: 2 }],
  ['刷题', { title: '刷题：', task_type: 'study', tags: '刷题', pomodoro_minutes: 25, break_minutes: 5, priority: 2 }],
  ['文献阅读', { title: '阅读：', task_type: 'once', tags: '文献', priority: 2 }],
]

function fmt(sec) {
  const s = Math.max(0, Math.floor(sec))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const ss = s % 60
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(ss).padStart(2, '0')}`
}

function TaskForm({ initial, goals, defaultPomo, defaultBreak, onClose, onSaved }) {
  const [form, setForm] = useState({
    title: initial?.title || '',
    description: initial?.description || '',
    task_type: initial?.task_type || 'once',
    priority: initial?.priority || 2,
    due_date: initial?.due_date || '',
    goal_id: initial?.goal_id || '',
    tags: initial?.tags || '',
    pomodoro_minutes: initial?.pomodoro_minutes || defaultPomo || 25,
    break_minutes: initial?.break_minutes || defaultBreak || 5,
    repeat_weekdays: initial?.repeat_weekdays || '',
    est_minutes: initial?.est_minutes ?? '',
  })
  const WEEKDAY_CN = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
  const toast = useToast()
  const set = k => v => setForm(f => ({ ...f, [k]: v }))

  const submit = async () => {
    if (!form.title.trim()) return toast('请输入任务标题', 'error')
    // est_minutes 空串转 null，避免 Pydantic 422（空串不是合法 int）
    const payload = {
      ...form,
      est_minutes: form.est_minutes === '' || form.est_minutes == null ? null : Number(form.est_minutes),
      actual_minutes: form.actual_minutes === '' || form.actual_minutes == null ? null : Number(form.actual_minutes),
      due_date: form.due_date || null,
      goal_id: form.goal_id || null,
    }
    try {
      if (initial?.id) await api.put(`/tasks/${initial.id}`, payload)
      else await api.post('/tasks', payload)
      onSaved()
      onClose()
    } catch (e) { toast(e.response?.data?.detail || '保存失败', 'error') }
  }

  return (
    <div className="modal-mask" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <h3>{initial ? '编辑任务' : '新建任务'}</h3>
        {!initial && (
          <label className="label">📋 从模板填充
            <select className="select" style={{ width: '100%', marginTop: 4 }} value="" onChange={e => {
              const tpl = TASK_TEMPLATES.find(([name]) => name === e.target.value)
              if (tpl) setForm(f => ({ ...f, ...tpl[1], title: f.title || tpl[1].title }))
            }}>
              <option value="">（选择后填充字段，可再修改）</option>
              {TASK_TEMPLATES.map(([name]) => <option key={name} value={name}>{name}</option>)}
            </select>
          </label>
        )}
        <label className="label">标题 *</label>
        <input className="input" value={form.title} onChange={e => set('title')(e.target.value)} />
        <label className="label">描述</label>
        <textarea className="textarea" value={form.description} onChange={e => set('description')(e.target.value)} />
        <label className="label">类型</label>
        <select className="select" value={form.task_type} onChange={e => set('task_type')(e.target.value)}>
          <option value="once">一次性任务</option>
          <option value="habit">习惯打卡</option>
          <option value="study">学习计时</option>
        </select>
        <div className="row">
          <div style={{ flex: 1 }}>
            <label className="label">截止日期</label>
            <input type="date" className="input" value={form.due_date} onChange={e => set('due_date')(e.target.value)} />
          </div>
          <div style={{ flex: 1 }}>
            <label className="label">优先级（1-5）</label>
            <select className="select" value={form.priority} onChange={e => set('priority')(Number(e.target.value))}>
              {[1, 2, 3, 4, 5].map(p => <option key={p} value={p}>{p}</option>)}
            </select>
          </div>
          <div style={{ flex: 1 }}>
            <label className="label">预估时长（分钟）</label>
            <input type="number" min="5" className="input" placeholder="AI 预估或手填" value={form.est_minutes} onChange={e => set('est_minutes')(e.target.value === '' ? '' : Number(e.target.value))} />
          </div>
        </div>
        <label className="label">关联目标</label>
        <select className="select" value={form.goal_id} onChange={e => set('goal_id')(e.target.value)}>
          <option value="">无</option>
          {goals.map(g => <option key={g.id} value={g.id}>{g.title}</option>)}
        </select>
        {form.task_type === 'study' && (
          <div className="row">
            <div style={{ flex: 1 }}>
              <label className="label">番茄钟工作分钟</label>
              <input type="number" className="input" value={form.pomodoro_minutes} onChange={e => set('pomodoro_minutes')(Number(e.target.value))} />
            </div>
            <div style={{ flex: 1 }}>
              <label className="label">番茄钟休息分钟</label>
              <input type="number" className="input" value={form.break_minutes} onChange={e => set('break_minutes')(Number(e.target.value))} />
            </div>
          </div>
        )}
        <label className="label">标签（逗号分隔）</label>
        <input className="input" value={form.tags} onChange={e => set('tags')(e.target.value)} />
        <label className="label">每周重复（勾选后每到该星期自动生成当天任务）</label>
        <div className="row" style={{ gap: 4, flexWrap: 'wrap' }}>
          {WEEKDAY_CN.map((l, i) => (
            <label key={l} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, cursor: 'pointer', padding: '3px 8px', border: '1px solid var(--border)', borderRadius: 8 }}>
              <input type="checkbox" checked={form.repeat_weekdays.split(',').includes(String(i))} onChange={e => {
                const cur = form.repeat_weekdays ? form.repeat_weekdays.split(',').filter(Boolean) : []
                const next = e.target.checked ? [...cur, String(i)] : cur.filter(x => x !== String(i))
                set('repeat_weekdays')([...new Set(next)].sort().join(','))
              }} />
              {l}
            </label>
          ))}
        </div>
        <div className="modal-actions">
          <button className="btn" onClick={onClose}>取消</button>
          <button className="btn btn-primary" onClick={submit}>保存</button>
        </div>
      </div>
    </div>
  )
}

const POMO_PRESETS = [15, 25, 35, 45]

function Timer({ task, onDone }) {
  const [mode, setMode] = useState('idle') // idle/work/break
  const [elapsed, setElapsed] = useState(0) // 本地已计秒数（暂停时不增）
  const [logId, setLogId] = useState(null)
  const [paused, setPaused] = useState(false)
  const [workMin, setWorkMin] = useState(task.pomodoro_minutes || 25)
  const [breakMin, setBreakMin] = useState(task.break_minutes || 5)
  const [remote, setRemote] = useState(null) // 桌面时钟状态快照
  const hadRemote = useRef(false)
  const toast = useToast()
  const totalWork = Math.max(1, Math.round(workMin)) * 60
  const totalBreak = Math.max(0, Math.round(breakMin)) * 60
  // 桌面时钟接管本任务（按 log 或任务匹配，页面刷新后仍能接上）
  const remoteHere = !!(remote && remote.active && (remote.log_id === logId || remote.task_id === task.id))

  // 轮询桌面时钟状态
  useEffect(() => {
    let stop = false
    const poll = () => {
      api.get('/pomodoro/widget/state').then(r => { if (!stop) setRemote(r.data?.active ? r.data : null) }).catch(() => {})
    }
    poll()
    const iv = setInterval(poll, 1500)
    return () => { stop = true; clearInterval(iv) }
  }, [])

  // 本地倒计时（桌面时钟接管时停走）
  useEffect(() => {
    if (mode === 'idle' || paused || remoteHere) return
    const iv = setInterval(() => setElapsed(s => s + 1), 1000)
    return () => clearInterval(iv)
  }, [mode, paused, remoteHere])

  // B2：本地番茄到点自动关账 + 进休息/结束（与桌面时钟行为一致，避免挂机无限计时）
  useEffect(() => {
    if (remoteHere || paused) return
    if (mode === 'work' && elapsed >= totalWork) completeLocal(true)
    else if (mode === 'break' && elapsed >= totalBreak) finishBreakLocal()
  }, [elapsed, mode, paused, remoteHere, totalWork, totalBreak])

  // B3：组件卸载（如任务被标完成）时若还有未结算的工作计时，先关账，避免悬挂 timelog
  const stateRef = useRef({ logId: null, mode: 'idle', elapsed: 0 })
  stateRef.current = { logId, mode, elapsed }
  useEffect(() => () => {
    const s = stateRef.current
    if (s.logId && s.mode === 'work') {
      api.put(`/tasks/timelogs/${s.logId}`, { duration_seconds: Math.max(1, Math.round(s.elapsed)) }).catch(() => {})
    }
  }, [])

  // 桌面时钟会话结束（休息完自动关闭）→ 本地复位
  useEffect(() => {
    if (remoteHere) { hadRemote.current = true; return }
    if (hadRemote.current) {
      hadRemote.current = false
      setMode('idle'); setElapsed(0); setPaused(false); setLogId(null)
      onDone()
    }
  }, [remoteHere])

  const notify = body => {
    if ('Notification' in window && Notification.permission === 'granted') {
      try { new Notification('番茄钟', { body }) } catch (e) {}
    }
  }

  const persistMinutes = (w, b) => {
    if (w !== task.pomodoro_minutes || b !== task.break_minutes) {
      api.put(`/tasks/${task.id}`, { pomodoro_minutes: w, break_minutes: b }).catch(() => {})
    }
  }

  const markDoing = async () => {
    if (task.status === 'todo') {
      await api.put(`/tasks/${task.id}`, { status: 'doing' }).catch(() => {})
      onDone()
    }
  }

  const startLocal = async () => {
    // B6：与桌面时钟互斥——桌面时钟正在用时不允许本地再开一条计时
    const st = await api.get('/pomodoro/widget/state').catch(() => ({ data: null }))
    if (st.data?.active && st.data.task_id === task.id) return toast('桌面时钟正在使用该任务，请在遥控面板操作', 'error')
    if (st.data?.active) return toast(`桌面时钟正被「${st.data.title}」使用，请先结束它`, 'error')
    // 与自由番茄钟互斥
    const fp = await api.get('/free-pomodoro/state').catch(() => ({ data: null }))
    if (fp.data?.session && ['running', 'paused'].includes(fp.data.session.status)) return toast(`自由番茄钟正在「${fp.data.session.state || '学习'}」中，请先完成或放弃`, 'error')
    const r = await api.post(`/tasks/${task.id}/timelogs`, { kind: 'pomodoro' })
    persistMinutes(Math.round(workMin), Math.round(breakMin))
    setLogId(r.data.id); setElapsed(0); setPaused(false); setMode('work')
    await markDoing()
  }

  const startDesktop = async () => {
    try {
      const st = await api.get('/pomodoro/widget/state')
      if (st.data?.active && st.data.task_id !== task.id) return toast(`桌面时钟正被「${st.data.title}」使用`, 'error')
      const fp = await api.get('/free-pomodoro/state').catch(() => ({ data: null }))
      if (fp.data?.session && ['running', 'paused'].includes(fp.data.session.status)) return toast(`自由番茄钟正在「${fp.data.session.state || '学习'}」中，请先完成或放弃`, 'error')
      const r = await api.post(`/tasks/${task.id}/timelogs`, { kind: 'pomodoro' })
      persistMinutes(Math.round(workMin), Math.round(breakMin))
      setLogId(r.data.id); setElapsed(0); setPaused(false); setMode('work')
      await api.post('/pomodoro/widget/start', { task_id: task.id, log_id: r.data.id, title: task.title, work_min: Math.round(workMin), break_min: Math.round(breakMin) })
      toast('🖥 桌面时钟已启动，可在桌面拖动/置顶')
      await markDoing()
    } catch (e) {
      toast(e.response?.data?.detail || '启动桌面时钟失败', 'error')
    }
  }

  const closeLog = counted => api.put(`/tasks/timelogs/${logId}`, { duration_seconds: Math.max(1, Math.round(counted)) }).catch(() => {})

  const completeLocal = async auto => {
    if (logId && mode === 'work') await closeLog(elapsed)
    setMode(totalBreak > 0 ? 'break' : 'idle'); setElapsed(0); setPaused(false)
    onDone()
    if (auto) {
      toast('🍅 番茄完成，进入休息')
      notify(`「${task.title}」一个番茄完成${totalBreak > 0 ? '，休息一下' : ''}`)
    }
  }

  const finishBreakLocal = () => {
    setMode('idle'); setElapsed(0); setPaused(false)
    toast('休息结束，加油！')
    onDone()
  }

  const abandonLocal = async () => {
    // 暂停/放弃明确区分：暂停保留计时，放弃则本次不计入（需确认，防误触）
    if (!confirm(`确定放弃这个番茄吗？已计时 ${fmtMMSS(elapsed)}，放弃后本次不计入时长统计。`)) return
    if (logId) await api.delete(`/tasks/timelogs/${logId}`).catch(() => {})
    setMode('idle'); setElapsed(0); setPaused(false); setLogId(null)
    toast('已放弃该番茄（不计入时长）')
  }

  const ctrl = async (action, value) => {
    try { await api.post('/pomodoro/widget/control', { action, value }) } catch (e) { toast(e.response?.data?.detail || '操作失败', 'error') }
  }
  const abandonRemote = async () => {
    if (!confirm('确定放弃这个番茄吗？放弃后本次不计入时长统计。')) return
    await ctrl('abandon')
    setMode('idle'); setElapsed(0); setPaused(false); setLogId(null)
    setRemote(null)
    toast('已放弃该番茄（不计入时长）')
  }

  const fmtMMSS = sec => `${String(Math.max(0, Math.floor(sec / 60))).padStart(2, '0')}:${String(Math.max(0, Math.floor(sec % 60))).padStart(2, '0')}`

  // ---------- 渲染 ----------
  if (remoteHere) {
    // 桌面时钟遥控面板
    const isBreak = remote.phase === 'break'
    const remain = remote.remaining
    const pct = isBreak ? ((remote.break_total - remain) / Math.max(1, remote.break_total)) * 100 : ((remote.work_total - remain) / Math.max(1, remote.work_total)) * 100
    return (
      <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--border)', textAlign: 'center' }}>
        <div className={`pomodoro-ring ${isBreak ? 'break' : ''}`} style={{ background: `conic-gradient(var(--primary) ${pct * 3.6}deg, transparent 0)` }}>
          <span style={{ background: 'var(--card)', borderRadius: '50%', width: 120, height: 120, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22 }}>{fmtMMSS(remain)}</span>
        </div>
        <div className="muted" style={{ margin: '8px 0' }}>🖥 桌面时钟{remote.paused ? '（已暂停）' : isBreak ? ' · 休息中' : ' · 工作中'}{remote.topmost ? ' · 📌置顶' : ''}</div>
        <div className="row" style={{ justifyContent: 'center', flexWrap: 'wrap' }}>
          <button className="btn btn-sm" onClick={() => ctrl(remote.paused ? 'resume' : 'pause')}>{remote.paused ? '继续' : '暂停'}</button>
          {isBreak ? (
            <button className="btn btn-sm btn-primary" onClick={() => ctrl('complete')}><Check size={14} strokeWidth={1.8} /> 结束休息</button>
          ) : (
            <>
              <button className="btn btn-sm btn-primary" onClick={() => ctrl('complete')}><Check size={14} strokeWidth={1.8} /> 完成→休息</button>
              <button className="btn btn-sm btn-danger" onClick={abandonRemote}><X size={14} strokeWidth={1.8} /> 放弃</button>
            </>
          )}
          <button className="btn btn-sm" onClick={() => ctrl('topmost', !remote.topmost)}>{remote.topmost ? '取消置顶' : '置顶'}</button>
        </div>
      </div>
    )
  }

  const display = mode === 'idle' ? fmt(0) : fmt(mode === 'work' ? totalWork - elapsed : totalBreak - elapsed)
  const pct = mode === 'idle' ? 0 : (elapsed / (mode === 'work' ? totalWork : totalBreak)) * 100

  return (
    <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--border)', textAlign: 'center' }}>
      {mode !== 'idle' && (
        <>
          <div className={`pomodoro-ring ${mode === 'work' ? 'work' : 'break'}`} style={{ background: `conic-gradient(var(--primary) ${pct * 3.6}deg, transparent 0)` }}>
            <span style={{ background: 'var(--card)', borderRadius: '50%', width: 120, height: 120, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20 }}>{display}</span>
          </div>
          <div className="muted" style={{ margin: '8px 0' }}>
            {mode === 'work' && (paused ? '⏸ 已暂停（暂停时间不计入时长）' : '工作中')}
            {mode === 'break' && '休息中'}
          </div>
        </>
      )}
      {mode === 'work' && (
        <div className="row" style={{ justifyContent: 'center' }}>
          <button className="btn" onClick={() => setPaused(p => !p)}>{paused ? '继续' : '暂停'}</button>
          <button className="btn btn-primary" onClick={() => completeLocal(false)}>完成 → 休息</button>
          <button className="btn btn-danger" onClick={abandonLocal}>放弃</button>
        </div>
      )}
      {mode === 'break' && <button className="btn btn-primary" onClick={finishBreakLocal}>结束休息</button>}

      {mode === 'idle' && (
        <>
          <div className="row" style={{ justifyContent: 'center', gap: 10, marginBottom: 8 }}>
            <label className="muted" style={{ fontSize: 12 }}>工作
              <input type="number" min="1" max="180" className="input d-weight-input" style={{ width: 64, marginLeft: 4 }} value={workMin}
                onChange={e => setWorkMin(e.target.value)} /> 分钟
            </label>
            <label className="muted" style={{ fontSize: 12 }}>休息
              <input type="number" min="0" max="60" className="input d-weight-input" style={{ width: 56, marginLeft: 4 }} value={breakMin}
                onChange={e => setBreakMin(e.target.value)} /> 分钟
            </label>
          </div>
          <div className="row" style={{ justifyContent: 'center', gap: 6, marginBottom: 10 }}>
            {POMO_PRESETS.map(m => (
              <button key={m} className={`btn btn-sm ${Number(workMin) === m && Number(breakMin) === 5 ? 'btn-primary' : ''}`} onClick={() => { setWorkMin(m); setBreakMin(5) }}>{m}′</button>
            ))}
          </div>
          <div className="row" style={{ justifyContent: 'center' }}>
            <button className="btn btn-primary" onClick={startLocal}><Play size={14} strokeWidth={1.8} /> 开始番茄钟</button>
            <button className="btn" onClick={startDesktop}><Monitor size={14} strokeWidth={1.8} /> 桌面时钟</button>
          </div>
          <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>时长修改后自动保存到该任务；桌面时钟悬浮于屏幕、可置顶</div>
        </>
      )}
    </div>
  )
}

function TaskCard({ task, goals, onChanged, onDragEnd, bulkMode, selected, onToggleSel, flash, noDrag }) {
  const [showTimer, setShowTimer] = useState(false)
  const [edit, setEdit] = useState(false)
  const [moreOpen, setMoreOpen] = useState(false)
  const [manualSec, setManualSec] = useState('')
  const [showCatchup, setShowCatchup] = useState(false)
  const [checkins, setCheckins] = useState([])
  const [showSubs, setShowSubs] = useState(false)
  const [subInput, setSubInput] = useState('')
  const [showDone, setShowDone] = useState(false)
  const [doneMin, setDoneMin] = useState('')
  const toast = useToast()

  const overdue = task.status !== 'done' && task.due_date && task.due_date < todayStr()
  const subDoneCount = (task.subtasks || []).filter(s => s.done).length

  const addSub = async () => {
    const title = subInput.trim()
    if (!title) return
    await api.post(`/tasks/${task.id}/subtasks`, { title })
    setSubInput('')
    onChanged()
  }
  const toggleSub = async s => {
    await api.put(`/tasks/subtasks/${s.id}`, { done: !s.done })
    onChanged()
  }
  const delSub = async s => {
    await api.delete(`/tasks/subtasks/${s.id}`)
    onChanged()
  }

  const checkin = async () => {
    if (task.checked_today && !confirm('取消今天的打卡？会中断连续打卡天数')) return
    await api.post(`/tasks/${task.id}/checkins`, { date: todayStr() })
    onChanged()
  }

  const openCatchup = async () => {
    const r = await api.get(`/tasks/${task.id}/checkins`)
    setCheckins(r.data)
    setShowCatchup(true)
  }
  const catchup = async d => {
    await api.post(`/tasks/${task.id}/checkins`, { date: d })
    toast('已补卡')
    onChanged()
    setShowCatchup(false)
  }
  const catchupDays = Array.from({ length: 7 }, (_, i) => {
    const d = new Date()
    d.setDate(d.getDate() - (i + 1))
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  })

  const setStatus = async st => {
    await api.put(`/tasks/${task.id}`, { status: st })
    onChanged()
  }

  // 标记完成：弹窗手填实际耗时（分钟，可跳过）→ 与 AI 预估形成「预计 vs 实际」对比
  const confirmDone = async () => {
    const m = Number(doneMin)
    const payload = { status: 'done' }
    if (m > 0) payload.actual_minutes = m
    await api.put(`/tasks/${task.id}`, payload)
    setShowDone(false)
    toast(m > 0 ? '已完成，实际用时已记录' : '已完成')
    onChanged()
  }

  const addManual = async () => {
    const min = Number(manualSec)
    if (!min || min <= 0) return
    await api.post(`/tasks/${task.id}/timelogs`, { duration_seconds: min * 60, kind: 'manual', note: '手动记录' })
    setManualSec('')
    toast('已记录时长')
    onChanged()
  }

  const del = async () => {
    if (!confirm(`删除任务「${task.title}」？`)) return
    await api.delete(`/tasks/${task.id}`)
    toast('已删除')
    onChanged()
  }

  const duplicate = async () => {
    try {
      await api.post(`/tasks/${task.id}/duplicate`)
      toast('已复制为新待办')
      onChanged()
    } catch (e) { toast('复制失败', 'error') }
  }

  return (
    <div
      className={`task-card ${task.task_type}${task.status === 'done' ? ' done' : ''}${overdue ? ' overdue' : ''}${flash ? ' flash' : ''}`}
      draggable={!bulkMode && !noDrag}
      onDragStart={e => { e.dataTransfer.setData('text/plain', String(task.id)); e.dataTransfer.effectAllowed = 'move' }}
      onDragEnd={onDragEnd}
    >
      <div className="row" style={{ justifyContent: 'space-between' }}>
        {bulkMode && (
          <input type="checkbox" checked={!!selected.has(task.id)} onChange={() => onToggleSel(task.id)} style={{ marginRight: 8 }} />
        )}
        <h4 style={{ flex: 1 }}>{task.title}</h4>
        <span className={`badge ${TYPE_BADGE[task.task_type] || 'badge-gray'}`}>{TYPE_LABEL[task.task_type] || task.task_type}</span>
      </div>
      {task.description && <div className="muted" style={{ marginBottom: 6 }}>{task.description}</div>}
      <div className="meta">
        <span className="priority-dots">
          {[1, 2, 3, 4, 5].map(p => <i key={p} className={p <= task.priority ? 'on' : ''} />)}
        </span>
        {task.due_date && <span className={overdue ? 'due-overdue' : ''}>📅 {task.due_date}{overdue ? ' ⚠已过期' : ''}</span>}
        {task.goal_title && <span>▲ {task.goal_title}</span>}
        {task.task_type === 'study' && <span>⏱ {fmt(task.total_seconds || 0)}</span>}
        {task.est_minutes && <span>⏱ 预计 {task.est_minutes} 分钟</span>}
        {task.actual_minutes && (
          <span style={{ color: task.est_minutes && task.actual_minutes > task.est_minutes * 1.2 ? 'var(--danger)' : 'var(--success)' }}>
            ✓ 实际 {task.actual_minutes} 分钟{task.est_minutes ? (task.actual_minutes > task.est_minutes ? '（超出预计）' : '（在预计内）') : ''}
          </span>
        )}
        {task.task_type === 'habit' && <span>🔥 {task.streak > 0 ? `连续 ${task.streak} 天` : (task.last_checkin ? `上次 ${task.last_checkin}` : '未开始')}</span>}
        {task.repeat_weekdays && <span className="badge badge-info">🔄 每周{task.repeat_weekdays.split(',').map(x => '一二三四五六日'[Number(x)] || x).join('、')}{task.next_repeat ? ` · 下次 ${task.next_repeat === todayStr() ? '今天' : task.next_repeat}` : ''}</span>}
        {task.repeat_source_id && <span className="badge badge-gray">🔄 循环实例</span>}
        {(task.subtasks || []).length > 0 && <span className="muted" style={{ fontWeight: 600 }}>☑ {subDoneCount}/{task.subtasks.length}</span>}
      </div>

      {showSubs && (
        <div style={{ marginTop: 8, borderTop: '1px dashed var(--border)', paddingTop: 8 }}>
          {(task.subtasks || []).map(s => (
            <div key={s.id} className="row" style={{ gap: 6, padding: '2px 0' }}>
              <input type="checkbox" checked={s.done} onChange={() => toggleSub(s)} />
              <span style={{ textDecoration: s.done ? 'line-through' : 'none', fontSize: 12, flex: 1, color: s.done ? 'var(--text-2)' : 'var(--text)' }}>{s.title}</span>
              <button className="btn btn-sm" onClick={() => delSub(s)} title="删除子任务"><X size={14} strokeWidth={1.8} /></button>
            </div>
          ))}
          <div className="row" style={{ gap: 6, marginTop: 4 }}>
            <input
              className="input"
              style={{ flex: 1, height: 26, fontSize: 12 }}
              placeholder="添加子任务，回车确认…"
              value={subInput}
              onChange={e => setSubInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !e.nativeEvent.isComposing) addSub() }}
            />
            <button className="btn btn-sm" onClick={addSub}>+ 添加</button>
          </div>
        </div>
      )}

      <div className="row" style={{ marginTop: 10, gap: 6 }}>
        {task.task_type === 'habit' ? (
          <>
            {task.status !== 'done' && (
              <button className={`btn btn-sm ${task.checked_today ? 'btn-success-checked' : 'btn-primary'}`} onClick={checkin}>
                {task.checked_today ? '已打卡' : '打卡'}
              </button>
            )}
            {task.status !== 'done' && <button className="btn btn-sm" onClick={openCatchup}>补卡</button>}
            {task.status === 'done' && <button className="btn btn-sm" onClick={() => setStatus('todo')}>恢复</button>}
          </>
        ) : (
          <>
            {task.status === 'todo' && <button className="btn btn-sm" onClick={() => setStatus('doing')}><Play size={14} strokeWidth={1.8} /> 开始</button>}
            {task.status === 'doing' && <button className="btn btn-sm" onClick={() => setStatus('todo')}><Pause size={14} strokeWidth={1.8} /> 暂停</button>}
            {task.status === 'done' && <button className="btn btn-sm" onClick={() => setStatus('todo')}>恢复</button>}
          </>
        )}
        {task.task_type === 'study' && task.status !== 'done' && (
          <button className="btn btn-sm btn-primary" onClick={() => setShowTimer(s => !s)}>
            {showTimer ? '收起计时器' : '🍅 番茄钟'}
          </button>
        )}
        <button className="btn btn-sm" onClick={() => setShowSubs(s => !s)}>
          {showSubs ? '收起子任务' : '子任务'}
        </button>
        <div style={{ position: 'relative' }}>
          <button className="btn btn-sm" onClick={() => setMoreOpen(o => !o)}>⋯</button>
          {moreOpen && (
            <div className="dropdown-menu task-menu" onClick={() => setMoreOpen(false)}>
              {task.status !== 'done' && <button className="btn" onClick={() => setShowDone(true)}><Check size={14} strokeWidth={1.8} /> 标记完成</button>}
              {task.task_type === 'study' && task.status !== 'done' && (
                <div className="row" style={{ gap: 6, padding: '2px 0' }}>
                  <input
                    className="input"
                    style={{ width: 72 }}
                    type="number"
                    placeholder="分钟"
                    value={manualSec}
                    onChange={e => setManualSec(e.target.value)}
                    onClick={e => e.stopPropagation()}
                  />
                  <button className="btn btn-sm" onClick={addManual}>+ 时长</button>
                </div>
              )}
              <button className="btn" onClick={() => setEdit(true)}><Pencil size={14} strokeWidth={1.8} /> 编辑</button>
              <button className="btn" onClick={duplicate}>⧉ 复制任务</button>
              <button className="btn btn-danger" onClick={del}><Trash2 size={14} strokeWidth={1.8} /> 删除</button>
            </div>
          )}
        </div>
      </div>

      {showTimer && task.task_type === 'study' && task.status !== 'done' && (
        <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--border)' }}>
          <Timer task={task} onDone={onChanged} />
        </div>
      )}

      {showCatchup && (
        <div className="modal-mask" onClick={() => setShowCatchup(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h3>补卡「{task.title}」</h3>
            <div className="muted" style={{ marginBottom: 10 }}>选择要补打卡的日期（最近 7 天）：</div>
            {catchupDays.map(d => {
              const done = checkins.includes(d)
              return (
                <div key={d} className="row" style={{ justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid var(--border)' }}>
                  <span>{d}</span>
                  {done ? (
                    <span className="badge badge-success">已打卡</span>
                  ) : (
                    <button className="btn btn-sm btn-primary" onClick={() => catchup(d)}>补卡</button>
                  )}
                </div>
              )
            })}
            <div className="modal-actions"><button className="btn" onClick={() => setShowCatchup(false)}>关闭</button></div>
          </div>
        </div>
      )}

      {edit && <TaskForm initial={task} goals={goals} onClose={() => setEdit(false)} onSaved={onChanged} />}

      {showDone && (
        <div className="modal-mask" onClick={() => setShowDone(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h3>✓ 完成「{task.title}」</h3>
            <label className="label">实际耗时（分钟，可跳过）</label>
            <input
              type="number"
              min="1"
              className="input"
              placeholder={task.est_minutes ? `预计 ${task.est_minutes} 分钟，实际用了多久？` : '如 45'}
              value={doneMin}
              onChange={e => setDoneMin(e.target.value)}
            />
            <div className="muted" style={{ marginTop: 6 }}>记录实际耗时后可与 AI 预估对比，方便以后排计划更准。</div>
            <div className="modal-actions">
              <button className="btn" onClick={() => setShowDone(false)}>取消</button>
              <button className="btn btn-primary" onClick={confirmDone}><Check size={14} strokeWidth={1.8} /> 标记完成</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default function Tasks() {
  const [tasks, setTasks] = useState([])
  const [goals, setGoals] = useState([])
  const [settings, setSettings] = useState({})
  const [showForm, setShowForm] = useState(false)
  const [bulkMode, setBulkMode] = useState(false)
  const [selected, setSelected] = useState(() => new Set())
  const [flashId, setFlashId] = useState(null)
  const [params] = useSearchParams()
  const [filter, setFilter] = useState('all')
  const [tagFilter, setTagFilter] = useState('')
  const [view, setView] = useState('board') // board/table/goal
  const [showTrash, setShowTrash] = useState(false)
  const [trash, setTrash] = useState([])
  const [collapsedGoals, setCollapsedGoals] = useState(() => new Set())
  // 统一「标记完成」弹窗（表格视图/批量完成与看板走同一套：可填实际耗时）
  const [donePrompt, setDonePrompt] = useState(null) // { ids:[], label:'' }
  const [donePromptMin, setDonePromptMin] = useState('')
  const toast = useToast()

  const load = () => {
    api.get('/tasks').then(r => setTasks(r.data)).catch(e => toast('加载任务失败', 'error'))
    api.get('/goals').then(r => setGoals(r.data))
    api.get('/settings').then(r => setSettings(r.data)).catch(() => {})
  }
  useEffect(load, [])

  // 搜索结果深链：/tasks?highlight=任务id 时高亮并滚动到该任务
  useEffect(() => {
    const h = params.get('highlight')
    if (h) {
      const id = Number(h)
      setFlashId(id)
      const timer = setTimeout(() => {
        const el = document.querySelector(`[data-task-id="${id}"]`)
        el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      }, 300)
      const t2 = setTimeout(() => setFlashId(null), 4000)
      return () => { clearTimeout(timer); clearTimeout(t2) }
    }
  }, [params])

  const toggleSel = id => setSelected(prev => {
    const next = new Set(prev)
    if (next.has(id)) next.delete(id); else next.add(id)
    return next
  })
  const bulkDone = () => {
    if (selected.size === 0) return
    setDonePromptMin('')
    setDonePrompt({ ids: [...selected], label: `批量完成 ${selected.size} 项` })
  }
  const confirmBulkDone = async () => {
    if (!donePrompt) return
    const m = Number(donePromptMin)
    const payload = m > 0 ? { status: 'done', actual_minutes: m } : { status: 'done' }
    await Promise.all(donePrompt.ids.map(id => api.put(`/tasks/${id}`, payload).catch(() => {})))
    toast(m > 0 ? `已批量完成 ${donePrompt.ids.length} 项（实际用时已记录）` : `已批量完成 ${donePrompt.ids.length} 项`)
    setDonePrompt(null); setDonePromptMin('')
    setSelected(new Set()); setBulkMode(false); load()
  }
  const bulkDelete = async () => {
    if (selected.size === 0) return
    if (!confirm(`删除选中的 ${selected.size} 项任务？`)) return
    await Promise.all([...selected].map(id => api.delete(`/tasks/${id}`).catch(() => {})))
    toast(`已删除 ${selected.size} 项`)
    setSelected(new Set()); setBulkMode(false); load()
  }

  // 智能筛选（全部/已逾期/高优先级/有DDL/无DDL + 标签）
  const allTags = [...new Set(tasks.flatMap(t => (t.tags || '').split(',').map(x => x.trim()).filter(Boolean)))]
  const today = todayStr()
  const visible = tasks.filter(t => {
    if (filter === 'overdue' && !(t.due_date && t.due_date < today && t.status !== 'done')) return false
    if (filter === 'high' && (t.priority || 2) < 3) return false
    if (filter === 'due' && !t.due_date) return false
    if (filter === 'nodue' && t.due_date) return false
    if (tagFilter && !(t.tags || '').split(',').map(x => x.trim()).includes(tagFilter)) return false
    return true
  })

  const cols = {
    todo: visible.filter(t => t.status === 'todo'),
    doing: visible.filter(t => t.status === 'doing'),
    done: visible.filter(t => t.status === 'done'),
  }

  const openTrash = async () => {
    setShowTrash(true)
    try { setTrash((await api.get('/tasks/trash')).data) } catch (e) { toast('加载回收站失败', 'error') }
  }

  const [dropHint, setDropHint] = useState(null)

  // 把 dragId 插入到 dropId 之前/之后（dropId 为 null 时插入到列末尾）。
  // B1：支持跨列拖拽——拖到其他列时先改任务状态，再在目标列执行插入排序。
  const insert = (colKey, dragId, dropId, before) => {
    const list = cols[colKey]
    const to = dropId ? list.findIndex(t => t.id === dropId) : -1
    if (dropId && to === -1) return
    const next = [...list]
    const from = next.findIndex(t => t.id === dragId)
    let moved
    if (from !== -1) {
      ;[moved] = next.splice(from, 1)
    } else {
      moved = tasks.find(t => t.id === dragId)
      if (!moved) return
      // 跨列：更新任务状态（todo/doing/done），后端会联动今日清单
      api.put(`/tasks/${dragId}`, { status: colKey }).catch(() => {})
    }
    const at = dropId ? next.findIndex(t => t.id === dropId) : next.length
    next.splice(before ? at : at + 1, 0, moved)
    next.forEach((t, i) => {
      if (t.sort_order !== i) {
        api.put(`/tasks/${t.id}`, { sort_order: i }).catch(() => {})
      }
    })
    // 重排数组（保持其他列相对顺序不变），否则界面不会实时更新
    setTasks(prev => {
      const ids = new Set(next.map(t => t.id))
      const rest = prev.filter(t => !ids.has(t.id))
      return [...rest, ...next]
    })
  }

  const isUpper = e => {
    const rect = e.currentTarget.getBoundingClientRect()
    return e.clientY < rect.top + rect.height / 2
  }

  const onDragOverCard = (e, dropId) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    const before = isUpper(e)
    setDropHint(h => (h && h.id === dropId && h.before === before) ? h : { id: dropId, before })
  }

  const onDragOverEnd = e => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    setDropHint(h => (h && h.id === null && h.before) ? h : { id: null, before: true })
  }

  const onDropCard = (colKey, e) => {
    e.preventDefault()
    e.stopPropagation() // 防止冒泡到列底部的 dropzone 再次触发“拖到末尾”
    setDropHint(null)
    const dragId = Number(e.dataTransfer.getData('text/plain'))
    const dropId = Number(e.currentTarget.dataset.taskId)
    if (dragId && dropId && dragId !== dropId) insert(colKey, dragId, dropId, isUpper(e))
  }

  const onDropEnd = (colKey, e) => {
    e.preventDefault()
    setDropHint(null)
    const dragId = Number(e.dataTransfer.getData('text/plain'))
    if (dragId) insert(colKey, dragId, null, true)
  }

  const clearHint = () => setDropHint(null)

  return (
    <div>
      <div className="page-header">
        <h1><span className="page-icon"><CheckSquare size={22} strokeWidth={1.75} /></span>任务</h1>
        <div className="row">
          {bulkMode ? (
            <>
              <span className="badge badge-info">已选 {selected.size} 项</span>
              <button className="btn btn-primary" onClick={bulkDone}><Check size={14} strokeWidth={1.8} /> 批量完成</button>
              <button className="btn btn-danger" onClick={bulkDelete}><Trash2 size={14} strokeWidth={1.8} /> 批量删除</button>
              <button className="btn" onClick={() => { setBulkMode(false); setSelected(new Set()) }}>取消</button>
            </>
          ) : (
            <>
              <button className="btn" onClick={() => setBulkMode(true)}><ListChecks size={14} strokeWidth={1.8} /> 批量操作</button>
              <button className="btn" onClick={openTrash}><Trash2 size={14} strokeWidth={1.8} /> 回收站</button>
              <button className="btn btn-primary" onClick={() => setShowForm(true)}>+ 新建任务</button>
            </>
          )}
        </div>
      </div>
      <div className="row" style={{ marginBottom: 12, gap: 6 }}>
        <button className={`btn btn-sm ${view === 'board' ? 'btn-primary' : ''}`} onClick={() => setView('board')}><ClipboardList size={14} strokeWidth={1.8} /> 看板</button>
        <button className={`btn btn-sm ${view === 'table' ? 'btn-primary' : ''}`} onClick={() => setView('table')}><BarChart3 size={14} strokeWidth={1.8} /> 表格</button>
        <button className={`btn btn-sm ${view === 'goal' ? 'btn-primary' : ''}`} onClick={() => setView('goal')} title="按目标分组查看任务，目标感强的任务聚在目标下，日常任务在「未关联」区"><MapIcon size={14} strokeWidth={1.8} /> 按目标</button>
        {[['all', '全部'], ['overdue', '已逾期'], ['high', '高优先级'], ['due', '有 DDL'], ['nodue', '无 DDL']].map(([k, l]) => (
          <button key={k} className={`btn btn-sm ${filter === k ? 'btn-primary' : ''}`} onClick={() => setFilter(k)}>{l}</button>
        ))}
        <select className="select" style={{ width: 130, height: 30, padding: '4px 8px' }} value={tagFilter} onChange={e => setTagFilter(e.target.value)}>
          <option value="">全部标签</option>
          {allTags.map(x => <option key={x} value={x}>{x}</option>)}
        </select>
        {(filter !== 'all' || tagFilter) && <button className="btn btn-sm" onClick={() => { setFilter('all'); setTagFilter('') }}><X size={14} strokeWidth={1.8} /> 清除筛选</button>}
      </div>
      {view === 'goal' ? (
        (() => {
          // 按目标分组：有目标的任务聚到对应目标下（凸显 目标→任务 层级），无目标的是日常任务
          const goalMap = new Map(goals.map(g => [g.id, g]))
          const grouped = new Map()
          const unassigned = []
          visible.forEach(t => {
            if (t.goal_id && goalMap.has(t.goal_id)) {
              if (!grouped.has(t.goal_id)) grouped.set(t.goal_id, [])
              grouped.get(t.goal_id).push(t)
            } else {
              unassigned.push(t)
            }
          })
          const so = { doing: 0, todo: 1, done: 2 }
          const sortT = (a, b) => (so[a.status] - so[b.status]) || (a.due_date || '').localeCompare(b.due_date || '')
          const LEVEL_LABEL = { annual: '年度', quarter: '季度', month: '月度', week: '周度' }
          const LEVEL_BADGE = { annual: 'badge-primary', quarter: 'badge-info', month: 'badge-warn', week: 'badge-gray' }
          const toggleGoal = id => setCollapsedGoals(s => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n })
          const renderGroup = (g, tasks) => {
            const collapsed = collapsedGoals.has(g.id)
            return (
              <div className="card" key={g.id} style={{ marginBottom: 12 }}>
                <div className="card-title" style={{ cursor: 'pointer', alignItems: 'center', gap: 8 }} onClick={() => toggleGoal(g.id)}>
                  <span>🎯 {g.title}</span>
                  <span className={`badge ${LEVEL_BADGE[g.level] || 'badge-gray'}`}>{LEVEL_LABEL[g.level] || g.level}</span>
                  <div className="progress-bar" style={{ flex: 1, maxWidth: 200 }}><div style={{ width: `${g.progress || 0}%`, background: 'var(--primary)' }} /></div>
                  <span className="muted" style={{ fontSize: 12 }}>{g.progress || 0}%</span>
                  <span className="muted" style={{ fontSize: 12 }}>{tasks.length} 项</span>
                  <span className="muted" style={{ fontSize: 12 }}>{collapsed ? '▶ 展开' : '▼ 收起'}</span>
                </div>
                {!collapsed && tasks.sort(sortT).map(t => (
                  <TaskCard key={t.id} task={t} goals={goals} onChanged={load} bulkMode={bulkMode} selected={selected} onToggleSel={toggleSel} flash={flashId === t.id} noDrag />
                ))}
              </div>
            )
          }
          return (
            <div>
              {visible.length === 0 && <div className="empty"><span className="empty-icon">📭</span>没有符合条件的任务</div>}
              {[...grouped.entries()].map(([gid, ts]) => renderGroup(goalMap.get(gid), ts))}
              {unassigned.length > 0 && (
                <div className="card" style={{ marginBottom: 12 }}>
                  <div className="card-title">📦 未关联任务（日常执行）</div>
                  {unassigned.sort(sortT).map(t => (
                    <TaskCard key={t.id} task={t} goals={goals} onChanged={load} bulkMode={bulkMode} selected={selected} onToggleSel={toggleSel} flash={flashId === t.id} noDrag />
                  ))}
                </div>
              )}
            </div>
          )
        })()
      ) : view === 'board' ? (
      <div className="kanban">
        {[
          { key: 'todo', label: '待办', color: 'var(--warn)' },
          { key: 'doing', label: '进行中', color: 'var(--info)' },
          { key: 'done', label: '已完成', color: 'var(--success)' },
        ].map(c => (
          <div className="kanban-col" key={c.key}>
            <h3><span style={{ color: c.color }}>{c.label}</span><span>{cols[c.key].length}</span></h3>
            <div
              className="kanban-dropzone"
              onDragOver={onDragOverEnd}
              onDrop={e => onDropEnd(c.key, e)}
            >
              {cols[c.key].length === 0 && <div className="empty"><span className="empty-icon">📭</span>暂无任务</div>}
              {cols[c.key].map(t => (
                <div
                  key={t.id}
                  data-task-id={t.id}
                  className="kanban-item"
                  onDragOver={e => onDragOverCard(e, t.id)}
                  onDrop={e => onDropCard(c.key, e)}
                >
                  {dropHint?.id === t.id && dropHint.before && <div className="drop-indicator" />}
                  <TaskCard task={t} goals={goals} onChanged={load} onDragEnd={clearHint} bulkMode={bulkMode} selected={selected} onToggleSel={toggleSel} flash={flashId === t.id} />
                  {dropHint?.id === t.id && !dropHint.before && <div className="drop-indicator" />}
                </div>
              ))}
{dropHint?.id === null && <div className="drop-indicator" />}
            </div>
          </div>
        ))}
      </div>
      ) : (
        <div className="card" style={{ padding: 0, overflow: 'auto' }}>
          <table className="compare-table" style={{ marginBottom: 0 }}>
            <thead>
              <tr>
                <th style={{ minWidth: 220 }}>标题</th><th>类型</th><th>优先级</th><th>截止日期</th><th>预计/实际</th><th>标签</th><th>关联目标</th><th>状态</th>
              </tr>
            </thead>
            <tbody>
              {visible.map(t => (
                <tr key={t.id}>
                  <td style={{ maxWidth: 280 }}>
                    <span style={{ fontWeight: 600 }}>{t.title}</span>
                    {t.repeat_weekdays && <span className="badge badge-info" style={{ marginLeft: 6 }}>🔄</span>}
                    {(t.subtasks || []).length > 0 && <span className="muted" style={{ marginLeft: 6 }}>☑ {t.subtasks.filter(s => s.done).length}/{t.subtasks.length}</span>}
                  </td>
                  <td><span className={`badge ${TYPE_BADGE[t.task_type] || 'badge-gray'}`}>{TYPE_LABEL[t.task_type] || t.task_type}</span></td>
                  <td>
                    <select
                      className="select"
                      style={{ width: 64, padding: '2px 4px', height: 26 }}
                      value={t.priority}
                      onChange={e => api.put(`/tasks/${t.id}`, { priority: Number(e.target.value) }).then(load)}
                    >
                      {[1, 2, 3, 4, 5].map(p => <option key={p} value={p}>{p}</option>)}
                    </select>
                  </td>
                  <td>
                    <input
                      type="date"
                      className="input"
                      style={{ width: 130, padding: '2px 6px', height: 26 }}
                      value={t.due_date || ''}
                      onChange={e => api.put(`/tasks/${t.id}`, { due_date: e.target.value || null }).then(load)}
                    />
                  </td>
                  <td>
                    {t.est_minutes ? `预计 ${t.est_minutes}m` : '—'}
                    {t.actual_minutes ? ` · 实际 ${t.actual_minutes}m` : ''}
                  </td>
                  <td style={{ maxWidth: 140, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{t.tags || '—'}</td>
                  <td style={{ maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{t.goal_title || '—'}</td>
                  <td>
                    <select
                      className="select"
                      style={{ width: 80, padding: '2px 4px', height: 26 }}
                      value={t.status}
                      onChange={e => {
                        const v = e.target.value
                        if (v === 'done' && t.status !== 'done') {
                          // 与看板一致：弹窗可填实际耗时（可留空）
                          setDonePromptMin('')
                          setDonePrompt({ ids: [t.id], label: t.title })
                        } else {
                          api.put(`/tasks/${t.id}`, { status: v }).then(load)
                        }
                      }}
                    >
                      <option value="todo">待办</option>
                      <option value="doing">进行中</option>
                      <option value="done">已完成</option>
                    </select>
                  </td>
                </tr>
              ))}
              {visible.length === 0 && (
                <tr><td colSpan="8"><div className="empty"><span className="empty-icon">📭</span>没有符合条件的任务</div></td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
      {donePrompt && (
        <div className="modal-mask" onClick={() => setDonePrompt(null)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h3>标记完成：{donePrompt.label}</h3>
            <div className="form-row">
              <label className="form-label">实际耗时（分钟，可留空跳过）</label>
              <input type="number" min="1" className="input" value={donePromptMin}
                onChange={e => setDonePromptMin(e.target.value)} autoFocus placeholder="如 45" />
            </div>
            <div className="modal-actions">
              <button className="btn" onClick={() => setDonePrompt(null)}>取消</button>
              <button className="btn btn-primary" onClick={confirmBulkDone}><Check size={14} strokeWidth={1.8} /> 确认完成</button>
            </div>
          </div>
        </div>
      )}
      {showForm && <TaskForm goals={goals} defaultPomo={Number(settings.pomodoro_minutes) || 25} defaultBreak={Number(settings.break_minutes) || 5} onClose={() => setShowForm(false)} onSaved={load} />}
      {showTrash && (
        <div className="modal-mask" onClick={() => setShowTrash(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h3>🗑 回收站</h3>
            <div className="row" style={{ justifyContent: 'space-between', marginBottom: 10 }}>
              <div className="muted">删除的任务在这里，可恢复或彻底删除。</div>
              {trash.length > 0 && (
                <button className="btn btn-sm btn-danger" onClick={async () => {
                  if (!confirm(`清空回收站全部 ${trash.length} 项任务？此操作不可恢复`)) return
                  await api.delete('/tasks/trash')
                  toast('回收站已清空')
                  setShowTrash(false); load()
                }}><Trash2 size={14} strokeWidth={1.8} /> 清空回收站</button>
              )}
            </div>
            {trash.length === 0 && <div className="empty"><span className="empty-icon">🗑</span>回收站是空的</div>}
            {trash.map(x => (
              <div key={x.id} className="row" style={{ justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid var(--border)' }}>
                <span style={{ flex: 1, minWidth: 0 }}>{x.title} <span className="muted">（{TYPE_LABEL[x.task_type] || x.task_type} · {x.archived_at?.slice(0, 10)}）</span></span>
                <button className="btn btn-sm" onClick={async () => {
                  await api.post(`/tasks/${x.id}/restore`)
                  toast('已恢复')
                  load(); openTrash()
                }}>恢复</button>
                <button className="btn btn-sm btn-danger" onClick={async () => {
                  if (!confirm(`彻底删除「${x.title}」？此操作不可恢复`)) return
                  await api.delete(`/tasks/${x.id}/purge`)
                  toast('已彻底删除')
                  openTrash()
                }}>彻底删除</button>
              </div>
            ))}
            <div className="modal-actions"><button className="btn" onClick={() => setShowTrash(false)}>关闭</button></div>
          </div>
        </div>
      )}
    </div>
  )
}
