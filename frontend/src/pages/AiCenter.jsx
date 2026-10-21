import React, { useEffect, useState } from 'react'
import api from '../api'
import { useToast } from '../components/Toast'
import CopyBtn from '../components/CopyBtn'
import { Sparkles, Trash2 } from 'lucide-react'

export default function AiCenter() {
  const [rows, setRows] = useState([])
  const [expanded, setExpanded] = useState(null)
  const [loading, setLoading] = useState(false)
  const toast = useToast()

  const load = () => {
    api.get('/ai/history').then(r => setRows(r.data)).catch(() => {})
  }
  useEffect(load, [])

  const clear = async () => {
    if (!confirm('清空全部 AI 历史记录？')) return
    await api.delete('/ai/history')
    toast('已清空')
    load()
  }

  return (
    <div>
      <div className="page-header">
        <h1><span className="page-icon"><Sparkles size={22} strokeWidth={1.75} /></span>AI 中心</h1>
        <div className="row">
          <span className="badge badge-info">共 {rows.length} 条记录</span>
          <button className="btn btn-danger" onClick={clear}><Trash2 size={14} strokeWidth={1.8} /> 清空历史</button>
        </div>
      </div>

      <div className="card">
        <div className="card-title">AI 调用历史（最近 60 条）</div>
        {rows.length === 0 && (
          <div className="empty">
            <span className="empty-icon">✨</span>
            暂无 AI 调用记录。使用任意 AI 功能（每日整理/复盘点评/文献总结/规划助手等）后，这里会自动保存结果，方便回看与复制。
          </div>
        )}
        {rows.map(r => (
          <div key={r.id} className="d-item" style={{ alignItems: 'flex-start' }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div className="d-item-title">
                <span className="badge badge-primary">{r.feature_label}</span>
                <span className="muted" style={{ fontSize: 12, fontWeight: 400 }}>{r.created_at?.slice(0, 16).replace('T', ' ')}</span>
              </div>
              {r.summary && <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>输入：{r.summary}</div>}
              {expanded === r.id ? (
                <div className="summ" style={{ marginTop: 6, whiteSpace: 'pre-wrap' }}>{r.result}</div>
              ) : (
                <div className="muted" style={{ fontSize: 12, marginTop: 2, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: '100%' }}>{r.result}</div>
              )}
            </div>
            <div className="row" style={{ gap: 4 }}>
              <button className="btn btn-sm" onClick={() => setExpanded(expanded === r.id ? null : r.id)}>
                {expanded === r.id ? '收起' : '展开'}
              </button>
              <CopyBtn text={r.result} />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}