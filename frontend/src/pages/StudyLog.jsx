import React, { useEffect, useState } from 'react'
import api, { todayStr } from '../api'
import { useToast } from '../components/Toast'
import { TrendingUp } from 'lucide-react'

export default function StudyLog() {
  const [logs, setLogs] = useState([])
  const [content, setContent] = useState('')
  const [date, setDate] = useState(todayStr())
  const toast = useToast()

  const load = () => {
    api.get('/studylog?limit=50').then(r => setLogs(r.data)).catch(() => {})
  }
  useEffect(load, [])

  const add = async () => {
    if (!content.trim()) return toast('请填写今天学了什么', 'error')
    try {
      await api.post('/studylog', { content, date })
      setContent('')
      toast('已记录')
      load()
    } catch (e) { toast('保存失败', 'error') }
  }

  const del = async id => {
    if (!confirm('删除这条学习记录？')) return
    await api.delete(`/studylog/${id}`)
    load()
  }

  const byDate = {}
  logs.forEach(l => {
    (byDate[l.date] = byDate[l.date] || []).push(l)
  })
  const dates = Object.keys(byDate).sort().reverse()

  return (
    <div>
      <div className="page-header">
        <h1><span className="page-icon"><TrendingUp size={22} strokeWidth={1.75} /></span>学习轨迹</h1>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-title">记录今天学了什么</div>
        <div className="row">
          <input type="date" className="input" style={{ width: 160 }} value={date} onChange={e => setDate(e.target.value)} />
          <input
            className="input"
            style={{ flex: 1 }}
            placeholder="例如：学会了 PyTorch 的 DataLoader 用法，复现了 SSIM 损失..."
            value={content}
            onChange={e => setContent(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.nativeEvent.isComposing) add() }}
          />
          <button className="btn btn-primary" onClick={add}>记录</button>
        </div>
        <div className="muted" style={{ marginTop: 6 }}>用一句话记录每天的技术/科研收获，形成你的成长轨迹</div>
      </div>

      {dates.length === 0 && <div className="card empty">还没有学习记录，从今天开始记录第一条吧</div>}

      <div className="timeline">
        {dates.map(d => (
          <div key={d} style={{ marginBottom: 14 }}>
            <div className="row" style={{ gap: 8, marginBottom: 6 }}>
              <div className="timeline-dot" style={{ background: 'var(--primary)' }} />
              <strong>{d}</strong>
              <span className="badge badge-info">{byDate[d].length} 条</span>
            </div>
            {byDate[d].map(l => (
              <div key={l.id} className="card" style={{ marginLeft: 24, marginBottom: 8, padding: '10px 14px' }}>
                <div className="row" style={{ justifyContent: 'space-between' }}>
                  <span style={{ flex: 1 }}>{l.content}</span>
                  <button className="btn btn-sm btn-danger" onClick={() => del(l.id)}>删除</button>
                </div>
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}
