import React, { useEffect, useRef, useState } from 'react'
import api, { todayStr } from '../api'
import { useToast } from '../components/Toast'
import CopyBtn from '../components/CopyBtn'
import DoubleConfirm from '../components/DoubleConfirm'
import { RotateCcw, Check, CornerDownRight, RefreshCw, Save, FileText } from 'lucide-react'

const FIELDS = [
  { key: 'done', label: '本周完成', ph: '这周完成了哪些事情？' },
  { key: 'todo', label: '下周计划', ph: '下周打算做什么？' },
  { key: 'progress', label: '论文/科研进展', ph: '论文进度、实验进展、遇到的问题' },
  { key: 'problems', label: '问题与卡点', ph: '遇到了什么困难？' },
  { key: 'improvements', label: '改进措施', ph: '下周要怎么改进？' },
]

export default function Review() {
  const [review, setReview] = useState(null)
  const [history, setHistory] = useState([])
  const [weekStats, setWeekStats] = useState(null)
  const [aiAdvice, setAiAdvice] = useState('')
  const [aiLoading, setAiLoading] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [expanded, setExpanded] = useState({}) // C21：历史复盘展开状态
  const [focusDays, setFocusDays] = useState({})
  const [exportOpen, setExportOpen] = useState(false)
  const [exportData, setExportData] = useState(null)
  const [exporting, setExporting] = useState(false)
  const toast = useToast()
  // C10：textarea 输入防抖，避免每键 PUT
  const saveTimers = useRef({})
  const contentRef = useRef(null)

  // 近 7 天投入（专注周报）
  const days7 = Array.from({ length: 7 }, (_, i) => {
    const d = new Date()
    d.setDate(d.getDate() - (6 - i))
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
    return [key, focusDays[key] || 0]
  })
  const maxFocus = Math.max(...days7.map(([, s]) => s), 0)
  const bestDay = maxFocus > 0 ? days7.find(([, s]) => s === maxFocus)?.[0]?.slice(5) : '—'

  const saveFocusNote = async () => {
    if (!weekStats) return
    const lines = [
      `# 专注周报 ${review.week_start} ~ ${review.week_end}`, '',
      '## 投入分布', '',
      ...days7.map(([d, s]) => `- ${d}：${fmt(s)}`), '',
      `## 汇总`, '',
      `- 本周投入 ${fmt(weekStats.total_seconds)} · 番茄 ${weekStats.pomodoros} 个`,
      `- 最投入的一天：${bestDay}（${fmt(maxFocus)}）`,
      `- 完成任务 ${weekStats.done_count} 项 · 打卡 ${weekStats.checkin_days} 天`, '',
    ]
    try {
      await api.post('/notes', { title: `专注周报 ${review.week_start}`, content: lines.join('\n'), folder: '复盘', tags: '复盘,专注' })
      toast('已存为笔记（文件夹「复盘」）')
    } catch (e) { toast('保存失败', 'error') }
  }

  const saveReviewNote = async () => {
    try {
      const lines = [
        `# 周复盘 ${review.week_start} ~ ${review.week_end}`, '',
        ...FIELDS.map(f => `## ${f.label}\n${review.content?.[f.key] || '（未填写）'}`), '',
      ]
      if (aiAdvice) lines.push('## ✨ AI 点评', aiAdvice, '')
      await api.post('/notes', { title: `周复盘 ${review.week_start}`, content: lines.join('\n'), folder: '复盘', tags: '复盘' })
      toast('已存为笔记（文件夹「复盘」）')
    } catch (e) { toast('保存失败', 'error') }
  }

  const openExport = async () => {
    try {
      const r = await api.post('/self-analysis/export-review', {})
      setExportData(r.data)
      setExportOpen(true)
    } catch (e) {
      toast(e.response?.data?.detail || '导出失败', 'error')
    }
  }

  const doExport = async () => {
    setExporting(true)
    try {
      const r = await api.post('/self-analysis/export-review', { apply: true })
      toast(`已导出到 Self_analysis/${r.data.filename}${r.data.backup ? '（原文件已备份）' : ''}`)
      setExportOpen(false)
      setExportData(null)
    } catch (e) {
      toast(e.response?.data?.detail || '导出失败', 'error')
    } finally {
      setExporting(false)
    }
  }

  const fmt = sec => {
    if (!sec) return '0 分钟'
    const h = Math.floor(sec / 3600)
    const m = Math.floor((sec % 3600) / 60)
    return h > 0 ? `${h}小时${m}分` : `${m}分钟`
  }

  const load = () => {
    setLoading(true)
    setError('')
    api.get('/reviews/current')
      .then(r => { setReview(r.data); contentRef.current = r.data.content; setLoading(false) })
      .catch(() => { setError('加载周复盘失败，请重试'); setLoading(false) })
    api.get('/reviews').then(r => setHistory(r.data)).catch(() => {})
    api.get('/stats/week').then(r => setWeekStats(r.data)).catch(() => {})
    api.get('/tasks/stats/heatmap?days=7').then(r => setFocusDays(r.data.data || {})).catch(() => {})
  }
  useEffect(load, [])

  // 进页自动生成 AI 点评（本周有数据且尚未生成过，每次进入页面最多一次）
  const aiFetchedRef = useRef(false)
  useEffect(() => {
    if (weekStats && !aiAdvice && !aiLoading && !aiFetchedRef.current) {
      const ws = weekStats || {}
      if ((ws.done_count || 0) > 0 || (ws.total_seconds || 0) > 0) {
        aiFetchedRef.current = true
        getAiAdvice()
      }
    }
  }, [weekStats])

  const update = async (key, val) => {
    if (!review) return
    // C10：本地立即更新 + 400ms 防抖保存（乱序风险：每次用 contentRef 最新内容）
    const content = { ...(contentRef.current || review.content || {}), [key]: val }
    contentRef.current = content
    setReview(r => ({ ...r, content }))
    clearTimeout(saveTimers.current[key])
    saveTimers.current[key] = setTimeout(async () => {
      try {
        await api.put(`/reviews/${review.id}`, { content })
      } catch (e) { toast('保存失败', 'error') }
    }, 400)
  }

  const toggleComplete = async () => {
    await api.put(`/reviews/${review.id}`, { completed: !review.completed })
    toast(review.completed ? '已取消完成' : '本周复盘完成，真棒！')
    load()
  }

  // 本周周目标未完成任务 → 一键带入「下周计划」（C14：已带入的行不重复追加）
  const importWeekGoals = async () => {
    const undone = (weekStats?.week_goals || [])
      .filter(g => g.undone_tasks && g.undone_tasks.length)
      .map(g => `【${g.title}】` + g.undone_tasks.map(t => `${t.title}${t.due_date ? `（截止 ${t.due_date}）` : ''}`).join('、'))
    if (!undone.length) return toast('本周周目标暂无未完成任务', 'error')
    const old = contentRef.current || review.content || {}
    const todoLines = (old.todo || '').split('\n').map(l => l.trim()).filter(Boolean)
    const fresh = undone.filter(l => !todoLines.includes(l))
    if (!fresh.length) return toast('未完成任务已在「下周计划」中')
    const content = { ...old, todo: [...todoLines, ...fresh].join('\n') }
    contentRef.current = content
    setReview(r => ({ ...r, content }))
    try {
      await api.put(`/reviews/${review.id}`, { content })
      toast(`已把 ${fresh.length} 项未完成任务带入「下周计划」`)
    } catch (e) { toast('保存失败', 'error') }
  }

  const getAiAdvice = async () => {
    if (aiLoading) return
    setAiLoading(true)
    setAiAdvice('')
    try {
      const ws = weekStats || {}
      const week = [
        `本周完成 ${ws.done_count || 0} 项任务，投入 ${fmt(ws.total_seconds || 0)}，`,
        `在岗 ${fmt(ws.attendance_seconds || 0)}（其中专注 ${fmt(ws.total_seconds || 0)}），`,
        `完成番茄钟 ${ws.pomodoros || 0} 个，打卡 ${ws.checkin_days || 0} 天，新增笔记 ${ws.new_notes || 0} 篇。`,
        `完成的任务：${(ws.done_tasks || []).join('、') || '无'}`,
      ].join('\n')
      const content = FIELDS.map(f => `${f.label}：${review.content?.[f.key] || '（未填写）'}`).join('\n')
      const r = await api.post('/ai/review-advice', { week, content })
      setAiAdvice(r.data.result)
    } catch (e) {
      setAiAdvice(e.response?.data?.detail || 'AI 调用失败')
    } finally {
      setAiLoading(false)
    }
  }

  if (loading && !review) return <div className="skeleton" style={{ height: 320 }} />
  if (error && !review) {
    return (
      <div className="card empty" style={{ marginTop: 40 }}>
        <div style={{ marginBottom: 12 }}>{error}</div>
        <button className="btn btn-primary" onClick={load}>重试</button>
      </div>
    )
  }

  return (
    <div>
      <div className="page-header">
        <h1><span className="page-icon"><RotateCcw size={22} strokeWidth={1.75} /></span>周复盘</h1>
        <div className="row">
          <span className="badge badge-info">{review.week_start} ~ {review.week_end}</span>
          <button className="btn" onClick={openExport}><FileText size={14} strokeWidth={1.8} /> 导出到 Self_analysis</button>
          <button className="btn btn-primary" onClick={toggleComplete}>
            {review.completed ? <><Check size={14} strokeWidth={1.8} /> 已完成本周复盘</> : '标记本周完成'}
          </button>
        </div>
      </div>

      {weekStats && (
        <div className="grid" style={{ gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', marginBottom: 16 }}>
          <div className="card">
            <div className="card-title">完成任务</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--success)', whiteSpace: 'nowrap' }}>{weekStats.done_count} 项</div>
          </div>
          <div className="card">
            <div className="card-title">投入时长</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--primary)', whiteSpace: 'nowrap' }}>{fmt(weekStats.total_seconds)}</div>
          </div>
          <div className="card">
            <div className="card-title">番茄钟</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--info)', whiteSpace: 'nowrap' }}>{weekStats.pomodoros} 个</div>
          </div>
          <div className="card">
            <div className="card-title">打卡 / 新笔记</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--warn)', whiteSpace: 'nowrap' }}>{weekStats.checkin_days}天 · {weekStats.new_notes}篇</div>
          </div>
          {weekStats.done_tasks.length > 0 && (
            <div className="card" style={{ gridColumn: '1 / -1' }}>
              <div className="card-title">本周完成</div>
              <div className="muted">
                {weekStats.done_tasks.map((t, i) => (
                  <span key={i} style={{ marginRight: 10 }}>✓ {t}</span>
                ))}
              </div>
            </div>
          )}
          {(weekStats.week_goals || []).length > 0 && (
            <div className="card" style={{ gridColumn: '1 / -1' }}>
              <div className="card-title">本周周目标
                <button className="btn btn-sm btn-primary" onClick={importWeekGoals}><CornerDownRight size={14} strokeWidth={1.8} /> 未完成任务带入下周计划</button>
              </div>
              {weekStats.week_goals.map(g => (
                <div key={g.id} style={{ padding: '6px 0', borderBottom: '1px solid var(--border)' }}>
                  <strong>{g.title}</strong> <span className="muted">进度 {g.progress}%</span>
                  {!g.undone_tasks || g.undone_tasks.length === 0 ? (
                    <span className="muted"> · 任务已全部完成 ✓</span>
                  ) : (
                    <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>
                      {g.undone_tasks.map(t => `◻ ${t.title}${t.due_date ? `（${t.due_date}）` : ''}`).join('  ')}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
          <div className="card" style={{ gridColumn: '1 / -1' }}>
            <div className="card-title">📊 专注周报
              <div>
                <button className="btn btn-sm" onClick={saveFocusNote}><Save size={14} strokeWidth={1.8} /> 存为笔记</button>
              </div>
            </div>
            <div className="chart-bars" style={{ height: 100 }}>
              {days7.map(([d, sec]) => (
                <div key={d} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, minWidth: 0 }}>
                  <div style={{ width: '100%', flex: 1, display: 'flex', alignItems: 'flex-end', justifyContent: 'center' }}>
                    <div
                      className={d === todayStr() ? 'chart-bar today' : 'chart-bar'}
                      style={{ height: sec > 0 ? `${Math.max(6, Math.round(sec / maxFocus * 100))}%` : '2px', maxWidth: 26 }}
                    />
                  </div>
                  <span className="chart-bar-label" style={{ whiteSpace: 'nowrap' }}>{d.slice(5)}</span>
                </div>
              ))}
            </div>
            <div className="muted" style={{ marginTop: 8 }}>
              本周投入 {fmt(weekStats.total_seconds)} · 番茄 {weekStats.pomodoros} 个
              {maxFocus > 0 && ` · 最投入的一天 ${bestDay}（${fmt(maxFocus)}）`}
            </div>
          </div>
          {weekStats.attendance_seconds > 0 && (
            <div className="card" style={{ gridColumn: '1 / -1' }}>
              <div className="card-title">📍 在岗 vs 专注</div>
              <div className="att-compare">
                <span>在岗 <b>{fmt(weekStats.attendance_seconds)}</b></span>
                <span>专注 <b>{fmt(weekStats.total_seconds)}</b></span>
                <span className="muted">差值 {fmt(Math.max(0, weekStats.attendance_seconds - weekStats.total_seconds))}（开会 / 上课 / 其他）</span>
              </div>
              <div className="att-ratio">
                <div className="att-ratio-in" style={{ width: `${Math.min(100, Math.round((weekStats.total_seconds / weekStats.attendance_seconds) * 100))}%` }} />
              </div>
              <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>出勤 {weekStats.attendance_days} 天 · 紫条为专注占在岗比例</div>
            </div>
          )}
        </div>
      )}

      <div className="review-grid">
        {FIELDS.map(f => (
          <div className="card" key={f.key}>
            <div className="card-title">{f.label}</div>
            <textarea
              className="textarea"
              style={{ minHeight: 120 }}
              placeholder={f.ph}
              value={review.content?.[f.key] || ''}
              onChange={e => update(f.key, e.target.value)}
            />
          </div>
        ))}
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <div className="card-title">✨ AI 复盘点评
          {aiAdvice && (
            <button className="btn btn-sm" onClick={saveReviewNote}><Save size={14} strokeWidth={1.8} /> 存为笔记</button>
          )}
        </div>
        {aiLoading ? (
          <div className="empty"><span className="spin" /> AI 正在分析本周数据...</div>
        ) : aiAdvice ? (
          <>
            <div style={{ whiteSpace: 'pre-wrap', fontSize: 13, lineHeight: 1.7 }}>{aiAdvice}</div>
            <div className="row" style={{ marginTop: 8 }}>
              <CopyBtn text={aiAdvice} />
              <button className="btn btn-sm" onClick={getAiAdvice}><RefreshCw size={14} strokeWidth={1.8} /> 重新生成</button>
            </div>
          </>
        ) : (
          <div className="empty">
            <div style={{ marginBottom: 8 }}>让 AI 结合本周数据和你的复盘内容，给出改进建议</div>
            <button className="btn btn-primary btn-sm" onClick={getAiAdvice}>生成 AI 点评</button>
          </div>
        )}
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <div className="card-title">历史复盘</div>
        {history.length === 0 && <div className="empty"><span className="empty-icon">📜</span>暂无历史复盘</div>}
        {history.map(h => {
          const isOpen = !!expanded[h.id]
          return (
            <div key={h.id} style={{ padding: '10px 0', borderBottom: '1px solid var(--border)' }}>
              <div
                className="row"
                style={{ justifyContent: 'space-between', cursor: 'pointer' }}
                onClick={() => setExpanded(e => ({ ...e, [h.id]: !e[h.id] }))}
                title={isOpen ? '收起' : '展开查看完整内容'}
              >
                <strong>{h.week_start} ~ {h.week_end} <span className="muted" style={{ fontSize: 12 }}>{isOpen ? '▾ 收起' : '▸ 展开'}</span></strong>
                <span className={`badge ${h.completed ? 'badge-success' : 'badge-gray'}`}>{h.completed ? '已完成' : '未完成'}</span>
              </div>
              {!isOpen && (h.content?.done || h.content?.problems) && (
                <div className="muted" style={{ marginTop: 4 }}>
                  完成：{h.content?.done || '无'} {h.content?.problems ? `· 问题：${h.content.problems}` : ''}
                </div>
              )}
              {isOpen && (
                <div className="card" style={{ marginTop: 8 }}>
                  {FIELDS.map(f => h.content?.[f.key] ? (
                    <div key={f.key} style={{ padding: '6px 0', borderBottom: '1px solid var(--border)', fontSize: 13 }}>
                      <strong>{f.label}：</strong>{h.content[f.key]}
                    </div>
                  ) : null)}
                  {FIELDS.every(f => !h.content?.[f.key]) && <div className="empty"><span className="empty-icon">✍</span>该周未填写复盘内容</div>}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {exportData && (
        <DoubleConfirm
          open={exportOpen}
          title="导出周复盘到 Self_analysis"
          desc={`将按 05 模板写入 ${exportData.filename}（量化数据由工作台自动统计）。${exportData.exists ? '该文件已存在，写入前会先备份。' : ''}`}
          onCancel={() => { if (!exporting) { setExportOpen(false); setExportData(null) } }}
          onConfirm={doExport}
          busy={exporting}
          confirmLabel="确定导出"
        >
          <pre className="dc-md-preview">{exportData.content}</pre>
        </DoubleConfirm>
      )}
    </div>
  )
}
