import React, { useEffect, useState } from 'react'
import api from '../api'
import { useToast } from '../components/Toast'
import { Library } from 'lucide-react'

const MASTERY = { 0: ['不会', 'badge-danger'], 1: ['模糊', 'badge-warn'], 2: ['掌握', 'badge-success'] }
const CATEGORIES = ['DL', 'CV', '算法', 'C++', 'Python', 'OS', '网络', '数据库', '项目', '其他']
// 与后端 interval 一致：0 不会 → 1 天、1 模糊 → 2 天、2 掌握 → 4 天
const REVIEW_INTERVAL = { 0: 1, 1: 2, 2: 4 }

function QuestionForm({ initial, onClose, onSaved }) {
  const [form, setForm] = useState({
    question: initial?.question || '',
    category: initial?.category || 'DL',
    answer: initial?.answer || '',
  })
  const toast = useToast()
  const set = k => v => setForm(f => ({ ...f, [k]: v }))
  const submit = async () => {
    if (!form.question.trim()) return toast('请输入问题', 'error')
    try {
      if (initial?.id) await api.put(`/interview/questions/${initial.id}`, form)
      else await api.post('/interview/questions', form)
      onSaved(); onClose()
    } catch (e) { toast('保存失败', 'error') }
  }
  return (
    <div className="modal-mask" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <h3>{initial ? '编辑题目' : '新增题目'}</h3>
        <label className="label">问题 *</label>
        <input className="input" placeholder="如 讲一下 NMS 的原理" value={form.question} onChange={e => set('question')(e.target.value)} />
        <label className="label">分类</label>
        <select className="select" value={form.category} onChange={e => set('category')(e.target.value)}>
          {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <label className="label">参考答案</label>
        <textarea className="textarea" style={{ minHeight: 120 }} placeholder="写下你整理的标准答案" value={form.answer} onChange={e => set('answer')(e.target.value)} />
        <div className="modal-actions">
          <button className="btn" onClick={onClose}>取消</button>
          <button className="btn btn-primary" onClick={submit}>保存</button>
        </div>
      </div>
    </div>
  )
}

export default function Interview() {
  const [items, setItems] = useState([])
  const [stats, setStats] = useState(null)
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState(null)
  const [cat, setCat] = useState('')
  const [dueOnly, setDueOnly] = useState(false)
  const [showAns, setShowAns] = useState({})
  const toast = useToast()

  const load = () => {
    api.get('/interview/questions', { params: { category: cat || undefined, due: dueOnly || undefined } })
      .then(r => setItems(r.data))
    api.get('/interview/stats').then(r => setStats(r.data))
  }
  useEffect(load, [cat, dueOnly])

  const review = async (q, mastery) => {
    try {
      await api.post(`/interview/questions/${q.id}/review`, { mastery })
      toast(`已记录复习，下次 ${REVIEW_INTERVAL[mastery] ?? 4} 天后复习`)
      load()
    } catch (e) { toast('保存失败', 'error') }
  }
  const del = async q => {
    if (!confirm(`删除「${q.question}」？`)) return
    try {
      await api.delete(`/interview/questions/${q.id}`)
      toast('已删除'); load()
    } catch (e) { toast('删除失败', 'error') }
  }

  return (
    <div>
      <div className="page-header">
        <h1><span className="page-icon"><Library size={22} strokeWidth={1.75} /></span>面试八股</h1>
        <button className="btn btn-primary" onClick={() => setShowForm(true)}>+ 新增题目</button>
      </div>

      <div className="grid grid-4" style={{ marginBottom: 16 }}>
        <div className="stat-card stat-purple"><div className="stat-value">{stats?.total ?? '–'}</div><div className="stat-label">总题数</div></div>
        <div className="stat-card stat-blue"><div className="stat-value">{stats?.due_today ?? '–'}</div><div className="stat-label">待复习</div></div>
        <div className="stat-card stat-green"><div className="stat-value">{stats?.reviewed_today ?? '–'}</div><div className="stat-label">今日已复习</div></div>
        <div className="stat-card stat-orange"><div className="stat-value">{stats ? `${stats.mastery[2]}/${stats.mastery[1]}/${stats.mastery[0]}` : '–'}</div><div className="stat-label">掌握/模糊/不会</div></div>
      </div>

      <div className="row" style={{ gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
        <button className={`btn btn-sm ${!cat ? 'btn-primary' : ''}`} onClick={() => setCat('')}>全部</button>
        {CATEGORIES.map(c => (
          <button key={c} className={`btn btn-sm ${cat === c ? 'btn-primary' : ''}`} onClick={() => setCat(c)}>{c}</button>
        ))}
        <label className="row" style={{ gap: 4, alignItems: 'center', cursor: 'pointer', marginLeft: 8 }}>
          <input type="checkbox" checked={dueOnly} onChange={e => setDueOnly(e.target.checked)} />
          <span className="muted">只看待复习</span>
        </label>
      </div>

      {items.length === 0 && <div className="card empty">还没有八股题目，先整理一道高频题吧</div>}

      {items.map(q => (
        <div className="card" key={q.id} style={{ marginBottom: 10 }}>
          <div className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div style={{ flex: 1 }}>
              <div className="row" style={{ gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <strong style={{ fontSize: 15 }}>{q.question}</strong>
                <span className="badge badge-info">{q.category}</span>
                <span className={`badge ${MASTERY[q.mastery][1]}`}>{MASTERY[q.mastery][0]}</span>
                {q.next_review && <span className="muted" style={{ fontSize: 12 }}>下次复习 {q.next_review}</span>}
              </div>
              {q.answer && (
                <div style={{ marginTop: 6 }}>
                  <button className="btn btn-sm" onClick={() => setShowAns(s => ({ ...s, [q.id]: !s[q.id] }))}>
                    {showAns[q.id] ? '收起答案' : '查看答案'}
                  </button>
                  {showAns[q.id] && <div className="muted" style={{ marginTop: 6, whiteSpace: 'pre-wrap' }}>{q.answer}</div>}
                </div>
              )}
            </div>
            <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
              {[0, 1, 2].map(m => (
                <button
                  key={m}
                  className={`btn btn-sm ${q.mastery === m ? 'btn-primary' : ''}`}
                  onClick={() => review(q, m)}
                  title={`标记为${MASTERY[m][0]}并安排下次复习`}
                >
                  {MASTERY[m][0]}
                </button>
              ))}
              <button className="btn btn-sm" onClick={() => setEditing(q)}>编辑</button>
              <button className="btn btn-sm btn-danger" onClick={() => del(q)}>删除</button>
            </div>
          </div>
        </div>
      ))}

      {showForm && <QuestionForm initial={null} onClose={() => setShowForm(false)} onSaved={load} />}
      {editing && <QuestionForm initial={editing} onClose={() => setEditing(null)} onSaved={load} />}
    </div>
  )
}
