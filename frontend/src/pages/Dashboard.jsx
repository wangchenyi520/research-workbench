import React, { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api'
import { LayoutDashboard, Clock, Timer, Flame, ListTodo, ArrowUpRight, Check, MoveHorizontal, Pencil, RotateCcw, Sparkles } from 'lucide-react'

const LEVEL = { l0: 0, l1: 1, l2: 2, l3: 3, l4: 4 }

function fmtDuration(sec) {
  if (!sec) return '0分钟'
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  return h > 0 ? `${h}小时${m}分钟` : `${m}分钟`
}

function fmtHours(sec) {
  if (!sec) return '0h'
  const h = sec / 3600
  return (Math.round(h * 10) / 10).toString() + 'h'
}

function Heatmap({ data }) {
  const days = data.days || 90
  const cells = []
  const today = new Date()
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(today)
    d.setDate(d.getDate() - i)
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
    const sec = data.data?.[key] || 0
    let lv = LEVEL.l0
    if (sec > 7200) lv = LEVEL.l4
    else if (sec > 3600) lv = LEVEL.l3
    else if (sec > 900) lv = LEVEL.l2
    else if (sec >= 60) lv = LEVEL.l1
    cells.push({ key, lv, sec })
  }
  return (
    <div className="heatmap">
      {cells.map(c => (
        <div key={c.key} className={`hm-cell l${c.lv}`} title={`${c.key}: ${fmtDuration(c.sec)}`} />
      ))}
    </div>
  )
}

const DEFAULT_SIZE = { w: 4, h: 2 }
const FULL_SIZE = { w: 12, h: 2 }
const DEFAULT_ORDER = ['monthly', 'week', 'heatmap', 'distribution', 'pomodoro', 'compare', 'goals', 'milestones', 'habits', 'today', 'ai']

export default function Dashboard() {
  const navigate = useNavigate()
  const [stats, setStats] = useState({ total_seconds: 0, pomodoros: 0 })
  const [heat, setHeat] = useState({ days: 90, data: {} })
  const [tasks, setTasks] = useState([])
  const [milestones, setMilestones] = useState([])
  const [monthly, setMonthly] = useState([])
  const [distribution, setDistribution] = useState([])
  const [compare, setCompare] = useState([])
  const [goalProgress, setGoalProgress] = useState([])
  const [pomodoro, setPomodoro] = useState({ data: [], total: 0, avg_per_day: 0 })
  const [habits, setHabits] = useState({ habits: [], achievements: [] })
  const [loading, setLoading] = useState(true)

  const [order, setOrder] = useState(() => {
    try {
      const saved = JSON.parse(localStorage.getItem('wb_dash_order'))
      if (Array.isArray(saved) && saved.length) {
        const merged = saved.filter(k => DEFAULT_ORDER.includes(k))
        DEFAULT_ORDER.forEach(k => { if (!merged.includes(k)) merged.push(k) })
        return merged
      }
    } catch (e) {}
    return DEFAULT_ORDER
  })
  const [sizes, setSizes] = useState(() => {
    try {
      const s = JSON.parse(localStorage.getItem('wb_dash_size'))
      return s && typeof s === 'object' ? s : {}
    } catch (e) { return {} }
  })
  const [editMode, setEditMode] = useState(false)
  const dragKeyRef = useRef(null)
  const resizeRef = useRef(null)

  useEffect(() => {
    const load = () => {
      Promise.all([
        api.get('/tasks/stats/today').then(r => setStats(r.data)).catch(() => {}),
        api.get('/tasks/stats/heatmap?days=90').then(r => setHeat(r.data)).catch(() => {}),
        api.get('/tasks').then(r => setTasks(r.data)).catch(() => {}),
        api.get('/goals/milestones').then(r => setMilestones(r.data)).catch(() => {}),
        api.get('/stats/monthly?days=30').then(r => setMonthly(r.data.data)).catch(() => {}),
        api.get('/stats/distribution?days=30').then(r => setDistribution(r.data)).catch(() => {}),
        api.get('/stats/compare?months=6').then(r => setCompare(r.data.data)).catch(() => {}),
        api.get('/stats/goal-progress').then(r => setGoalProgress(r.data)).catch(() => {}),
        api.get('/stats/pomodoro?days=14').then(r => setPomodoro(r.data)).catch(() => {}),
        api.get('/stats/habits').then(r => setHabits(r.data)).catch(() => {}),
      ]).finally(() => setLoading(false))
    }
    load()
    // B12：页面停留期间定时刷新 + 窗口重新聚焦时刷新（桌面时钟后台计时也能跟上）
    const iv = setInterval(load, 30000)
    const onFocus = () => load()
    window.addEventListener('focus', onFocus)
    return () => { clearInterval(iv); window.removeEventListener('focus', onFocus) }
  }, [])

  const todayTasks = useMemo(() => {
    const d = new Date()
    const todayKey = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
    // B9：已完成(标 done)的习惯任务不再计入「待打卡」
    const habit = tasks.filter(t => t.task_type === 'habit' && t.status !== 'done')
    const once = tasks.filter(t =>
      t.task_type === 'once' && t.status === 'todo' && t.due_date === todayKey
    )
    return { habit, once }
  }, [tasks])

  const weekBars = useMemo(() => {
    const now = new Date()
    const start = new Date(now)
    // 本周起点（周一）：周日 getDay()=0 时往前推 6 天
    const dow = start.getDay()
    const diff = dow === 0 ? 6 : dow - 1
    start.setDate(start.getDate() - diff)
    const out = []
    for (let i = 0; i < 7; i++) {
      const d = new Date(start)
      d.setDate(start.getDate() + i)
      const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
      const sec = heat.data?.[key] || 0
      out.push({ key, sec, label: ['一', '二', '三', '四', '五', '六', '日'][i] })
    }
    const max = Math.max(...out.map(o => o.sec), 1)
    return { out, max }
  }, [heat])

  const monthlyBars = useMemo(() => {
    const data = monthly.length ? monthly : Array.from({ length: 30 }, (_, i) => {
      const d = new Date()
      d.setDate(d.getDate() - (29 - i))
      return { label: `${d.getMonth() + 1}/${d.getDate()}`, seconds: 0 }
    })
    const max = Math.max(...data.map(d => d.seconds), 1)
    return { data, max }
  }, [monthly])

  const distMax = Math.max(...distribution.map(d => d.seconds), 1)

  const sizeOf = key => ({ ...(key === 'monthly' ? FULL_SIZE : DEFAULT_SIZE), ...(sizes[key] || {}) })
  const persistSizes = next => { setSizes(next); localStorage.setItem('wb_dash_size', JSON.stringify(next)) }
  const updateSize = (key, dw, dh) => {
    const cur = sizeOf(key)
    const next = { ...sizes, [key]: { w: Math.min(12, Math.max(2, cur.w + dw)), h: Math.min(4, Math.max(1, cur.h + dh)) } }
    persistSizes(next)
  }
  const resetLayout = () => {
    persistSizes({})
    setOrder(DEFAULT_ORDER)
    localStorage.setItem('wb_dash_order', JSON.stringify(DEFAULT_ORDER))
  }

  const onDragStart = key => { dragKeyRef.current = key }
  const onDrop = key => {
    const from = order.indexOf(dragKeyRef.current)
    const to = order.indexOf(key)
    if (from === -1 || to === -1 || from === to) { return }
    const next = [...order]
    const [moved] = next.splice(from, 1)
    next.splice(to, 0, moved)
    setOrder(next)
    localStorage.setItem('wb_dash_order', JSON.stringify(next))
  }

  const onResizeStart = (key, e) => {
    e.preventDefault()
    e.stopPropagation()
    resizeRef.current = { key, accX: 0, accY: 0, lastX: e.clientX, lastY: e.clientY, active: true }
    document.body.style.cursor = 'nwse-resize'
    document.body.style.userSelect = 'none'
    window.addEventListener('mousemove', onResizeMove)
    window.addEventListener('mouseup', onResizeEnd)
  }
  const onResizeMove = e => {
    const r = resizeRef.current
    if (!r || !r.active) return
    r.accX += e.clientX - r.lastX
    r.accY += e.clientY - r.lastY
    r.lastX = e.clientX
    r.lastY = e.clientY
    let dw = 0, dh = 0
    while (r.accX > 40) { dw += 1; r.accX -= 40 }
    while (r.accX < -40) { dw -= 1; r.accX += 40 }
    while (r.accY > 40) { dh += 1; r.accY -= 40 }
    while (r.accY < -40) { dh -= 1; r.accY += 40 }
    if (dw || dh) updateSize(r.key, dw, dh)
  }
  const onResizeEnd = () => {
    resizeRef.current = null
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
    window.removeEventListener('mousemove', onResizeMove)
    window.removeEventListener('mouseup', onResizeEnd)
  }
  const toggleSpan = key => {
    const cur = sizeOf(key)
    updateSize(key, cur.w === 12 ? -8 : 8, 0)
  }

  const cards = {
    week: { title: '本周投入时长', link: '/reports', body: (
      <div className="chart-bars">
        {weekBars.out.map(b => (
          <div key={b.key} style={{ display: 'flex', flexDirection: 'column', flex: 1, height: '100%' }}>
            <div style={{ flex: 1, display: 'flex', alignItems: 'flex-end' }}>
              <div className="chart-bar" style={{ height: `${(b.sec / weekBars.max) * 100}%` }} title={fmtDuration(b.sec)} />
            </div>
            <div className="chart-bar-label">{b.label}</div>
          </div>
        ))}
      </div>
    ) },
    monthly: { title: '近 30 天投入趋势', link: '/reports', body: (
      <>
        <div style={{ height: 120, display: 'flex', alignItems: 'flex-end', gap: 2 }}>
          {monthlyBars.data.map((b, i) => (
            <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'flex-end', height: '100%', minWidth: 0 }}>
              <div className="chart-bar" style={{ flex: '0 0 auto', width: '80%', height: `${(b.seconds / monthlyBars.max) * 100}%`, background: 'linear-gradient(180deg,var(--info),var(--primary))' }} title={`${b.label}: ${fmtDuration(b.seconds)}`} />
            </div>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 2, marginTop: 4 }}>
          {monthlyBars.data.map((b, i) => {
            const fromEnd = monthlyBars.data.length - 1 - i
            const show = fromEnd % 7 === 0
            return (
              <div key={i} style={{ flex: 1, textAlign: 'center', fontSize: 10, fontWeight: 500, color: fromEnd === 0 ? 'var(--primary)' : 'var(--text-2)', overflow: 'hidden', whiteSpace: 'nowrap', minWidth: 0 }}>
                {show ? (fromEnd === 0 ? '今天' : b.label) : ''}
              </div>
            )
          })}
        </div>
      </>
    ) },
    heatmap: { title: '近 90 天投入热力图', link: '/calendar', body: <Heatmap data={heat} /> },
    distribution: { title: '任务耗时分布（近 30 天）', link: '/tasks', body: (
      <>
        {distribution.length === 0 && <div className="empty"><span className="empty-icon">⏱</span>暂无计时数据</div>}
        {distribution.map(d => (
          <div key={d.task_id} style={{ marginBottom: 8 }}>
            <div className="row" style={{ justifyContent: 'space-between' }}>
              <span style={{ fontSize: 13 }}>{d.title}</span>
              <span className="muted">{fmtDuration(d.seconds)}</span>
            </div>
            <div className="progress-bar" style={{ marginTop: 4 }}><div style={{ width: `${(d.seconds / distMax) * 100}%` }} /></div>
          </div>
        ))}
      </>
    ) },
    milestones: { title: '里程碑倒计时', link: '/goals', body: (
      <>
        {milestones.length === 0 && <div className="empty"><span className="empty-icon">🏁</span>暂无里程碑，去「规划」页添加</div>}
        <div className="timeline">
          {milestones.map(m => (
            <div className="timeline-item" key={m.id}>
              <div className="timeline-dot" style={{ background: m.completed ? 'var(--success)' : m.color }} />
              <div>
                <div style={{ fontWeight: 600, textDecoration: m.completed ? 'line-through' : 'none' }}>{m.title}</div>
                <div className="muted">
                  {m.due_date ? `${m.due_date} · ` : ''}
                  {m.completed ? '已完成' : m.days_left !== null ? (m.days_left < 0 ? `已过期 ${-m.days_left} 天` : `还剩 ${m.days_left} 天`) : ''}
                </div>
              </div>
            </div>
          ))}
        </div>
      </>
    ) },
    pomodoro: { title: '番茄统计', link: '/tasks', body: (() => {
      const last14 = pomodoro.data.slice(-14)
      const todayCount = last14.length ? last14[last14.length - 1].count : 0
      const max14 = Math.max(...last14.map(d => d.count), 1)
      return (
        <>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
            <span style={{ fontSize: 38, fontWeight: 800, color: 'var(--primary)', lineHeight: 1 }}>{todayCount}</span>
            <span className="muted" style={{ fontSize: 13 }}>个 · 今日</span>
            <span className="muted" style={{ marginLeft: 'auto', fontSize: 12 }}>
              近14天累计 <b style={{ color: 'var(--info)' }}>{pomodoro.total}</b> · 日均 <b>{pomodoro.avg_per_day}</b>
            </span>
          </div>
          <div style={{ flex: 1, minHeight: 0, display: 'flex', alignItems: 'flex-end', gap: 6, marginTop: 10 }}>
            {last14.map((d, i) => {
              const isToday = i === last14.length - 1
              return (
                <div
                  key={d.date}
                  title={`${d.date}: ${d.count} 个番茄`}
                  style={{
                    flex: 1,
                    maxWidth: 16,
                    height: d.count > 0 ? `${Math.max(12, (d.count / max14) * 100)}%` : 5,
                    borderRadius: 4,
                    background: isToday
                      ? 'linear-gradient(180deg,var(--primary),var(--info))'
                      : d.count > 0 ? 'var(--info)' : 'var(--border)',
                    opacity: isToday ? 1 : d.count > 0 ? 0.75 : 1,
                    boxShadow: isToday ? '0 0 0 2px var(--card), 0 0 0 3.5px var(--primary)' : 'none',
                  }}
                />
              )
            })}
          </div>
          <div className="row" style={{ justifyContent: 'space-between', marginTop: 6 }}>
            <span className="muted" style={{ fontSize: 10 }}>近 14 天</span>
            <span className="muted" style={{ fontSize: 10 }}>今天</span>
          </div>
        </>
      )
    })() },
    compare: { title: '近 6 月趋势对比', link: '/reports', body: (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
        {compare.length === 0 && <div className="empty"><span className="empty-icon">📉</span>暂无数据</div>}
        <div className="row" style={{ gap: 10, alignItems: 'flex-end' }}>
          {compare.map(c => (
            <div key={c.month} style={{ flex: 1, textAlign: 'center' }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--primary)' }}>{fmtHours(c.seconds)}</div>
              <div className="progress-bar" style={{ marginTop: 6, height: 10 }}><div style={{ width: `${Math.min(c.seconds / (Math.max(...compare.map(x => x.seconds), 1)) * 100, 100)}%` }} /></div>
              <div className="chart-bar-label">{c.label.slice(2)}</div>
              <div className="muted">{c.done} 完成</div>
            </div>
          ))}
        </div>
      </div>
    ) },
    goals: { title: '目标完成率', link: '/goals', body: (
      <>
        {goalProgress.length === 0 && <div className="empty"><span className="empty-icon">🎯</span>暂无目标，去「规划」页添加</div>}
        {goalProgress.slice(0, 6).map(g => (
          <div key={g.id} style={{ marginBottom: 10 }}>
            <div className="row" style={{ justifyContent: 'space-between' }}>
              <span style={{ fontSize: 13 }}>{g.title}</span>
              <span className="muted">{g.progress}%</span>
            </div>
            <div className="progress-bar" style={{ marginTop: 4 }}><div style={{ width: `${Math.min(g.progress, 100)}%`, background: g.status === 'done' ? 'var(--success)' : undefined }} /></div>
          </div>
        ))}
      </>
    ) },
    habits: { title: '习惯连续打卡', link: '/tasks', body: (
      <>
        {habits.habits.length === 0 && <div className="empty"><span className="empty-icon">🔥</span>暂无习惯任务，去「任务」页添加习惯</div>}
        {habits.habits.map(h => (
          <div key={h.task_id} className="row" style={{ padding: '6px 0', justifyContent: 'space-between' }}>
            <span>{h.title}</span>
            <span className="badge badge-success">🔥 连续 {h.streak} 天 · 共 {h.total} 天</span>
          </div>
        ))}
        <div className="muted" style={{ fontWeight: 600, margin: '10px 0 6px' }}>成就</div>
        <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
          {habits.achievements.map(a => (
            <span key={a.key} className={`badge ${a.achieved ? 'badge-success' : 'badge-gray'}`} title={a.label} style={{ fontSize: 12 }}>
              {a.icon} {a.label} {a.achieved ? '' : `(${a.progress}/${a.target})`}
            </span>
          ))}
        </div>
      </>
    ) },
    today: { title: '今日概览', link: '/tasks', body: (
      <>
        {todayTasks.habit.length === 0 && todayTasks.once.length === 0 && <div className="empty"><span className="empty-icon">📋</span>今天暂无安排，去「任务」页添加</div>}
        {todayTasks.habit.map(t => (
          <div key={t.id} className="row" style={{ padding: '6px 0', justifyContent: 'space-between' }}>
            <span>【习惯】{t.title}</span>
            <span className={`badge ${t.checked_today ? 'badge-success' : 'badge-warn'}`}>{t.checked_today ? '已打卡' : '待打卡'}</span>
          </div>
        ))}
        {todayTasks.once.map(t => (
          <div key={t.id} className="row" style={{ padding: '6px 0', justifyContent: 'space-between' }}>
            <span>【今日截止】{t.title}</span>
            <span className="badge badge-danger">今天到期</span>
          </div>
        ))}
      </>
    ) },
    ai: { title: '✨ AI 今日建议', link: '/today', body: (
      <div className="empty">
        <span className="empty-icon">✨</span>
        <div style={{ marginBottom: 8 }}>AI 每日整理已迁移到「今日」页：自动生成建议、可勾选多条采纳，并综合文献/技能/长期规划。</div>
        <button className="btn btn-primary btn-sm" onClick={() => navigate('/today')}><Sparkles size={14} strokeWidth={1.8} /> 去今日页查看</button>
      </div>
    ) },
  }

  return (
    <div>
      <div className="page-header">
        <h1><span className="page-icon"><LayoutDashboard size={22} strokeWidth={1.75} /></span>仪表盘</h1>
        <div className="row">
          <button className={`btn ${editMode ? 'btn-primary' : ''}`} onClick={() => setEditMode(!editMode)}>
            {editMode ? <><Check size={14} strokeWidth={1.8} /> 完成编辑</> : <><Pencil size={14} strokeWidth={1.8} /> 编辑布局</>}
          </button>
          {editMode && <button className="btn" onClick={resetLayout}><RotateCcw size={14} strokeWidth={1.8} /> 重置布局</button>}
        </div>
      </div>

      {loading ? (
        <>
          <div className="grid grid-4" style={{ marginBottom: 16 }}>
            {[0, 1, 2, 3].map(i => <div key={i} className="card skeleton" style={{ height: 96 }} />)}
          </div>
          <div className="dash-grid">
            {DEFAULT_ORDER.filter(k => cards[k]).map(k => {
              const size = sizeOf(k)
              return <div key={k} className="card skeleton" style={{ gridColumn: `span ${size.w}`, gridRow: `span ${size.h}` }} />
            })}
          </div>
        </>
      ) : (
      <>
      <div className="grid grid-4" style={{ marginBottom: 16 }}>
        <div className="stat-card stat-purple">
          <span className="stat-icon" title="前往报告页" onClick={() => navigate('/reports')}><Clock size={15} strokeWidth={2} /></span><div className="stat-label">今日投入</div><div className="stat-value">{fmtDuration(stats.total_seconds)}</div>
        </div>
        <div className="stat-card stat-blue">
          <span className="stat-icon" title="前往任务页" onClick={() => navigate('/tasks')}><Timer size={15} strokeWidth={2} /></span><div className="stat-label">今日番茄</div><div className="stat-value">{stats.pomodoros} 个</div>
        </div>
        <div className="stat-card stat-green">
          <span className="stat-icon" title="前往任务页" onClick={() => navigate('/tasks')}><Flame size={15} strokeWidth={2} /></span><div className="stat-label">今日待打卡</div><div className="stat-value">{todayTasks.habit.filter(t => !t.checked_today).length} 项</div>
        </div>
        <div className="stat-card stat-orange">
          <span className="stat-icon" title="前往任务页" onClick={() => navigate('/tasks')}><ListTodo size={15} strokeWidth={2} /></span><div className="stat-label">未完成任务</div><div className="stat-value">{tasks.filter(t => t.status !== 'done').length} 项</div>
        </div>
      </div>

      {editMode && (
        <div className="dash-editbar card">
          <strong>编辑布局</strong>
          <span className="muted">拖动卡片右下角手柄调整大小；拖动卡片调整位置；点击 ⇔ 切换全宽</span>
        </div>
      )}

      <div className="dash-grid">
{order.filter(k => cards[k]).map(k => {
            const size = sizeOf(k)
            return (
              <div
                key={k}
                className={`dash-card ${editMode ? 'editing' : ''}`}
                style={{ gridColumn: `span ${size.w}`, gridRow: `span ${size.h}` }}
                draggable={!editMode}
                onDragStart={() => onDragStart(k)}
                onDragOver={e => e.preventDefault()}
                onDrop={() => onDrop(k)}
              >
                <div className="dash-card-header">
                  <span className="dash-card-title">{cards[k].title}</span>
                  <span className="dash-card-actions">
                    <button className="dash-action" title="切换全宽" onClick={() => toggleSpan(k)}><MoveHorizontal size={14} strokeWidth={1.8} /></button>
                    {cards[k].link && <button className="dash-action" title="前往详情" onClick={() => navigate(cards[k].link)}><ArrowUpRight size={14} strokeWidth={1.8} /></button>}
                  </span>
                </div>
                <div className="dash-card-body">{cards[k].body}</div>
                {editMode && <span className="resize-handle" onMouseDown={e => onResizeStart(k, e)}>◢</span>}
              </div>
            )
          })}
        </div>
        </>
      )}
      <div className="muted" style={{ marginTop: 10 }}>提示：点击「编辑布局」可调整卡片大小和位置，布局自动保存</div>
    </div>
  )
}
