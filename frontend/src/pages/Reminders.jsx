import React, { useEffect, useRef, useState } from 'react'
import api from '../api'
import { useToast } from '../components/Toast'
import { Bell, Check, Pencil, Trash2, X, Monitor } from 'lucide-react'

const REPEAT_OPTIONS = [
  ['none', '一次性'],
  ['daily', '每天'],
  ['weekly', '每周'],
  ['monthly', '每月'],
]

const fmtAdv = m =>
  m >= 1440 ? `${Math.round(m / 1440)}天` : m >= 60 ? `${Math.round(m / 60)}小时` : `${m}分钟`

const relTime = (iso, now = new Date()) => {
  if (!iso) return ''
  const d = new Date(iso)
  const diffMin = Math.round((d - now) / 60000)
  if (diffMin <= 0) return '已过'
  if (diffMin < 60) return `${diffMin} 分钟后`
  if (diffMin < 1440) return `${Math.floor(diffMin / 60)} 小时后`
  const diffD = Math.round((d - now) / 86400000)
  if (diffD === 1) return '明天'
  if (diffD < 7) return `${diffD} 天后`
  const wd = ['日', '一', '二', '三', '四', '五', '六'][d.getDay()]
  return diffD < 14 ? `下周${wd}` : `${Math.round(diffD / 7)} 周后`
}

const fmtDt = (iso, now = new Date()) => {
  if (!iso) return ''
  const d = new Date(iso)
  const hm = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  const today0 = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const d0 = new Date(d.getFullYear(), d.getMonth(), d.getDate())
  const diff = Math.round((d0 - today0) / 86400000)
  if (diff === 0) return `今天 ${hm}`
  if (diff === 1) return `明天 ${hm}`
  const wd = ['日', '一', '二', '三', '四', '五', '六'][d.getDay()]
  if (diff > 1 && diff < 7) return `周${wd} ${hm}`
  if (d.getFullYear() === now.getFullYear()) return `${d.getMonth() + 1}月${d.getDate()}日 ${hm}`
  return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日 ${hm}`
}

const toLocalInput = iso => (iso ? iso.slice(0, 16) : '')

// 新建提醒默认时间：本地当前时间向上取整到 5 分钟（不用 toISOString，否则 UTC 早 8 小时，见坑 #48）
const defaultRemindInput = () => {
  const d = new Date(Date.now() + 4 * 60000)
  d.setMinutes(Math.ceil(d.getMinutes() / 5) * 5, 0, 0)
  const p = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`
}

function ClockDot() {
  const [t, setT] = useState(new Date())
  useEffect(() => {
    const iv = setInterval(() => setT(new Date()), 1000)
    return () => clearInterval(iv)
  }, [])
  const hm = `${String(t.getHours()).padStart(2, '0')}:${String(t.getMinutes()).padStart(2, '0')}`
  const wd = ['日', '一', '二', '三', '四', '五', '六'][t.getDay()]
  return <span className="rm-clock">🕐 {t.getMonth() + 1}月{t.getDate()}日 {hm} 周{wd}</span>
}

function ReminderForm({ initial, onSave, onClose }) {
  const toast = useToast()
  const [title, setTitle] = useState(initial?.title || '')
  const [remindAt, setRemindAt] = useState(() => initial?.remind_at ? toLocalInput(initial.remind_at) : defaultRemindInput())
  const [repeat, setRepeat] = useState(initial?.repeat || 'none')
  const [adv, setAdv] = useState(initial?.advance_minutes?.slice() || [])
  const [note, setNote] = useState(initial?.note || '')
  const advOn = adv.length > 0

  const addAdv = m => {
    setAdv(a => (a.includes(m) || a.length >= 5 ? a : [...a, m]))
  }
  const save = () => {
    if (!title.trim()) return toast('请填写提醒内容', 'error')
    if (!remindAt) return toast('请选择提醒时间', 'error')
    const body = {
      title: title.trim(),
      remind_at: remindAt + ':00',
      repeat,
      advance_minutes: advOn ? adv.slice(0, 5) : [],
      note: note.trim(),
    }
    const req = initial ? api.put(`/reminders/${initial.id}`, body) : api.post('/reminders', body)
    req.then(r => onSave(r.data)).catch(e => toast(e.response?.data?.detail || '保存失败', 'error'))
  }

  return (
    <div className="modal-mask" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <h3>{initial ? '编辑提醒' : '新建提醒'}</h3>
        <div className="form-row">
          <label className="form-label">提醒内容</label>
          <input className="input" value={title} onChange={e => setTitle(e.target.value)} placeholder="如：下午四点去找老师 / 周六早上去图书馆还书" autoFocus />
        </div>
        <div className="form-row">
          <label className="form-label">提醒时间</label>
          <input type="datetime-local" className="input" value={remindAt} onChange={e => setRemindAt(e.target.value)} />
        </div>
        <div className="form-row">
          <label className="form-label">周期</label>
          <select className="select" value={repeat} onChange={e => setRepeat(e.target.value)}>
            {REPEAT_OPTIONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
        <div className="form-row">
          <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            提前提醒
            <input type="checkbox" checked={advOn} onChange={e => { e.target.checked ? setAdv([10]) : setAdv([]) }} />
          </label>
          {advOn && (
            <div className="reminder-adv">
              {adv.map((m, i) => (
                <div key={i} className="row" style={{ gap: 8, marginBottom: 6 }}>
                  <span className="muted">提前</span>
                  <input
                    type="number" min={1} max={10080} className="input" style={{ width: 90 }}
                    value={m}
                    onChange={e => setAdv(a => a.map((x, j) => j === i ? Math.max(1, Number(e.target.value) || 1) : x))}
                  />
                  <span className="muted">分钟</span>
                  <button className="btn btn-sm btn-danger" onClick={() => setAdv(a => a.filter((_, j) => j !== i))}><X size={14} strokeWidth={1.8} /></button>
                </div>
              ))}
              <div className="row" style={{ gap: 6, marginBottom: 6 }}>
                <button className="btn btn-sm" onClick={() => addAdv(10)}>+10分钟</button>
                <button className="btn btn-sm" onClick={() => addAdv(60)}>+1小时</button>
                <button className="btn btn-sm" onClick={() => addAdv(1440)}>+1天</button>
                <button className="btn btn-sm" disabled={adv.length >= 5} onClick={() => addAdv(30)}>+ 自定义</button>
              </div>
              <div className="muted" style={{ fontSize: 12 }}>最多 5 次提前提醒{adv.length >= 5 ? '（已达上限）' : ''}</div>
            </div>
          )}
        </div>
        <div className="form-row">
          <label className="form-label">备注</label>
          <textarea className="textarea" rows={2} value={note} onChange={e => setNote(e.target.value)} placeholder="可选，如：带上前两轮的实验记录" />
        </div>
        <div className="modal-actions">
          <button className="btn" onClick={onClose}>取消</button>
          <button className="btn btn-primary" onClick={save}>保存</button>
        </div>
      </div>
    </div>
  )
}

function ReminderCard({ r, now, flash, onDone, onEdit, onDelete }) {
  const strip = r.status === 'done' ? 'strip-done' : r.overdue ? 'strip-overdue' : fmtDt(r.next_trigger || r.remind_at, now).startsWith('今天') ? 'strip-today' : 'strip-upcoming'
  const isCycle = r.repeat !== 'none'
  const showAt = isCycle ? r.next_trigger : r.remind_at
  return (
    <div className={`reminder-card ${r.overdue ? 'overdue' : ''} ${r.status === 'done' ? 'done' : ''} ${flash ? 'reminder-flash' : ''}`}>
      <div className={`reminder-strip ${strip}`} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="row" style={{ gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <strong style={{ fontSize: 14 }}>{r.title}</strong>
          {r.repeat !== 'none' && <span className="badge badge-info">{r.repeat_label}</span>}
          {r.advance_minutes.length > 0 && (
            <span className="badge badge-warn" title="到点前提前提醒">提前 {r.advance_minutes.map(fmtAdv).join('、')}</span>
          )}
        </div>
        <div className="muted" style={{ fontSize: 12.5, marginTop: 4 }}>
          {isCycle ? <>⏰ 下次：{fmtDt(r.next_trigger, now)}</> : <>⏰ {fmtDt(r.remind_at, now)}{r.overdue && <span style={{ color: 'var(--danger)' }}>（已过期）</span>}</>}
          {r.status === 'pending' && <span className="muted" style={{ fontSize: 11.5, marginLeft: 6 }}>（{relTime(showAt, now)}）</span>}
        </div>
        {isCycle && r.last_done_at && !r.overdue && (
          <div className="muted" style={{ fontSize: 12, marginTop: 3 }}>
            <span style={{ color: 'var(--success)', fontWeight: 600 }}>✓ 已处理本次</span>
            <span style={{ fontSize: 11, marginLeft: 4 }}>上次完成于 {fmtDt(r.last_done_at, now)}</span>
          </div>
        )}
        {r.note && <div className="muted" style={{ fontSize: 12, marginTop: 3 }}>📝 {r.note}</div>}
      </div>
      <div className="row" style={{ gap: 4, alignItems: 'center' }}>
        {r.status !== 'done' && (
          <button className="btn btn-sm" title={isCycle ? '标记本次已处理（下次继续提醒）' : '标记完成'} onClick={() => onDone(r)}>
            <Check size={14} strokeWidth={1.8} /> {isCycle ? '本次完成' : '完成'}
          </button>
        )}
        <button className="btn btn-sm" title="编辑" onClick={() => onEdit(r)}><Pencil size={14} strokeWidth={1.8} /></button>
        <button className="btn btn-sm btn-danger" title="删除" onClick={() => onDelete(r)}><Trash2 size={14} strokeWidth={1.8} /></button>
      </div>
    </div>
  )
}

export default function Reminders() {
  const toast = useToast()
  const [data, setData] = useState(null)
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState(null)
  const [flashIds, setFlashIds] = useState([])
  const flashTimer = useRef(null)
  // 桌面提醒胶囊开关（设置页「桌面胶囊」也能开关，这里保持同步）
  const [pillOpen, setPillOpen] = useState(false)
  useEffect(() => {
    const loadPill = () => {
      api.get('/reminder-pill/state').then(r => setPillOpen(!!r.data.active)).catch(() => {})
    }
    loadPill()
    const iv = setInterval(loadPill, 10000)
    return () => clearInterval(iv)
  }, [])
  const togglePill = async () => {
    try {
      await api.post('/reminder-pill/control', { action: pillOpen ? 'hide' : 'show' })
      setPillOpen(!pillOpen)
      toast(pillOpen ? '提醒胶囊已关闭' : '提醒胶囊已打开：桌面小条常驻显示下一个提醒倒计时')
    } catch (e) { toast(e.response?.data?.detail || '操作失败', 'error') }
  }

  const load = () => {
    api.get('/reminders').then(r => {
      setData(r.data)
      // 到点提醒：页面开着时闪烁 + toast（localStorage 去重，不重复打扰）
      // 规则：① 每条提醒聚合为一次；② 只对「刚刚到点」（1 分钟内）的触发点提示，
      //       过期已久的打开页面不补弹（与「过期只标红」设计一致）；
      //       ③ 提前点与主触发文案区分。
      const now = Date.now()
      const fired = []
      r.data.items.forEach(it => {
        if (it.status !== 'pending') return
        const trig = new Date(it.next_trigger).getTime()
        const pts = [{ pt: trig, adv: 0 }]
        it.advance_minutes.forEach(a => pts.push({ pt: trig - a * 60000, adv: a }))
        let live = null
        pts.forEach(({ pt, adv }) => {
          const key = `wb_rm_fired_${it.id}_${pt}`
          if (pt <= now && !localStorage.getItem(key)) {
            localStorage.setItem(key, '1')
            if (now - pt <= 60000) live = { adv }
          }
        })
        if (live) fired.push({ id: it.id, title: it.title, adv: live.adv, trig })
      })
      if (fired.length) {
        setFlashIds(fired.map(f => f.id))
        clearTimeout(flashTimer.current)
        flashTimer.current = setTimeout(() => setFlashIds([]), 5000)
        fired.forEach(f => {
          if (f.adv > 0) {
            const left = Math.max(1, Math.round((f.trig - now) / 60000))
            const txt = left >= 1440 ? `${Math.round(left / 1440)} 天` : left >= 60 ? `${Math.round(left / 60)} 小时` : `${left} 分钟`
            toast(`⏰ 「${f.title}」还有约 ${txt}（提前提醒）`)
          } else {
            toast(`⏰ 「${f.title}」时间到了，别忘了！`)
          }
        })
      }
    }).catch(() => {})
  }

  useEffect(() => {
    load()
    const iv = setInterval(load, 20000)
    return () => { clearInterval(iv); clearTimeout(flashTimer.current) }
  }, [])

  const now = new Date()
  const items = data?.items || []
  const groups = { overdue: [], today: [], upcoming: [], done: [] }
  items.forEach(it => {
    if (it.status === 'done') groups.done.push(it)
    else if (it.overdue) groups.overdue.push(it)
    else if (fmtDt(it.next_trigger || it.remind_at, now).startsWith('今天')) groups.today.push(it)
    else groups.upcoming.push(it)
  })

  const save = r => {
    setShowForm(false)
    setEditing(null)
    toast('已保存')
    load()
  }
  const del = r => {
    if (!window.confirm(`删除提醒「${r.title}」？`)) return
    api.delete(`/reminders/${r.id}`).then(() => { toast('已删除'); load() }).catch(e => toast(e.response?.data?.detail || '删除失败', 'error'))
  }
  const done = r => {
    api.post(`/reminders/${r.id}/done`).then(() => {
      toast(r.repeat !== 'none' ? '已标记本次完成，下个周期继续提醒' : '已完成')
      load()
    }).catch(e => toast(e.response?.data?.detail || '操作失败', 'error'))
  }

  const s = data?.stats || {}
  const GROUP_CFG = [
    ['overdue', '已过期（未处理）', 'red', groups.overdue],
    ['today', '今天', 'purple', groups.today],
    ['upcoming', '即将到来', 'blue', groups.upcoming],
    ['done', '已完成', 'gray', groups.done],
  ]

  return (
    <div>
      <div className="page-header">
        <h1><span className="page-icon"><Bell size={22} strokeWidth={1.75} /></span>提醒事项</h1>
        <div className="row">
          <ClockDot />
          <span className="muted" style={{ fontSize: 13 }}>琐事提醒：找老师 / 还书 / 考试 / 缴费…到点弹窗提醒</span>
          <button className={`btn btn-sm ${pillOpen ? 'btn-primary' : ''}`} onClick={togglePill}
            title="桌面小条常驻显示最近一个提醒的倒计时，点击可跳转本页">
            <Monitor size={14} strokeWidth={1.8} /> 桌面胶囊
          </button>
          <button className="btn btn-primary" onClick={() => { setEditing(null); setShowForm(true) }}>+ 新建提醒</button>
        </div>
      </div>

      <div className="grid grid-4" style={{ marginBottom: 16 }}>
        <div className="rm-stat rm-stat-purple"><div className="stat-label">待提醒</div><div className="stat-value">{s.pending ?? 0}</div></div>
        <div className="rm-stat rm-stat-blue"><div className="stat-label">今天</div><div className="stat-value">{s.today ?? 0}</div></div>
        <div className="rm-stat rm-stat-orange"><div className="stat-label">已过期</div><div className="stat-value">{s.overdue ?? 0}</div></div>
        <div className="rm-stat rm-stat-green"><div className="stat-label">已完成</div><div className="stat-value">{s.done ?? 0}</div></div>
      </div>

      {items.length === 0 ? (
        <div className="card">
          <div className="empty"><span className="empty-icon">⏰</span>还没有提醒事项<br />点击右上角「+ 新建提醒」，把明天下午 4 点找老师、周六还书这种琐事交给我</div>
        </div>
      ) : (
        <div className="reminder-tl">
          {GROUP_CFG.map(([key, label, color, list]) => list.length === 0 ? null : (
            <div key={key}>
              <div className={`reminder-group g-${color}`}>
                <span className="tl-dot" />
                {label} <span className="muted" style={{ fontSize: 12 }}>{list.length} 件</span>
              </div>
              <div className={`reminder-group-body g-${color}`}>
                {list.map(r => (
                  <ReminderCard key={r.id} r={r} now={now} flash={flashIds.includes(r.id)} onDone={done} onEdit={r => { setEditing(r); setShowForm(true) }} onDelete={del} />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {showForm && <ReminderForm initial={editing} onSave={save} onClose={() => { setShowForm(false); setEditing(null) }} />}
    </div>
  )
}