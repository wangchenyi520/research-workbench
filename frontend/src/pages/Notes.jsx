import React, { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import api, { todayStr } from '../api'
import { useToast } from '../components/Toast'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import 'katex/dist/katex.min.css'
import MdCodeBlock from '../components/MdCodeBlock'
import { ArrowUpRight, Camera, Check, ClipboardList, Crop, FileDown, FileUp, Link2, ListTree, Mic, NotebookPen, Paperclip, Pencil, RefreshCw, Sparkles, Square, Trash2, Undo2, X } from 'lucide-react'

const FOLDER_COLORS = ['#7c6cf0', '#3aa8ff', '#2fc98e', '#f5a623', '#ec4899', '#ef4444']
const folderColor = f => {
  let h = 0
  for (const ch of (f || '')) h = (h * 31 + ch.charCodeAt(0)) % 997
  return FOLDER_COLORS[h % FOLDER_COLORS.length]
}

const NOTE_TEMPLATES = [
  ['空白', ''],
  ['组会纪要', `# 组会纪要 ${new Date().toISOString().slice(0, 10)}

## 讨论主题
## 汇报进展
## 讨论要点
## 结论与决定
## 行动项（下一步）
`],
  ['周复盘', `# 周复盘

## 本周完成
## 本周进展（科研/学习）
## 问题与卡点
## 下周计划
`],
  ['文献精读', `# 文献精读

## 基本信息
- 标题：
- 作者/年份/期刊：
- 领域关键词：

## 解决的问题 / 动机
## 方法（核心思路）
## 关键实验与结果
## 我的评价与启发
## 可复现/可借鉴的点
`],
  ['实验记录', `# 实验记录

## 实验目的
## 数据集 / 配置
## 方法 / 模型
## 指标对比
| 方法 | mAP | IoU | 备注 |
| --- | --- | --- | --- |
|  |  |  |  |

## 问题与下一步
`],
  ['开题报告', `# 开题报告草稿

## 研究背景与意义
## 国内外研究现状
## 研究内容与方法
## 创新点
## 进度安排
`],
]

const loadCustomTemplates = () => {
  try { return JSON.parse(localStorage.getItem('wb_note_templates') || '[]') } catch (e) { return [] }
}

function ImageEditor({ src, onSave, onClose }) {
  const canvasRef = useRef(null)
  const imgRef = useRef(null)
  const [color, setColor] = useState('#ff3b30')
  const [tool, setTool] = useState('arrow') // arrow/text/rect/pen
  const [text, setText] = useState('')
  const [fontSize, setFontSize] = useState(20)
  const drawingRef = useRef({ dragging: false, startX: 0, startY: 0 })
  const objectsRef = useRef([])

  useEffect(() => {
    const img = new Image()
    img.onload = () => {
      const cv = canvasRef.current
      const maxW = 800
      const scale = img.width > maxW ? maxW / img.width : 1
      cv.width = img.width * scale
      cv.height = img.height * scale
      const ctx = cv.getContext('2d')
      ctx.drawImage(img, 0, 0, cv.width, cv.height)
      imgRef.current = img
    }
    img.src = src
  }, [src])

  const getPos = e => {
    const cv = canvasRef.current
    const rect = cv.getBoundingClientRect()
    return { x: (e.clientX - rect.left) * (cv.width / rect.width), y: (e.clientY - rect.top) * (cv.height / rect.height) }
  }

  const redraw = () => {
    const cv = canvasRef.current
    const ctx = cv.getContext('2d')
    ctx.clearRect(0, 0, cv.width, cv.height)
    ctx.drawImage(imgRef.current, 0, 0, cv.width, cv.height)
    for (const obj of objectsRef.current) {
      ctx.strokeStyle = obj.color
      ctx.fillStyle = obj.color
      ctx.lineWidth = obj.width || 3
      ctx.font = `${obj.fontSize || 20}px sans-serif`
      if (obj.type === 'arrow') {
        const a = obj.a, b = obj.b
        ctx.beginPath()
        ctx.moveTo(a.x, a.y)
        ctx.lineTo(b.x, b.y)
        ctx.stroke()
        const angle = Math.atan2(b.y - a.y, b.x - a.x)
        const len = 12
        ctx.beginPath()
        ctx.moveTo(b.x, b.y)
        ctx.lineTo(b.x - len * Math.cos(angle - 0.4), b.y - len * Math.sin(angle - 0.4))
        ctx.lineTo(b.x - len * Math.cos(angle + 0.4), b.y - len * Math.sin(angle + 0.4))
        ctx.closePath()
        ctx.fill()
      } else if (obj.type === 'rect') {
        ctx.strokeRect(obj.a.x, obj.a.y, obj.b.x - obj.a.x, obj.b.y - obj.a.y)
      } else if (obj.type === 'pen') {
        ctx.lineWidth = obj.width || 3
        ctx.lineCap = 'round'
        ctx.lineJoin = 'round'
        ctx.beginPath()
        ctx.moveTo(obj.points[0].x, obj.points[0].y)
        for (const p of obj.points.slice(1)) ctx.lineTo(p.x, p.y)
        ctx.stroke()
      } else if (obj.type === 'text') {
        ctx.fillText(obj.text, obj.a.x, obj.a.y)
      }
    }
  }

  useEffect(redraw)

  const onDown = e => {
    const p = getPos(e)
    const ref = drawingRef.current
    ref.dragging = true
    ref.startX = p.x
    ref.startY = p.y
    if (tool === 'pen') objectsRef.current.push({ type: 'pen', points: [p], color, width: 3 })
    if (tool === 'arrow' || tool === 'rect') objectsRef.current.push({ type: tool, a: { ...p }, b: { ...p }, color, width: 3 })
    if (tool === 'text' && text) {
      objectsRef.current.push({ type: 'text', a: { x: p.x, y: p.y }, text, color, fontSize })
    }
  }
  const onMove = e => {
    const ref = drawingRef.current
    if (!ref.dragging) return
    const p = getPos(e)
    const objs = objectsRef.current
    const last = objs[objs.length - 1]
    if (last) {
      if (last.type === 'pen') last.points.push(p)
      else last.b = { ...p }
    }
  }
  const onUp = () => { drawingRef.current.dragging = false }

  const undo = () => { objectsRef.current.pop(); redraw() }
  const rotate = () => {
    const cv = canvasRef.current
    const off = document.createElement('canvas')
    off.width = cv.height
    off.height = cv.width
    const octx = off.getContext('2d')
    octx.translate(off.width / 2, off.height / 2)
    octx.rotate(Math.PI / 2)
    octx.drawImage(cv, -cv.width / 2, -cv.height / 2)
    cv.width = off.width
    cv.height = off.height
    const ctx = cv.getContext('2d')
    ctx.drawImage(off, 0, 0)
    objectsRef.current = []
    imgRef.current = off
    redraw()
  }
  const crop = () => {
    const cv = canvasRef.current
    const off = document.createElement('canvas')
    off.width = Math.floor(cv.width * 0.8)
    off.height = Math.floor(cv.height * 0.8)
    off.getContext('2d').drawImage(cv, 0, 0, off.width, off.height)
    cv.width = off.width
    cv.height = off.height
    cv.getContext('2d').drawImage(off, 0, 0)
    objectsRef.current = []
    imgRef.current = off
    redraw()
  }

  const save = () => {
    const cv = canvasRef.current
    cv.toBlob(async blob => {
      const fd = new FormData()
      fd.append('file', blob, 'edit.png')
      const r = await api.post('/notes/images', fd)
      onSave(r.data.url)
    }, 'image/png')
  }

  return (
    <div className="modal-mask">
      <div className="modal" style={{ maxWidth: 880 }}>
        <h3>图片编辑</h3>
        <div className="row" style={{ marginBottom: 10, flexWrap: 'wrap' }}>
          {['arrow', 'text', 'rect', 'pen'].map(t => (
            <button key={t} className={`btn btn-sm ${tool === t ? 'btn-primary' : ''}`} onClick={() => setTool(t)}>
              {t === 'arrow' ? (<><ArrowUpRight size={14} strokeWidth={1.8} /> 箭头</>) : t === 'text' ? 'A 文字' : t === 'rect' ? (<><Square size={14} strokeWidth={1.8} /> 框选</>) : (<><Pencil size={14} strokeWidth={1.8} /> 画笔</>)}
            </button>
          ))}
          <input type="color" value={color} onChange={e => setColor(e.target.value)} style={{ width: 36, height: 30 }} />
          {tool === 'text' && (
            <>
              <input className="input" style={{ width: 120 }} placeholder="输入文字" value={text} onChange={e => setText(e.target.value)} />
              <input type="number" className="input" style={{ width: 70 }} value={fontSize} onChange={e => setFontSize(Number(e.target.value))} />
            </>
          )}
          <button className="btn btn-sm" onClick={undo}><Undo2 size={14} strokeWidth={1.8} /> 撤销</button>
          <button className="btn btn-sm" onClick={rotate}><RefreshCw size={14} strokeWidth={1.8} /> 旋转90°</button>
          <button className="btn btn-sm" onClick={crop}><Crop size={14} strokeWidth={1.8} /> 裁剪</button>
        </div>
        <canvas
          ref={canvasRef}
          style={{ maxWidth: '100%', cursor: 'crosshair', border: '1px solid var(--border)', borderRadius: 8 }}
          onMouseDown={onDown}
          onMouseMove={onMove}
          onMouseUp={onUp}
          onMouseLeave={onUp}
        />
        <div className="modal-actions">
          <button className="btn" onClick={onClose}>取消</button>
          <button className="btn btn-primary" onClick={save}>保存</button>
        </div>
      </div>
    </div>
  )
}

function NoteEditor({ note, goals, defaultFolder = '', onOpenNote, onClose, onSaved }) {
  const [content, setContent] = useState(note?.content || '')
  const [title, setTitle] = useState(note?.title || '')
  const [goalId, setGoalId] = useState(note?.goal_id || '')
  const [folder, setFolder] = useState(note?.folder || defaultFolder)
  const [view, setView] = useState('edit') // edit/preview
  const [editing, setEditing] = useState(null)
  const [recording, setRecording] = useState(false)
  const toast = useToast()
  const fileRef = useRef(null)
  const mediaRef = useRef(null)
  const chunksRef = useRef([])
  const [customTemplates, setCustomTemplates] = useState(loadCustomTemplates)
  const [backlinks, setBacklinks] = useState([])
  const [blOpen, setBlOpen] = useState(false)
  const [attachments, setAttachments] = useState([])
  const attachRef = useRef(null)
  const [tocOpen, setTocOpen] = useState(false)

  // 预览大纲：从 markdown 提取 # 标题
  const toc = useMemo(() => {
    const rows = []
    const re = /^(#{1,3})\s+(.+)$/gm
    let m
    while ((m = re.exec(content))) {
      rows.push({ level: m[1].length, text: m[2].trim().replace(/[*_`#]/g, ''), slug: m[2].trim() })
    }
    return rows
  }, [content])

  const tocClick = slug => {
    document.getElementById(slug)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  useEffect(() => {
    if (note?.id) {
      api.get(`/notes/${note.id}/backlinks`).then(r => setBacklinks(r.data)).catch(() => setBacklinks([]))
      api.get(`/notes/${note.id}/attachments`).then(r => setAttachments(r.data)).catch(() => setAttachments([]))
    } else {
      setBacklinks([])
      setAttachments([])
    }
  }, [note?.id])

  const onAttach = async e => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    if (!note?.id) {
      toast('请先保存笔记再上传附件', 'error')
      return
    }
    try {
      const fd = new FormData()
      fd.append('file', file)
      const r = await api.post(`/notes/${note.id}/attachments`, fd)
      setAttachments(a => [r.data, ...a])
      toast(`已上传「${file.name}」`)
    } catch (err) {
      toast(err.response?.data?.detail || '上传失败', 'error')
    }
  }

  const delAttach = async a => {
    if (!confirm(`删除附件「${a.original_name}」？`)) return
    try {
      await api.delete(`/notes/attachments/${a.id}`)
      setAttachments(list => list.filter(x => x.id !== a.id))
      toast('已删除附件')
    } catch (err) { toast('删除失败', 'error') }
  }

  const applyTemplate = tpl => {
    setContent(tpl)
    const first = tpl.split('\n').find(l => l.trim().startsWith('# '))
    if (first && !title.trim()) setTitle(first.replace(/^#\s+/, '').trim())
  }
  const saveAsTemplate = () => {
    if (!content.trim()) return toast('笔记内容为空，无法存为模板', 'error')
    const name = title.trim() || `模板 ${customTemplates.length + 1}`
    const next = [...customTemplates, [name, content]]
    setCustomTemplates(next)
    localStorage.setItem('wb_note_templates', JSON.stringify(next))
    toast(`已存为模板「${name}」`)
  }

  const preprocess = c => c.replace(/\[\[([^\]]+)\]\]/g, (m, t) => `[${t}](wiki:${t})`)
  const mdComponents = {
    a: ({ href, children, ...rest }) => {
      if (href && href.startsWith('wiki:')) {
        const target = decodeURIComponent(href.slice(5))
        return (
          <a
            className="wiki-link"
            href="#"
            onClick={e => { e.preventDefault(); onOpenNote?.(target) }}
            title={`打开笔记：${target}`}
          >
            {children}
          </a>
        )
      }
      return <a href={href} {...rest}>{children}</a>
    },
    // 图片预览可点击 → 打开 Canvas 编辑器（箭头/文字/框选/画笔/裁剪/旋转）
    img: ({ src, ...rest }) => (
      <img
        src={src}
        {...rest}
        style={{ cursor: 'pointer', maxWidth: '100%' }}
        onClick={e => { e.preventDefault(); e.stopPropagation(); setEditing(src) }}
        title="点击编辑图片（箭头/文字/画笔/裁剪）"
      />
    ),
    pre: ({ children }) => <MdCodeBlock>{children}</MdCodeBlock>,
    // 标题加 id 供大纲跳转
    h1: ({ children, ...rest }) => <h1 id={String(children ?? '').trim()} {...rest}>{children}</h1>,
    h2: ({ children, ...rest }) => <h2 id={String(children ?? '').trim()} {...rest}>{children}</h2>,
    h3: ({ children, ...rest }) => <h3 id={String(children ?? '').trim()} {...rest}>{children}</h3>,
  }

  const save = async () => {
    const payload = { title, content, folder, goal_id: goalId || null }
    try {
      if (note?.id) {
        await api.put(`/notes/${note.id}`, payload)
      } else {
        await api.post('/notes', payload)
      }
      onSaved()
      onClose()
    } catch (err) {
      toast('保存笔记失败，请重试', 'error')
    }
  }

  const toggleRecord = async () => {
    if (recording) {
      mediaRef.current?.stop()
      return
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const rec = new MediaRecorder(stream)
      chunksRef.current = []
      rec.ondataavailable = e => chunksRef.current.push(e.data)
      rec.onstop = async () => {
        stream.getTracks().forEach(t => t.stop())
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' })
        const fd = new FormData()
        fd.append('file', blob, 'voice.webm')
        toast('正在转写语音（首次需下载模型）...')
        try {
          const r = await api.post('/voice/transcribe', fd)
          if (r.data.text) {
            setContent(c => `${c}${c ? '\n' : ''}${r.data.text}`)
            toast('语音已转写')
          } else {
            toast('未识别到内容', 'error')
          }
        } catch (e) {
          toast(e.response?.data?.detail || '转写失败', 'error')
        }
      }
      rec.start()
      mediaRef.current = rec
      setRecording(true)
    } catch (e) {
      toast('无法访问麦克风', 'error')
    }
  }

  const onPaste = async e => {
    const items = e.clipboardData?.items || []
    for (const it of items) {
      if (it.type?.startsWith('image/')) {
        const file = it.getAsFile()
        try {
          const fd = new FormData()
          fd.append('file', file, 'paste.png')
          const r = await api.post('/notes/images', fd)
          setContent(c => `${c}\n![图片](${r.data.url})\n`)
          toast('图片已粘贴')
        } catch (err) { toast('图片上传失败', 'error') }
      }
    }
  }

  const onFile = async e => {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      const fd = new FormData()
      fd.append('file', file)
      const r = await api.post('/notes/images', fd)
      setContent(c => `${c}\n![图片](${r.data.url})\n`)
      toast('图片已插入')
    } catch (err) { toast('图片上传失败', 'error') }
  }

  const aiHelp = async () => {
    try {
      const r = await api.post('/ai/writing', { prompt: '请帮我润色并整理这段笔记，使其结构清晰', context: content })
      setContent(r.data.result)
      toast('AI 已处理')
    } catch (err) {
      toast(err.response?.data?.detail || 'AI 调用失败，请检查 API Key', 'error')
    }
  }

  const aiOrganize = async () => {
    if (!content.trim()) return toast('笔记内容为空', 'error')
    try {
      const r = await api.post('/ai/organize-note', { content })
      setContent(r.data.result)
      toast('AI 已整理')
    } catch (err) {
      toast(err.response?.data?.detail || 'AI 调用失败，请检查 API Key', 'error')
    }
  }

  return (
    <div className="modal-mask" style={{ alignItems: 'flex-start', overflowY: 'auto' }} onClick={onClose}>
      <div className="modal" style={{ maxWidth: 900, maxHeight: '92vh' }} onClick={e => e.stopPropagation()}>
        <div className="row" style={{ justifyContent: 'space-between', marginBottom: 12 }}>
          <input className="input" style={{ fontWeight: 700, fontSize: 17, flex: 1 }} value={title} placeholder="笔记标题" onChange={e => setTitle(e.target.value)} />
          <input className="input" style={{ width: 170 }} value={folder} placeholder="文件夹 如 文献/红外" onChange={e => setFolder(e.target.value)} />
          <select className="select" style={{ width: 180 }} value={goalId} onChange={e => setGoalId(e.target.value)}>
            <option value="">关联目标（可选）</option>
            {goals.map(g => <option key={g.id} value={g.id}>▲ {g.title}</option>)}
          </select>
        </div>
        {note?.id && backlinks.length > 0 && (
          <div style={{ marginBottom: 10 }}>
            <button className="btn btn-sm" onClick={() => setBlOpen(o => !o)}><Link2 size={14} strokeWidth={1.8} /> 被 {backlinks.length} 篇笔记引用 {blOpen ? '▾' : '▸'}</button>
            {blOpen && (
              <div style={{ marginTop: 6, border: '1px solid var(--border)', borderRadius: 8, padding: 8 }}>
                {backlinks.map(b => (
                  <div key={b.id} style={{ fontSize: 13, padding: '3px 0' }}>
                    <a href="#" className="wiki-link" onClick={e => { e.preventDefault(); onOpenNote(b.title) }}>📄 {b.title}</a>
                    {b.folder && <span className="muted" style={{ fontSize: 11 }}>（{b.folder}）</span>}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
        <div className="row" style={{ marginBottom: 10, gap: 6 }}>
          <button className={`btn btn-sm ${view === 'edit' ? 'btn-primary' : ''}`} onClick={() => setView('edit')}>编辑</button>
          <button className={`btn btn-sm ${view === 'preview' ? 'btn-primary' : ''}`} onClick={() => setView('preview')}>预览</button>
          {!note?.id && (
            <>
              <select className="select" style={{ width: 130 }} value="" onChange={e => { const tpl = e.target.value; if (tpl) applyTemplate(tpl) }} title="选择模板填充内容">
                <option value="">📋 模板</option>
                {[...NOTE_TEMPLATES, ...customTemplates].map(([name, body]) => <option key={name} value={body}>{name}</option>)}
              </select>
              <button className="btn btn-sm" onClick={saveAsTemplate} title="把当前内容存为自定义模板">＋ 存为模板</button>
            </>
          )}
          <button className="btn btn-sm" onClick={() => fileRef.current?.click()}><Camera size={14} strokeWidth={1.8} /> 插入图片</button>
          <button className="btn btn-sm" onClick={() => attachRef.current?.click()}><Paperclip size={14} strokeWidth={1.8} /> 附件</button>
          <input ref={attachRef} type="file" style={{ display: 'none' }} onChange={onAttach} />
          <button className={`btn btn-sm ${recording ? 'btn-danger' : ''}`} onClick={toggleRecord}>
            {recording ? (<><Square size={14} strokeWidth={1.8} /> 停止录音</>) : (<><Mic size={14} strokeWidth={1.8} /> 语音录入</>)}
          </button>
          <button className="btn btn-sm" onClick={aiHelp}><Sparkles size={14} strokeWidth={1.8} /> AI 润色</button>
          <button className="btn btn-sm" onClick={aiOrganize}><ClipboardList size={14} strokeWidth={1.8} /> AI 整理</button>
          <span className="muted">支持直接 Ctrl+V 粘贴剪贴板图片</span>
        </div>
        <input ref={fileRef} type="file" accept="image/*" style={{ display: 'none' }} onChange={onFile} />
        {attachments.length > 0 && (
          <div style={{ marginBottom: 10, border: '1px dashed var(--border)', borderRadius: 10, padding: 8 }}>
            <div className="muted" style={{ fontWeight: 600, marginBottom: 6 }}>📎 附件（{attachments.length}）</div>
            {attachments.map(a => (
              <div key={a.id} className="row" style={{ justifyContent: 'space-between', padding: '3px 0', gap: 8 }}>
                <a href={a.url} download={a.original_name} style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: 13 }}>📄 {a.original_name}</a>
                <span className="muted">{a.size > 1048576 ? `${(a.size / 1048576).toFixed(1)}MB` : `${Math.max(1, Math.round(a.size / 1024))}KB`}</span>
                <button className="btn btn-sm" onClick={() => delAttach(a)} title="删除附件"><X size={14} strokeWidth={1.8} /></button>
              </div>
            ))}
          </div>
        )}
        {view === 'preview' && toc.length > 0 && (
          <div style={{ marginBottom: 8 }}>
            <button className="btn btn-sm" onClick={() => setTocOpen(o => !o)}><ListTree size={14} strokeWidth={1.8} /> 大纲（{toc.length}）{tocOpen ? '▾' : '▸'}</button>
            {tocOpen && (
              <div style={{ marginTop: 6, border: '1px solid var(--border)', borderRadius: 8, padding: 8, maxHeight: 240, overflowY: 'auto' }}>
                {toc.map((h, i) => (
                  <div key={i} style={{ padding: '3px 0', cursor: 'pointer', fontSize: 13, paddingLeft: (h.level - 1) * 14 }} onClick={() => tocClick(h.slug)}>
                    {h.text}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
        <div onPaste={onPaste}>
          {view === 'edit' ? (
            <textarea
              className="textarea"
              style={{ minHeight: '50vh', fontFamily: 'monospace' }}
              value={content}
              onChange={e => setContent(e.target.value)}
            />
          ) : (
            <div className="card md-body" style={{ minHeight: '50vh' }}>
              <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]} urlTransform={u => u} components={mdComponents}>{preprocess(content)}</ReactMarkdown>
            </div>
          )}
        </div>
        <div className="modal-actions">
          <button className="btn" onClick={onClose}>取消</button>
          <button className="btn btn-primary" onClick={save}>保存</button>
        </div>
      </div>
      {editing && <ImageEditor src={editing} onClose={() => setEditing(null)} onSave={url => { setContent(c => c.replace(editing, url)); setEditing(null); }} />}
    </div>
  )
}

function buildTree(folders) {
  const root = { name: '', children: {} }
  folders.forEach(f => {
    if (!f) return
    const parts = f.split('/').filter(Boolean)
    let node = root
    parts.forEach(p => {
      if (!node.children[p]) node.children[p] = { name: p, children: {} }
      node = node.children[p]
    })
  })
  return root
}

function FolderTree({ tree, current, onSelect, depth = 0 }) {
  const entries = Object.values(tree.children)
  return (
    <>
      {entries.map(child => {
        const path = current.full ? `${current.full}/${child.name}` : child.name
        const hasKids = Object.keys(child.children).length > 0
        return (
          <div key={child.name}>
            <div
              className={`folder-item ${current.path === path ? 'active' : ''}`}
              style={{ paddingLeft: 8 + depth * 14 }}
              onClick={() => onSelect(path)}
            >
              <span>{hasKids ? '📁' : '📄'}</span> {child.name}
            </div>
            {hasKids && <FolderTree tree={child} current={{ path, full: path }} onSelect={onSelect} depth={depth + 1} />}
          </div>
        )
      })}
    </>
  )
}

export default function Notes() {
  const [notes, setNotes] = useState([])
  const [goals, setGoals] = useState([])
  const [editing, setEditing] = useState(null)
  const [creating, setCreating] = useState(false)
  const [currentPath, setCurrentPath] = useState('') // '' = 全部
  const [search, setSearch] = useState('')
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const [showTrash, setShowTrash] = useState(false)
  const [trash, setTrash] = useState([])
  const [noteTagPreview, setNoteTagPreview] = useState(null)
  const [tagApplying, setTagApplying] = useState(false)
  const toast = useToast()
  const searchTimer = useRef(null)

  const aiTagNotes = async () => {
    try {
      const r = await api.post('/ai/note-tags', {})
      setNoteTagPreview(r.data.items)
      if (r.data.items.length === 0) toast('没有未打标的笔记', 'error')
    } catch (e) {
      toast(e.response?.data?.detail || 'AI 打标失败，请检查 API Key', 'error')
    }
  }

  const applyNoteTags = async () => {
    if (!noteTagPreview) return
    setTagApplying(true)
    try {
      const r = await api.post('/ai/note-tags/apply', { changes: noteTagPreview })
      toast(`已应用 ${r.data.done} 条标签`)
      setNoteTagPreview(null)
      load(search.trim())
    } catch (e) { toast('应用失败', 'error') }
    finally { setTagApplying(false) }
  }

  const onSearch = v => {
    setSearch(v)
    clearTimeout(searchTimer.current)
    searchTimer.current = setTimeout(() => load(v.trim()), 400)
  }

  const load = q => {
    api.get('/notes', { params: q ? { q } : {} }).then(r => setNotes(r.data))
    api.get('/goals').then(r => setGoals(r.data)).catch(() => {})
  }
  useEffect(() => { load('') }, [])

  // 搜索结果深链：/notes?highlight=id 时自动打开该笔记
  useEffect(() => {
    const h = params.get('highlight')
    const ht = params.get('highlight_title')
    if (h && notes.length) {
      const n = notes.find(x => x.id === Number(h))
      if (n) { openNote(n); setCurrentPath(n.folder || '') }
    } else if (ht && notes.length) {
      const n = notes.find(x => x.title === ht)
      if (n) { openNote(n); setCurrentPath(n.folder || '') }
    }
  }, [params, notes])

  // 快捷键 Ctrl+N：/notes?new=1 直接进入新建笔记编辑态（打开后清掉参数，便于再次触发）
  useEffect(() => {
    if (params.get('new') === '1') {
      setCreating(true)
      navigate('/notes', { replace: true })
    }
  }, [params, navigate])

  const openNote = async n => {
    try {
      const r = await api.get(`/notes/${n.id}`)
      setEditing(r.data)
    } catch (e) { toast('打开笔记失败', 'error') }
  }

  const folders = [...new Set(notes.map(n => n.folder).filter(Boolean))]
  const tree = buildTree(folders)

  const visibleNotes = currentPath ? notes.filter(n => n.folder === currentPath) : notes

  const del = async n => {
    if (!confirm(`删除笔记「${n.title}」？会进入回收站，可恢复`)) return
    try {
      await api.delete(`/notes/${n.id}`)
      toast('已删除'); load(search.trim())
    } catch (e) { toast('删除失败', 'error') }
  }

  const openTrash = async () => {
    setShowTrash(true)
    try { setTrash((await api.get('/notes/trash')).data) } catch (e) { toast('加载回收站失败', 'error') }
  }
  const togglePin = async n => {
    try {
      await api.put(`/notes/${n.id}`, { pinned: !n.pinned })
      load(search.trim())
    } catch (e) { toast('操作失败', 'error') }
  }

  const createInFolder = () => setCreating(true)

  const openNoteByTitle = async title => {
    const n = notes.find(x => x.title === title)
    if (n) { await openNote(n); setCurrentPath(n.folder) }
    else toast(`未找到笔记「${title}」`, 'error')
  }

  const exportAll = async () => {
    try {
      const list = (await api.get('/notes')).data
      if (list.length === 0) return toast('暂无笔记可导出', 'error')
      const full = await Promise.all(list.map(n => api.get(`/notes/${n.id}`).then(r => r.data)))
      const md = full.map(n => `# ${n.title}\n${n.folder ? `\n> 文件夹：${n.folder}\n` : ''}\n\n${n.content}`).join('\n\n---\n\n')
      const blob = new Blob(['\ufeff' + md], { type: 'text/markdown' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a'); a.href = url; a.download = `notes_${todayStr()}.md`; a.click()
      URL.revokeObjectURL(url)
      toast('已导出全部笔记为 Markdown')
    } catch (err) { toast('导出失败', 'error') }
  }

  const onImport = async e => {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      const text = await file.text()
      const title = file.name.replace(/\.md$/i, '') || '导入笔记'
      const result = await api.post('/notes', { title, content: text, folder: currentPath })
      toast(`已导入「${result.data.title}」`)
      load(search.trim())
    } catch (err) { toast('导入失败', 'error') }
    e.target.value = ''
  }
  const importRef = useRef(null)

  return (
    <div>
      <div className="page-header">
        <h1><span className="page-icon"><NotebookPen size={22} strokeWidth={1.75} /></span>笔记</h1>
        <div className="row">
          <input
            className="input"
            style={{ width: 220 }}
            placeholder="🔍 搜索笔记标题/内容..."
            value={search}
            onChange={e => onSearch(e.target.value)}
          />
          {search && <button className="btn btn-sm" onClick={() => onSearch('')}>清除</button>}
          <button className="btn btn-sm" onClick={aiTagNotes}><Sparkles size={14} strokeWidth={1.8} /> AI 打标</button>
          <button className="btn" onClick={openTrash}><Trash2 size={14} strokeWidth={1.8} /> 回收站</button>
          <button className="btn" onClick={exportAll}><FileDown size={14} strokeWidth={1.8} /> 导出 Markdown</button>
          <button className="btn" onClick={() => importRef.current?.click()}><FileUp size={14} strokeWidth={1.8} /> 导入 Markdown</button>
          <input ref={importRef} type="file" accept=".md,.markdown,text/markdown" style={{ display: 'none' }} onChange={onImport} />
          <button className="btn btn-primary" onClick={createInFolder}>+ 新建笔记</button>
        </div>
      </div>

      <div className="notes-layout">
        <div className="folder-panel">
          <div
            className={`folder-item ${currentPath === '' ? 'active' : ''}`}
            onClick={() => setCurrentPath('')}
          >
            <span>🗂</span> 全部笔记
          </div>
          <FolderTree tree={tree} current={{ path: '', full: '' }} onSelect={setCurrentPath} />
          {currentPath && (
            <button className="btn btn-sm" style={{ marginTop: 8 }} onClick={() => setCreating(true)}>
              + 在此文件夹新建
            </button>
          )}
        </div>

        <div className="note-list">
          {visibleNotes.map(n => (
            <div className={`card note-card ${n.pinned ? 'pinned' : ''}`} key={n.id} onClick={() => openNote(n)}>
              <div className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <strong style={{ fontSize: 14, flex: 1 }}>{n.title}</strong>
                {n.pinned && <span className="badge badge-warn">置顶</span>}
              </div>
              <div className="row" style={{ marginTop: 6, gap: 6, flexWrap: 'wrap' }}>
                {n.folder && (
                  <span className="badge note-folder" style={{ background: `${folderColor(n.folder)}1a`, color: folderColor(n.folder) }}>
                    <span className="folder-dot" style={{ background: folderColor(n.folder) }} />{n.folder}
                  </span>
                )}
                {(n.tags || '').split(',').map(t => t.trim()).filter(Boolean).slice(0, 3).map(t => (
                  <span key={t} className="badge badge-gray">{t}</span>
                ))}
              </div>
              <div className="note-summary">{n.content?.replace(/[#*`!\[\]()]/g, '').slice(0, 120) || '空白笔记'}</div>
              <div className="row" style={{ marginTop: 8, justifyContent: 'space-between' }}>
                <span className="muted">{n.updated_at?.slice(0, 10)}</span>
                <span>
                  <button className="btn btn-sm" onClick={e => { e.stopPropagation(); togglePin(n) }}>{n.pinned ? '取消置顶' : '置顶'}</button>
                  <button className="btn btn-sm btn-danger" onClick={e => { e.stopPropagation(); del(n) }}>删除</button>
                </span>
              </div>
            </div>
          ))}
          {visibleNotes.length === 0 && <div className="card empty">{currentPath ? `「${currentPath}」文件夹还没有笔记` : '还没有笔记，点击右上角新建，粘贴截图快速记录'}</div>}
        </div>
      </div>

      {creating && <NoteEditor key="new" note={null} goals={goals} defaultFolder={currentPath} onOpenNote={openNoteByTitle} onClose={() => setCreating(false)} onSaved={() => { setCreating(false); load(search.trim()) }} />}
      {editing && <NoteEditor key={editing.id} note={editing} goals={goals} onOpenNote={openNoteByTitle} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(search.trim()) }} />}
      {showTrash && (
        <div className="modal-mask" onClick={() => setShowTrash(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h3>🗑 回收站</h3>
            <div className="row" style={{ justifyContent: 'space-between', marginBottom: 10 }}>
              <div className="muted">删除的笔记在这里，可恢复或彻底删除。</div>
              {trash.length > 0 && (
                <button className="btn btn-sm btn-danger" onClick={async () => {
                  if (!confirm(`清空回收站全部 ${trash.length} 篇笔记？此操作不可恢复`)) return
                  await api.delete('/notes/trash')
                  toast('回收站已清空')
                  setShowTrash(false); load(search.trim())
                }}><Trash2 size={14} strokeWidth={1.8} /> 清空回收站</button>
              )}
            </div>
            {trash.length === 0 && <div className="empty"><span className="empty-icon">🗑</span>回收站是空的</div>}
            {trash.map(x => (
              <div key={x.id} className="row" style={{ justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid var(--border)' }}>
                <span style={{ flex: 1, minWidth: 0 }}>{x.title} {x.folder && <span className="muted">（{x.folder} · {x.deleted_at?.slice(0, 10)}）</span>}</span>
                <button className="btn btn-sm" onClick={async () => {
                  await api.post(`/notes/${x.id}/restore`)
                  toast('已恢复')
                  load(search.trim()); openTrash()
                }}>恢复</button>
                <button className="btn btn-sm btn-danger" onClick={async () => {
                  if (!confirm(`彻底删除「${x.title}」？此操作不可恢复`)) return
                  await api.delete(`/notes/${x.id}/purge`)
                  toast('已彻底删除')
                  openTrash()
                }}>彻底删除</button>
              </div>
            ))}
            <div className="modal-actions"><button className="btn" onClick={() => setShowTrash(false)}>关闭</button></div>
          </div>
        </div>
      )}
      {noteTagPreview && (
        <div className="modal-mask" onClick={() => setNoteTagPreview(null)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h3>✨ AI 笔记打标</h3>
            <div className="muted" style={{ marginBottom: 10 }}>AI 为未打标的笔记生成建议标签，可修改后应用（应用到标题即可生效）。</div>
            {noteTagPreview.map((n, i) => (
              <div key={n.id} className="row" style={{ alignItems: 'flex-start', padding: '6px 0', borderBottom: '1px solid var(--border)' }}>
                <span style={{ flex: 1, minWidth: 0, fontSize: 13 }}>{n.title}</span>
                <input
                  className="input"
                  style={{ width: 220, height: 28, fontSize: 12 }}
                  value={n.tags || (n.suggested || []).join(',')}
                  onChange={e => setNoteTagPreview(list => list.map((x, j) => (j === i ? { ...x, tags: e.target.value } : x)))}
                />
              </div>
            ))}
            <div className="modal-actions">
              <button className="btn" onClick={() => setNoteTagPreview(null)}>取消</button>
              <button className="btn btn-primary" onClick={applyNoteTags} disabled={tagApplying}>{tagApplying ? '应用中...' : (<><Check size={14} strokeWidth={1.8} /> 应用 {noteTagPreview.length} 条标签</>)}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
