import React, { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import api from '../api'
import { useToast } from '../components/Toast'
import CopyBtn from '../components/CopyBtn'
import ReactMarkdown from 'react-markdown'
import MdCodeBlock from '../components/MdCodeBlock'
import { BookMarked, BookPlus, ChevronDown, ChevronRight, FileText, Library, Quote, RefreshCw, Sparkles, Tags, X, Zap } from 'lucide-react'

function ReactMarkdownBlock({ text }) {
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
  return <ReactMarkdown urlTransform={u => u} components={mdComponents}>{preprocess(text)}</ReactMarkdown>
}

function ReadNote({ it, onSave }) {
  const [open, setOpen] = useState(false)
  if (!open) {
    return (
      <div className="read-note-fold" onClick={() => setOpen(true)} title="点击展开编辑阅读笔记">
        📝 {it.my_notes || '记录这篇文献的核心方法、对你的启发...'}
      </div>
    )
  }
  return (
    <div style={{ marginTop: 10 }}>
      <div className="muted" style={{ marginBottom: 4 }}>我的阅读笔记</div>
      <textarea
        className="textarea"
        style={{ minHeight: 56 }}
        placeholder="记录这篇文献的核心方法、对你的启发..."
        defaultValue={it.my_notes}
        onBlur={e => { onSave(e.target.value); setOpen(false) }}
      />
    </div>
  )
}

const TYPE_LABEL = { journalArticle: '期刊', thesis: '学位论文', conferencePaper: '会议', book: '图书', preprint: '预印本' }
const STATUS = [
  ['unread', '待读', 'badge-warn'],
  ['reading', '在读', 'badge-info'],
  ['read', '已读', 'badge-success'],
]

export default function Literature() {
  const [items, setItems] = useState([])
  const [collections, setCollections] = useState([])
  const [zoteroStatus, setZoteroStatus] = useState({ running: false })
  const [syncing, setSyncing] = useState(false)
  const [summarizing, setSummarizing] = useState(null)
  const [pasteText, setPasteText] = useState('')
  const [qaQuestion, setQaQuestion] = useState('')
  const [qaLoading, setQaLoading] = useState(false)
  const [filter, setFilter] = useState({ type: 'all', value: '' })
  const [search, setSearch] = useState('')
  const [recItems, setRecItems] = useState([])
  const [recLoading, setRecLoading] = useState(false)
  const [aiToolsOpen, setAiToolsOpen] = useState(false)
  const [tagPreview, setTagPreview] = useState(null)
  const [batchLoading, setBatchLoading] = useState(null)
  const [qaHistory, setQaHistory] = useState([])
  const [moreOpen, setMoreOpen] = useState(false)
  const [flashId, setFlashId] = useState(null)
  const [params] = useSearchParams()
  const [citeFor, setCiteFor] = useState(null)
  const [journalLoading, setJournalLoading] = useState(false)
  const [kbQ, setKbQ] = useState('')
  const [kbLoading, setKbLoading] = useState(false)
  const [kbResult, setKbResult] = useState(null)
  const [reading, setReading] = useState({ count: 0, goal: 0 })
  const [pdfUploadId, setPdfUploadId] = useState(null)
  const pdfRef = useRef(null)
  const toast = useToast()

  // 搜索结果深链：/literature?highlight=id 时滚动定位到该文献并高亮
  useEffect(() => {
    const h = params.get('highlight')
    if (h) {
      const id = Number(h)
      setFlashId(id)
      const t1 = setTimeout(() => {
        const el = document.querySelector(`[data-lit-id="${id}"]`)
        el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      }, 300)
      const t2 = setTimeout(() => setFlashId(null), 4000)
      return () => { clearTimeout(t1); clearTimeout(t2) }
    }
  }, [params])

  const load = () => {
    api.get('/literature').then(r => setItems(r.data))
    api.get('/literature/collections').then(r => setCollections(r.data)).catch(() => {})
    api.get('/stats/reading-goal').then(r => setReading(r.data)).catch(() => {})
  }
  useEffect(() => {
    load()
    api.get('/literature/zotero/status').then(r => setZoteroStatus(r.data))
  }, [])

  const sync = async () => {
    setSyncing(true)
    try {
      const r = await api.post('/literature/sync')
      toast(`同步完成，新增 ${r.data.added} 条`)
      load()
    } catch (e) {
      toast(e.response?.data?.detail || '同步失败', 'error')
    } finally {
      setSyncing(false)
    }
  }

  const filteredItems = useMemo(() => {
    let list = items
    if (filter.type === 'collection' && filter.value) {
      list = list.filter(it => (it.collection_keys || '').split(',').includes(filter.value))
    } else if (filter.type === 'item_type' && filter.value) {
      list = list.filter(it => it.item_type === filter.value)
    } else if (filter.type === 'status' && filter.value) {
      list = list.filter(it => it.read_status === filter.value)
    }
    const q = search.trim().toLowerCase()
    if (q) {
      list = list.filter(it =>
        (it.title || '').toLowerCase().includes(q) ||
        (it.authors || []).join(' ').toLowerCase().includes(q) ||
        (it.tags || '').toLowerCase().includes(q)
      )
    }
    return list
  }, [items, filter, search])

  // 类型统计（用于收纳栏）
  const typeCounts = useMemo(() => {
    const c = {}
    items.forEach(it => { c[it.item_type] = (c[it.item_type] || 0) + 1 })
    return c
  }, [items])

  const colName = key => collections.find(c => c.key === key)?.name || key

  const summarize = async id => {
    setSummarizing(id)
    try {
      const r = await api.post(`/literature/${id}/summarize`)
      toast('AI 总结完成')
      load()
    } catch (e) {
      toast(e.response?.data?.detail || 'AI 调用失败，请检查 API Key 或文献摘要', 'error')
    } finally {
      setSummarizing(null)
    }
  }

  const summarizePaste = async () => {
    if (!pasteText.trim()) return toast('请先粘贴内容', 'error')
    try {
      const r = await api.post('/ai/summarize', { text: pasteText })
      toast('AI 总结完成')
      setPasteText(prev => `${prev}\n\n【AI 总结】\n${r.data.result}`)
    } catch (e) {
      toast(e.response?.data?.detail || 'AI 调用失败', 'error')
    }
  }

  const askQa = async () => {
    if (!qaQuestion.trim()) return toast('请输入问题', 'error')
    setQaLoading(true)
    try {
      const r = await api.post('/ai/literature-qa', { question: qaQuestion, history: qaHistory })
      // C16：最新回答只渲染一份（并入 qaHistory），不再单独渲染 qaAnswer
      setQaHistory(h => [...h, { q: qaQuestion, a: r.data.result }].slice(-10))
      setQaQuestion('')
    } catch (e) {
      toast(e.response?.data?.detail || 'AI 调用失败', 'error')
    } finally {
      setQaLoading(false)
    }
  }

  const askKb = async () => {
    if (!kbQ.trim()) return toast('请输入问题', 'error')
    setKbLoading(true)
    setKbResult(null)
    try {
      const r = await api.post('/ai/kb-qa', { question: kbQ })
      setKbResult(r.data)
    } catch (e) {
      toast(e.response?.data?.detail || 'AI 调用失败，请检查 API Key', 'error')
    } finally {
      setKbLoading(false)
    }
  }

  const del = async id => {
    if (!confirm('删除该文献记录？')) return
    try {
      await api.delete(`/literature/${id}`)
      load()
    } catch (e) { toast('删除失败', 'error') }
  }

  const setStatus = async (it, status) => {
    try {
      await api.put(`/literature/${it.id}`, { read_status: status })
      load()
    } catch (e) { toast('状态保存失败', 'error') }
  }

  const saveNote = async (it, text) => {
    try {
      await api.put(`/literature/${it.id}`, { my_notes: text })
      toast('笔记已保存')
      load()
    } catch (e) { toast('笔记保存失败', 'error') }
  }

  const tagIt = async it => {
    try {
      const r = await api.post('/ai/tag-literature', { item_id: it.id, preview: true })
      setTagPreview({ item: it, suggested: r.data.suggested || [], existing: r.data.existing || [] })
    } catch (e) {
      toast(e.response?.data?.detail || 'AI 打标失败，请检查 API Key', 'error')
    }
  }

  const confirmTag = async () => {
    try {
      await api.post('/ai/tag-literature', { item_id: tagPreview.item.id, preview: false })
      toast('AI 打标完成')
      setTagPreview(null)
      load()
    } catch (e) {
      toast(e.response?.data?.detail || '保存失败', 'error')
    }
  }

  const batchTag = async () => {
    setBatchLoading('tag')
    try {
      const r = await api.post('/ai/batch-tag', { limit: 50 })
      toast(`批量打标完成：${r.data.done}/${r.data.total}`)
      load()
    } catch (e) {
      toast(e.response?.data?.detail || '批量打标失败', 'error')
    } finally {
      setBatchLoading(null)
    }
  }

  const batchSummarize = async () => {
    setBatchLoading('summarize')
    try {
      const r = await api.post('/ai/batch-summarize', { limit: 20 })
      toast(`批量总结完成：${r.data.done}/${r.data.total}`)
      load()
    } catch (e) {
      toast(e.response?.data?.detail || '批量总结失败', 'error')
    } finally {
      setBatchLoading(null)
    }
  }

  const readToday = async it => {
    try {
      await api.post('/daily', {
        content: `读文献：${it.title}`,
        kind: 'literature',
        source_id: it.id,
        quadrant: 'important_urgent',
        weight: 15,
        pomodoros: 1,
      })
      toast('已加入今日清单')
    } catch (e) {
      toast(e.response?.data?.detail || '加入失败', 'error')
    }
  }

  const recommend = async () => {
    setRecLoading(true)
    setRecItems([])
    try {
      const r = await api.post('/ai/recommend-literature')
      setRecItems(r.data.items || [])
    } catch (e) {
      toast(e.response?.data?.detail || 'AI 推荐失败，请检查 API Key', 'error')
    } finally {
      setRecLoading(false)
    }
  }

  const cleanupTags = async () => {
    try {
      const r = await api.post('/literature/cleanup-tags', { preview: true })
      const sug = r.data.suggestions || []
      if (sug.length === 0) return toast('没有发现重复标签')
      const detail = sug.map(s => `「${s.standard}」← ${s.variants.join('、')}`).join('\n')
      if (!confirm(`发现 ${sug.length} 组近似重复标签，是否合并为统一标签？\n\n${detail}`)) return
      const rr = await api.post('/literature/cleanup-tags', { preview: false })
      toast(`已合并 ${rr.data.merged_items} 处标签`)
      load()
    } catch (e) {
      toast(e.response?.data?.detail || '清理失败', 'error')
    }
  }

  const citeItem = async (it, style) => {
    try {
      const r = await api.get(`/literature/${it.id}/cite`, { params: { style } })
      const label = { gb7714: 'GB/T 7714', apa: 'APA', bibtex: 'BibTeX' }[style] || style
      navigator.clipboard?.writeText(r.data.text).catch(() => {})
      toast(`已复制 ${label} 引用`)
      setCiteFor(null)
    } catch (e) { toast('生成引用失败', 'error') }
  }

  const batchJournal = async () => {
    setJournalLoading(true)
    try {
      const r = await api.post('/literature/batch-journal-info', { limit: 50 })
      toast(`已补全 ${r.data.done} 篇期刊信息（AI 推断，请核实）`)
      load()
    } catch (e) {
      toast(e.response?.data?.detail || '补全失败', 'error')
    } finally {
      setJournalLoading(false)
    }
  }

  const exportBib = () => {
    if (items.length === 0) return toast('暂无文献', 'error')
    const bib = items.map(it => {
      const authors = (it.authors || []).map(a => a.replace(/ /g, ', ')).join(' and ')
      const key = (it.title || 'item').replace(/[^\w\u4e00-\u9fa5]/g, '').slice(0, 20) + it.id
      return `@article{${key},\n  title = {${it.title}},\n  author = {${authors || 'Unknown'}},\n  year = {${it.year || ''}},\n  journal = {${it.publication || ''}},\n}`
    }).join('\n\n')
    const blob = new Blob(['\ufeff' + bib], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a'); a.href = url; a.download = 'references.bib'; a.click()
    URL.revokeObjectURL(url)
    toast('已导出 BibTeX 引用')
  }

  const navItem = (type, value, label, count, active) => (
    <div
      className={`folder-item ${active ? 'active' : ''}`}
      onClick={() => setFilter({ type, value })}
    >
      <span>{label}</span>
      {typeof count === 'number' && <span className="muted" style={{ marginLeft: 'auto' }}>{count}</span>}
    </div>
  )

  return (
    <div>
      <div className="page-header">
        <h1><span className="page-icon"><BookMarked size={22} strokeWidth={1.75} /></span>文献</h1>
        <div className="row">
          <span className={`badge ${zoteroStatus.running ? 'badge-success' : 'badge-warn'}`}>
            Zotero {zoteroStatus.running ? '已连接' : '未运行'}
          </span>
          <button className="btn btn-primary" onClick={sync} disabled={syncing}>
            {syncing ? '同步中...' : (<><RefreshCw size={14} strokeWidth={1.8} /> 从 Zotero 同步</>)}
          </button>
          <button className="btn" onClick={recommend} disabled={recLoading}>{recLoading ? '推荐中...' : (<><Sparkles size={14} strokeWidth={1.8} /> AI 推荐阅读</>)}</button>
          <div style={{ position: 'relative' }}>
            <button className="btn" onClick={() => setMoreOpen(o => !o)}>⋯ 更多工具</button>
            {moreOpen && (
              <div className="dropdown-menu" onClick={() => setMoreOpen(false)}>
                <button className="btn" onClick={batchTag} disabled={batchLoading === 'tag'}>{batchLoading === 'tag' ? '批量打标中(约1分钟)...' : (<><Zap size={14} strokeWidth={1.8} /> 批量打标</>)}</button>
                <button className="btn" onClick={batchSummarize} disabled={batchLoading === 'summarize'}>{batchLoading === 'summarize' ? '批量总结中(约1分钟)...' : (<><Zap size={14} strokeWidth={1.8} /> 批量总结</>)}</button>
                <button className="btn" onClick={batchJournal} disabled={journalLoading}>{journalLoading ? '补全中(约1分钟)...' : (<><Sparkles size={14} strokeWidth={1.8} /> AI 补全期刊分区</>)}</button>
                <button className="btn" onClick={cleanupTags}><Tags size={14} strokeWidth={1.8} /> 清理重复标签</button>
                <button className="btn" onClick={exportBib}><Library size={14} strokeWidth={1.8} /> 导出 BibTeX</button>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-title">📖 阅读计划
          <span className="muted">本周已读 {reading.count} 篇{reading.goal > 0 ? ` / 目标 ${reading.goal} 篇` : '（设置每周目标后显示进度）'}</span>
        </div>
        {reading.goal > 0 && (
          <div className="progress-bar" style={{ height: 10 }}>
            <div style={{ width: `${Math.min(100, Math.round(reading.count / reading.goal * 100))}%` }} />
          </div>
        )}
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-title">🤖 AI 工具
          <button className="btn btn-sm" onClick={() => setAiToolsOpen(o => !o)}>{aiToolsOpen ? (<><ChevronDown size={14} strokeWidth={1.8} /> 收起</>) : (<><ChevronRight size={14} strokeWidth={1.8} /> 展开</>)}</button>
        </div>
        {aiToolsOpen && (
          <div className="grid grid-3">
            <div>
              <div className="card-title" style={{ fontSize: 13 }}>✨ AI 总结粘贴内容</div>
              <textarea className="textarea" style={{ minHeight: 60 }} placeholder="粘贴论文摘要/段落，AI 帮你结构化总结..." value={pasteText} onChange={e => setPasteText(e.target.value)} />
              <div className="row" style={{ marginTop: 8, justifyContent: 'flex-end' }}>
                <button className="btn btn-primary btn-sm" onClick={summarizePaste}><Sparkles size={14} strokeWidth={1.8} /> AI 总结</button>
              </div>
              {pasteText.includes('【AI 总结】') && (
                <div className="card summ" style={{ marginTop: 8 }}>
                  <ReactMarkdownBlock text={pasteText.split('【AI 总结】')[1]} />
                  <div style={{ marginTop: 6 }}><CopyBtn text={pasteText.split('【AI 总结】')[1]} /></div>
                </div>
              )}
            </div>

            <div>
              <div className="card-title" style={{ fontSize: 13 }}>💬 文献库问答
                {qaHistory.length > 0 && <button className="btn btn-sm" onClick={() => setQaHistory([])}>清空对话</button>}
              </div>
              <div className="row">
                <input
                  className="input"
                  style={{ flex: 1 }}
                  placeholder="关于红外小目标检测，文献库有哪些主流方法？"
                  value={qaQuestion}
                  onChange={e => setQaQuestion(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter' && !e.nativeEvent.isComposing) askQa() }}
                />
                <button className="btn btn-primary" onClick={askQa} disabled={qaLoading}>
                  {qaLoading ? '思考中...' : '提问'}
                </button>
              </div>
              {qaHistory.map((h, i) => (
                <div key={i} style={{ marginTop: 8 }}>
                  <div className="muted" style={{ fontSize: 12, fontWeight: 600 }}>问：{h.q}</div>
                  <div className="card summ" style={{ marginTop: 4, whiteSpace: 'pre-wrap' }}>{h.a}</div>
                </div>
              ))}
            </div>

            <div>
              <div className="card-title" style={{ fontSize: 13 }}>🗂 问我的知识库</div>
              <div className="row">
                <input
                  className="input"
                  style={{ flex: 1 }}
                  placeholder="如：我笔记里写过 DNANet 的注意力设计吗？"
                  value={kbQ}
                  onChange={e => setKbQ(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter' && !e.nativeEvent.isComposing) askKb() }}
                />
                <button className="btn btn-primary" onClick={askKb} disabled={kbLoading}>
                  {kbLoading ? '检索中...' : '提问'}
                </button>
              </div>
              <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>在全部笔记 + 文献 + 实验记录中检索，回答带来源。</div>
              {kbResult && (
                <div style={{ marginTop: 8 }}>
                  <div className="card summ" style={{ whiteSpace: 'pre-wrap' }}>{kbResult.result}</div>
                  {(kbResult.sources || []).length > 0 && (
                    <div style={{ marginTop: 6 }}>
                      <div className="muted" style={{ fontSize: 12, marginBottom: 4 }}>来源：</div>
                      {kbResult.sources.map((s, i) => (
                        <div key={i} style={{ fontSize: 12, marginBottom: 2 }}>
                          <a
                            href="#"
                            onClick={e => { e.preventDefault(); window.location.hash = s.type === 'note' ? `#/notes?highlight=${s.id}` : `#/literature?highlight=${s.id}` }}
                            style={{ color: 'var(--primary)' }}
                          >{s.type === 'note' ? '📝' : s.type === 'literature' ? '▤' : '🧪'} {s.title}</a>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      <div className="notes-layout">
        {/* 左侧收纳栏 */}
        <div className="folder-panel">
          <div className="side-group-label">文献收纳</div>
          {navItem('all', '', '🗂 全部文献', items.length, filter.type === 'all')}
          <div className="side-group-label">按集合</div>
          {collections.map(c => navItem('collection', c.key, `📁 ${c.name}`, items.filter(it => (it.collection_keys || '').split(',').includes(c.key)).length, filter.type === 'collection' && filter.value === c.key))}
          <div className="side-group-label">按类型</div>
          {Object.keys(typeCounts).map(t => navItem('item_type', t, `📄 ${TYPE_LABEL[t] || t || '未分类'}`, typeCounts[t], filter.type === 'item_type' && filter.value === t))}
          <div className="side-group-label">按状态</div>
          {STATUS.map(([v, l]) => navItem('status', v, `· ${l}`, items.filter(it => it.read_status === v).length, filter.type === 'status' && filter.value === v))}
        </div>

        {/* 右侧文献列表 */}
        <div>
          <div className="row" style={{ marginBottom: 12 }}>
            <input
              className="input"
              style={{ flex: 1 }}
              placeholder="搜索标题 / 作者 / 标签..."
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
            {filter.type !== 'all' && (
              <button className="btn btn-sm" onClick={() => setFilter({ type: 'all', value: '' })}>清除筛选</button>
            )}
          </div>

          {filteredItems.length === 0 && (
            <div className="card empty">
              没有匹配的文献{items.length === 0 ? '，点击「从 Zotero 同步」导入' : ''}
            </div>
          )}

          {filteredItems.map(it => (
            <div className={`card lit-card ${flashId === it.id ? 'flash' : ''}`} key={it.id} data-lit-id={it.id}>
              <div className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div style={{ flex: 1 }}>
                  <strong>{it.title}</strong>
                  <div className="muted" style={{ marginTop: 4 }}>
                    {it.authors?.length ? it.authors.join('、') : '—'}
                    {it.year ? ` · ${it.year}` : ''}
                    {it.publication ? ` · ${it.publication}` : ''}
                  </div>
                  <div className="row" style={{ marginTop: 6, gap: 6, flexWrap: 'wrap' }}>
                    <span className="badge badge-gray">{TYPE_LABEL[it.item_type] || it.item_type || '未分类'}</span>
                    {it.journal_level && <span className="badge badge-warn" title="AI 推断的分区/等级，投稿前请核实">{it.journal_level}{it.impact_factor ? ` · IF ${it.impact_factor}` : ''}</span>}
                    {(it.collection_keys || '').split(',').filter(Boolean).map(ck => (
                      <span key={ck} className="badge badge-primary">📁 {colName(ck)}</span>
                    ))}
                    {it.tags && it.tags.split(',').filter(Boolean).map(t => <span key={t} className="badge badge-info">{t}</span>)}
                    <span className={`badge ${STATUS.find(s => s[0] === it.read_status)?.[2] || 'badge-gray'}`}>
                      {STATUS.find(s => s[0] === it.read_status)?.[1] || '待读'}
                    </span>
                  </div>
                  {it.abstract && <div className="muted" style={{ marginTop: 8, fontSize: 12 }}>{it.abstract.slice(0, 150)}{it.abstract.length > 150 ? '...' : ''}</div>}
                </div>
                <div className="row" style={{ gap: 6 }}>
                  <select className="select" style={{ width: 80, padding: '4px 8px' }} value={it.read_status || 'unread'} onChange={e => setStatus(it, e.target.value)}>
                    {STATUS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </select>
                  {it.read_status !== 'read' && (
                    <button className="btn btn-sm btn-primary" onClick={() => readToday(it)}><BookPlus size={14} strokeWidth={1.8} /> 今天读</button>
                  )}
                  <button className="btn btn-sm btn-primary" onClick={() => summarize(it.id)} disabled={summarizing === it.id}>
                    {summarizing === it.id ? '总结中...' : (<><Sparkles size={14} strokeWidth={1.8} /> AI 总结</>)}
                  </button>
                  <button className="btn btn-sm" onClick={() => tagIt(it)}><Tags size={14} strokeWidth={1.8} /> 打标</button>
                  {it.pdf_path ? (
                    <>
                      <button className="btn btn-sm btn-primary" onClick={() => window.open(`/api/literature/pdf/${it.pdf_path}`, '_blank')} title="打开 PDF"><FileText size={14} strokeWidth={1.8} /> PDF</button>
                      <button className="btn btn-sm" onClick={async () => { await api.delete(`/literature/${it.id}/pdf`); load(); toast('已移除 PDF') }} title="移除 PDF"><X size={14} strokeWidth={1.8} /></button>
                    </>
                  ) : (
                    <button className="btn btn-sm" onClick={() => { setPdfUploadId(it.id); pdfRef.current?.click() }}><FileText size={14} strokeWidth={1.8} /> 上传 PDF</button>
                  )}
                  <input ref={pdfRef} type="file" accept=".pdf" style={{ display: 'none' }} onChange={async e => {
                    const file = e.target.files?.[0]
                    e.target.value = ''
                    if (!file || !pdfUploadId) return
                    try {
                      const fd = new FormData()
                      fd.append('file', file)
                      await api.post(`/literature/${pdfUploadId}/pdf`, fd)
                      toast('PDF 已关联')
                      load()
                    } catch (err) { toast(err.response?.data?.detail || '上传失败', 'error') }
                  }} />
                  <div style={{ position: 'relative' }}>
                    <button className="btn btn-sm" onClick={() => setCiteFor(c => (c === it.id ? null : it.id))}><Quote size={14} strokeWidth={1.8} /> 引用</button>
                    {citeFor === it.id && (
                      <div className="dropdown-menu" style={{ right: 0, left: 'auto' }} onClick={() => setCiteFor(null)}>
                        <button className="btn" onClick={() => citeItem(it, 'gb7714')}>GB/T 7714（学位论文）</button>
                        <button className="btn" onClick={() => citeItem(it, 'apa')}>APA</button>
                        <button className="btn" onClick={() => citeItem(it, 'bibtex')}>BibTeX</button>
                      </div>
                    )}
                  </div>
                  <button className="btn btn-sm btn-danger" onClick={() => del(it.id)}>删除</button>
                </div>
              </div>
              {it.ai_summary && (
                <div className="summ">
                  <div style={{ fontWeight: 600, marginBottom: 4 }}>AI 总结</div>
                  <ReactMarkdownBlock text={it.ai_summary} />
                </div>
              )}
              <div style={{ marginTop: 10 }}>
                <ReadNote it={it} onSave={text => saveNote(it, text)} />
              </div>
            </div>
          ))}
        </div>
      </div>

      {recItems.length > 0 && (
        <div className="modal-mask" onClick={() => setRecItems([])}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h3>✨ AI 推荐今天阅读</h3>
            <div className="muted" style={{ marginBottom: 10 }}>按年份新旧、主题相关度与领域价值推荐，可一键加入今日清单。</div>
            {recItems.map(r => (
              <div className="d-item" key={r.id}>
                <div style={{ flex: 1 }}>
                  <div className="d-item-title">{r.title}</div>
                  <div className="muted" style={{ fontSize: 12 }}>
                    {r.year ? `${r.year}年 · ` : ''}{r.reason}
                  </div>
                </div>
                <button className="btn btn-sm btn-primary" onClick={() => { readToday({ id: r.id, title: r.title }); setRecItems(list => list.filter(x => x.id !== r.id)) }}><BookPlus size={14} strokeWidth={1.8} /> 今天读</button>
              </div>
            ))}
            <div className="modal-actions">
              <button className="btn" onClick={() => setRecItems([])}>关闭</button>
            </div>
          </div>
        </div>
      )}

      {tagPreview && (
        <div className="modal-mask" onClick={() => setTagPreview(null)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h3>🏷 AI 打标确认</h3>
            <div className="muted" style={{ marginBottom: 8 }}>「{tagPreview.item.title.slice(0, 40)}」</div>
            <div className="muted" style={{ marginBottom: 4 }}>已有标签：</div>
            <div className="row" style={{ gap: 6, marginBottom: 10 }}>
              {tagPreview.existing.length === 0 && <span className="muted" style={{ fontSize: 12 }}>（无）</span>}
              {tagPreview.existing.map(t => <span key={t} className="badge badge-gray">{t}</span>)}
            </div>
            <div className="muted" style={{ marginBottom: 4 }}>AI 建议新增：</div>
            <div className="row" style={{ gap: 6, marginBottom: 10 }}>
              {tagPreview.suggested.length === 0 && <span className="muted" style={{ fontSize: 12 }}>（没有新标签）</span>}
              {tagPreview.suggested.map(t => <span key={t} className="badge badge-primary">{t}</span>)}
            </div>
            <div className="modal-actions">
              <button className="btn" onClick={() => setTagPreview(null)}>取消</button>
              <button className="btn btn-primary" onClick={confirmTag} disabled={tagPreview.suggested.length === 0}>确认合并</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
