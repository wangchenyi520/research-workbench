import React, { useEffect, useMemo, useRef, useState } from 'react'
import api from '../api'
import { useToast } from '../components/Toast'
import CopyBtn from '../components/CopyBtn'
import { BarChart3, CircleCheck, Clock, Timer, FlaskConical, Printer, Save, RefreshCw } from 'lucide-react'

function fmt(sec) {
  if (!sec) return '0 分钟'
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  return h > 0 ? `${h} 小时 ${m} 分钟` : `${m} 分钟`
}

export default function Reports() {
  const now = new Date()
  const [month, setMonth] = useState(`${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`)
  const [report, setReport] = useState(null)
  const [ai, setAi] = useState('')
  const [aiLoading, setAiLoading] = useState(false)
  const toast = useToast()

  const load = () => {
    api.get('/stats/monthly-report', { params: { month } }).then(r => setReport(r.data)).catch(() => {})
  }
  useEffect(load, [month])

  // 切月：清掉上月 AI 点评并重置生成标记（C11）
  useEffect(() => {
    setAi('')
    aiFetchedRef.current = false
  }, [month])

  // 进页自动生成 AI 点评（当月有数据且尚未生成过）
  const aiFetchedRef = useRef(false)
  const monthRef = useRef(month)
  useEffect(() => { monthRef.current = month }, [month])
  useEffect(() => {
    if (report && !ai && !aiLoading && !aiFetchedRef.current) {
      if ((report.done_count || 0) > 0 || (report.total_seconds || 0) > 0) {
        aiFetchedRef.current = true
        aiComment()
      }
    }
  }, [report])

  const dailyBars = useMemo(() => {
    if (!report?.daily) return []
    const today = new Date().getDate()
    return report.daily.map(d => ({
      date: d.date,
      day: d.day,
      label: d.day,
      sec: d.seconds,
      isToday: d.day === today && report.month === `${new Date().getFullYear()}-${String(new Date().getMonth() + 1).padStart(2, '0')}`,
    }))
  }, [report])

  const maxDaily = Math.max(...dailyBars.map(d => d.sec), 1)

  const saveReportNote = async () => {
    if (!report) return
    try {
      const lines = [
        `# 月度报告 ${report.month}`, '',
        `## 📊 统计`, '',
        `- 完成任务 ${report.done_count} 项`,
        `- 投入 ${fmt(report.total_seconds)} · 番茄 ${report.pomodoros} 个`,
        `- 在岗 ${fmt(report.attendance_seconds || 0)}（专注 ${fmt(report.total_seconds)}，出勤 ${report.attendance_days || 0} 天）`,
        `- 打卡 ${report.checkin_days} 天`,
        `- 新增笔记 ${report.new_notes} 篇 · 文献 ${report.new_literature} 篇 · 实验 ${report.new_experiments} 个 · 论文 ${report.new_papers} 篇`, '',
        '## ✅ 本月完成', '',
        ...(report.done_tasks.length ? report.done_tasks.map(t => `- ${t}`) : ['（无）']), '',
      ]
      if (ai) lines.push('## ✨ AI 点评', ai, '')
      await api.post('/notes', { title: `月度报告 ${report.month}`, content: lines.join('\n'), folder: '复盘', tags: '复盘,报告' })
      toast('已存为笔记（文件夹「复盘」）')
    } catch (e) { toast('保存失败', 'error') }
  }

  const aiComment = async () => {
    const m = month
    setAiLoading(true)
    setAi('')
    try {
      const text = [
        `${report.month} 月度统计：`,
        `完成任务 ${report.done_count} 项，投入 ${fmt(report.total_seconds)}，番茄 ${report.pomodoros} 个，`,
        `在岗 ${fmt(report.attendance_seconds || 0)}（其中专注 ${fmt(report.total_seconds)}），`,
        `打卡 ${report.checkin_days} 天，新增笔记 ${report.new_notes} 篇、文献 ${report.new_literature} 篇、实验 ${report.new_experiments} 个、论文 ${report.new_papers} 篇。`,
        `完成：${report.done_tasks.join('、') || '无'}`,
      ].join('\n')
      const r = await api.post('/ai/review-advice', { week: text, content: '请给出本月总结和改进建议' })
      if (monthRef.current === m) setAi(r.data.result)
    } catch (e) {
      if (monthRef.current === m) setAi(e.response?.data?.detail || 'AI 调用失败')
    } finally {
      if (monthRef.current === m) setAiLoading(false)
    }
  }

  return (
    <div>
      <div className="page-header">
        <h1><span className="page-icon"><BarChart3 size={22} strokeWidth={1.75} /></span>月度报告</h1>
        <div className="row">
          <button className="btn" onClick={() => window.print()}><Printer size={14} strokeWidth={1.8} /> 打印/导出 PDF</button>
          <input type="month" className="input" style={{ width: 180 }} value={month} onChange={e => setMonth(e.target.value)} />
        </div>
      </div>

      {!report && <div className="skeleton" style={{ height: 260 }} />}

      {report && (
        <>
          <div className="grid grid-4" style={{ marginBottom: 16 }}>
            <div className="stat-card stat-purple"><span className="stat-icon"><CircleCheck size={15} strokeWidth={2} /></span><div className="stat-label">完成任务</div><div className="stat-value">{report.done_count} 项</div></div>
            <div className="stat-card stat-blue"><span className="stat-icon"><Clock size={15} strokeWidth={2} /></span><div className="stat-label">投入时长</div><div className="stat-value">{fmt(report.total_seconds)}</div></div>
            <div className="stat-card stat-green"><span className="stat-icon"><Timer size={15} strokeWidth={2} /></span><div className="stat-label">番茄 / 打卡</div><div className="stat-value">{report.pomodoros} / {report.checkin_days}天</div></div>
            <div className="stat-card stat-orange"><span className="stat-icon"><FlaskConical size={15} strokeWidth={2} /></span><div className="stat-label">新增内容</div><div className="stat-value">{report.new_notes + report.new_literature + report.new_experiments + report.new_papers}</div></div>
          </div>

          <div className="card" style={{ marginBottom: 16 }}>
            <div className="card-title">本月每日投入</div>
            {dailyBars.length === 0 && <div className="empty"><span className="empty-icon">⏱</span>本月暂无投入记录</div>}
            <div className="chart-bars" style={{ height: 160, alignItems: 'flex-end', gap: 4 }}>
              {dailyBars.map(d => (
                <div key={d.date} style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'flex-end', height: '100%' }}>
                  <div
                    className={`chart-bar ${d.isToday ? 'today' : ''}`}
                    style={{
                      flex: '0 0 auto',
                      width: d.sec > 0 ? '70%' : '40%',
                      height: `${(d.sec / maxDaily) * 100}%`,
                      minHeight: d.sec > 0 ? 4 : 2,
                      borderRadius: 3,
                    }}
                    title={`${d.date}: ${fmt(d.sec)}`}
                  />
                  <div className="chart-bar-label">{d.isToday ? '今天' : (d.day % 5 === 0 ? d.day : '')}</div>
                </div>
              ))}
            </div>
            <div className="row" style={{ justifyContent: 'space-between' }}><span className="muted">月初</span><span className="muted">月末</span></div>
          </div>

          {report.attendance_seconds > 0 && (
            <div className="card" style={{ marginBottom: 16 }}>
              <div className="card-title">📍 在岗 vs 专注</div>
              <div className="att-compare">
                <span>在岗 <b>{fmt(report.attendance_seconds)}</b></span>
                <span>专注 <b>{fmt(report.total_seconds)}</b></span>
                <span className="muted">差值 {fmt(Math.max(0, report.attendance_seconds - report.total_seconds))}（开会 / 上课 / 其他）</span>
              </div>
              <div className="att-ratio">
                <div className="att-ratio-in" style={{ width: `${Math.min(100, Math.round((report.total_seconds / report.attendance_seconds) * 100))}%` }} />
              </div>
              <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>出勤 {report.attendance_days} 天 · 紫条为专注占在岗比例</div>
            </div>
          )}

          <div className="grid grid-2">
            <div className="card">
              <div className="card-title">本月完成的任务</div>
              {report.done_tasks.length === 0 && <div className="empty"><span className="empty-icon">✅</span>本月暂无完成任务</div>}
              {report.done_tasks.map((t, i) => (
                <div key={i} className="row" style={{ padding: '6px 0', borderBottom: '1px solid var(--border)' }}><span>✓ {t}</span></div>
              ))}
            </div>

            <div className="card">
              <div className="card-title">✨ AI 本月点评
                {ai && <button className="btn btn-sm" onClick={saveReportNote}><Save size={14} strokeWidth={1.8} /> 存为笔记</button>}
              </div>
              {aiLoading ? <div className="empty"><span className="spin" /> AI 分析中...</div> : ai ? (
                <>
                  <div style={{ whiteSpace: 'pre-wrap', fontSize: 13, lineHeight: 1.7 }}>{ai}</div>
                  <div className="row" style={{ marginTop: 8 }}>
                    <CopyBtn text={ai} />
                    <button className="btn btn-sm" onClick={aiComment}><RefreshCw size={14} strokeWidth={1.8} /> 重新生成</button>
                  </div>
                </>
              ) : (
                <div className="empty">
                  <div style={{ marginBottom: 8 }}>生成本月科研与学习总结</div>
                  <button className="btn btn-primary btn-sm" onClick={aiComment}>生成 AI 点评</button>
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
