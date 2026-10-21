import React, { useEffect, useRef, useState } from 'react'
import api, { todayStr } from '../api'
import { useToast } from '../components/Toast'
import FreePomodoroCard from '../components/FreePomodoroCard'
import { MapPin, CalendarDays, CalendarRange, Coffee, Play, Pause, Check, Pencil, Trash2, TriangleAlert, Monitor } from 'lucide-react'

const STATUS_META = {
  idle: { label: '尚未打卡', dot: 'att-dot-idle' },
  working: { label: '在岗中', dot: 'att-dot-working' },
  paused: { label: '休息中', dot: 'att-dot-paused' },
  closed: { label: '今日已结束', dot: 'att-dot-closed' },
}

const WEEK_CN = ['日', '一', '二', '三', '四', '五', '六']

function fmtHM(sec) {
  const s = Math.max(0, Math.floor(sec || 0))
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60)
  return `${h}h ${m}m`
}

function fmtLong(sec) {
  const s = Math.max(0, Math.floor(sec || 0))
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60)
  if (h > 0) return m > 0 ? `${h}小时${m}分` : `${h}小时`
  if (m > 0) return `${m}分钟`
  return `${s}秒`
}

function fmtHMS(sec) {
  const s = Math.max(0, Math.floor(sec || 0))
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), ss = s % 60
  return `${h}:${String(m).padStart(2, '0')}:${String(ss).padStart(2, '0')}`
}

const hhmm = iso => (iso ? iso.slice(11, 16) : '—')
const weekdayOf = iso => WEEK_CN[new Date(`${iso}T00:00:00`).getDay()]

// 修正考勤弹窗：改各段的到岗/离开时间与原因，删除误建段；保存时逐段 PUT/DELETE
function AttendanceEditor({ date, segments, focusSegId, onClose, onSaved, toast }) {
  const [rows, setRows] = useState(() => segments.map(s => ({
    id: s.id,
    start: s.start_at.slice(11, 16),
    end: s.end_at ? s.end_at.slice(11, 16) : '',
    reason: s.reason || '',
    auto_closed: !!s.auto_closed,
    origStart: s.start_at,
    origEnd: s.end_at,
    origReason: s.reason || '',
    removed: false,
  })))
  const [saving, setSaving] = useState(false)
  const savingRef = useRef(false) // 防双击/连点「保存修正」重复提交
  const setRow = (id, k, v) => setRows(rs => rs.map(r => (r.id === id ? { ...r, [k]: v } : r)))
  const changed = rows.filter(r => r.removed
    || r.start !== r.origStart.slice(11, 16)
    || (r.end || '') !== (r.origEnd ? r.origEnd.slice(11, 16) : '')
    || r.reason !== r.origReason)

  const save = async () => {
    if (savingRef.current) return
    // 只校验本次要提交（改动/删除）的行；时间只在被改动时校验，
    // 避免历史零时长段（点了到位后立刻离开）仅改原因时被误拦
    for (const r of changed) {
      if (r.removed) continue
      const startChanged = r.start !== r.origStart.slice(11, 16)
      const origEndHM = r.origEnd ? r.origEnd.slice(11, 16) : ''
      const endChanged = (r.end || '') !== origEndHM
      if (!r.end && r.origEnd) { toast('已结束的时间段需要填写结束时间；如需恢复进行中请删除该段', 'error'); return }
      if ((startChanged || endChanged) && r.end && r.end <= r.start) { toast('结束时间需晚于开始时间', 'error'); return }
    }
    savingRef.current = true
    setSaving(true)
    try {
      for (const r of rows) {
        if (r.removed) { await api.delete(`/attendance/segments/${r.id}`); continue }
        const body = {}
        if (r.start !== r.origStart.slice(11, 16)) body.start_at = `${date}T${r.start}:00`
        const origEndHM = r.origEnd ? r.origEnd.slice(11, 16) : ''
        if (r.end && r.end !== origEndHM) body.end_at = `${date}T${r.end}:00`
        if (r.reason !== r.origReason) body.reason = r.reason
        if (Object.keys(body).length) await api.put(`/attendance/segments/${r.id}`, body)
      }
      toast('已保存修正')
      onSaved()
    } catch (e) {
      toast(e.response?.data?.detail || '保存失败', 'error')
    } finally {
      savingRef.current = false
      setSaving(false)
    }
  }

  return (
    <div className="modal-mask" onClick={onClose}>
      <div className="modal att-edit-modal" onClick={e => e.stopPropagation()}>
        <h3>修正考勤 · {date.slice(5).replace('-', '月')}日</h3>
        <div className="muted" style={{ fontSize: 13, marginBottom: 10 }}>
          忘记点「离开」时，把该段的结束时间改成实际离开时刻；也可修正到岗时间。结束时间留空表示仍在计时。
        </div>
        {rows.filter(r => !r.removed).length === 0 && (
          <div className="muted" style={{ marginBottom: 8 }}>该日已无时间段，保存后记录将被清空。</div>
        )}
        {rows.map(r => (r.removed ? (
          <div key={r.id} className="att-seg-row att-seg-removed">
            <span className="muted" style={{ flex: 1 }}>{r.start} → {r.end || '进行中'}（已标记删除）</span>
            <button className="btn btn-sm" onClick={() => setRow(r.id, 'removed', false)}>撤销</button>
          </div>
        ) : (
          <div key={r.id} className="att-seg-row">
            <input type="time" className="input" style={{ width: 116 }} value={r.start}
              autoFocus={r.id === focusSegId} onChange={e => setRow(r.id, 'start', e.target.value)} />
            <span className="muted">→</span>
            <input type="time" className="input" style={{ width: 116 }} value={r.end}
              title="留空表示仍在计时" onChange={e => setRow(r.id, 'end', e.target.value)} />
            <input className="input" style={{ flex: 1, minWidth: 130 }} placeholder="离开原因（可选）"
              value={r.reason} onChange={e => setRow(r.id, 'reason', e.target.value)} />
            {r.auto_closed && <span className="badge badge-warn" title="跨天自动收口，时间可能不准">疑似未离开</span>}
            <button className="btn btn-sm" title="删除该段"
              onClick={() => { if (confirm('删除该时间段？保存后生效')) setRow(r.id, 'removed', true) }}>
              <Trash2 size={13} strokeWidth={1.8} />
            </button>
          </div>
        )))}
        <div className="modal-actions">
          <span className="muted" style={{ marginRight: 'auto', fontSize: 12 }}>
            {changed.length > 0 ? `${changed.length} 处待保存` : '未修改'}
          </span>
          <button className="btn" onClick={onClose}>取消</button>
          <button className="btn btn-primary" disabled={saving || changed.length === 0} onClick={save}>
            {saving ? '保存中…' : '保存修正'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function Attendance() {
  const toast = useToast()
  const [data, setData] = useState(null)
  const [stats, setStats] = useState(null)
  const [history, setHistory] = useState([])
  const [leaveOpen, setLeaveOpen] = useState(false)
  const [reason, setReason] = useState('')
  const [custom, setCustom] = useState('')
  const [loadErr, setLoadErr] = useState(false)
  const [editor, setEditor] = useState(null)
  const [dismissedAuto, setDismissedAuto] = useState(() => {
    const raw = localStorage.getItem('wb_att_autoclosed_dismissed') || ''
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed)) return parsed
    } catch { /* 旧格式为单个日期字符串，下面兼容处理 */ }
    return raw ? [raw] : []
  })
  const [, setTick] = useState(0)
  const lastDate = useRef(todayStr())
  // 桌面考勤胶囊开关（设置页「桌面胶囊」也能开关，这里保持同步）
  const [pillOpen, setPillOpen] = useState(false)
  useEffect(() => {
    const loadPill = () => {
      api.get('/attendance-pill/state').then(r => setPillOpen(!!r.data.active)).catch(() => {})
    }
    loadPill()
    const iv = setInterval(loadPill, 10000)
    return () => clearInterval(iv)
  }, [])
  const togglePill = async () => {
    try {
      await api.post('/attendance-pill/control', { action: pillOpen ? 'hide' : 'show' })
      setPillOpen(!pillOpen)
      toast(pillOpen ? '考勤胶囊已关闭' : '考勤胶囊已打开：桌面小条显示在岗计时，可直接点「离开」')
    } catch (e) { toast(e.response?.data?.detail || '操作失败', 'error') }
  }

  const load = () => {
    api.get('/attendance/today').then(r => { setData(r.data); setLoadErr(false) }).catch(() => setLoadErr(true))
    api.get('/attendance/stats?days=14').then(r => setStats(r.data)).catch(() => {})
    api.get('/attendance/history?days=30').then(r => setHistory(r.data.items || [])).catch(() => {})
  }
  useEffect(() => { load() }, [])
  // 本地每秒走秒（后端数据定时校准）；跨天自动重载（触发后端跨天收口）
  useEffect(() => {
    const iv = setInterval(() => {
      setTick(t => t + 1)
      if (todayStr() !== lastDate.current) { lastDate.current = todayStr(); load() }
    }, 1000)
    return () => clearInterval(iv)
  }, [])
  useEffect(() => {
    const iv = setInterval(load, 60000)
    return () => clearInterval(iv)
  }, [])

  const meta = STATUS_META[data?.status] || STATUS_META.idle
  const segs = data?.segments || []
  const closedSeconds = segs.filter(s => s.end_at).reduce((a, s) => a + s.seconds, 0)
  const openSeconds = data?.status === 'working' && data.open_since
    ? Math.max(0, Math.floor((Date.now() - new Date(data.open_since).getTime()) / 1000))
    : 0
  const todaySeconds = closedSeconds + openSeconds
  const pauses = []
  for (let i = 0; i < segs.length - 1; i++) {
    const a = segs[i], b = segs[i + 1]
    if (a.end_at && b.start_at > a.end_at) {
      pauses.push({ seconds: Math.max(0, Math.round((new Date(b.start_at) - new Date(a.end_at)) / 1000)), reason: a.reason })
    }
  }
  const lastSeg = segs[segs.length - 1]
  const currentPause = data?.status === 'paused' && lastSeg?.end_at
    ? Math.max(0, Math.floor((Date.now() - new Date(lastSeg.end_at).getTime()) / 1000))
    : 0
  if (currentPause > 0) pauses.push({ seconds: currentPause, reason: lastSeg.reason })
  const pauseSeconds = pauses.reduce((a, p) => a + p.seconds, 0)

  // 异常提示：①今天单段在岗超过阈值 ②历史上有跨天自动收口的段（疑似忘记点离开）
  const openSeg = segs.find(s => !s.end_at)
  const longStayHours = data?.long_stay_hours ?? 12
  const longStay = data?.status === 'working' && openSeg && longStayHours > 0
    && openSeconds >= longStayHours * 3600
  const autoDay = history.find(h => h.auto_closed && !dismissedAuto.includes(h.date))
  const openEditor = (date, segsOfDay, focusSegId) => setEditor({ date, segments: segsOfDay || [], focusSegId })

  const checkIn = async () => {
    try {
      const r = await api.post('/attendance/check-in')
      setData(r.data)
      load()
      toast('✓ 已到位，开始计时')
    } catch (e) { toast(e.response?.data?.detail || '操作失败', 'error') }
  }
  const doLeave = async () => {
    try {
      const why = (custom.trim() || reason).trim()
      const r = await api.post('/attendance/check-out', { reason: why })
      setData(r.data)
      setLeaveOpen(false)
      load()
      toast(why ? `已离开（${why}）` : '已离开，回来记得再「到位」')
    } catch (e) { toast(e.response?.data?.detail || '操作失败', 'error') }
  }
  const endDay = async () => {
    if (!confirm('确定结束今日考勤吗？在岗计时会收工，之后仍可重新「到位」。')) return
    try {
      const r = await api.post('/attendance/end-day')
      setData(r.data)
      load()
      toast('✓ 今日考勤已结束')
    } catch (e) { toast(e.response?.data?.detail || '操作失败', 'error') }
  }

  const series = stats?.series || []
  const maxDay = Math.max(...series.map(s => s.seconds), 1)

  return (
    <div>
      <div className="page-header">
        <h1><span className="page-icon"><MapPin size={22} strokeWidth={1.75} /></span>考勤</h1>
        <div className="row">
          <span className="badge badge-info">{data?.date || todayStr()}</span>
          <button className={`btn btn-sm ${pillOpen ? 'btn-primary' : ''}`} onClick={togglePill}
            title="桌面小条常驻显示今日在岗计时（到秒跳动），可直接「离开/到位」，防忘点">
            <Monitor size={14} strokeWidth={1.8} /> 桌面胶囊
          </button>
        </div>
      </div>

      {loadErr && (
        <div className="card" style={{ marginBottom: 16, borderColor: 'var(--danger)' }}>
          <div className="row" style={{ justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
            <span>考勤数据加载失败：请确认后端已重启到最新版本（旧后端没有考勤接口，会返回 404）。</span>
            <button className="btn btn-sm" onClick={load}>重试</button>
          </div>
        </div>
      )}

      {longStay && (
        <div className="card att-hint" style={{ marginBottom: 16 }}>
          <div className="row" style={{ justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
            <span className="row" style={{ gap: 6 }}>
              <TriangleAlert size={15} strokeWidth={1.8} style={{ color: 'var(--warn)' }} />
              本次在岗已 {fmtLong(openSeconds)}，是不是忘记点「离开」了？
            </span>
            <button className="btn btn-sm btn-primary" onClick={() => openEditor(data.date, segs, openSeg.id)}>修正离开时间</button>
          </div>
        </div>
      )}
      {autoDay && (
        <div className="card att-hint" style={{ marginBottom: 16 }}>
          <div className="row" style={{ justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
            <span className="row" style={{ gap: 6 }}>
              <TriangleAlert size={15} strokeWidth={1.8} style={{ color: 'var(--warn)' }} />
              {autoDay.date.slice(5).replace('-', '月')}日的记录疑似忘记点「离开」，已在跨天时自动记到 23:59
            </span>
            <div className="row" style={{ gap: 6 }}>
              <button className="btn btn-sm btn-primary" onClick={() => openEditor(autoDay.date, autoDay.segments, null)}>去修正</button>
              <button className="btn btn-sm" onClick={() => {
                const next = [...new Set([...dismissedAuto, autoDay.date])]
                localStorage.setItem('wb_att_autoclosed_dismissed', JSON.stringify(next))
                setDismissedAuto(next)
              }}>忽略</button>
            </div>
          </div>
        </div>
      )}

      <div className={`card att-hero att-hero-${data?.status || 'idle'}`} style={{ marginBottom: 16 }}>
        <div className="att-hero-main">
          <div>
            <div className="att-hero-kicker">今日打卡</div>
            <div className="att-status-label">
              <span className={`att-dot ${meta.dot}`} />
              <span>{meta.label}</span>
              {data?.status === 'working' && <span className="badge badge-success">计时中</span>}
              {data?.status === 'working' && data.open_since && <span className="att-since">自 {hhmm(data.open_since)} 起</span>}
              {data?.status === 'paused' && currentPause > 0 && <span className="att-since">已休息 {fmtLong(currentPause)}</span>}
            </div>
            <div className="att-times">
              {hhmm(data?.first_in)} 签到 · 最近离开 {hhmm(data?.last_out)} · 在岗外休息 {fmtLong(pauseSeconds)}
            </div>
          </div>
          <div className="att-hero-time">
            <div className="att-hero-time-label">今日在岗</div>
            <div className="att-hero-time-value">{data?.status === 'working' ? fmtHMS(todaySeconds) : fmtHM(todaySeconds)}</div>
          </div>
        </div>
        <div className="att-actions">
          <button className="btn btn-primary att-btn" disabled={!data || data.status === 'working'} onClick={checkIn}><Play size={14} strokeWidth={1.8} /> 到位</button>
          <button className="btn att-btn" disabled={!data || data.status !== 'working'} onClick={() => { setReason(''); setCustom(''); setLeaveOpen(true) }}><Pause size={14} strokeWidth={1.8} /> 离开</button>
          <button className="btn att-btn" disabled={!data || data.status === 'idle' || data.status === 'closed'} onClick={endDay}><Check size={14} strokeWidth={1.8} /> 结束今日</button>
          <button className="btn att-btn" disabled={!data || segs.length === 0} onClick={() => openEditor(data.date, segs, openSeg?.id)}><Pencil size={14} strokeWidth={1.8} /> 修正记录</button>
        </div>
      </div>

      <div className="grid grid-4" style={{ marginBottom: 16 }}>
        <div className="stat-card stat-purple"><span className="stat-icon"><MapPin size={15} strokeWidth={2} /></span><div className="stat-label">今日在岗</div><div className="stat-value">{fmtHM(todaySeconds)}</div></div>
        <div className="stat-card stat-blue"><span className="stat-icon"><CalendarDays size={15} strokeWidth={2} /></span><div className="stat-label">本周累计</div><div className="stat-value">{fmtHM(stats?.week_seconds)}</div></div>
        <div className="stat-card stat-green"><span className="stat-icon"><CalendarRange size={15} strokeWidth={2} /></span><div className="stat-label">本月累计</div><div className="stat-value">{fmtHM(stats?.month_seconds)}</div></div>
        <div className="stat-card stat-orange"><span className="stat-icon"><Coffee size={15} strokeWidth={2} /></span><div className="stat-label">本月休息</div><div className="stat-value">{fmtHM(stats?.month_pause_seconds)}</div></div>
      </div>

      <FreePomodoroCard />

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-title">近 14 天在岗</div>
        {!stats ? <div className="skeleton" style={{ height: 150 }} /> : (
          <div className="chart-bars" style={{ height: 150, alignItems: 'flex-end', gap: 4 }}>
            {series.map(d => (
              <div key={d.date} style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'flex-end', height: '100%' }}>
                <div
                  className={`chart-bar ${d.date === todayStr() ? 'today' : ''}`}
                  style={{
                    flex: '0 0 auto',
                    width: d.seconds > 0 ? '70%' : '40%',
                    height: `${(d.seconds / maxDay) * 100}%`,
                    minHeight: d.seconds > 0 ? 4 : 2,
                    borderRadius: 3,
                  }}
                  title={`${d.date}: ${fmtHM(d.seconds)}`}
                />
                <div className="chart-bar-label">{d.date.slice(8)}</div>
              </div>
            ))}
          </div>
        )}
        <div className="muted" style={{ marginTop: 8 }}>
          {stats ? `本月出勤 ${stats.month_days} 天 · 本月在岗 ${fmtHM(stats.month_seconds)}` : ''}
        </div>
      </div>

      {stats && stats.pause_reasons.length > 0 && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-title">休息原因 · 本月</div>
          <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
            {stats.pause_reasons.map(r => (
              <span key={r.reason} className="badge badge-warn">☕ {r.reason} · {r.count} 次 · {fmtLong(r.seconds)}</span>
            ))}
          </div>
        </div>
      )}

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-title">历史记录</div>
        {history.length === 0 && <div className="empty"><span className="empty-icon">📍</span>还没有考勤记录，点「到位」开始第一次计时</div>}
        {history.map(h => (
          <div key={h.date} className="att-hist-row att-hist-click" title="点击修正这一天的记录"
            onClick={() => openEditor(h.date, h.segments, null)}>
            <span className="att-hist-date">{h.date.slice(5)} 周{weekdayOf(h.date)}</span>
            <span className="att-hist-time">{hhmm(h.first_in)} → {h.last_out ? hhmm(h.last_out) : '进行中'}</span>
            <span className="att-hist-main">{fmtHM(h.seconds)}</span>
            <span className="muted">休息 {h.pause_count} 次{h.pause_seconds > 0 ? ` · ${fmtLong(h.pause_seconds)}` : ''}</span>
            {h.auto_closed && <span className="badge badge-warn">疑似未离开</span>}
            <span className={`badge ${h.status === 'working' ? 'badge-success' : h.status === 'paused' ? 'badge-warn' : 'badge-gray'}`}>
              {h.status === 'working' ? '在岗中' : h.status === 'paused' ? '休息中' : '已结束'}
            </span>
            <button className="btn btn-sm" title="修正"
              onClick={e => { e.stopPropagation(); openEditor(h.date, h.segments, null) }}>
              <Pencil size={13} strokeWidth={1.8} />
            </button>
          </div>
        ))}
      </div>

      {leaveOpen && (
        <div className="modal-mask" onClick={() => setLeaveOpen(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h3>离开 · 休息原因（可选）</h3>
            <div className="muted" style={{ fontSize: 13, marginBottom: 10 }}>离开期间不计入在岗时长；回来点「到位」继续计时。</div>
            <div className="row" style={{ gap: 6, flexWrap: 'wrap', marginBottom: 10 }}>
              {['上课', '吃饭', '其他'].map(r => (
                <button key={r} className={`btn btn-sm fp-preset ${reason === r ? 'fp-preset-on' : ''}`} onClick={() => { setReason(r); setCustom('') }}>{r}</button>
              ))}
            </div>
            <input
              className="input"
              placeholder="或自定义原因（回车确认）"
              value={custom}
              onChange={e => { setCustom(e.target.value); setReason('') }}
              onKeyDown={e => { if (e.key === 'Enter' && !e.nativeEvent.isComposing) doLeave() }}
            />
            <div className="modal-actions">
              <button className="btn" onClick={() => setLeaveOpen(false)}>取消</button>
              <button className="btn btn-primary" onClick={doLeave}>确认离开</button>
            </div>
          </div>
        </div>
      )}

      {editor && (
        <AttendanceEditor
          date={editor.date}
          segments={editor.segments}
          focusSegId={editor.focusSegId}
          toast={toast}
          onClose={() => setEditor(null)}
          onSaved={() => { setEditor(null); load() }}
        />
      )}
    </div>
  )
}
