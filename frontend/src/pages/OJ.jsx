import React, { useEffect, useState } from 'react'
import api from '../api'
import { useToast } from '../components/Toast'
import { Code2 } from 'lucide-react'

const DIFF = {
  easy: ['简单', 'badge-success'],
  medium: ['中等', 'badge-warn'],
  hard: ['困难', 'badge-danger'],
}
const DIFF_FILTER = [['all', '全部'], ['easy', '简单'], ['medium', '中等'], ['hard', '困难']]
const STATUS_LABEL = { todo: '待做', doing: '进行中', done: '已 AC' }

function ProblemForm({ initial, onClose, onSaved }) {
  const [form, setForm] = useState({
    title: initial?.title || '',
    platform: initial?.platform || 'LeetCode',
    difficulty: initial?.difficulty || 'medium',
    tags: initial?.tags || '',
    url: initial?.url || '',
    notes: initial?.notes || '',
  })
  const toast = useToast()
  const set = k => v => setForm(f => ({ ...f, [k]: v }))
  const submit = async () => {
    if (!form.title.trim()) return toast('请输入题目', 'error')
    try {
      if (initial?.id) await api.put(`/oj/problems/${initial.id}`, form)
      else await api.post('/oj/problems', form)
      onSaved(); onClose()
    } catch (e) { toast('保存失败', 'error') }
  }
  return (
    <div className="modal-mask" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <h3>{initial ? '编辑题目' : '新增题目'}</h3>
        <label className="label">题号 + 名称 *</label>
        <input className="input" placeholder="如 1. 两数之和" value={form.title} onChange={e => set('title')(e.target.value)} />
        <div className="row">
          <div style={{ flex: 1 }}><label className="label">平台</label>
            <select className="select" value={form.platform} onChange={e => set('platform')(e.target.value)}>
              {['LeetCode', '牛客', '洛谷', '其他'].map(x => <option key={x} value={x}>{x}</option>)}
            </select>
          </div>
          <div style={{ flex: 1 }}><label className="label">难度</label>
            <select className="select" value={form.difficulty} onChange={e => set('difficulty')(e.target.value)}>
              {Object.entries(DIFF).map(([k, v]) => <option key={k} value={k}>{v[0]}</option>)}
            </select>
          </div>
        </div>
        <label className="label">标签（逗号分隔）</label>
        <input className="input" placeholder="如 数组,双指针,哈希" value={form.tags} onChange={e => set('tags')(e.target.value)} />
        <label className="label">题目链接</label>
        <input className="input" placeholder="https://leetcode.cn/..." value={form.url} onChange={e => set('url')(e.target.value)} />
        <label className="label">备注 / 思路</label>
        <textarea className="textarea" value={form.notes} onChange={e => set('notes')(e.target.value)} />
        <div className="modal-actions">
          <button className="btn" onClick={onClose}>取消</button>
          <button className="btn btn-primary" onClick={submit}>保存</button>
        </div>
      </div>
    </div>
  )
}

export default function OJ() {
  const [items, setItems] = useState([])
  const [stats, setStats] = useState(null)
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState(null)
  const [diff, setDiff] = useState('all')
  const [tag, setTag] = useState('')
  const toast = useToast()

  const load = () => {
    api.get('/oj/problems').then(r => setItems(r.data))
    api.get('/oj/stats').then(r => setStats(r.data))
  }
  useEffect(load, [])

  const setStatus = async (p, s) => {
    await api.put(`/oj/problems/${p.id}`, { status: s })
    load()
  }
  const markSolved = async p => {
    await api.post(`/oj/problems/${p.id}/solve`)
    toast('已打卡 AC'); load()
  }
  const del = async p => {
    if (!confirm(`删除题目「${p.title}」？`)) return
    await api.delete(`/oj/problems/${p.id}`)
    toast('已删除'); load()
  }

  const allTags = [...new Set(items.flatMap(p => p.tags.split(',').map(t => t.trim()).filter(Boolean)))]
  const filtered = items.filter(p =>
    (diff === 'all' || p.difficulty === diff) &&
    (!tag || p.tags.split(',').map(t => t.trim()).includes(tag))
  )

  return (
    <div>
      <div className="page-header">
        <h1><span className="page-icon"><Code2 size={22} strokeWidth={1.75} /></span>刷题记录</h1>
        <button className="btn btn-primary" onClick={() => setShowForm(true)}>+ 新增题目</button>
      </div>

      <div className="grid grid-4" style={{ marginBottom: 16 }}>
        <div className="stat-card stat-purple"><div className="stat-value">{stats?.today_count ?? '–'}</div><div className="stat-label">今日刷题</div></div>
        <div className="stat-card stat-blue"><div className="stat-value">{stats?.streak ?? '–'}</div><div className="stat-label">连续刷题 🔥</div></div>
        <div className="stat-card stat-green"><div className="stat-value">{stats?.total_done ?? '–'}<span className="muted">/{stats?.total ?? 0}</span></div><div className="stat-label">已 AC 总数</div></div>
        <div className="stat-card stat-orange"><div className="stat-value">{stats ? `${stats.difficulty.easy}/${stats.difficulty.medium}/${stats.difficulty.hard}` : '–'}</div><div className="stat-label">简单/中等/困难</div></div>
      </div>

      <div className="row" style={{ gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
        {DIFF_FILTER.map(([k, label]) => (
          <button key={k} className={`btn btn-sm ${diff === k ? 'btn-primary' : ''}`} onClick={() => setDiff(k)}>{label}</button>
        ))}
        <select className="select" style={{ width: 140 }} value={tag} onChange={e => setTag(e.target.value)}>
          <option value="">全部标签</option>
          {allTags.map(t => <option key={t} value={t}>{t}</option>)}
        </select>
      </div>

      {items.length === 0 && <div className="card empty">还没有刷题记录，从一道「两数之和」开始吧</div>}
      {items.length > 0 && filtered.length === 0 && <div className="card empty">没有符合筛选的题目</div>}

      {filtered.map(p => (
        <div className="card" key={p.id} style={{ marginBottom: 10 }}>
          <div className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div style={{ flex: 1 }}>
              <div className="row" style={{ gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <strong style={{ fontSize: 15 }}>{p.title}</strong>
                <span className={`badge ${DIFF[p.difficulty]?.[1] || 'badge-gray'}`}>{DIFF[p.difficulty]?.[0] || p.difficulty}</span>
                <span className={`badge ${p.status === 'done' ? 'badge-success' : p.status === 'doing' ? 'badge-info' : 'badge-gray'}`}>{STATUS_LABEL[p.status]}</span>
                {p.solved_count > 0 && <span className="badge badge-primary">打卡 {p.solved_count} 次</span>}
              </div>
              <div className="muted" style={{ marginTop: 4 }}>
                {p.platform}
                {p.tags && ` · ${p.tags}`}
                {p.url && <span> · <a href={p.url} target="_blank" rel="noreferrer">链接 ↗</a></span>}
              </div>
              {p.notes && <div className="muted" style={{ marginTop: 4 }}>{p.notes}</div>}
            </div>
            <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
              {p.status !== 'done' && <button className="btn btn-sm btn-primary" onClick={() => markSolved(p)}>打卡 AC</button>}
              <button className="btn btn-sm" onClick={() => setStatus(p, p.status === 'doing' ? 'todo' : 'doing')}>
                {p.status === 'doing' ? '转待做' : '开始'}
              </button>
              <button className="btn btn-sm" onClick={() => setEditing(p)}>编辑</button>
              <button className="btn btn-sm btn-danger" onClick={() => del(p)}>删除</button>
            </div>
          </div>
        </div>
      ))}

      {showForm && <ProblemForm initial={null} onClose={() => setShowForm(false)} onSaved={load} />}
      {editing && <ProblemForm initial={editing} onClose={() => setEditing(null)} onSaved={load} />}
    </div>
  )
}
