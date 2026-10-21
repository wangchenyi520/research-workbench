import React, { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api, { todayStr } from '../api'
import { useToast } from '../components/Toast'
import CopyBtn from '../components/CopyBtn'
import { parseQuickInput } from '../utils/quickParse'
import { Sun, Sparkles, Save, BookPlus, Play, X, Check, Monitor, ChevronDown } from 'lucide-react'

const QUADRANTS = [
  { key: 'important_urgent', label: '重要紧急', color: 'var(--danger)' },
  { key: 'important_not', label: '重要不紧急', color: 'var(--primary)' },
  { key: 'not_urgent_important', label: '紧急不重要', color: 'var(--warn)' },
  { key: 'not_important_not', label: '不重要不紧急', color: 'var(--text-2)' },
]

const QUADRANT_EMPTY = {
  important_urgent: '今天最重要最紧急的事，优先处理',
  important_not: '重要但不紧急，安排整块时间推进',
  not_urgent_important: '紧急但不重要，快速处理或委托他人',
  not_important_not: '不重要不紧急，减少精力投入',
}

function fmt(sec) {
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60)
  return h > 0 ? `${h}小时${m}分` : `${m}分钟`
}

function Ring({ percent, size = 88 }) {
  return (
    <div className="ring" style={{ width: size, height: size, background: `conic-gradient(var(--primary) ${percent * 3.6}deg, var(--card-2) 0)` }}>
      <div className="ring-inner">{percent}%</div>
    </div>
  )
}

function ItemForm({ initial, skills, onClose, onSaved }) {
  const toast = useToast()
  const [form, setForm] = useState({
    content: initial?.content || '',
    kind: initial?.kind || 'manual',
    quadrant: initial?.quadrant || 'important_urgent',
    scheduled_date: initial?.scheduled_date || todayStr(),
    due_date: initial?.due_date || '',
    weight: initial?.weight || 10,
    pomodoros: initial?.pomodoros || 0,
    time_range: initial?.time_range || '',
    est_minutes: initial?.est_minutes ?? '',
  })
  const [quick, setQuick] = useState('')
  const set = k => v => setForm(f => ({ ...f, [k]: v }))
  const applyQuick = () => {
    if (!quick.trim()) return
    const p = parseQuickInput(quick)
    setForm(f => ({ ...f, content: p.content, quadrant: p.quadrant, scheduled_date: p.scheduled_date || f.scheduled_date, due_date: p.due_date || f.due_date, weight: p.weight, pomodoros: p.pomodoros, time_range: p.time_range }))
    toast('已解析填充，可再微调')
  }
  const submit = async () => {
    if (!form.content.trim()) return toast('请输入内容', 'error')
    const payload = {
      ...form,
      scheduled_date: form.scheduled_date || null,
      due_date: form.due_date || null,
      est_minutes: form.est_minutes === '' || form.est_minutes == null ? null : Number(form.est_minutes),
    }
    try {
      if (initial?.id) await api.put(`/daily/${initial.id}`, payload)
      else await api.post('/daily', payload)
      toast('已保存'); onSaved(); onClose()
    } catch (e) { toast(e.response?.data?.detail || '保存失败', 'error') }
  }
  return (
    <div className="modal-mask" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <h3>{initial?.id ? '编辑清单项' : '添加到今日清单'}</h3>
        <label className="label">一句话快速填写（可选）</label>
        <div className="row">
          <input className="input" style={{ flex: 1 }} placeholder="如：明天下午3点写综述 p3 2个番茄" value={quick} onChange={e => setQuick(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.nativeEvent.isComposing) applyQuick() }} />
          <button className="btn btn-sm" onClick={applyQuick}><Sparkles size={14} strokeWidth={1.8} /> 解析填充</button>
        </div>
        <label className="label">内容 *</label>
        <input className="input" value={form.content} onChange={e => set('content')(e.target.value)} />
        <div className="row">
          <div style={{ flex: 1 }}>
            <label className="label">象限</label>
            <select className="select" value={form.quadrant} onChange={e => set('quadrant')(e.target.value)}>
              {QUADRANTS.map(q => <option key={q.key} value={q.key}>{q.label}</option>)}
            </select>
          </div>
          <div style={{ flex: 1 }}>
            <label className="label">计划日（哪天做）</label>
            <input type="date" className="input" value={form.scheduled_date} onChange={e => set('scheduled_date')(e.target.value)} />
          </div>
        </div>
        <div className="row">
          <div style={{ flex: 1 }}>
            <label className="label">截止日期</label>
            <input type="date" className="input" value={form.due_date} onChange={e => set('due_date')(e.target.value)} />
          </div>
          <div style={{ flex: 1 }}>
            <label className="label">权重（占今日精力 %）</label>
            <input type="number" className="input" min="1" max="100" value={form.weight} onChange={e => set('weight')(Number(e.target.value))} />
          </div>
        </div>
        <div className="row">
          <div style={{ flex: 1 }}>
            <label className="label">预计番茄钟</label>
            <input type="number" className="input" min="0" value={form.pomodoros} onChange={e => set('pomodoros')(Number(e.target.value))} />
          </div>
          <div style={{ flex: 1 }}>
            <label className="label">预估时长（分钟，可 AI 或手填）</label>
            <input type="number" className="input" min="1" placeholder="如 45" value={form.est_minutes} onChange={e => set('est_minutes')(e.target.value === '' ? '' : Number(e.target.value))} />
          </div>
          <div style={{ flex: 1 }}>
            <label className="label">时间段（可选，如 09:00-10:30）</label>
            <input className="input" placeholder="09:00-10:30" value={form.time_range} onChange={e => set('time_range')(e.target.value)} />
          </div>
        </div>
        <div className="modal-actions">
          <button className="btn" onClick={onClose}>取消</button>
          <button className="btn btn-primary" onClick={submit}>保存</button>
        </div>
      </div>
    </div>
  )
}

function SkillEditor({ skill, goals, onClose, onSaved }) {
  const toast = useToast()
  const [form, setForm] = useState({ name: skill?.name || '', description: skill?.description || '', goal_id: skill?.goal_id || '' })
  const [stages, setStages] = useState(skill?.stages || [])
  const [newStage, setNewStage] = useState('')

  const addStage = async () => {
    if (!newStage.trim()) return
    const r = await api.post(`/skills/${skill.id}/stages`, { name: newStage.trim() })
    setStages(s => [...s, r.data]); setNewStage('')
  }
  const upStage = async (st, k, v) => {
    setStages(list => list.map(x => (x.id === st.id ? { ...x, [k]: v } : x)))
    await api.put(`/skills/stages/${st.id}`, { [k]: v }).catch(() => {})
  }
  const delStage = async st => {
    await api.delete(`/skills/stages/${st.id}`)
    setStages(list => list.filter(x => x.id !== st.id))
  }
  const save = async () => {
    if (!form.name.trim()) return toast('请输入技能名称', 'error')
    const payload = { ...form, goal_id: form.goal_id || null }
    try {
      if (skill) await api.put(`/skills/${skill.id}`, payload)
      else await api.post('/skills', payload)
      toast('已保存'); onSaved(); onClose()
    } catch (e) { toast(e.response?.data?.detail || '保存失败', 'error') }
  }
  const del = async () => {
    if (!confirm(`删除技能「${skill.name}」？`)) return
    await api.delete(`/skills/${skill.id}`)
    onSaved(); onClose()
  }
  return (
    <div className="modal-mask" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <h3>编辑技能</h3>
        <label className="label">名称 *</label>
        <input className="input" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
        <label className="label">描述</label>
        <textarea className="textarea" value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} />
        <label className="label">从属目标</label>
        <select className="select" value={form.goal_id} onChange={e => setForm(f => ({ ...f, goal_id: e.target.value }))}>
          <option value="">无</option>
          {goals.map(g => <option key={g.id} value={g.id}>{g.title}</option>)}
        </select>
        <label className="label">阶段（总进度 = 各阶段平均）</label>
        {!skill && <div className="muted" style={{ marginBottom: 8, fontSize: 12 }}>保存后自动创建「入门 / 进阶 / 实战」三阶段，可在编辑时增删改。</div>}
        {stages.map((st, i) => (
          <div className="row" key={st.id} style={{ marginBottom: 6 }}>
            <span style={{ width: 24, color: 'var(--text-2)' }}>{i + 1}.</span>
            <input className="input" style={{ flex: 2 }} value={st.name} onChange={e => upStage(st, 'name', e.target.value)} />
            <input type="number" className="input" style={{ width: 80 }} min="0" max="100" value={st.progress} onChange={e => upStage(st, 'progress', Number(e.target.value))} />
            <button className="btn btn-sm btn-danger" onClick={() => delStage(st)}>删</button>
          </div>
        ))}
        <div className="row">
          <input className="input" style={{ flex: 2 }} placeholder="新阶段名（如：实战）" value={newStage} onChange={e => setNewStage(e.target.value)} />
          <button className="btn btn-sm" onClick={addStage}>+ 阶段</button>
        </div>
        <div className="modal-actions">
          <button className="btn btn-danger" onClick={del}>删除技能</button>
          <button className="btn" onClick={onClose}>取消</button>
          <button className="btn btn-primary" onClick={save}>保存</button>
        </div>
      </div>
    </div>
  )
}


const ATT_STATUS = {
  idle: ['尚未打卡', 'att-dot-idle'],
  working: ['在岗中', 'att-dot-working'],
  paused: ['休息中', 'att-dot-paused'],
  closed: ['今日已结束', 'att-dot-closed'],
}

function fmtHM(sec) {
  const s = Math.max(0, Math.floor(sec || 0))
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60)
  return `${h}h ${m}m`
}

// 今日页考勤快捷小卡：只做状态展示 + 跳转考勤独立页（打卡/统计都在那边）
function AttendanceQuickCard() {
  const navigate = useNavigate()
  const [att, setAtt] = useState(null)
  const [attErr, setAttErr] = useState(false)
  useEffect(() => {
    const load = () => { api.get('/attendance/today').then(r => { setAtt(r.data); setAttErr(false) }).catch(() => setAttErr(true)) }
    load()
    const iv = setInterval(load, 60000)
    return () => clearInterval(iv)
  }, [])
  const [label, dot] = (attErr && !att) ? ['状态未知', 'att-dot-idle'] : (ATT_STATUS[att?.status] || ATT_STATUS.idle)
  return (
    <div className="card att-quick" style={{ marginBottom: 16 }} onClick={() => navigate('/attendance')}>
      <span className="att-quick-icon">📍</span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="row" style={{ gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <span style={{ fontWeight: 700 }}>考勤</span>
          <span className="att-status-label" style={{ fontSize: 13.5 }}>
            <span className={`att-dot ${dot}`} />{label}
          </span>
        </div>
        <div className="muted" style={{ fontSize: 12.5, marginTop: 2 }}>
          {att
            ? `今日在岗 ${fmtHM(att.today_seconds)}${att.status === 'working' ? ' · 计时中' : ' · 点击进入打卡与统计'}`
            : (attErr ? '点击进入打卡与统计' : '加载中…')}
        </div>
      </div>
      <span className="btn btn-sm btn-primary">去打卡 →</span>
    </div>
  )
}

export default function Today() {
  const toast = useToast()
  const [data, setData] = useState({ items: [], done: [], stats: { percent: 0, pending_count: 0, done_count: 0, carryover_percent: 0, carryover_pending_count: 0, carryover_done_count: 0 } })
  const [skills, setSkills] = useState([])
  const [goals, setGoals] = useState([])
  const [settings, setSettings] = useState({})
  const [todayStats, setTodayStats] = useState({ total_seconds: 0 })
  const [view, setView] = useState(() => localStorage.getItem('wb_today_view') || 'plan') // plan / list / week / done（记住用户选择，切换页面/重开仍保留）
  const [showAdd, setShowAdd] = useState(false)
  const [editItem, setEditItem] = useState(null)
  const [editSkill, setEditSkill] = useState(null)
  const [aiItems, setAiItems] = useState([])
  const [aiLoading, setAiLoading] = useState(false)
  const [aiAutoLand, setAiAutoLand] = useState(false)
  const [aiLandedCount, setAiLandedCount] = useState(0)
  const [aiCollapsed, setAiCollapsed] = useState(true)
  const [aiSelected, setAiSelected] = useState([])
  const [focusText, setFocusText] = useState('')
  const [collapsed, setCollapsed] = useState({ not_important_not: true })
  const [quickText, setQuickText] = useState('')
  const [upcoming, setUpcoming] = useState([])
  const [reward, setReward] = useState({ streak: 0, threshold: 7 })
  const [guideHidden, setGuideHidden] = useState(false)
  const [rmToday, setRmToday] = useState(0)
  const [deskListOpen, setDeskListOpen] = useState(false)
  const [deskListMin, setDeskListMin] = useState(false)
  // 顶部状态胶囊行：点开的那个胶囊（null=全收起）
  const [openPill, setOpenPill] = useState(null)
  // 刚勾选完成的事项：留在原视图 6 秒（划线 + 撤销按钮），防误勾选无可挽回
  const [justDone, setJustDone] = useState([])
  const [dailyPaper, setDailyPaper] = useState(null)
  const [dpFailed, setDpFailed] = useState(false)
  const navigate = useNavigate()
  const aiFetched = useRef(false)
  const userSwitched = useRef(false)
  const aiCtrl = useRef(null)
  const lastDateRef = useRef(todayStr())

  const load = () => {
    api.get('/daily').then(r => setData(r.data)).catch(() => {})
    api.get('/daily/upcoming?days=7').then(r => setUpcoming(r.data)).catch(() => {})
    api.get('/skills').then(r => setSkills(r.data)).catch(() => {})
    api.get('/goals').then(r => setGoals(r.data)).catch(() => {})
    api.get('/settings').then(r => setSettings(r.data)).catch(() => {})
    api.get('/tasks/stats/today').then(r => setTodayStats(r.data)).catch(() => {})
    api.get('/stats/reward-streak').then(r => setReward(r.data)).catch(() => {})
    api.get('/reminders').then(r => setRmToday(r.data?.stats?.today ?? 0)).catch(() => {})
    api.get('/checklist-widget/state').then(r => { setDeskListOpen(!!r.data.active); setDeskListMin(!!r.data.minimized) }).catch(() => {})
    // 每日论文：首次打开工作台自动生成（后端幂等，当天已有直接返回）
    api.post('/daily-paper/generate').then(r => { setDailyPaper(r.data); setDpFailed(false) }).catch(() => setDpFailed(true))
  }
  useEffect(load, [])

  // 跨天检测：窗口/页面长期不刷新（如昨天没关工作台）时，日期变化自动重新加载，
  // 触发当天的懒生成并刷新「今日论文推荐」banner（避免显示/误操作昨天的论文）
  useEffect(() => {
    const check = () => {
      const d = todayStr()
      if (d !== lastDateRef.current) {
        lastDateRef.current = d
        load()
      }
    }
    // 桌面悬浮清单可能在窗口外打勾：定时/回到窗口时同步今日清单与开关状态
    const syncDesk = () => {
      if (document.visibilityState !== 'visible') return
      api.get('/daily').then(r => setData(r.data)).catch(() => {})
      api.get('/checklist-widget/state').then(r => { setDeskListOpen(!!r.data.active); setDeskListMin(!!r.data.minimized) }).catch(() => {})
    }
    const t = setInterval(() => { check(); syncDesk() }, 20 * 1000)
    const onVisible = () => { if (document.visibilityState === 'visible') { check(); syncDesk() } }
    window.addEventListener('focus', onVisible)
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      clearInterval(t)
      window.removeEventListener('focus', onVisible)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [])

  const quickAdd = async () => {
    if (!quickText.trim()) return toast('请输入内容', 'error')
    const p = parseQuickInput(quickText)
    try {
      await api.post('/daily', {
        content: p.content, kind: 'manual', quadrant: p.quadrant,
        weight: p.weight, pomodoros: p.pomodoros, time_range: p.time_range,
        due_date: p.due_date, scheduled_date: p.scheduled_date,
      })
      toast('已添加到今日清单')
      setQuickText('')
      load()
    } catch (e) { toast(e.response?.data?.detail || '添加失败', 'error') }
  }

  // 每日论文：一键「今天读」加入今日清单（自动入库拿到 literature_id）
  const addTodayPaper = async () => {
    if (!dailyPaper) return
    try {
      let litId = dailyPaper.literature_id
      if (!litId) {
        const r = await api.post(`/daily-paper/${dailyPaper.id}/archive`)
        litId = r.data.id
      }
      await api.post('/daily', {
        content: `读论文：${dailyPaper.title}`,
        kind: 'literature',
        source_id: litId,
        scheduled_date: todayStr(),
        quadrant: 'important_not',
        weight: 10,
      })
      toast('已加入今日清单')
      api.post(`/daily-paper/${dailyPaper.id}/read`).catch(() => {})
      setDailyPaper(p => (p ? { ...p, read: true } : p))
      load()
    } catch (e) { toast(e.response?.data?.detail || '加入失败', 'error') }
  }

  // AI 预估时长：弹窗式（勾选单项/全部 → AI 预估预览可修改 → 确认应用）
  const [estOpen, setEstOpen] = useState(false)
  const [estPhase, setEstPhase] = useState('pick') // pick / result
  const [estSel, setEstSel] = useState(() => new Set())
  const [estLoading, setEstLoading] = useState(false)
  const [estResults, setEstResults] = useState({})
  const estCands = (data.items || [])
    .filter(i => !i.est_minutes)
    .map(i => ({
      key: (i.kind === 'task' && i.source_id ? 't' : 'd') + (i.kind === 'task' && i.source_id ? i.source_id : i.id),
      type: i.kind === 'task' && i.source_id ? 'task' : 'item',
      id: i.kind === 'task' && i.source_id ? i.source_id : i.id,
      content: i.content,
      kind_label: i.kind_label,
    }))
  const openEstimate = () => {
    if (estCands.length === 0) return toast('今日清单里的任务都已有时长预估', 'error')
    setEstSel(new Set(estCands.map(c => c.key)))
    setEstResults({})
    setEstPhase('pick')
    setEstOpen(true)
  }
  const runEstimate = async () => {
    const sel = estCands.filter(c => estSel.has(c.key))
    if (sel.length === 0) return toast('请先勾选要预估的事项', 'error')
    setEstLoading(true)
    try {
      const ids = sel.filter(c => c.type === 'task').map(c => c.id)
      const itemIds = sel.filter(c => c.type === 'item').map(c => c.id)
      const r = await api.post('/ai/estimate-tasks', { ids, item_ids: itemIds, preview: true })
      const m = {}
      sel.forEach(c => {
        const v = c.type === 'task' ? r.data.tasks?.[String(c.id)] : r.data.items?.[String(c.id)]
        if (v) m[c.key] = v
      })
      if (Object.keys(m).length === 0) return toast('AI 未能给出预估，可稍后再试', 'error')
      setEstResults(m)
      setEstPhase('result')
    } catch (e) {
      toast(e.response?.data?.detail || '预估失败', 'error')
    } finally {
      setEstLoading(false)
    }
  }
  const applyEstimate = async () => {
    let n = 0
    for (const c of estCands) {
      const v = estResults[c.key]
      if (!v) continue
      if (c.type === 'task') await api.put(`/tasks/${c.id}`, { est_minutes: Number(v) }).catch(() => {})
      else await api.put(`/daily/${c.id}`, { est_minutes: Number(v) }).catch(() => {})
      n++
    }
    toast(`已应用 ${n} 项预估时长，可随时再改`)
    setEstOpen(false)
    load()
  }

  // 顺延到明天：单选一个清单项，把它的计划日改为明天（今天清单里消失，明天自动出现）
  const [delayOpen, setDelayOpen] = useState(false)
  const [delayTarget, setDelayTarget] = useState(null)
  const nextDayStr = () => {
    const d = new Date()
    d.setDate(d.getDate() + 1)
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  }
  const delayToTomorrow = async () => {
    if (!delayTarget) return
    try {
      await api.put(`/daily/${delayTarget}`, { scheduled_date: nextDayStr() })
      toast('已顺延到明天，明天清单会自动出现它')
      setDelayOpen(false)
      load()
    } catch (e) { toast(e.response?.data?.detail || '顺延失败', 'error') }
  }

  // 晚间视角：晚于设置时间默认落「完成情况」，用户手动切换/曾选择过视图后不再干预
  useEffect(() => {
    if (settings.evening_view_enabled === 'true' && !userSwitched.current && !localStorage.getItem('wb_today_view')) {
      const [h, m] = (settings.evening_view_time || '22:00').split(':').map(Number)
      const now = new Date()
      const evening = now.getHours() > h || (now.getHours() === h && now.getMinutes() >= m)
      if (evening) setView('done')
    }
  }, [settings])

  useEffect(() => {
    if (settings.daily_ai_enabled === 'true' && !aiFetched.current) {
      aiFetched.current = true
      // 同一天只自动触发一次，避免每次进入页面重复消耗
      const last = localStorage.getItem('wb_ai_daily_date')
      const t = todayStr()
      if (last !== t) {
        localStorage.setItem('wb_ai_daily_date', t)
        genAi()
      }
    }
  }, [settings])

  const genAi = async () => {
    setAiLoading(true)
    aiCtrl.current = new AbortController()
    try {
      const r = await api.post('/ai/daily-plan', { focus: focusText }, { signal: aiCtrl.current.signal })
      const auto = r.data.auto_land === true
      setAiAutoLand(auto)
      setAiItems(r.data.items || [])
      setAiLandedCount(r.data.landed_count || 0)
      if (auto) {
        if (r.data.landed_count > 0) {
          toast(`AI 已自动加入今日清单 ${r.data.landed_count} 项（可删改）`)
          load()
        } else if ((r.data.items || []).length > 0) {
          toast('AI 建议与今日清单已有内容重复，未重复添加')
        }
      } else if (r.data.count > 0) {
        toast(`✨ 已生成 ${r.data.count} 条今日建议，可逐条采纳`)
      }
    } catch (e) {
      if (e.code !== 'ERR_CANCELED') toast(e.response?.data?.detail || 'AI 整理失败', 'error')
    } finally {
      setAiLoading(false)
      aiCtrl.current = null
    }
  }

  const cancelAi = () => {
    aiCtrl.current?.abort()
    setAiLoading(false)
  }

  const toggleAiSel = i => setAiSelected(s => (s.includes(i) ? s.filter(x => x !== i) : [...s, i]))

  const saveAi = async x => {
    await api.post('/daily', {
      content: x.content, kind: x.kind || 'ai', source_id: x.source_id || null,
      quadrant: x.quadrant || 'important_urgent', weight: x.weight || 10,
      pomodoros: x.pomodoros || 0, due_date: x.due_date || null,
    })
  }

  const adopt = async (selectedIdx, all = false) => {
    const list = all ? aiItems : (selectedIdx != null ? [aiItems[selectedIdx]] : [])
    if (list.length === 0) return
    for (const x of list) {
      try { await saveAi(x) } catch (e) { toast(e.response?.data?.detail || '采纳失败', 'error') }
    }
    // 只移除已采纳的条目，其余建议保留、不关闭
    setAiItems(prev => (all ? [] : prev.filter((_, j) => j !== selectedIdx)))
    setAiSelected([])
    toast(`已采纳 ${list.length} 条，其余建议保留`)
    load()
  }

  const adoptSelected = async () => {
    if (aiSelected.length === 0) return toast('请先勾选要采纳的建议', 'error')
    const list = aiSelected.map(i => aiItems[i]).filter(Boolean)
    for (const x of list) {
      try { await saveAi(x) } catch (e) { toast(e.response?.data?.detail || '采纳失败', 'error') }
    }
    setAiItems(prev => prev.filter((_, j) => !aiSelected.includes(j)))
    setAiSelected([])
    toast(`已采纳 ${list.length} 条，其余建议保留`)
    load()
  }

  const toggle = async (item) => {
    const wasDone = item.status === 'done'
    await api.put(`/daily/${item.id}`, { status: wasDone ? 'pending' : 'done' })
    const r = await api.get('/daily')
    setData(r.data)
    if (!wasDone) {
      // 保留 6 秒可撤销（以划线行显示在原视图，避免误勾后找不到）
      const entry = { ...item, status: 'done', _undoId: `${item.id}-${Date.now()}` }
      setJustDone(list => [...list.filter(x => x.id !== item.id), entry])
      setTimeout(() => setJustDone(list => list.filter(x => x._undoId !== entry._undoId)), 6000)
      // A12：按勾选项归属弹对应文案，避免补完旧账却弹「今日全部完成」
      const s = r.data.stats
      const isCarry = item.scheduled_date && item.scheduled_date < r.data.today
      if (!isCarry && s.percent >= 100 && s.done_count > 0) toast('🎉 今日事项全部完成，太棒了！')
      else if (isCarry && s.carryover_percent >= 100 && s.carryover_done_count > 0) toast('🎉 顺延欠账全部补完！')
    } else {
      setJustDone(list => list.filter(x => x.id !== item.id))
    }
  }
  const undoDone = async (item) => {
    try {
      await api.put(`/daily/${item.id}`, { status: 'pending' })
      setJustDone(list => list.filter(x => x.id !== item.id))
      toast('已撤销')
      load()
    } catch (e) { toast('撤销失败', 'error') }
  }
  const remove = async (item) => {
    if (!confirm(`删除「${item.content}」？`)) return
    await api.delete(`/daily/${item.id}`)
    toast('已删除'); load()
  }

  const pending = data.items
  // 刚勾选完成的行在 6 秒撤销窗口内仍然显示（划线 + 撤销）
  const undoItems = justDone.filter(j => !pending.some(i => i.id === j.id))
  const pendingView = [...pending, ...undoItems]
  // 权重编辑：直接显示/提交存储的原始 weight。
  // 后端 PUT 时固定该项、其余项按比例缩放，保证「已完成 + 剩余」恒=100。
  const changeWeight = async (item, newPct) => {
    const w = Math.max(1, Math.min(99, Number(newPct) || 1))
    await api.put(`/daily/${item.id}`, { weight: w }).catch(() => {})
    toast('权重已更新，其余项已自动调整')
    load()
  }

  const sorted = [...pendingView].sort((a, b) => {
    const da = a.due_date || a.scheduled_date
    const db = b.due_date || b.scheduled_date
    return (da || '').localeCompare(db || '') || (a.created_at || '').localeCompare(b.created_at || '')
  })

  // 桌面悬浮清单开关：与页面双向打勾（数据走同一份，悬浮窗每 4 秒自刷新）
  // 已最小化（桌面底部小条）时，点击 = 还原展开态
  const toggleDeskList = async () => {
    try {
      if (!deskListOpen) {
        await api.post('/checklist-widget/start')
        setDeskListOpen(true)
        setDeskListMin(false)
        toast('桌面清单已打开：可在桌面小窗查看/勾选今日清单')
      } else if (deskListMin) {
        await api.post('/checklist-widget/control', { action: 'restore' })
        setDeskListMin(false)
        toast('桌面清单已还原')
      } else {
        await api.post('/checklist-widget/control', { action: 'hide' })
        setDeskListOpen(false)
        setDeskListMin(false)
        toast('桌面清单已关闭')
      }
    } catch (e) {
      toast(e.response?.data?.detail || '操作失败', 'error')
    }
  }

  const archiveToday = async () => {
    const d = data.today || todayStr()
    const items = data.items || []
    const done = data.done || []
    const stats = data.stats || {}
    const lines = [`# 日记 ${d}`, '']
    const todayItems = items.filter(i => i.scheduled_date === d)
    const carryItems = items.filter(i => i.scheduled_date < d)
    lines.push(`## 📋 今日清单（${items.length + done.length} 项）`, '')
    if (todayItems.length) {
      lines.push('**计划（待办）**', '')
      todayItems.forEach(i => lines.push(`- [ ] ${i.content}${i.time_range ? ` （${i.time_range}）` : ''}${i.pomodoros > 0 ? ` · 🍅×${i.pomodoros}` : ''}`))
      lines.push('')
    }
    if (carryItems.length) {
      lines.push('**顺延欠账（待补）**', '')
      carryItems.forEach(i => lines.push(`- [ ] ${i.content}（顺延）`))
      lines.push('')
    }
    if (done.length) {
      lines.push('**已完成**', '')
      done.forEach(i => lines.push(`- [x] ${i.content}`))
      lines.push('')
    }
    lines.push('## 📊 统计', '')
    lines.push(`- 完成度：${stats.done_count || 0}/${(stats.pending_count || 0) + (stats.done_count || 0)}（今日 ${stats.percent || 0}% · 顺延 ${stats.carryover_percent || 0}%）`)
    lines.push(`- 投入时长：${fmt(todayStats.total_seconds || 0)} · 番茄 ${todayStats.pomodoros || 0} 个`, '')
    lines.push('## 💭 今日感想', '')
    try {
      const q = await api.get('/notes', { params: { q: `日记 ${d}` } })
      const list = Array.isArray(q.data) ? q.data : (q.data?.items || [])
      const existing = list.find(n => (n.title || '') === `日记 ${d}`)
      const body = { title: `日记 ${d}`, content: lines.join('\n'), folder: '日记', tags: '日记' }
      if (existing) {
        await api.put(`/notes/${existing.id}`, body)
        toast('已更新今日日记（同名不重复生成）')
      } else {
        await api.post('/notes', body)
        toast('已存档为笔记（文件夹「日记」）')
      }
    } catch (e) { toast('存档失败', 'error') }
  }

  const isEvening = settings.evening_view_enabled === 'true' && (() => {
    const [h, m] = (settings.evening_view_time || '22:00').split(':').map(Number)
    const now = new Date()
    return now.getHours() > h || (now.getHours() === h && now.getMinutes() >= m)
  })()

  const renderItem = item => (
    <div key={item.id} className={`d-item ${item.status === 'done' ? 'done' : ''} ${item.overdue ? 'overdue' : ''}`}>
      <input type="checkbox" checked={item.status === 'done'} onChange={() => toggle(item)} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="d-item-title">
          {item.content}
          <span className={`badge ${item.kind === 'ai' ? 'badge-info' : 'badge-gray'}`}>{item.kind_label}</span>
          {item.overdue && <span className="badge badge-warn">待补</span>}
          {item.due_overdue && <span className="badge badge-gray">截止已过</span>}
          {item.overdue && <span className="d-pending">📌 {item.overdue_text}</span>}
          {item.due_overdue && <span className="d-pending">📌 {item.due_overdue_text}</span>}
        </div>
<div className="muted" style={{ fontSize: 12 }}>
          {item.time_range && `🕐 ${item.time_range}`}
          {item.pomodoros > 0 && ` · 🍅×${item.pomodoros}`}
          {item.est_minutes && ` · ⏱ 预计 ${item.est_minutes} 分钟`}
          {item.due_date && ` · 截止 ${item.due_date}`}
          {item.status !== 'done' && (
            <span className="d-weight" title="权重 = 该项占当日体系精力的百分比，修改后同体系其余项自动重分配，总和恒 100">
              {' '}权重 <input key={`${item.id}-${item.weight}`} type="number" min="1" max="99" className="d-weight-input" defaultValue={item.weight || 1} onBlur={e => { const v = Number(e.target.value); if (v && v !== (item.weight || 1)) changeWeight(item, v) }} />%
            </span>
          )}
        </div>
      </div>
      {item.status !== 'done' && <button className="btn btn-sm" onClick={() => setEditItem(item)}>编辑</button>}
      {item.status !== 'done' && (
        <button className="btn btn-sm" title="推迟到明天，明天清单自动出现" onClick={() => { setDelayTarget(item.id); setDelayOpen(true) }}>顺延</button>
      )}
      {item._undoId && <button className="btn btn-sm btn-primary" onClick={() => undoDone(item)}>撤销</button>}
      <button className="btn btn-sm btn-danger" onClick={() => remove(item)}>删除</button>
    </div>
  )

  // 今日引导：顺延待补优先，其次按权重取最重要的 1-3 件事
  const topItems = [...data.items]
    .sort((a, b) => {
      if (a.overdue !== b.overdue) return a.overdue ? -1 : 1
      if (a.quadrant !== b.quadrant) {
        const qo = { important_urgent: 0, important_not: 1, not_urgent_important: 2, not_important_not: 3 }
        return (qo[a.quadrant] ?? 9) - (qo[b.quadrant] ?? 9)
      }
      return (b.weight || 0) - (a.weight || 0)
    })
    .slice(0, 3)
  const guideLine = topItems[0]
    ? `今天最重要的事：${topItems[0].content}。先完成它，你就超过了昨天的自己。`
    : '今天从一件小事开始就好。'

  const startFocus = async () => {
    const top = topItems[0]
    if (!top) return toast('今天还没有安排，先加一项吧', 'error')
    try {
      // 与自由番茄钟互斥
      const fp = await api.get('/free-pomodoro/state').catch(() => ({ data: null }))
      if (fp.data?.session && ['running', 'paused'].includes(fp.data.session.status)) return toast(`自由番茄钟正在「${fp.data.session.state || '学习'}」中，请先完成或放弃`, 'error')
      if (top.kind === 'task' && top.source_id) {
        const log = await api.post(`/tasks/${top.source_id}/timelogs`, { kind: 'pomodoro' })
        await api.post('/pomodoro/widget/start', { task_id: top.source_id, log_id: log.data.id, title: top.content })
        toast('🍅 番茄钟已启动，开始干活！')
      } else {
        // 非任务项（手动/顺延/AI 建议等）：按事项内容启动自由番茄钟，保证主 CTA 永远可执行
        const r = await api.post('/free-pomodoro/start', {
          state: (top.content || '').slice(0, 50),
          mode: 'tomato',
          work_min: Number(settings.pomodoro_minutes) || 25,
          break_min: Number(settings.break_minutes) || 5,
        })
        await api.post('/pomodoro/widget/start', {
          session_id: r.data.id, title: top.content, mode: 'tomato',
          work_min: r.data.work_min, break_min: r.data.break_min,
          phase: 'work', remaining: r.data.remaining, paused: false,
        })
        toast('🍅 已按该事项开始专注，加油！')
      }
    } catch (e) {
      toast(e.response?.data?.detail || '启动番茄钟失败', 'error')
    }
  }

  return (
    <div>
      <div className="page-header">
        <h1><span className="page-icon"><Sun size={22} strokeWidth={1.75} /></span>今日</h1>
        <div className="row">
          <span className="badge badge-info">{data.today} · 投入 {fmt(todayStats.total_seconds || 0)}</span>
          <button className="btn btn-sm" onClick={openEstimate} title="勾选要预估的事项，AI 预估后确认应用（可修改）"><Sparkles size={14} strokeWidth={1.8} /> AI 预估时长</button>
          <button className={`btn btn-sm ${deskListOpen ? 'btn-primary' : ''}`} onClick={toggleDeskList} title="桌面悬浮小窗显示今日清单，支持置顶/最小化到桌面底部/缩放/快速添加，与页面双向打勾">
            <Monitor size={14} strokeWidth={1.8} /> 桌面清单{deskListMin ? '（已最小化）' : ''}
          </button>
          <button className="btn" onClick={archiveToday}><Save size={14} strokeWidth={1.8} /> 今日存档</button>
          <button className="btn btn-primary" onClick={() => setShowAdd(true)}>+ 添加事项</button>
        </div>
      </div>

      <div className="row" style={{ marginBottom: 12 }}>
        <input
          className="input"
          style={{ flex: 1 }}
          placeholder="⚡ 快速添加：如「明天下午3点写综述 p3 2个番茄」，回车即添加"
          value={quickText}
          onChange={e => setQuickText(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.nativeEvent.isComposing) quickAdd() }}
        />
        <button className="btn btn-primary" onClick={quickAdd}>+ 快速添加</button>
      </div>

      <AttendanceQuickCard />

      {/* 顶部状态胶囊行：一行小胶囊，点开才展开详情（页面更清爽） */}
      <div className="pill-row">
        {reward.streak >= 1 && (
          <button className={`status-pill ${openPill === 'reward' ? 'on' : ''}`}
            onClick={() => setOpenPill(p => (p === 'reward' ? null : 'reward'))}>
            <span className="status-pill-ico">🔥</span>连续 {reward.streak} 天
            <ChevronDown size={13} className={`pill-chev ${openPill === 'reward' ? 'up' : ''}`} />
          </button>
        )}
        <button className={`status-pill ${openPill === 'reminder' ? 'on' : ''}`}
          onClick={() => setOpenPill(p => (p === 'reminder' ? null : 'reminder'))}>
          <span className="status-pill-ico">⏰</span>
          {rmToday > 0 ? `今天 ${rmToday} 件提醒` : '提醒事项'}
          <ChevronDown size={13} className={`pill-chev ${openPill === 'reminder' ? 'up' : ''}`} />
        </button>
        {(dailyPaper || dpFailed) && (
          <button className={`status-pill ${openPill === 'paper' ? 'on' : ''}`}
            onClick={() => setOpenPill(p => (p === 'paper' ? null : 'paper'))}>
            <span className="status-pill-ico">📖</span>
            {dailyPaper ? (dailyPaper.read ? '今日论文已读' : '今日论文') : '论文生成失败'}
            <ChevronDown size={13} className={`pill-chev ${openPill === 'paper' ? 'up' : ''}`} />
          </button>
        )}
      </div>

      {openPill === 'reward' && reward.streak >= 1 && (
        <div className="reward-banner" style={{ marginBottom: 16 }}>
          {reward.streak >= reward.threshold
            ? <>🎁 已连续 {reward.streak} 天完成任务，今天值得奖励自己一顿好的！</>
            : <>🔥 已连续 {reward.streak} 天有产出，再坚持 {reward.threshold - reward.streak} 天就可以犒劳自己</>}
        </div>
      )}

      {openPill === 'reminder' && (
        <div className="reminder-banner" style={{ marginBottom: 16, cursor: 'pointer' }}
          onClick={() => navigate('/reminders')} title="点击查看提醒事项">
          <div className="row" style={{ gap: 8, alignItems: 'center' }}>
            <span style={{ fontSize: 18 }}>⏰</span>
            {rmToday > 0 ? (
              <>
                <span style={{ fontWeight: 700 }}>今天还有 {rmToday} 件琐事提醒</span>
                <span className="muted" style={{ fontSize: 13 }}>找老师 / 还书 / 考试… 点击查看 →</span>
              </>
            ) : (
              <>
                <span style={{ fontWeight: 700 }}>提醒事项</span>
                <span className="muted" style={{ fontSize: 13 }}>找老师 / 还书 / 考试… 到点弹窗提醒 →</span>
              </>
            )}
          </div>
        </div>
      )}

      {openPill === 'paper' && dailyPaper && (
        <div className="daily-paper-banner" style={{ marginBottom: 16 }}>
          <div style={{ flex: 1, cursor: 'pointer', minWidth: 0 }} onClick={() => navigate('/daily-paper')}>
            <div className="row" style={{ gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <span style={{ fontSize: 18 }}>📖</span>
              <span style={{ fontWeight: 700 }}>今日论文推荐</span>
              <span className="badge badge-info">{dailyPaper.year || ''} {dailyPaper.citation_count ? `· ${dailyPaper.citation_count} 引` : '· 最新'}</span>
              {dailyPaper.pdf_file && <span className="badge badge-success">PDF 已下载</span>}
              {dailyPaper.zotero_key && <span className="badge badge-success">🗂 已入 Zotero</span>}
            </div>
            <div style={{ fontWeight: 600, marginTop: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{dailyPaper.title}</div>
            <div className="muted" style={{ fontSize: 13, marginTop: 2 }}>{dailyPaper.why_read || '点击查看 AI 导读与全文'}</div>
          </div>
          <button className="btn btn-sm" onClick={addTodayPaper} title="加入今日清单（kind=literature，完成自动置已读）"><BookPlus size={14} strokeWidth={1.8} /> 今天读</button>
          <button className="btn btn-sm btn-primary" onClick={() => navigate('/daily-paper')}>查看 →</button>
        </div>
      )}

      {openPill === 'paper' && dpFailed && !dailyPaper && (
        <div className="daily-paper-banner" style={{ marginBottom: 16, borderColor: 'var(--danger)' }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="row" style={{ gap: 8, alignItems: 'center' }}>
              <span style={{ fontSize: 18 }}>📖</span>
              <span style={{ fontWeight: 700 }}>今日论文生成失败</span>
            </div>
            <div className="muted" style={{ fontSize: 13, marginTop: 2 }}>网络或数据源暂时不可用，可稍后重试，或到「每日论文」页手动生成</div>
          </div>
          <button className="btn btn-sm" onClick={() => load()}>重试</button>
        </div>
      )}

      <div className="card guide-card" style={{ marginBottom: 16 }}>
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <div className="card-title">🎯 今日引导</div>
          <button className="btn btn-sm" onClick={() => setGuideHidden(g => !g)}>{guideHidden ? '展开' : '收起'}</button>
        </div>
        {!guideHidden && (
          topItems.length === 0 ? (
            <div className="muted" style={{ padding: '6px 0' }}>今天还没有安排。先「快速添加」一件最重要的事，或让 AI 帮你整理今日清单。</div>
          ) : (
            <div className="row" style={{ alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
              <div style={{ flex: 1, minWidth: 280 }}>
                <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 6, color: 'var(--primary)' }}>
                  {guideLine}
                </div>
                <div style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.9 }}>
                  {topItems.map((it, i) => (
                    <div key={it.id} style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 520 }}>
                      {['①', '②', '③'][i]} {it.content}
                      {it.overdue ? '（待补）' : ''}
                      {it.time_range ? ` · ${it.time_range}` : ''}
                      {it.pomodoros > 0 ? ` · 🍅×${it.pomodoros}` : ''}
                    </div>
                  ))}
                </div>
              </div>
              <button className="btn btn-primary" onClick={startFocus}><Play size={14} strokeWidth={1.8} /> 开始干活</button>
            </div>
          )
        )}
      </div>

      <div className="grid grid-3" style={{ marginBottom: 16 }}>
        <div className="card" style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <Ring percent={data.stats.percent} />
          <div>
            <div style={{ fontWeight: 700 }}>今日完成度</div>
            <div className="muted">完成 {data.stats.done_count} · 待办 {data.stats.pending_count}{data.stats.carryover_pending_count > 0 && `（含顺延待补 ${data.stats.carryover_pending_count}）`}</div>
            <div className="muted">剩余精力 {Math.max(0, 100 - data.stats.percent)}%</div>
          </div>
        </div>
        <div className="card" style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          {data.stats.carryover_done_count + data.stats.carryover_pending_count > 0 ? (
            <Ring percent={data.stats.carryover_percent} />
          ) : (
            <div className="ring" style={{ width: 88, height: 88, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--card-2)', border: '1px dashed var(--text-3)' }}>
              <span style={{ fontSize: 30 }}>✅</span>
            </div>
          )}
          <div>
            <div style={{ fontWeight: 700 }}>顺延完成度</div>
            {data.stats.carryover_done_count + data.stats.carryover_pending_count > 0 ? (
              <>
                <div className="muted">补完 {data.stats.carryover_done_count} · 待补 {data.stats.carryover_pending_count}</div>
                <div className="muted">剩余欠账 {Math.round(100 - data.stats.carryover_percent)}%</div>
              </>
            ) : (
              <div className="muted">今日没有顺延欠账 🎉</div>
            )}
          </div>
        </div>
        <div className="card" style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <div style={{ flex: 1 }}>
            <div className="card-title">技能进度</div>
            {skills.length === 0 && <div className="muted">暂无技能，AI 整理会建议推进</div>}
            {skills.map(s => (
              <div key={s.id} className="row" style={{ marginBottom: 6, cursor: 'pointer' }} onClick={() => setEditSkill(s)}>
                <span style={{ width: 110, fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.name}</span>
                <div className="progress-bar" style={{ flex: 1 }}><div style={{ width: `${s.total_progress}%`, background: 'var(--primary)' }} /></div>
                <span className="muted" style={{ width: 36, textAlign: 'right', fontSize: 12 }}>{s.total_progress}%</span>
              </div>
            ))}
            <button className="btn btn-sm" onClick={e => { e.stopPropagation(); setEditSkill({ id: null, name: '', description: '', stages: [], goal_id: '' }) }}>+ 新技能</button>
          </div>
        </div>
      </div>

      <div className="row" style={{ gap: 6, marginBottom: 12 }}>
        {[['plan', '四象限'], ['list', '清单'], ['week', '未来7天'], ['done', '完成情况']].map(([k, l]) => (
          <button key={k} className={`btn ${view === k ? 'btn-primary' : ''}`} onClick={() => { userSwitched.current = true; setView(k); localStorage.setItem('wb_today_view', k) }}>{l}</button>
        ))}
        {isEvening && <span className="badge badge-warn">晚间模式：默认显示完成情况</span>}
      </div>

      {view === 'plan' && (
        <div className="grid-quadrant">
          {QUADRANTS.map(q => {
            const items = pendingView.filter(i => i.quadrant === q.key)
            const isCollapsed = collapsed[q.key]
            return (
              <div className="card" key={q.key} style={{ borderTop: `4px solid ${q.color}`, minHeight: 120, maxHeight: 420, overflowY: 'auto' }}>
                <div className="card-title" style={{ color: q.color, cursor: q.key === 'not_important_not' ? 'pointer' : 'default' }}
                  onClick={() => q.key === 'not_important_not' && setCollapsed(c => ({ ...c, [q.key]: !c[q.key] }))}>
                  {q.label} <span className="muted">{items.length}</span>
                  {q.key === 'not_important_not' && <span className="muted" style={{ fontSize: 11 }}>{isCollapsed ? '▶ 展开' : '▼ 收起'}</span>}
                </div>
                {!isCollapsed && items.length === 0 && <div className="muted" style={{ fontSize: 12, padding: '8px 0' }}>{QUADRANT_EMPTY[q.key]}</div>}
                {!isCollapsed && items.map(renderItem)}
                {isCollapsed && items.length > 0 && <div className="muted" style={{ fontSize: 12, padding: '4px 0' }}>已折叠 {items.length} 项</div>}
              </div>
            )
          })}
        </div>
      )}

      {view === 'list' && (
        <div className="card">
          <div className="card-title">今日清单（按时间排序）</div>
          {sorted.length === 0 && <div className="empty"><span className="empty-icon">📝</span>今天还没有安排，点「+ 添加事项」或让 AI 整理</div>}
          {sorted.map(renderItem)}
        </div>
      )}

      {view === 'week' && (
        <div className="card">
          <div className="card-title">未来 7 天到期（提前看节奏）</div>
          {upcoming.length === 0 && <div className="empty"><span className="empty-icon">📅</span>未来 7 天没有到期事项</div>}
          {[...new Set(upcoming.map(i => i.due_date || i.scheduled_date))].map(d => (
            <div key={d} style={{ marginBottom: 10 }}>
              <div className="muted" style={{ fontWeight: 700, fontSize: 13, marginBottom: 6 }}>📅 {d}</div>
              {upcoming.filter(i => (i.due_date || i.scheduled_date) === d).map(renderItem)}
            </div>
          ))}
        </div>
      )}

      {view === 'done' && (() => {
        // 完成明细按体系分组：今日完成 / 顺延补完 / 提前完成
        // 统计卡与明细同口径：已完成事项 = 今天实际完成的总数（含补完/提前），
        // 完成度仍按两套体系分开展示（今日 % + 顺延 %），不混账（见「五.17」双环设计）
        const doneToday = data.done.filter(i => i.scheduled_date === data.today)
        const doneCarry = data.done.filter(i => i.scheduled_date < data.today)
        const doneEarly = data.done.filter(i => i.scheduled_date > data.today)
        return (
          <>
            <div className="grid grid-4" style={{ marginBottom: 12 }}>
              <div className="card" style={{ textAlign: 'center' }}>
                <div className="stat-value" style={{ color: 'var(--success)' }}>{data.stats.percent}%</div>
                <div className="stat-label">今日完成度</div>
                <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>顺延完成度 {data.stats.carryover_percent}%</div>
              </div>
              <div className="card" style={{ textAlign: 'center' }}>
                <div className="stat-value">{data.done.length}</div>
                <div className="stat-label">已完成事项</div>
                <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>
                  今日 {doneToday.length} · 补完 {doneCarry.length}{doneEarly.length > 0 ? ` · 提前 ${doneEarly.length}` : ''}
                </div>
              </div>
              <div className="card" style={{ textAlign: 'center' }}>
                <div className="stat-value">{fmt(todayStats.total_seconds || 0)}</div>
                <div className="stat-label">今日投入</div>
              </div>
              <div className="card" style={{ textAlign: 'center' }}>
                <div className="stat-value">{todayStats.pomodoros || 0}</div>
                <div className="stat-label">番茄钟</div>
              </div>
            </div>
            <div className="card">
              <div className="card-title">今日完成明细（{data.done.length} 项）</div>
              {data.done.length === 0 && <div className="empty"><span className="empty-icon">✅</span>今天还没完成任何事项</div>}
              {doneToday.length > 0 && <div className="muted" style={{ fontWeight: 700, fontSize: 13, margin: '8px 0 4px' }}>✅ 今日完成</div>}
              {doneToday.map(renderItem)}
              {doneCarry.length > 0 && <div className="muted" style={{ fontWeight: 700, fontSize: 13, margin: '8px 0 4px' }}>🔁 顺延补完（昨日欠账）</div>}
              {doneCarry.map(renderItem)}
              {doneEarly.length > 0 && <div className="muted" style={{ fontWeight: 700, fontSize: 13, margin: '8px 0 4px' }}>⏩ 提前完成（计划在未来）</div>}
              {doneEarly.map(renderItem)}
            </div>
          </>
        )
      })()}

      <div className="card ai-suggest" style={{ marginTop: 16 }}>
        <div className="card-title">✨ AI 今日建议
          <button className="btn btn-sm" onClick={() => setAiCollapsed(c => !c)}>{aiCollapsed ? '展开' : '收起'}</button>
          {aiLoading ? (
            <button className="btn btn-sm btn-danger" onClick={cancelAi}><X size={14} strokeWidth={1.8} /> 取消</button>
          ) : (
            <button className="btn btn-sm btn-primary" onClick={genAi}>AI 整理今日清单</button>
          )}
          {!aiCollapsed && !aiAutoLand && aiItems.length > 0 && aiSelected.length > 0 && (
            <button className="btn btn-sm btn-primary" onClick={adoptSelected}>采纳选中（{aiSelected.length}）</button>
          )}
          {!aiCollapsed && !aiAutoLand && aiItems.length > 0 && <button className="btn btn-sm" onClick={() => adopt(null, true)}>全部采纳</button>}
          {!aiCollapsed && aiItems.length > 0 && <CopyBtn text={aiItems.map(x => x.content).join('\n')} />}
        </div>
        {!aiCollapsed && (
          <>
            <div className="row" style={{ gap: 6, marginTop: 8, marginBottom: 6 }}>
              <input
                className="input"
                style={{ flex: 1 }}
                placeholder="今日侧重（可选）：如 复现 DNANet / 跑 ROC 评估 / 写综述第三章…"
                value={focusText}
                onChange={e => setFocusText(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && !e.nativeEvent.isComposing) genAi() }}
              />
              <button className="btn btn-sm btn-primary" disabled={aiLoading} onClick={genAi}><Sparkles size={14} strokeWidth={1.8} /> 按侧重生成</button>
            </div>
            <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
              {aiAutoLand
                ? 'AI 已自动把任务加入今日清单（带时间段），可直接在清单里删改；点「按侧重生成」可重新生成。'
                : '输入今天的侧重点后，AI 会围绕它 + 当前阶段目标生成 5~7 条按优先级排序的建议。'}
            </div>
            {aiItems.length === 0 && !aiLoading && (
              <div className="muted" style={{ fontSize: 12 }}>
                {aiAutoLand
                  ? 'AI 会结合作战计划（当前阶段/本周目标/固定节奏）自动生成今日任务并加入上方清单，可删改。'
                  : 'AI 会综合今日侧重、任务、习惯、文献、技能进度与长期规划，给出一条条建议（可勾选多条采纳）。'}
              </div>
            )}
            {aiAutoLand && aiLandedCount > 0 && (
              <div className="ai-landed-note">✅ 本次已自动加入今日清单 {aiLandedCount} 项（在上方清单直接删改）</div>
            )}
            {aiItems.map((it, i) => (
              <div className={`d-item ${aiSelected.includes(i) ? 'ai-sel' : ''}`} key={i} style={{ background: 'var(--card-2)' }}>
                {!aiAutoLand && <input type="checkbox" checked={aiSelected.includes(i)} onChange={() => toggleAiSel(i)} />}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="d-item-title">
                    {it.content}
                    <span className="badge badge-info">AI建议</span>
                    <span className="badge badge-primary">{QUADRANTS.find(q => q.key === it.quadrant)?.label}</span>
                  </div>
                  <div className="muted ai-reason" style={{ fontSize: 12 }}>
                    🍅×{it.pomodoros} · 权重 {it.weight}%{it.time_range ? ` · ⏰ ${it.time_range}` : ''}{it.reason ? ` · ${it.reason}` : ''}
                  </div>
                </div>
                {aiAutoLand ? (
                  <span className="badge badge-success">已加入</span>
                ) : (
                  <>
                    <button className="btn btn-sm btn-primary" onClick={() => adopt(i)}>采纳</button>
                    <button className="btn btn-sm" onClick={() => setAiItems(list => list.filter((_, j) => j !== i))}>忽略</button>
                  </>
                )}
              </div>
            ))}
          </>
        )}
        {aiCollapsed && aiItems.length > 0 && <div className="muted" style={{ fontSize: 12 }}>已收起 {aiItems.length} 条建议</div>}
      </div>

      {showAdd && <ItemForm skills={skills} onClose={() => setShowAdd(false)} onSaved={load} />}
      {editItem && <ItemForm initial={editItem} skills={skills} onClose={() => setEditItem(null)} onSaved={load} />}
      {editSkill && <SkillEditor skill={editSkill.id ? editSkill : null} goals={goals} onClose={() => setEditSkill(null)} onSaved={load} />}

      {delayOpen && (
        <div className="modal-mask" onClick={() => setDelayOpen(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h3>⏩ 顺延到明天</h3>
            <div className="muted" style={{ marginBottom: 10 }}>选择要顺延的事项（今天不做，明天清单会自动出现它）：</div>
            {pending.length === 0 && <div className="empty"><span className="empty-icon">📝</span>今天没有待办事项可顺延</div>}
            {pending.map(i => (
              <label key={i.id} className="row" style={{ gap: 8, padding: '6px 0', borderBottom: '1px solid var(--border)', cursor: 'pointer', alignItems: 'center' }}>
                <input type="radio" name="delay-target" checked={delayTarget === i.id} onChange={() => setDelayTarget(i.id)} />
                <span style={{ flex: 1, minWidth: 0, fontSize: 13 }}>{i.content}</span>
                <span className="badge badge-gray">{i.kind_label}</span>
                {i.overdue && <span className="badge badge-warn">待补</span>}
              </label>
            ))}
            <div className="modal-actions">
              <button className="btn" onClick={() => setDelayOpen(false)}>取消</button>
              <button className="btn btn-primary" disabled={!delayTarget} onClick={delayToTomorrow}><Check size={14} strokeWidth={1.8} /> 顺延到明天</button>
            </div>
          </div>
        </div>
      )}

      {estOpen && (
        <div className="modal-mask" onClick={() => setEstOpen(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h3>✨ AI 预估时长</h3>
            {estPhase === 'pick' ? (
              <>
                <div className="muted" style={{ marginBottom: 10 }}>勾选要 AI 预估的事项（{estCands.length} 项未预估）：</div>
                <div className="row" style={{ gap: 8, marginBottom: 8 }}>
                  <button className="btn btn-sm" onClick={() => setEstSel(new Set(estCands.map(c => c.key)))}>全选</button>
                  <button className="btn btn-sm" onClick={() => setEstSel(new Set())}>全不选</button>
                </div>
                {estCands.map(c => (
                  <label key={c.key} className="row" style={{ gap: 8, padding: '6px 0', borderBottom: '1px solid var(--border)', cursor: 'pointer', alignItems: 'center' }}>
                    <input type="checkbox" checked={estSel.has(c.key)} onChange={() => setEstSel(s => { const n = new Set(s); if (n.has(c.key)) n.delete(c.key); else n.add(c.key); return n })} />
                    <span style={{ flex: 1, minWidth: 0, fontSize: 13 }}>{c.content}</span>
                    <span className="badge badge-gray">{c.kind_label}</span>
                  </label>
                ))}
                <div className="modal-actions">
                  <button className="btn" onClick={() => setEstOpen(false)}>取消</button>
                  <button className="btn btn-primary" disabled={estLoading || estSel.size === 0} onClick={runEstimate}>
                    {estLoading ? 'AI 估算中…' : `开始预估（${estSel.size} 项）`}
                  </button>
                </div>
              </>
            ) : (
              <>
                <div className="muted" style={{ marginBottom: 10 }}>AI 预估结果如下，可直接确认或修改后应用：</div>
                {estCands.filter(c => estResults[c.key]).map(c => (
                  <div key={c.key} className="row" style={{ gap: 8, padding: '6px 0', borderBottom: '1px solid var(--border)', alignItems: 'center' }}>
                    <span style={{ flex: 1, minWidth: 0, fontSize: 13 }}>{c.content}</span>
                    <input
                      type="number"
                      min="5"
                      className="input"
                      style={{ width: 90, height: 28 }}
                      value={estResults[c.key]}
                      onChange={e => setEstResults(m => ({ ...m, [c.key]: e.target.value === '' ? '' : Number(e.target.value) }))}
                    />
                    <span className="muted" style={{ fontSize: 12 }}>分钟</span>
                  </div>
                ))}
                <div className="modal-actions">
                  <button className="btn" onClick={() => setEstOpen(false)}><X size={14} strokeWidth={1.8} /> 取消（不应用）</button>
                  <button className="btn btn-primary" onClick={applyEstimate}><Check size={14} strokeWidth={1.8} /> 确认应用（{Object.keys(estResults).filter(k => estResults[k]).length} 项）</button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}