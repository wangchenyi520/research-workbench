import React, { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api'
import { Tag } from 'lucide-react'

const TYPE_LABEL = { habit: '习惯', study: '学习', once: '一次性' }
const KIND_LABEL = { notes: '笔记', literature: '文献', tasks: '任务' }

export default function Tags() {
  const [notes, setNotes] = useState([])
  const [literature, setLiterature] = useState([])
  const [tasks, setTasks] = useState([])
  const [active, setActive] = useState(null)
  const navigate = useNavigate()

  useEffect(() => {
    api.get('/notes').then(r => setNotes(r.data)).catch(() => {})
    api.get('/literature').then(r => setLiterature(r.data)).catch(() => {})
    api.get('/tasks').then(r => setTasks(r.data)).catch(() => {})
  }, [])

  // 聚合所有标签：{ tag: { notes: [..], literature: [..], tasks: [..] } }
  const byTag = useMemo(() => {
    const map = {}
    const add = (tag, kind, item) => {
      const k = tag.trim()
      if (!k) return
      if (!map[k]) map[k] = { notes: [], literature: [], tasks: [] }
      map[k][kind].push(item)
    }
    notes.forEach(n => (n.tags || '').split(',').forEach(t => add(t, 'notes', { id: n.id, title: n.title, sub: n.folder || '' })))
    literature.forEach(l => (l.tags || '').split(',').forEach(t => add(t, 'literature', { id: l.id, title: l.title, sub: l.year ? String(l.year) : '' })))
    tasks.forEach(t => (t.tags || '').split(',').forEach(tag => add(tag, 'tasks', { id: t.id, title: t.title, sub: TYPE_LABEL[t.task_type] || t.task_type })))
    return map
  }, [notes, literature, tasks])

  const tags = Object.keys(byTag).sort((a, b) => {
    const ca = byTag[a].notes.length + byTag[a].literature.length + byTag[a].tasks.length
    const cb = byTag[b].notes.length + byTag[b].literature.length + byTag[b].tasks.length
    return cb - ca
  })

  const sel = active ? byTag[active] : null
  const selTotal = sel ? sel.notes.length + sel.literature.length + sel.tasks.length : 0

  const go = (kind, id) => {
    const paths = { notes: '/notes', literature: '/literature', tasks: '/tasks' }
    navigate(`${paths[kind]}?highlight=${id}`)
  }

  return (
    <div>
      <div className="page-header">
        <h1><span className="page-icon"><Tag size={22} strokeWidth={1.75} /></span>标签</h1>
        <div className="row">
          <span className="badge badge-info">{tags.length} 个标签</span>
        </div>
      </div>

      {tags.length === 0 && (
        <div className="card empty">
          <span className="empty-icon">🏷</span>
          <div>还没有任何标签。给笔记、文献或任务添加标签（逗号分隔）后，这里会自动聚合。</div>
        </div>
      )}

      {tags.length > 0 && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="tag-cloud">
            {tags.map(tag => {
              const s = byTag[tag]
              const cnt = s.notes.length + s.literature.length + s.tasks.length
              return (
                <span key={tag} className={`tag-pill ${active === tag ? 'active' : ''}`} onClick={() => setActive(active === tag ? null : tag)}>
                  #{tag} <span className="cnt">{cnt}</span>
                </span>
              )
            })}
          </div>
        </div>
      )}

      {sel && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div className="card">
            <div className="card-title">#{active} · {selTotal} 条</div>
            {(['notes', 'literature', 'tasks']).map(kind => (
              <div key={kind} style={{ marginBottom: kind === 'tasks' ? 0 : 14 }}>
                <div className="muted" style={{ fontWeight: 600, margin: '6px 0 4px' }}>{KIND_LABEL[kind]}（{sel[kind].length}）</div>
                {sel[kind].length === 0 && <div className="muted">无</div>}
                {sel[kind].map(item => (
                  <div key={`${kind}-${item.id}`} className="row" style={{ padding: '7px 0', borderBottom: '1px solid var(--border)', cursor: 'pointer' }} onClick={() => go(kind, item.id)}>
                    <span style={{ flex: 1 }}>{item.title}</span>
                    {item.sub && <span className="muted">{item.sub}</span>}
                    <span className="badge badge-gray">{KIND_LABEL[kind]}</span>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}