import React, { useEffect, useRef, useState } from 'react'
import api, { todayStr } from '../api'
import { useToast } from '../components/Toast'
import CopyBtn from '../components/CopyBtn'
import ReactMarkdown from 'react-markdown'
import MdCodeBlock from '../components/MdCodeBlock'
import { FileText, MessagesSquare, Save, Sparkles } from 'lucide-react'

export default function Meeting() {
  const [text, setText] = useState('')
  const [result, setResult] = useState('')
  const [loading, setLoading] = useState(false)
  const [history, setHistory] = useState([])
  const fileRef = useRef(null)
  const toast = useToast()

  const preprocess = c => c.replace(/\[\[([^\]]+)\]\]/g, (m, t) => `[${t}](wiki:${encodeURIComponent(t)})`)
  const mdComponents = {
    a: ({ href, children, ...rest }) => {
      if (href && href.startsWith('wiki:')) {
        const target = decodeURIComponent(href.slice(5))
        return (
          <a href="#" className="wiki-link" title={`打开笔记：${target}`}
            onClick={e => { e.preventDefault(); window.location.hash = `#/notes?highlight_title=${encodeURIComponent(target)}` }}>
            {children}
          </a>
        )
      }
      return <a href={href} {...rest}>{children}</a>
    },
    pre: ({ children }) => <MdCodeBlock>{children}</MdCodeBlock>,
  }

  const loadHistory = () => {
    api.get('/notes').then(r => setHistory(r.data.filter(n => n.folder === '组会纪要').slice(0, 10))).catch(() => {})
  }
  useEffect(loadHistory, [])

  const generate = async () => {
    if (!text.trim()) return toast('请输入或上传会议内容', 'error')
    setLoading(true)
    setResult('')
    try {
      const r = await api.post('/ai/meeting-notes', { text })
      setResult(r.data.result)
      toast('纪要已生成')
    } catch (e) {
      setResult(e.response?.data?.detail || 'AI 调用失败，请检查 API Key')
    } finally {
      setLoading(false)
    }
  }

  const onFile = async e => {
    const file = e.target.files?.[0]
    if (!file) return
    const t = await file.text()
    setText(prev => `${prev}${prev ? '\n' : ''}${t}`)
    toast('文件内容已导入')
    e.target.value = ''
  }

  const saveToNote = async () => {
    if (!result) return
    try {
      await api.post('/notes', { title: `组会纪要 ${todayStr()}`, content: result, folder: '组会纪要' })
      toast('已保存为笔记')
      loadHistory()
    } catch (e) { toast('保存失败', 'error') }
  }

  const loadNote = async id => {
    try {
      const r = await api.get(`/notes/${id}`)
      setResult(r.data.content)
      toast('已载入历史纪要')
    } catch (e) { toast('载入失败', 'error') }
  }

  return (
    <div>
      <div className="page-header">
        <h1><span className="page-icon"><MessagesSquare size={22} strokeWidth={1.75} /></span>组会纪要</h1>
        <button className="btn" onClick={() => fileRef.current?.click()}><FileText size={14} strokeWidth={1.8} /> 导入文本文件</button>
        <input ref={fileRef} type="file" accept=".txt,.md" style={{ display: 'none' }} onChange={onFile} />
      </div>

      <div className="grid grid-2">
        <div className="card">
          <div className="card-title">会议内容</div>
          <textarea
            className="textarea"
            style={{ minHeight: 320 }}
            placeholder="粘贴组会录音转写文字、讨论内容等..."
            value={text}
            onChange={e => setText(e.target.value)}
          />
          <div className="row" style={{ marginTop: 10, justifyContent: 'flex-end' }}>
            <button className="btn btn-primary" onClick={generate} disabled={loading}>
              {loading ? 'AI 生成中...' : (<><Sparkles size={14} strokeWidth={1.8} /> 生成纪要</>)}
            </button>
          </div>
        </div>

        <div className="card">
          <div className="card-title">生成的纪要</div>
          {loading && <div className="empty"><span className="spin" /> 正在整理纪要...</div>}
          {!loading && !result && <div className="empty"><span className="empty-icon">🗣</span>输入会议内容后点击「生成纪要」</div>}
          {result && (
            <>
              {/* C19：AI 纪要渲染为 Markdown（标题/列表/加粗），复制仍保留原始文本 */}
              <div className="md-body" style={{ fontSize: 13, lineHeight: 1.7 }}>
                <ReactMarkdown urlTransform={u => u} components={mdComponents}>{preprocess(result)}</ReactMarkdown>
              </div>
              <div className="row" style={{ marginTop: 12, justifyContent: 'flex-end' }}>
                <CopyBtn text={result} />
                <button className="btn btn-primary btn-sm" onClick={saveToNote}><Save size={14} strokeWidth={1.8} /> 保存为笔记</button>
              </div>
            </>
          )}
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <div className="card-title">📚 历史纪要（最近 10 条，保存在「组会纪要」文件夹）</div>
        {history.length === 0 && <div className="empty"><span className="empty-icon">📋</span>还没有历史纪要，生成后点「保存为笔记」会出现在这里</div>}
        {history.map(h => (
          <div key={h.id} className="row" style={{ padding: '8px 0', borderBottom: '1px solid var(--border)' }}>
            <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{h.title}</span>
            <span className="muted" style={{ fontSize: 12 }}>{h.updated_at?.slice(0, 10)}</span>
            <button className="btn btn-sm" onClick={() => loadNote(h.id)}>载入</button>
          </div>
        ))}
      </div>
    </div>
  )
}
