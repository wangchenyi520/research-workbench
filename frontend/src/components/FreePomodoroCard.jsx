import React, { useEffect, useRef, useState } from 'react'
import api from '../api'
import { useToast } from './Toast'
import { BarChart3, Timer, Play, Pause, SkipForward, Check, Monitor, X } from 'lucide-react'

const FP_PRESETS = ['数学', '看论文', '写代码', '刷题', '阅读']

function fmtMMSS(sec) {
  const s = Math.max(0, Math.floor(sec || 0))
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
}

// 自由计时的大数字时钟格式：<1 小时 mm:ss，>=1 小时 h:mm:ss
function fmtClock(sec) {
  const s = Math.max(0, Math.floor(sec || 0))
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), ss = s % 60
  return h > 0
    ? `${h}:${String(m).padStart(2, '0')}:${String(ss).padStart(2, '0')}`
    : `${String(m).padStart(2, '0')}:${String(ss).padStart(2, '0')}`
}

function fmtLong(sec) {
  const s = Math.max(0, Math.floor(sec || 0))
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60)
  return h > 0 ? `${h}小时${m}分` : `${m}分钟${s % 60 > 0 ? ` ${s % 60}秒` : ''}`
}

export default function FreePomodoroCard() {
  const toast = useToast()
  const [session, setSession] = useState(null)
  const [mode, setMode] = useState('tomato') // tomato / free
  const [stateText, setStateText] = useState('')
  const [workMin, setWorkMin] = useState(Number(localStorage.getItem('wb_fp_work') || 25))
  const [breakMin, setBreakMin] = useState(Number(localStorage.getItem('wb_fp_break') || 5))
  const [hist, setHist] = useState(null)
  const [showHist, setShowHist] = useState(false)
  const running = !!(session && (session.status === 'running' || session.status === 'paused'))

  const load = () => {
    api.get('/free-pomodoro/state').then(r => {
      setSession(r.data?.session || null)
    }).catch(() => {})
  }
  useEffect(() => {
    load()
    const iv = setInterval(load, 1500)
    return () => clearInterval(iv)
  }, [])
  useEffect(() => {
    if (!showHist) return
    api.get('/free-pomodoro/history?days=7').then(r => setHist(r.data)).catch(() => {})
  }, [showHist])

  // 到点精确结算：轮询发现 remaining 从 >0 变为 0 且仍在工作阶段 → 后端结算进休息（幂等）
  const prevRem = useRef(null)
  useEffect(() => {
    if (!session) { prevRem.current = null; return }
    if (session.mode === 'tomato' && session.phase === 'work' && session.status === 'running'
      && session.remaining === 0 && prevRem.current !== null && prevRem.current > 0) {
      api.post('/free-pomodoro/settle').then(() => toast('🍅 一个番茄完成，进入休息')).catch(() => {})
    }
    prevRem.current = session.remaining
  }, [session])

  const start = async () => {
    try {
      const st = await api.get('/pomodoro/widget/state').catch(() => ({ data: null }))
      if (st.data?.active) return toast(`桌面时钟正被「${st.data.title}」使用`, 'error')
      const r = await api.post('/free-pomodoro/start', { state: stateText, mode, work_min: Math.round(workMin), break_min: Math.round(breakMin) })
      setSession(r.data)
      toast('🎧 已开始学习，加油！')
    } catch (e) { toast(e.response?.data?.detail || '启动失败', 'error') }
  }
  // 桌面时钟接管时：pause/resume/skipBreak 走 widget（其事件同步 session，避免重复调 API 400）；
  // 完成/放弃走 API + quit 收起 widget（quit 无事件无竞态）
  const isWidgetHere = async () => {
    try {
      const w = await api.get('/pomodoro/widget/state')
      return !!(w.data?.active && w.data.session_id === session.id)
    } catch (e) { return false }
  }
  const pause = async () => {
    try {
      if (await isWidgetHere()) await api.post('/pomodoro/widget/control', { action: 'pause' })
      else { const r = await api.post('/free-pomodoro/pause'); setSession(r.data) }
    } catch (e) { toast(e.response?.data?.detail || '操作失败', 'error') }
  }
  const resume = async () => {
    try {
      if (await isWidgetHere()) await api.post('/pomodoro/widget/control', { action: 'resume' })
      else { const r = await api.post('/free-pomodoro/resume'); setSession(r.data) }
    } catch (e) { toast(e.response?.data?.detail || '操作失败', 'error') }
  }
  const finish = async () => {
    try {
      try {
        const w = await api.get('/pomodoro/widget/state')
        if (w.data?.active && w.data.session_id === session.id) await api.post('/pomodoro/widget/control', { action: 'quit' })
      } catch (e) { /* 静默 */ }
      const r = await api.post('/free-pomodoro/finish'); setSession(r.data); toast('✓ 本次专注已保存')
    } catch (e) { toast(e.response?.data?.detail || '操作失败', 'error') }
  }
  const abandon = async () => {
    if (!confirm('确定放弃本次自由番茄钟吗？放弃后本次不计入时长统计。')) return
    try {
      try {
        const w = await api.get('/pomodoro/widget/state')
        if (w.data?.active && w.data.session_id === session.id) await api.post('/pomodoro/widget/control', { action: 'quit' })
      } catch (e) { /* 静默 */ }
      const r = await api.post('/free-pomodoro/abandon'); setSession(r.data); toast('已放弃（不计入时长）')
    } catch (e) { toast(e.response?.data?.detail || '操作失败', 'error') }
  }
  const skipBreak = async () => {
    try {
      if (await isWidgetHere()) await api.post('/pomodoro/widget/control', { action: 'complete' })
      else { const r = await api.post('/free-pomodoro/skip-break'); setSession(r.data) }
      toast('已跳过休息，开始下一轮')
    } catch (e) { toast(e.response?.data?.detail || '操作失败', 'error') }
  }
  const desktop = async () => {
    try {
      await api.post('/pomodoro/widget/start', {
        session_id: session.id, title: session.state || '自由番茄钟',
        work_min: session.work_min, break_min: session.break_min,
        mode: session.mode, elapsed_init: session.mode === 'free' ? session.work_seconds : 0,
        // 同步当前阶段/剩余/暂停态：暂停中打开或中途接管时不重头计时、不把暂停算进去
        phase: session.phase, paused: session.status === 'paused', remaining: session.remaining,
      })
      toast('🖥 桌面时钟已启动，可在桌面拖动/置顶')
    } catch (e) { toast(e.response?.data?.detail || '启动桌面时钟失败', 'error') }
  }

  const setWork = v => {
    setWorkMin(v)
    localStorage.setItem('wb_fp_work', String(v))
  }
  const setBreak = v => {
    setBreakMin(v)
    localStorage.setItem('wb_fp_break', String(v))
  }

  const disp = !session ? '' : (session.mode === 'free'
    ? fmtClock(session.work_seconds)
    : fmtMMSS(session.remaining))

  // 环形进度百分比（free 模式满环显示累计）
  const ringPct = !session ? 0 : (session.mode === 'free' ? 100 : (() => {
    const total = session.phase === 'break' ? session.break_min * 60 : session.work_min * 60
    return total > 0 ? Math.max(0, Math.min(100, Math.round(((total - (session.remaining || 0)) / total) * 100))) : 0
  })())
  const ringPhaseCls = session?.phase === 'break' ? 'fp-break' : (session?.paused ? 'fp-paused' : '')
  const dotPhaseCls = session?.phase === 'break' ? 'fp-dot-break' : (session?.paused ? 'fp-dot-paused' : '')
  const ringSub = !session ? '' : (session.mode === 'free' ? '已专注' : `${ringPct}%`)
  const timeLong = !session ? '' : (session.mode === 'free' && session.work_seconds >= 3600 ? 'fp-time-long' : '')

  return (
    <div className="card free-pomo-card" style={{ marginBottom: 16 }}>
      <div className="row" style={{ justifyContent: 'space-between', marginBottom: 8 }}>
        <div className="card-title">🎧 自由番茄钟 <span className="muted" style={{ fontSize: 12 }}>不绑定任务，设定学习状态直接开始</span></div>
        <button className="btn btn-sm" onClick={() => setShowHist(h => !h)}><BarChart3 size={14} strokeWidth={1.8} /> 近 7 天记录{hist && !showHist ? `（${hist.groups.length} 种）` : ''}</button>
      </div>

      {!running ? (
        <>
          <div className="row" style={{ gap: 6, marginBottom: 10, flexWrap: 'wrap' }}>
            <button className={`btn btn-sm ${mode === 'tomato' ? 'btn-primary' : ''}`} onClick={() => setMode('tomato')}>🍅 番茄模式（定时轮休）</button>
            <button className={`btn btn-sm ${mode === 'free' ? 'btn-primary' : ''}`} onClick={() => setMode('free')}><Timer size={14} strokeWidth={1.8} /> 自由计时（手动结束）</button>
          </div>
          <div className="row" style={{ gap: 6, marginBottom: 10, flexWrap: 'wrap' }}>
            {FP_PRESETS.map(p => (
              <button key={p} className={`btn btn-sm fp-preset ${stateText === p ? 'fp-preset-on' : ''}`} onClick={() => setStateText(p)}>{p}</button>
            ))}
            <input className="input" style={{ flex: 1, minWidth: 140 }} placeholder="学习状态（如：复现 DNANet）" value={stateText}
              onChange={e => setStateText(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.nativeEvent.isComposing) start() }} />
          </div>
          {mode === 'tomato' && (
            <div className="row" style={{ gap: 8, marginBottom: 10, flexWrap: 'wrap', alignItems: 'center' }}>
              <span className="muted" style={{ fontSize: 12.5 }}>工作</span>
              <input type="number" className="input" style={{ width: 64 }} min="1" max="180" value={workMin} onChange={e => setWork(Math.max(1, Math.min(180, Number(e.target.value) || 25)))} />
              <span className="muted" style={{ fontSize: 12.5 }}>分钟 · 休息</span>
              <input type="number" className="input" style={{ width: 64 }} min="0" max="60" value={breakMin} onChange={e => setBreak(Math.max(0, Math.min(60, Number(e.target.value) || 0)))} />
              <span className="muted" style={{ fontSize: 12.5 }}>分钟</span>
              {[15, 25, 35, 45].map(m => <button key={m} className="btn btn-sm" onClick={() => setWork(m)}>{m}'</button>)}
            </div>
          )}
          <div className="row" style={{ gap: 8 }}>
            <button className="btn btn-primary" onClick={start}><Play size={14} strokeWidth={1.8} /> 开始学习</button>
          </div>
        </>
      ) : (
        <>
          <div className="row" style={{ alignItems: 'center', gap: 20, flexWrap: 'wrap' }}>
            <div
              className={`fp-ring ${ringPhaseCls} ${!session.paused ? 'running-glow' : ''}`}
              style={{ '--fp-pct': `${ringPct * 3.6}deg` }}
            >
              <span className="fp-ring-inner">
                <span className={`fp-ring-time ${timeLong}`}>{disp}</span>
                <span className="fp-ring-sub">{ringSub}</span>
              </span>
            </div>
            <div style={{ flex: 1, minWidth: 230 }}>
              <div className="row" style={{ alignItems: 'center', gap: 8, marginBottom: 6 }}>
                <span className={`fp-status-dot ${dotPhaseCls}`} />
                <span style={{ fontWeight: 700, fontSize: 16 }}>{session.state || '学习'}</span>
                {session.mode === 'tomato' && (
                  <span className="badge badge-info">
                    {session.phase === 'break' ? '☕ 休息' : `🍅 第 ${session.rounds + 1} 轮`}
                  </span>
                )}
                {session.mode === 'free' && <span className="badge badge-warn">⏱ 自由计时</span>}
              </div>
              <div className="muted" style={{ margin: '2px 0 10px', fontSize: 13.5 }}>
                {session.paused
                  ? '⏸ 已暂停（暂停不计时）'
                  : session.phase === 'break'
                    ? `☕ 休息中，${session.break_min > 0 ? `还有 ${fmtMMSS(session.remaining)}` : '休息结束'}，休息完自动开始下一轮`
                    : session.mode === 'free'
                      ? `⏱ 自由计时中，已专注 ${disp}`
                      : `🍅 工作中，专注第 ${session.rounds + 1} 轮`}
              </div>
              <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
                {session.paused
                  ? <button className="btn btn-sm" onClick={resume}><Play size={14} strokeWidth={1.8} /> 继续</button>
                  : <button className="btn btn-sm" onClick={pause}><Pause size={14} strokeWidth={1.8} /> 暂停</button>}
                {session.phase === 'break'
                  ? <button className="btn btn-sm" onClick={skipBreak}><SkipForward size={14} strokeWidth={1.8} /> 跳过休息</button>
                  : <button className="btn btn-sm btn-primary" onClick={finish}><Check size={14} strokeWidth={1.8} /> 完成</button>}
                {session.phase === 'work' && (
                  <button className="btn btn-sm" onClick={desktop} title="右上角悬浮小窗显示计时"><Monitor size={14} strokeWidth={1.8} /> 桌面时钟</button>
                )}
                <button className="btn btn-sm btn-danger" onClick={abandon}><X size={14} strokeWidth={1.8} /> 放弃</button>
              </div>
            </div>
          </div>
        </>
      )}

      {showHist && (
        <div style={{ borderTop: '1px solid var(--border)', marginTop: 10, paddingTop: 10 }}>
          {!hist ? <div className="skeleton" style={{ height: 48 }} /> : (
            <>
              <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
                {hist.groups.length === 0 && <div className="muted" style={{ fontSize: 13 }}>近 7 天还没有自由番茄记录，开始第一次专注吧</div>}
                {hist.groups.map(g => (
                  <span key={g.state} className="badge badge-info">📚 {g.state} · {g.count} 次 · {fmtLong(g.seconds)}</span>
                ))}
              </div>
              {hist.sessions.length > 0 && (
                <div style={{ marginTop: 8, fontSize: 12.5, color: 'var(--text-2)', lineHeight: 1.8 }}>
                  {hist.sessions.map(s => (
                    <div key={s.id} style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {s.started_at.slice(5, 16).replace('T', ' ')} · {s.state || '学习'} · {s.mode === 'tomato' ? `${s.rounds} 轮` : '自由'} · {fmtLong(s.work_seconds)} · {s.status === 'done' ? '✓' : s.status === 'abandoned' ? '放弃' : '进行中'}
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}
