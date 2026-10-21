import React, { useEffect, useRef, useState } from 'react'
import api from '../api'

// ⑦ 命令面板：Ctrl+P 全局唤起，搜页面 / 笔记 / 快捷动作
export default function CommandPalette({ open, onClose, pages, onNavigate, onAction }) {
  const [q, setQ] = useState('')
  const [notes, setNotes] = useState([])
  const [idx, setIdx] = useState(0)
  const inputRef = useRef(null)

  useEffect(() => {
    if (open) {
      setQ(''); setIdx(0)
      setTimeout(() => inputRef.current?.focus(), 30)
      api.get('/notes').then(r => setNotes(r.data || [])).catch(() => setNotes([]))
    }
  }, [open])

  useEffect(() => {
    if (!open) return
    const onKey = e => {
      if (e.key === 'Escape') { onClose(); return }
      if (e.key === 'ArrowDown') { e.preventDefault(); setIdx(i => Math.min(i + 1, results.length - 1)) }
      if (e.key === 'ArrowUp') { e.preventDefault(); setIdx(i => Math.max(i - 1, 0)) }
      if (e.key === 'Enter' && results[idx]) { results[idx].run(); }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  const notesActions = notes
    .filter(n => (n.title || '').toLowerCase().includes(q.toLowerCase()) && !q.trim().startsWith('>'))
    .slice(0, 8)
    .map(n => ({
      label: n.title,
      sub: n.folder || '笔记',
      run: () => { onNavigate(`/notes?highlight=${n.id}`); onClose() },
    }))

  const pageActions = pages
    .filter(p => (p.label || '').toLowerCase().includes(q.toLowerCase()))
    .map(p => ({
      label: p.label,
      sub: '页面',
      run: () => { onNavigate(p.path); onClose() },
    }))

  const quickActions = [
    { label: '新建笔记', sub: '动作', run: () => { onAction('new-note'); onClose() } },
    { label: '新建任务', sub: '动作', run: () => { onAction('new-task'); onClose() } },
    { label: '今日页', sub: '动作', run: () => { onNavigate('/today'); onClose() } },
  ]
  const results = q.trim() ? [...pageActions, ...notesActions] : [...pageActions, ...quickActions, ...notesActions]
  const shown = results.slice(0, 12)

  useEffect(() => { setIdx(0) }, [q])

  if (!open) return null
  return (
    <div className="modal-mask" style={{ alignItems: 'flex-start', paddingTop: '12vh' }} onClick={onClose}>
      <div className="modal" style={{ maxWidth: 520, padding: 12 }} onClick={e => e.stopPropagation()}>
        <input
          ref={inputRef}
          className="input"
          style={{ width: '100%', fontSize: 15 }}
          placeholder="搜索页面、打开笔记，或输入 > 执行动作..."
          value={q}
          onChange={e => setQ(e.target.value)}
        />
        <div style={{ marginTop: 8, maxHeight: 340, overflowY: 'auto' }}>
          {shown.length === 0 && <div className="muted" style={{ padding: 12, fontSize: 13 }}>没有匹配结果</div>}
          {shown.map((r, i) => (
            <div
              key={r.label}
              className={`palette-item ${i === idx ? 'active' : ''}`}
              onMouseEnter={() => setIdx(i)}
              onClick={() => r.run()}
            >
              <span>{r.label}</span>
              <span className="muted" style={{ fontSize: 11 }}>{r.sub}</span>
            </div>
          ))}
        </div>
        <div className="muted" style={{ fontSize: 11, marginTop: 6, textAlign: 'center' }}>↑↓ 选择 · Enter 执行 · Esc 关闭</div>
      </div>
    </div>
  )
}