import React, { useEffect, useState } from 'react'
import api, { todayStr } from '../api'
import { useToast } from '../components/Toast'
import CopyBtn from '../components/CopyBtn'
import ReactMarkdown from 'react-markdown'
import { FileText, ListTree, Pencil, PenLine, Rocket, Save, Sparkles } from 'lucide-react'

const STATUS = {
  planning: ['规划', 'badge-gray'],
  writing: ['写作中', 'badge-info'],
  draft: ['初稿完成', 'badge-warn'],
  polish: ['润色中', 'badge-warn'],
  submitted: ['已投稿', 'badge-primary'],
  revision: ['返修中', 'badge-info'],
  accepted: ['已接收', 'badge-success'],
}
const FLOW = ['planning', 'writing', 'draft', 'polish', 'submitted', 'revision', 'accepted']

// ④ 论文写作助手：大纲 → 章节初稿 → 润色，结果可一键存为笔记
function PaperAiModal({ paper, onClose }) {
  const [step, setStep] = useState('outline')
  const [direction, setDirection] = useState('')
  const [chapter, setChapter] = useState('')
  const [polishText, setPolishText] = useState('')
  const [polishMode, setPolishMode] = useState('polish')
  const [result, setResult] = useState('')
  const [loading, setLoading] = useState(false)
  const [aiCtrl, setAiCtrl] = useState(null)
  const toast = useToast()

  const run = async (endpoint, payload) => {
    setLoading(true); setResult('')
    const ctrl = new AbortController(); setAiCtrl(ctrl)
    try {
      const r = await api.post(endpoint, payload, { signal: ctrl.signal })
      setResult(r.data.result)
    } catch (e) {
      if (e.code !== 'ERR_CANCELED') toast(e.response?.data?.detail || 'AI 调用失败，请检查 API Key', 'error')
    } finally {
      setLoading(false); setAiCtrl(null)
    }
  }

  const genOutline = () => run('/ai/paper-outline', { title: paper.title, direction, notes: paper.notes })
  const genChapter = () => run('/ai/paper-chapter', { title: paper.title, chapter, notes: paper.notes })
  const genPolish = () => run('/ai/paper-polish', { text: polishText, mode: polishMode })

  const saveAsNote = async () => {
    try {
      const title = step === 'chapter' ? `${paper.title} · ${chapter}` : step === 'outline' ? `${paper.title} · 大纲` : `${paper.title} · 润色`
      await api.post('/notes', { title, content: result, folder: '论文' })
      toast('已保存为笔记（论文文件夹）')
    } catch (e) { toast('保存失败', 'error') }
  }

  return (
    <div className="modal-mask" onClick={onClose}>
      <div className="modal" style={{ maxWidth: 780, maxHeight: '90vh', overflowY: 'auto' }} onClick={e => e.stopPropagation()}>
        <h3>✍ AI 写作助手：{paper.title.slice(0, 30)}</h3>
        <div className="row" style={{ gap: 6, marginBottom: 12 }}>
          {[['outline', ListTree, '生成大纲'], ['chapter', Pencil, '章节写作'], ['polish', Sparkles, '润色/翻译']].map(([k, Icon, l]) => (
            <button key={k} className={`btn btn-sm ${step === k ? 'btn-primary' : ''}`} onClick={() => { setStep(k); setResult(''); setAiCtrl(null) }}><Icon size={14} strokeWidth={1.8} /> {l}</button>
          ))}
        </div>

        {step === 'outline' && (
          <>
            <label className="label">研究方向/侧重（可空，默认参考你的科研画像）</label>
            <input className="input" value={direction} onChange={e => setDirection(e.target.value)} placeholder="如 红外小目标检测、轻量化注意力..." />
            <div className="row" style={{ marginTop: 10, justifyContent: 'flex-end' }}>
              <button className="btn btn-primary" onClick={genOutline} disabled={loading}>{loading ? '生成中...' : (<><Rocket size={14} strokeWidth={1.8} /> 生成大纲</>)}</button>
            </div>
          </>
        )}
        {step === 'chapter' && (
          <>
            <label className="label">章节名称</label>
            <input className="input" value={chapter} onChange={e => setChapter(e.target.value)} placeholder="如 引言 / 相关工作 / 方法：注意力增强的小目标检测 / 实验" />
            <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>会自动检索你的知识库（笔记/文献/实验）作为参考素材。</div>
            <div className="row" style={{ marginTop: 10, justifyContent: 'flex-end' }}>
              <button className="btn btn-primary" onClick={genChapter} disabled={loading || !chapter.trim()}>{loading ? '写作中...' : (<><Pencil size={14} strokeWidth={1.8} /> 生成初稿</>)}</button>
            </div>
          </>
        )}
        {step === 'polish' && (
          <>
            <label className="label">论文文字</label>
            <textarea className="textarea" style={{ minHeight: 120 }} value={polishText} onChange={e => setPolishText(e.target.value)} placeholder="粘贴需要润色/翻译的段落..." />
            <div className="row" style={{ marginTop: 8 }}>
              {[['polish', '学术润色'], ['translate_en', '中译英'], ['translate_zh', '英译中']].map(([k, l]) => (
                <button key={k} className={`btn btn-sm ${polishMode === k ? 'btn-primary' : ''}`} onClick={() => setPolishMode(k)}>{l}</button>
              ))}
            </div>
            <div className="row" style={{ marginTop: 10, justifyContent: 'flex-end' }}>
              <button className="btn btn-primary" onClick={genPolish} disabled={loading || !polishText.trim()}>{loading ? '处理中...' : (<><Sparkles size={14} strokeWidth={1.8} /> 处理</>)}</button>
            </div>
          </>
        )}

        {loading && <div className="empty" style={{ marginTop: 12 }}><span className="spin" /> AI 生成中，可能需要 1-2 分钟...</div>}
        {result && !loading && (
          <div style={{ marginTop: 14, borderTop: '1px solid var(--border)', paddingTop: 12 }}>
            <div className="row" style={{ justifyContent: 'space-between', marginBottom: 8 }}>
              <b>结果</b>
              <div className="row" style={{ gap: 6 }}>
                <CopyBtn text={result} />
                <button className="btn btn-sm btn-primary" onClick={saveAsNote}><Save size={14} strokeWidth={1.8} /> 存为笔记</button>
              </div>
            </div>
            <div className="card md-body" style={{ maxHeight: 360, overflowY: 'auto' }}>
              <ReactMarkdown>{result}</ReactMarkdown>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function PaperForm({ initial, onClose, onSaved }) {
  const [form, setForm] = useState({
    title: initial?.title || '',
    venue: initial?.venue || '',
    status: initial?.status || 'planning',
    submitted_at: initial?.submitted_at || '',
    notes: initial?.notes || '',
  })
  const toast = useToast()
  const set = k => v => setForm(f => ({ ...f, [k]: v }))
  const submit = async () => {
    if (!form.title.trim()) return toast('请输入论文标题', 'error')
    const payload = { ...form, submitted_at: form.submitted_at || null }
    try {
      if (initial?.id) await api.put(`/research/papers/${initial.id}`, payload)
      else await api.post('/research/papers', payload)
      onSaved(); onClose()
    } catch (e) { toast('保存失败', 'error') }
  }
  return (
    <div className="modal-mask" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <h3>{initial ? '编辑论文' : '新建论文'}</h3>
        <label className="label">论文标题 *</label>
        <input className="input" value={form.title} onChange={e => set('title')(e.target.value)} />
        <div className="row">
          <div style={{ flex: 1 }}><label className="label">目标会议/期刊</label><input className="input" placeholder="如 CVPR/TPAMI" value={form.venue} onChange={e => set('venue')(e.target.value)} /></div>
          <div style={{ flex: 1 }}><label className="label">阶段</label>
            <select className="select" value={form.status} onChange={e => set('status')(e.target.value)}>
              {FLOW.map(s => <option key={s} value={s}>{STATUS[s][0]}</option>)}
            </select>
          </div>
        </div>
        <label className="label">投稿日期</label>
        <input type="date" className="input" value={form.submitted_at} onChange={e => set('submitted_at')(e.target.value)} />
        <label className="label">备注</label>
        <textarea className="textarea" value={form.notes} onChange={e => set('notes')(e.target.value)} />
        <div className="modal-actions">
          <button className="btn" onClick={onClose}>取消</button>
          <button className="btn btn-primary" onClick={submit}>保存</button>
        </div>
      </div>
    </div>
  )
}

export default function Papers() {
  const [items, setItems] = useState([])
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState(null)
  const [aiFor, setAiFor] = useState(null)
  const toast = useToast()

  const load = () => {
    api.get('/research/papers').then(r => setItems(r.data))
  }
  useEffect(load, [])

  const setStatus = async (p, s) => {
    // C17：切到「已投稿」且没有投稿日期时，自动记录今天
    const payload = { status: s }
    if (s === 'submitted' && !p.submitted_at) payload.submitted_at = todayStr()
    try {
      await api.put(`/research/papers/${p.id}`, payload)
      if (payload.submitted_at) toast('已自动记录投稿日期')
      load()
    } catch (e) { toast('保存失败', 'error') }
  }
  const del = async p => {
    if (!confirm(`删除论文「${p.title}」？`)) return
    await api.delete(`/research/papers/${p.id}`)
    toast('已删除'); load()
  }

  return (
    <div>
      <div className="page-header">
        <h1><span className="page-icon"><FileText size={22} strokeWidth={1.75} /></span>论文进度</h1>
        <button className="btn btn-primary" onClick={() => setShowForm(true)}>+ 新建论文</button>
      </div>

      {items.length === 0 && <div className="card empty">还没有论文，从第一篇开始规划吧</div>}

      {items.map(p => {
        const curIdx = FLOW.indexOf(p.status)
        return (
          <div className="card" key={p.id} style={{ marginBottom: 14 }}>
            <div className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div style={{ flex: 1 }}>
                <strong style={{ fontSize: 15 }}>{p.title}</strong>
                <div className="muted" style={{ marginTop: 4 }}>
                  {p.venue ? `${p.venue} · ` : ''}更新于 {p.updated_at?.slice(0, 10)}
                </div>
              </div>
              <div className="row" style={{ gap: 6 }}>
                <select className="select" style={{ width: 110, padding: '4px 8px' }} value={p.status} onChange={e => setStatus(p, e.target.value)}>
                  {FLOW.map(s => <option key={s} value={s}>{STATUS[s][0]}</option>)}
                </select>
                <button className="btn btn-sm btn-primary" onClick={() => setAiFor(p)}><PenLine size={14} strokeWidth={1.8} /> AI 写作</button>
                <button className="btn btn-sm" onClick={() => setEditing(p)}>编辑</button>
                <button className="btn btn-sm btn-danger" onClick={() => del(p)}>删除</button>
              </div>
            </div>

            <div className="paper-flow">
              {FLOW.map((s, i) => (
                <React.Fragment key={s}>
                  <div className={`flow-node ${i <= curIdx ? 'done' : ''} ${i === curIdx ? 'current' : ''}`} onClick={() => setStatus(p, s)} title={`设为「${STATUS[s][0]}」`}>
                    <span className="flow-dot" />
                    <span className="flow-label">{STATUS[s][0]}</span>
                  </div>
                  {i < FLOW.length - 1 && <div className={`flow-line ${i < curIdx ? 'done' : ''}`} />}
                </React.Fragment>
              ))}
            </div>

            {p.notes && <div className="muted" style={{ marginTop: 8 }}>{p.notes}</div>}
          </div>
        )
      })}

      {showForm && <PaperForm initial={null} onClose={() => setShowForm(false)} onSaved={() => { setShowForm(false); load() }} />}
      {editing && <PaperForm initial={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load() }} />}
      {aiFor && <PaperAiModal paper={aiFor} onClose={() => setAiFor(null)} />}
    </div>
  )
}
