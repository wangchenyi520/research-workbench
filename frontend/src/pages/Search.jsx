import React, { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import api from '../api'
import { Search as SearchIcon } from 'lucide-react'

const TYPE_LABEL = { habit: '习惯', study: '学习', once: '一次性' }

const highlight = (text, q) => {
  if (!q || !text) return text
  const escaped = q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const parts = String(text).split(new RegExp(`(${escaped})`, 'gi'))
  return parts.map((p, i) => (p.toLowerCase() === q.toLowerCase() ? <mark key={i} className="search-hl">{p}</mark> : p))
}

export default function Search() {
  const [params] = useSearchParams()
  const [q, setQ] = useState(params.get('q') || '')
  const [results, setResults] = useState(null)
  const [tab, setTab] = useState('all') // all/tasks/notes/literature/goals
  const navigate = useNavigate()

  useEffect(() => {
    const query = params.get('q')
    if (!query) return
    api.get('/stats/search', { params: { q: query } }).then(r => setResults(r.data)).catch(() => {})
  }, [params])

  const doSearch = e => {
    e.preventDefault()
    if (!q.trim()) return
    // C12：只 navigate，由 useEffect 统一发请求（相同关键词再搜时 effect 不触发，手动补一次）
    if (params.get('q') === q) {
      api.get('/stats/search', { params: { q } }).then(r => setResults(r.data)).catch(() => {})
    } else {
      navigate(`/search?q=${encodeURIComponent(q)}`)
    }
  }

  // 深链：跳转目标页并定位到对应卡片（各页面读取 ?highlight=id）
  const go = (path, id) => navigate(id ? `${path}?highlight=${id}` : path)

  const total = results ? results.tasks.length + results.notes.length + results.literature.length + results.goals.length : 0
  const tabs = [
    ['all', `全部 ${total}`],
    ['tasks', `任务 ${results?.tasks.length || 0}`],
    ['notes', `笔记 ${results?.notes.length || 0}`],
    ['literature', `文献 ${results?.literature.length || 0}`],
    ['goals', `目标 ${results?.goals.length || 0}`],
  ]

  return (
    <div>
      <div className="page-header">
        <h1><span className="page-icon"><SearchIcon size={22} strokeWidth={1.75} /></span>搜索</h1>
      </div>
      <form className="row" style={{ marginBottom: 16 }} onSubmit={doSearch}>
        <input
          className="input"
          style={{ flex: 1, fontSize: 15, padding: '10px 14px' }}
          placeholder="搜索任务、笔记、文献、目标..."
          value={q}
          onChange={e => setQ(e.target.value)}
          autoFocus
        />
        <button className="btn btn-primary" type="submit">搜索</button>
      </form>

      {!results && <div className="empty"><span className="empty-icon">⌕</span>输入关键词开始搜索</div>}
      {results && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div className="row" style={{ gap: 6 }}>
            {tabs.map(([k, l]) => (
              <button key={k} className={`btn btn-sm ${tab === k ? 'btn-primary' : ''}`} onClick={() => setTab(k)}>{l}</button>
            ))}
          </div>
          {tab !== 'tasks' && tab !== 'all' ? null : (
            <div className="card">
              <div className="card-title">任务（{results.tasks.length}）</div>
              {results.tasks.length === 0 && <div className="empty"><span className="empty-icon">🔍</span>无结果</div>}
              {results.tasks.map(t => (
                <div key={t.id} className="row" style={{ padding: '8px 0', borderBottom: '1px solid var(--border)', cursor: 'pointer' }} onClick={() => go('/tasks', t.id)}>
                  <span style={{ flex: 1 }}>{highlight(t.title, q)}</span>
                  <span className={`badge ${t.status === 'done' ? 'badge-success' : 'badge-gray'}`}>{TYPE_LABEL[t.task_type] || t.task_type} · {t.status === 'done' ? '已完成' : t.status}</span>
                </div>
              ))}
            </div>
          )}
          {tab !== 'notes' && tab !== 'all' ? null : (
            <div className="card">
              <div className="card-title">笔记（{results.notes.length}）</div>
              {results.notes.length === 0 && <div className="empty"><span className="empty-icon">🔍</span>无结果</div>}
              {results.notes.map(n => (
                <div key={n.id} className="row" style={{ padding: '8px 0', borderBottom: '1px solid var(--border)', cursor: 'pointer' }} onClick={() => go('/notes', n.id)}>
                  <span style={{ flex: 1 }}>{highlight(n.title, q)} {n.pinned && <span className="badge badge-warn">置顶</span>}</span>
                </div>
              ))}
            </div>
          )}
          {tab !== 'literature' && tab !== 'all' ? null : (
            <div className="card">
              <div className="card-title">文献（{results.literature.length}）</div>
              {results.literature.length === 0 && <div className="empty"><span className="empty-icon">🔍</span>无结果</div>}
              {results.literature.map(l => (
                <div key={l.id} className="row" style={{ padding: '8px 0', borderBottom: '1px solid var(--border)', cursor: 'pointer' }} onClick={() => go('/literature', l.id)}>
                  <span style={{ flex: 1 }}>{highlight(l.title, q)}</span>
                </div>
              ))}
            </div>
          )}
          {tab !== 'goals' && tab !== 'all' ? null : (
            <div className="card">
              <div className="card-title">目标（{results.goals.length}）</div>
              {results.goals.length === 0 && <div className="empty"><span className="empty-icon">🔍</span>无结果</div>}
              {results.goals.map(g => (
                <div key={g.id} className="row" style={{ padding: '8px 0', borderBottom: '1px solid var(--border)', cursor: 'pointer' }} onClick={() => go('/goals', g.id)}>
                  <span style={{ flex: 1 }}>{highlight(g.title, q)}</span>
                  <span className="badge badge-info">{g.level}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}