import React, { useEffect, useRef, useState } from 'react'
import api from '../api'
import { useToast } from '../components/Toast'
import CopyBtn from '../components/CopyBtn'
import { MessageSquare, Trash2 } from 'lucide-react'

export default function Chat() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const toast = useToast()
  const bodyRef = useRef(null)

  // 自动滚动到底部
  useEffect(() => {
    bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight })
  }, [messages, loading])

  const send = async () => {
    const text = input.trim()
    if (!text || loading) return
    setInput('')
    const next = [...messages, { role: 'user', content: text }]
    setMessages(next)
    setLoading(true)
    try {
      const r = await api.post('/ai/chat', { messages: next.slice(-6) })
      setMessages(m => [...m, { role: 'assistant', content: r.data.result }])
    } catch (e) {
      setMessages(m => [...m, { role: 'assistant', content: `⚠️ ${e.response?.data?.detail || 'AI 调用失败'}` }])
      toast(e.response?.data?.detail || 'AI 调用失败', 'error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <div className="page-header">
        <h1><span className="page-icon"><MessageSquare size={22} strokeWidth={1.75} /></span>AI 助手</h1>
        <div className="row">
          <span className="muted">自动结合你的知识库（笔记/文献/实验）与科研画像回答</span>
          {messages.length > 0 && <button className="btn btn-sm" onClick={() => setMessages([])}><Trash2 size={14} strokeWidth={1.8} /> 清空对话</button>}
        </div>
      </div>

      <div className="card" style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 220px)', minHeight: 420 }}>
        <div ref={bodyRef} style={{ flex: 1, overflowY: 'auto', padding: 4 }}>
          {messages.length === 0 && (
            <div className="empty" style={{ marginTop: 60 }}>
              <span className="empty-icon">💬</span>
              <div style={{ marginBottom: 14 }}>可以问我关于科研、代码、论文、文献的问题，例如：</div>
              <div className="row" style={{ justifyContent: 'center', gap: 8, flexWrap: 'wrap' }}>
                {['红外小目标检测的主流方法有哪些？', '帮我解释一下注意力机制', '我的笔记里提到过什么关于 DNANet 的内容？', '论文摘要怎么写更吸引人？'].map(s => (
                  <button key={s} className="btn btn-sm" onClick={() => setInput(s)}>{s}</button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className="row" style={{ justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start', marginBottom: 10 }}>
              <div
                className={m.role === 'user' ? 'chat-bubble user' : 'chat-bubble ai'}
                style={{ maxWidth: '78%', whiteSpace: 'pre-wrap' }}
              >
                {m.content}
                {m.role === 'assistant' && <div style={{ marginTop: 6 }}><CopyBtn text={m.content} /></div>}
              </div>
            </div>
          ))}
          {loading && (
            <div className="row" style={{ justifyContent: 'flex-start', marginBottom: 10 }}>
              <div className="chat-bubble ai"><span className="spin" /> 思考中...</div>
            </div>
          )}
        </div>
        <div className="row" style={{ marginTop: 12, borderTop: '1px solid var(--border)', paddingTop: 12 }}>
          <input
            className="input"
            style={{ flex: 1 }}
            placeholder="输入问题，回车发送（可问科研/代码/文献/论文）"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.nativeEvent.isComposing) send() }}
          />
          <button className="btn btn-primary" onClick={send} disabled={loading}>{loading ? '发送中...' : '发送'}</button>
        </div>
      </div>
    </div>
  )
}