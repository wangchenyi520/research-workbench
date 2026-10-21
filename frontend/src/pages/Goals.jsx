import React, { useEffect, useRef, useState } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import api, { todayStr } from '../api'
import { useToast } from '../components/Toast'
import { Target, ClipboardList, Map, Rocket, Save, Sparkles, X } from 'lucide-react'

const LEVEL_LABEL = { annual: '年度', quarter: '季度', month: '月度', week: '周' }

function PField({ label, value, onChange, type = 'text', style }) {
  const inner = type === 'select' ? (
    <select className="select" value={value || 'quarter'} onChange={e => onChange(e.target.value)} style={{ padding: '6px 10px', fontSize: 12 }}>
      <option value="annual">年度</option>
      <option value="quarter">季度</option>
      <option value="month">月度</option>
      <option value="week">周</option>
    </select>
  ) : (
    <input type={type} className="input" value={value || ''} onChange={e => onChange(e.target.value)} style={{ padding: '6px 10px', fontSize: 12 }} />
  )
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12, color: 'var(--text-2)', flex: 1, minWidth: 110, ...style }}>
      {label}
      {inner}
    </label>
  )
}

function AiPlanner({ goals, onClose, onSaved }) {
  const toast = useToast()
  const [mode, setMode] = useState('generate')
  const [text, setText] = useState('')
  const [selected, setSelected] = useState([])
  const [plan, setPlan] = useState(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const aiCtrl = useRef(null)

  const toggleSel = id => setSelected(s => (s.includes(id) ? s.filter(x => x !== id) : [...s, id]))

  const generate = async () => {
    setError('')
    if (mode !== 'optimize' && !text.trim()) return toast('请输入内容', 'error')
    setLoading(true)
    aiCtrl.current = new AbortController()
    try {
      const payload = { mode, text }
      if (mode === 'optimize') payload.goal_ids = selected
      const r = await api.post('/ai/plan', payload, { signal: aiCtrl.current.signal })
      setPlan(r.data.plan)
    } catch (e) {
      if (e.code !== 'ERR_CANCELED') setError(e.response?.data?.detail || '生成失败')
    } finally {
      setLoading(false)
      aiCtrl.current = null
    }
  }

  const cancel = () => {
    aiCtrl.current?.abort()
    setLoading(false)
  }

  const save = async () => {
    setSaving(true)
    try {
      const r = await api.post('/ai/plan/save', { plan })
      const far = r.data.skipped_far_tasks || 0
      toast(
        `已创建 ${r.data.goals} 个目标、${r.data.tasks} 个任务、${r.data.milestones} 个里程碑` +
        (far ? `（${far} 个远期任务只保留在目标层级，未建为待办）` : '')
      )
      onSaved(); onClose()
    } catch (e) {
      toast(e.response?.data?.detail || '保存失败', 'error')
    } finally {
      setSaving(false)
    }
  }

  const setAnnual = (k, v) => setPlan(p => ({ ...p, annual: { ...(p.annual || {}), [k]: v } }))
  const setMilestone = (i, k, v) => setPlan(p => ({ ...p, milestones: (p.milestones || []).map((m, j) => (j === i ? { ...m, [k]: v } : m)) }))
  const delMilestone = i => setPlan(p => ({ ...p, milestones: (p.milestones || []).filter((_, j) => j !== i) }))
  const addMilestone = () => setPlan(p => ({ ...p, milestones: [...(p.milestones || []), { title: '', due_date: '' }] }))
  const setGoal = (i, k, v) => setPlan(p => ({ ...p, goals: (p.goals || []).map((g, j) => (j === i ? { ...g, [k]: v } : g)) }))
  const delGoal = i => setPlan(p => ({ ...p, goals: (p.goals || []).filter((_, j) => j !== i) }))
  const addGoal = () => setPlan(p => ({ ...p, goals: [...(p.goals || []), { level: 'quarter', title: '', parent: 'annual', period_start: '', period_end: '', tasks: [] }] }))
  const setTask = (i, ti, k, v) => setPlan(p => ({ ...p, goals: (p.goals || []).map((g, j) => (j === i ? { ...g, tasks: (g.tasks || []).map((t, m) => (m === ti ? { ...t, [k]: v } : t)) } : g)) }))
  const delTask = (i, ti) => setPlan(p => ({ ...p, goals: (p.goals || []).map((g, j) => (j === i ? { ...g, tasks: (g.tasks || []).filter((_, m) => m !== ti) } : g)) }))
  const addTask = i => setPlan(p => ({ ...p, goals: (p.goals || []).map((g, j) => (j === i ? { ...g, tasks: [...(g.tasks || []), { title: '', due_date: '', priority: 2 }] } : g)) }))

  return (
    <div className="modal-mask" onClick={onClose}>
      <div className="modal" style={{ maxWidth: 760 }} onClick={e => e.stopPropagation()}>
        <h3>✨ AI 规划助手</h3>

        <div className="row" style={{ gap: 6, marginBottom: 14 }}>
          {[
            ['generate', '一句话描述'],
            ['parse', '粘贴规划文本'],
            ['optimize', '优化已有'],
          ].map(([m, label]) => (
            <button
              key={m}
              className={`btn ${mode === m ? 'btn-primary' : ''}`}
              onClick={() => { setMode(m); setText(''); setSelected([]); setPlan(null); setError('') }}
            >
              {label}
            </button>
          ))}
        </div>

        {mode === 'optimize' ? (
          <div style={{ maxHeight: 140, overflowY: 'auto', border: '1px solid var(--border)', borderRadius: 8, padding: 10, marginBottom: 10 }}>
            <div className="muted" style={{ marginBottom: 8 }}>勾选需要 AI 优化的现有目标（不选则基于全部数据）：</div>
            {goals.length === 0 && <div className="muted">暂无现有目标，可留空直接优化（将结合文献/实验/习惯）</div>}
            {goals.map(g => (
              <label key={g.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 0', fontSize: 13 }}>
                <input type="checkbox" checked={selected.includes(g.id)} onChange={() => toggleSel(g.id)} />
                <span className="badge badge-primary">{LEVEL_LABEL[g.level]}</span>
                {g.title}
              </label>
            ))}
          </div>
        ) : (
          <textarea
            className="textarea"
            style={{ minHeight: 90, marginBottom: 10 }}
            placeholder={mode === 'generate' ? '例如：2029 前发一篇红外小目标论文并毕业' : '粘贴你的规划文字（纯文字段落），AI 会识别填入各层级'}
            value={text}
            onChange={e => setText(e.target.value)}
          />
        )}
        {mode === 'optimize' && (
          <textarea
            className="textarea"
            style={{ minHeight: 60 }}
            placeholder="补充说明（可选）：如毕业时间、研究方向、重点事项……"
            value={text}
            onChange={e => setText(e.target.value)}
          />
        )}

        <div className="row" style={{ justifyContent: 'flex-end', marginTop: 12 }}>
          {loading ? (
            <button className="btn btn-danger" onClick={cancel}><X size={14} strokeWidth={1.8} /> 取消生成</button>
          ) : (
            <button className="btn btn-primary" onClick={generate}><Rocket size={14} strokeWidth={1.8} /> 生成规划</button>
          )}
        </div>
        {error && <div className="muted" style={{ color: 'var(--danger)', marginTop: 8 }}>{error}</div>}

        {plan && (
          <div style={{ marginTop: 18, borderTop: '1px solid var(--border)', paddingTop: 14 }}>
            <div className="row" style={{ justifyContent: 'space-between', marginBottom: 10 }}>
              <b>规划预览（可直接编辑）</b>
              <span className="muted" style={{ fontSize: 12 }}>层级 · 标题 · 周期/DDL · 任务优先级</span>
            </div>

            <div className="card" style={{ padding: 12, borderTop: '4px solid var(--primary)', marginBottom: 12 }}>
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <b>🎯 年度目标</b>
                <span className="badge badge-primary">年度</span>
              </div>
              <div className="row" style={{ marginTop: 8 }}>
                <PField label="标题" value={plan.annual?.title} onChange={v => setAnnual('title', v)} style={{ flex: 2 }} />
                <PField label="截止" type="date" value={plan.annual?.deadline} onChange={v => setAnnual('deadline', v)} />
              </div>
              <PField label="描述" value={plan.annual?.description} onChange={v => setAnnual('description', v)} style={{ marginTop: 8 }} />
            </div>

            {plan.milestones && (
              <div style={{ marginBottom: 12 }}>
                <div className="row" style={{ justifyContent: 'space-between', marginBottom: 6 }}>
                  <b>🏁 里程碑</b>
                  <button className="btn btn-sm" onClick={addMilestone}>+ 添加</button>
                </div>
                {(plan.milestones || []).map((m, i) => (
                  <div className="row" key={i} style={{ marginBottom: 6 }}>
                    <PField label="里程碑" value={m.title} onChange={v => setMilestone(i, 'title', v)} />
                    <PField label="日期" type="date" value={m.due_date} onChange={v => setMilestone(i, 'due_date', v)} />
                    <button className="btn btn-sm btn-danger" style={{ marginTop: 16 }} onClick={() => delMilestone(i)}>删除</button>
                  </div>
                ))}
              </div>
            )}

            {plan.goals && (
              <div>
                <div className="row" style={{ justifyContent: 'space-between', marginBottom: 6 }}>
                  <b>🗂 目标金字塔</b>
                  <button className="btn btn-sm" onClick={addGoal}>+ 添加目标</button>
                </div>
                {(plan.goals || []).map((g, i) => (
                  <div key={i} className="card" style={{ padding: 12, marginBottom: 10, borderLeft: '4px solid var(--info)' }}>
                    <div className="row" style={{ justifyContent: 'space-between', marginBottom: 8 }}>
                      <span className="badge badge-info">{LEVEL_LABEL[g.level] || g.level}</span>
                      <button className="btn btn-sm btn-danger" onClick={() => delGoal(i)}>删除该目标</button>
                    </div>
                    <div className="row" style={{ marginBottom: 8 }}>
                      <PField label="层级" type="select" value={g.level} onChange={v => setGoal(i, 'level', v)} />
                      <PField label="标题" value={g.title} onChange={v => setGoal(i, 'title', v)} style={{ flex: 2 }} />
                    </div>
                    <div className="row" style={{ marginBottom: 8 }}>
                      <PField label="父级标题" value={g.parent} onChange={v => setGoal(i, 'parent', v)} />
                      <PField label="开始" type="date" value={g.period_start} onChange={v => setGoal(i, 'period_start', v)} />
                      <PField label="结束" type="date" value={g.period_end} onChange={v => setGoal(i, 'period_end', v)} />
                    </div>
                    <div className="muted" style={{ fontSize: 12, marginBottom: 4 }}>任务：</div>
                    {(g.tasks || []).map((t, ti) => (
                      <div className="row" key={ti} style={{ marginBottom: 6 }}>
                        <PField label="任务标题" value={t.title} onChange={v => setTask(i, ti, 'title', v)} style={{ flex: 2 }} />
                        <PField label="DDL" type="date" value={t.due_date} onChange={v => setTask(i, ti, 'due_date', v)} />
                        <PField label="优先级" type="number" value={t.priority} onChange={v => setTask(i, ti, 'priority', v)} />
                        <button className="btn btn-sm btn-danger" style={{ marginTop: 16 }} onClick={() => delTask(i, ti)}>删</button>
                      </div>
                    ))}
                    <button className="btn btn-sm" onClick={() => addTask(i)}>+ 添加任务</button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        <div className="modal-actions">
          <button className="btn" onClick={onClose}>关闭</button>
          {plan && (
            <button className="btn btn-primary" onClick={save} disabled={saving}>
              {saving ? '保存中…' : <><Save size={14} strokeWidth={1.8} /> 批量保存</>}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

function GoalForm({ initial, parentId, onClose, onSaved }) {
  const [form, setForm] = useState({
    title: initial?.title || '',
    description: initial?.description || '',
    level: initial?.level || 'quarter',
    period_start: initial?.period_start || '',
    period_end: initial?.period_end || '',
    parent_id: parentId || initial?.parent_id || '',
    progress: initial?.progress || 0,
  })
  const toast = useToast()
  const set = k => v => setForm(f => ({ ...f, [k]: v }))
  const submit = async () => {
    if (!form.title.trim()) return toast('请输入目标标题', 'error')
    const payload = { ...form, period_start: form.period_start || null, period_end: form.period_end || null, parent_id: form.parent_id || null }
    try {
      if (initial?.id) await api.put(`/goals/${initial.id}`, payload)
      else await api.post('/goals', payload)
      onSaved(); onClose()
    } catch (e) { toast('保存失败', 'error') }
  }
  return (
    <div className="modal-mask" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <h3>{initial ? '编辑目标' : '新建目标'}</h3>
        <label className="label">标题 *</label>
        <input className="input" value={form.title} onChange={e => set('title')(e.target.value)} />
        <label className="label">描述</label>
        <textarea className="textarea" value={form.description} onChange={e => set('description')(e.target.value)} />
        <label className="label">层级</label>
        <select className="select" value={form.level} onChange={e => set('level')(e.target.value)}>
          <option value="annual">年度目标</option>
          <option value="quarter">季度目标</option>
          <option value="month">月度目标</option>
          <option value="week">周目标</option>
        </select>
        <div className="row">
          <div style={{ flex: 1 }}><label className="label">开始</label><input type="date" className="input" value={form.period_start} onChange={e => set('period_start')(e.target.value)} /></div>
          <div style={{ flex: 1 }}><label className="label">结束</label><input type="date" className="input" value={form.period_end} onChange={e => set('period_end')(e.target.value)} /></div>
        </div>
        <div className="modal-actions">
          <button className="btn" onClick={onClose}>取消</button>
          <button className="btn btn-primary" onClick={submit}>保存</button>
        </div>
      </div>
    </div>
  )
}

function GoalBlock({ goal, children, onChanged, flash, nested }) {
  const [showForm, setShowForm] = useState(false)
  const [edit, setEdit] = useState(false)
  const toast = useToast()
  const del = async () => {
    if (!confirm(`删除目标「${goal.title}」？其子目标与关联将被删除`)) return
    try {
      await api.delete(`/goals/${goal.id}`)
      toast('已删除'); onChanged()
    } catch (e) { toast('删除失败', 'error') }
  }
  const recalc = async () => { await api.post(`/goals/${goal.id}/progress`); onChanged() }
  const toggle = async () => { await api.put(`/goals/${goal.id}`, { status: goal.status === 'done' ? 'active' : 'done' }); onChanged() }
  return (
    <div className={`card ${flash ? 'flash' : ''} ${nested ? 'goal-child-card' : ''}`} data-goal-id={goal.id} style={{ borderTop: '4px solid var(--primary)' }}>
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 700, fontSize: 15, textDecoration: goal.status === 'done' ? 'line-through' : 'none' }}>
            {goal.title} <span className="badge badge-primary">{LEVEL_LABEL[goal.level]}</span>
          </div>
          {goal.description && <div className="muted">{goal.description}</div>}
          <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 8 }}>
            <div className="progress-bar" style={{ flex: 1 }}><div style={{ width: `${Math.min(goal.progress, 100)}%` }} /></div>
            <span className="muted">{goal.progress}%</span>
          </div>
        </div>
        <div className="row" style={{ gap: 6 }}>
          <button className="btn btn-sm" onClick={recalc}>同步进度</button>
          <button className="btn btn-sm" onClick={toggle}>{goal.status === 'done' ? '恢复' : '完成'}</button>
          <button className="btn btn-sm" onClick={() => setEdit(true)}>编辑</button>
          <button className="btn btn-sm btn-danger" onClick={del}>删除</button>
        </div>
      </div>
      <div className="row" style={{ marginTop: 10, gap: 6 }}>
        <button className="btn btn-sm" onClick={() => setShowForm(true)}>+ 子目标</button>
      </div>
      {children}
      {showForm && <GoalForm parentId={goal.id} onClose={() => setShowForm(false)} onSaved={onChanged} />}
      {edit && <GoalForm initial={goal} onClose={() => setEdit(false)} onSaved={onChanged} />}
    </div>
  )
}

function MilestoneManager() {
  const [list, setList] = useState([])
  const [form, setForm] = useState({ title: '', description: '', due_date: '', color: '#7c6cf0' })
  const [showForm, setShowForm] = useState(false)
  const toast = useToast()
  const load = () => {
    api.get('/goals/milestones').then(r => setList(r.data))
  }
  useEffect(load, [])

  const add = async () => {
    if (!form.title.trim()) return toast('请输入里程碑标题', 'error')
    await api.post('/goals/milestones', { ...form, due_date: form.due_date || null })
    setForm({ title: '', description: '', due_date: '', color: '#7c6cf0' })
    setShowForm(false)
    toast('已添加'); load()
  }
  const toggle = async m => { await api.put(`/goals/milestones/${m.id}`, { completed: !m.completed }); load() }
  const del = async m => {
    if (!confirm(`删除里程碑「${m.title}」？`)) return
    try {
      await api.delete(`/goals/milestones/${m.id}`)
      toast('已删除'); load()
    } catch (e) { toast('删除失败', 'error') }
  }

  return (
    <div className="card">
      <div className="card-title">毕业里程碑
        <button className="btn btn-sm btn-primary" onClick={() => setShowForm(s => !s)}>+ 添加</button>
      </div>
      {showForm && (
        <div style={{ marginBottom: 12 }}>
          <input className="input" placeholder="里程碑标题" value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))} />
          <div className="row" style={{ marginTop: 8 }}>
            <input type="date" className="input" style={{ flex: 1 }} value={form.due_date} onChange={e => setForm(f => ({ ...f, due_date: e.target.value }))} />
            <input type="color" value={form.color} onChange={e => setForm(f => ({ ...f, color: e.target.value }))} style={{ width: 44, height: 36, border: 'none', background: 'transparent' }} />
            <button className="btn btn-primary" onClick={add}>保存</button>
          </div>
        </div>
      )}
      {list.length === 0 && <div className="empty"><span className="empty-icon">🏁</span>暂无里程碑，建议添加「开题报告 / 中期检查 / 论文初稿 / 毕业答辩」</div>}
      <div className="timeline">
        {list.map(m => (
          <div className="timeline-item" key={m.id}>
            <div className="timeline-dot" onClick={() => toggle(m)} style={{ cursor: 'pointer', background: m.completed ? 'var(--success)' : m.color }} />
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 600, textDecoration: m.completed ? 'line-through' : 'none' }}>{m.title}</div>
              <div className="muted">
                {m.due_date ? `${m.due_date} · ` : ''}
                {m.completed ? '已完成' : m.days_left !== null ? (m.days_left < 0 ? `已过期 ${-m.days_left} 天` : `还剩 ${m.days_left} 天`) : ''}
              </div>
              <button className="btn btn-sm btn-danger" onClick={() => del(m)} style={{ marginTop: 4 }}>删除</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// 规划路线图：纵向流程图（终点 → 阶段 → 现在 → 未来），当前位置高亮 + 升级条件门
function RoadmapView({ goals, milestones, tasks, skills }) {
  const navigate = useNavigate()
  const today = todayStr()
  const annual = goals.find(g => g.level === 'annual')
  const kidsOf = pid => goals.filter(g => g.parent_id === pid)
  const stages = goals
    .filter(g => g.level !== 'annual' && (g.period_start || g.period_end))
    .sort((a, b) => (a.period_start || a.period_end || '').localeCompare(b.period_start || b.period_end || ''))
  const unplanned = goals.filter(g => g.level !== 'annual' && !g.period_start && !g.period_end)
  const contains = g => (!g.period_start || g.period_start <= today) && (!g.period_end || g.period_end >= today)
  const current = [...stages].filter(contains).sort((a, b) => (b.period_start || '').localeCompare(a.period_start || ''))[0] || null
  const [openId, setOpenId] = useState('auto')
  const expandedId = openId === 'auto' ? current?.id : openId

  const subtreeTasks = gid => {
    const out = []
    const stack = [gid]
    while (stack.length) {
      const id = stack.pop()
      tasks.filter(t => t.goal_id === id).forEach(t => out.push(t))
      kidsOf(id).forEach(c => stack.push(c.id))
    }
    return out
  }
  const taskStats = gid => {
    const list = subtreeTasks(gid)
    return { total: list.length, done: list.filter(t => t.status === 'done').length, list }
  }
  const range = g => {
    if (g.period_start && g.period_end) return `${g.period_start.replace(/-/g, '.')} - ${g.period_end.replace(/-/g, '.')}`
    if (g.period_start) return `${g.period_start} 起`
    if (g.period_end) return `截止 ${g.period_end}`
    return ''
  }
  const daysLeft = annual?.period_end ? Math.ceil((new Date(annual.period_end) - new Date(today)) / 86400000) : null
  const nextStage = current ? stages.find(s => (s.period_start || '') > (current.period_start || '')) : null
  const sortedMs = [...milestones].sort((a, b) => (a.due_date || '').localeCompare(b.due_date || ''))
  const nextMs = sortedMs.find(m => !m.completed && m.due_date && m.due_date >= today)

  const nodeClass = g => {
    if (g.status === 'done') return 'past'
    // 结束于今天且不是主阶段（被更新的阶段接棒）→ 视为收尾/已结束，保证「你在这里」唯一
    if (g.period_end && (g.period_end < today || (g.period_end === today && g.id !== current?.id))) return 'past'
    if (contains(g)) return 'current'
    return 'future'
  }
  const badgeOf = (g, cls) => {
    if (g.status === 'done') return <span className="badge badge-success">已完成</span>
    if (cls === 'past') return <span className="badge badge-gray">已结束</span>
    if (cls === 'current') return <span className="badge badge-primary">进行中</span>
    return <span className="badge badge-gray">未开始</span>
  }

  const renderDetail = g => {
    const st = taskStats(g.id)
    const stageSkills = skills.filter(s => s.goal_id === g.id)
    const pending = st.list.filter(t => t.status !== 'done')
    const doneList = st.list.filter(t => t.status === 'done')
    const isCurrent = g.id === current?.id
    const gateEnd = nextStage?.period_start || g.period_end || ''
    const ms = milestones.filter(m => {
      if (!m.due_date) return false
      if (g.period_start && m.due_date < g.period_start) return false
      if (gateEnd && m.due_date > gateEnd) return false
      return true
    })
    const unfSkills = stageSkills.filter(s => (s.total_progress || 0) < 100)
    const unfMs = ms.filter(m => !m.completed)
    const gateTotal = pending.length + unfSkills.length + unfMs.length
    return (
      <div className="rm-detail" onClick={e => e.stopPropagation()}>
        <div>
          <div className="rm-sec-title">本阶段任务（{st.done}/{st.total} 完成）</div>
          {st.total === 0 && <div className="muted" style={{ fontSize: 12 }}>暂无关联任务（远期内容保留在目标层级）</div>}
          {pending.map(t => (
            <div key={t.id} className="rm-task" onClick={() => navigate(`/tasks?highlight=${t.id}`)} title="点击到任务页查看">
              <span className="rm-task-dot" />
              <span>{t.title}</span>
              {t.due_date && <span className="muted" style={{ fontSize: 11, marginLeft: 'auto' }}>DDL {t.due_date.slice(5)}</span>}
            </div>
          ))}
          {doneList.map(t => (
            <div key={t.id} className="rm-task done"><span>✓</span><span>{t.title}</span></div>
          ))}
        </div>
        {stageSkills.length > 0 && (
          <div>
            <div className="rm-sec-title">本阶段技能</div>
            {stageSkills.map(s => (
              <div key={s.id} className="rm-skill">
                <span style={{ minWidth: 140 }}>{s.name}</span>
                <div className="progress-bar"><div style={{ width: `${s.total_progress || 0}%` }} /></div>
                <span className="muted" style={{ minWidth: 36, textAlign: 'right' }}>{s.total_progress || 0}%</span>
              </div>
            ))}
          </div>
        )}
        {ms.length > 0 && (
          <div>
            <div className="rm-sec-title">本阶段里程碑</div>
            {ms.map(m => (
              <div key={m.id} className="rm-ms-row">
                <span>{m.completed ? '✓' : '○'}</span>
                <span style={{ textDecoration: m.completed ? 'line-through' : 'none' }}>{m.title}</span>
                <span className="muted" style={{ fontSize: 11, marginLeft: 'auto' }}>{m.due_date}</span>
              </div>
            ))}
          </div>
        )}
        {isCurrent && (
          <div className="rm-gate">
            <div className="rm-gate-title">🔓 升级门 · 进入「{nextStage ? nextStage.title : '终点'}」需要集齐</div>
            <div className="rm-cond">
              <span className="rm-cond-k">任务</span>
              {pending.length === 0 ? <span>✅ 已全部完成（{st.total} 项）</span> : <span>还差 {pending.length} 项／共 {st.total} 项</span>}
            </div>
            {stageSkills.length > 0 && (
              <div className="rm-cond">
                <span className="rm-cond-k">技能</span>
                {unfSkills.length === 0 ? <span>✅ 已就绪</span> : <span>{unfSkills.map(s => `${s.name} ${s.total_progress || 0}%`).join('、')}</span>}
              </div>
            )}
            {ms.length > 0 && (
              <div className="rm-cond">
                <span className="rm-cond-k">里程碑</span>
                {unfMs.length === 0 ? <span>✅ 已达成</span> : <span>{unfMs.map(m => `${m.title}（${m.due_date}）`).join('、')}</span>}
              </div>
            )}
            <div className="rm-cond">
              <span className="rm-cond-k">时间</span>
              <span>{g.period_end
                ? (today > g.period_end ? `已超过阶段结束时间 ${g.period_end}` : `到 ${g.period_end} 自动推进`)
                : '未设置结束时间'}</span>
            </div>
            {gateTotal === 0
              ? <div className="rm-gate-ready">✅ 条件已集齐，可以进入下一阶段</div>
              : <div className="rm-cond-hint">集齐以上条件（或到达阶段结束时间）即可进入下一阶段</div>}
          </div>
        )}
      </div>
    )
  }

  const renderNode = (g, { dim } = {}) => {
    const cls = dim ? 'future' : nodeClass(g)
    const st = taskStats(g.id)
    const pct = g.progress || 0
    const expanded = expandedId === g.id
    return (
      <div key={g.id} className={`rm-node ${cls}`} data-goal-id={g.id}>
        <div className="rm-rail"><span className="rm-dot" /><span className="rm-line" /></div>
        <div className="rm-body">
          <div className="rm-card" onClick={() => setOpenId(prev => {
            const cur = prev === 'auto' ? current?.id : prev
            return cur === g.id ? null : g.id
          })}>
            <div className="rm-head">
              <span className="rm-title">{g.title}</span>
              {badgeOf(g, cls)}
              {g.id === current?.id && <span className="badge badge-primary">📍 你在这里</span>}
              <span className="muted" style={{ fontSize: 11, marginLeft: 'auto' }}>{expanded ? '收起 ▴' : '展开 ▾'}</span>
            </div>
            <div className="rm-meta">{range(g)}{st.total > 0 ? ` · 任务 ${st.done}/${st.total}` : ''}</div>
            <div className="rm-bar">
              <div className="progress-bar"><div style={{ width: `${pct}%` }} /></div>
              <span className="rm-pct">{pct}%</span>
            </div>
            {expanded && renderDetail(g)}
          </div>
        </div>
      </div>
    )
  }

  if (goals.length === 0) {
    return <div className="card empty">还没有目标。建议从「年度目标」开始：我的毕业目标是什么？</div>
  }

  return (
    <div className="roadmap">
      {annual && (
        <div className="rm-dest">
          <Target size={20} strokeWidth={1.9} style={{ color: 'var(--primary)', flexShrink: 0 }} />
          <div style={{ minWidth: 0 }}>
            <div className="rm-dest-title">{annual.title}</div>
            <div className="rm-dest-meta">
              终极目标{annual.period_end ? ` · 截止 ${annual.period_end}` : ''}{daysLeft !== null ? ` · 还剩 ${daysLeft} 天` : ''}
            </div>
          </div>
          <div className="rm-dest-progress">
            <div className="rm-bar">
              <div className="progress-bar"><div style={{ width: `${annual.progress || 0}%` }} /></div>
              <span className="rm-pct">{annual.progress || 0}%</span>
            </div>
          </div>
        </div>
      )}

      {sortedMs.length > 0 && (
        <div className="rm-milestones">
          <span className="muted" style={{ fontSize: 12 }}>🏁 里程碑：</span>
          {sortedMs.map(m => (
            <span
              key={m.id}
              className={`rm-ms ${m.completed ? 'done' : ''} ${nextMs && m.id === nextMs.id ? 'next' : ''}`}
            >
              {m.completed ? '✓ ' : '🎯 '}{m.title}{m.due_date ? ` · ${m.due_date}` : ''}
            </span>
          ))}
        </div>
      )}

      {stages.map(g => renderNode(g))}
      {unplanned.map(g => renderNode(g, { dim: true }))}
      {stages.length === 0 && unplanned.length === 0 && (
        <div className="card empty">目标缺少周期信息，无法绘制路线图；可在「列表」视图给目标补充开始/结束时间。</div>
      )}
    </div>
  )
}

export default function Goals() {
  const [goals, setGoals] = useState([])
  const [milestones, setMilestones] = useState([])
  const [tasks, setTasks] = useState([])
  const [skills, setSkills] = useState([])
  const [view, setView] = useState('roadmap') // roadmap / list
  const [showForm, setShowForm] = useState(false)
  const [showAi, setShowAi] = useState(false)
  const [flashId, setFlashId] = useState(null)
  const [params] = useSearchParams()
  const toast = useToast()
  const load = () => {
    api.get('/goals').then(r => setGoals(r.data)).catch(() => toast('加载失败', 'error'))
    api.get('/goals/milestones').then(r => setMilestones(r.data)).catch(() => {})
    api.get('/tasks').then(r => setTasks(r.data)).catch(() => {})
    api.get('/skills').then(r => setSkills(r.data)).catch(() => {})
  }
  useEffect(load, [])

  // 搜索结果深链：/goals?highlight=id 时滚动定位到该目标并高亮
  useEffect(() => {
    const h = params.get('highlight')
    if (h) {
      const id = Number(h)
      setFlashId(id)
      const t1 = setTimeout(() => {
        const el = document.querySelector(`[data-goal-id="${id}"]`)
        el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      }, 300)
      const t2 = setTimeout(() => setFlashId(null), 4000)
      return () => { clearTimeout(t1); clearTimeout(t2) }
    }
  }, [params])

  const kids = pid => goals.filter(g => g.parent_id === pid)

  const renderGoalTree = g => (
    <div key={g.id} style={{ marginBottom: 10 }}>
      <GoalBlock goal={g} onChanged={load} flash={flashId === g.id} nested={!!g.parent_id}>
        {kids(g.id).length > 0 && (
          <div className="goal-children">
            {kids(g.id).map(c => renderGoalTree(c))}
          </div>
        )}
      </GoalBlock>
    </div>
  )

  return (
    <div>
      <div className="page-header">
        <h1><span className="page-icon"><Target size={22} strokeWidth={1.75} /></span>规划</h1>
        <div className="row">
          <button className={`btn ${view === 'roadmap' ? 'btn-primary' : ''}`} onClick={() => setView('roadmap')}><Map size={14} strokeWidth={1.8} /> 路线图</button>
          <button className={`btn ${view === 'list' ? 'btn-primary' : ''}`} onClick={() => setView('list')}><ClipboardList size={14} strokeWidth={1.8} /> 列表</button>
          <button className="btn btn-primary" onClick={() => setShowAi(true)}><Sparkles size={14} strokeWidth={1.8} /> AI 规划助手</button>
          <button className="btn btn-primary" onClick={() => setShowForm(true)}>+ 新建目标</button>
        </div>
      </div>

      {view === 'roadmap' ? (
        <RoadmapView goals={goals} milestones={milestones} tasks={tasks} skills={skills} />
      ) : (
      <div className="grid grid-2">
        <div>
          <h2 style={{ fontSize: 16, marginBottom: 12 }}>目标金字塔（年度 → 季度 → 月 → 周）</h2>
          {goals.filter(g => !g.parent_id).map(g => renderGoalTree(g))}
          {goals.length === 0 && <div className="card empty">还没有目标。建议从「年度目标」开始：我的毕业目标是什么？</div>}
        </div>
        <MilestoneManager />
      </div>
      )}

      {showForm && <GoalForm onClose={() => setShowForm(false)} onSaved={load} />}
      {showAi && <AiPlanner goals={goals} onClose={() => setShowAi(false)} onSaved={load} />}
    </div>
  )
}
