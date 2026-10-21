import React, { useEffect, useRef, useState } from 'react'
import api, { todayStr } from '../api'
import { useToast } from '../components/Toast'
import { Archive, BookOpen, BookPlus, Check, FileText, FolderOpen, Link2, Sparkles, Upload } from 'lucide-react'

const RATE_OPTS = [
  { key: 'useful', label: '有用', icon: '👍' },
  { key: 'general', label: '一般', icon: '🙂' },
  { key: 'not_interested', label: '不感兴趣', icon: '👎' },
]
const RATE_LABEL = { useful: '有用', general: '一般', not_interested: '不感兴趣' }

export default function DailyPaper() {
  const toast = useToast()
  const [paper, setPaper] = useState(null)
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(false)
  const [showAbs, setShowAbs] = useState(false)
  const [syncOpen, setSyncOpen] = useState(false)
  const [syncLoading, setSyncLoading] = useState(false)
  const [scan, setScan] = useState(null)
  const [selection, setSelection] = useState({})
  const [syncing, setSyncing] = useState(false)
  const [syncResult, setSyncResult] = useState(null)

  const load = () => {
    api.get('/daily-paper/today').then(r => setPaper(r.data)).catch(() => {})
    api.get('/daily-paper/history').then(r => setHistory(r.data)).catch(() => {})
  }
  useEffect(load, [])

  // 跨天检测：页面长期不刷新（如昨天没关工作台）时，日期变化自动重新加载
  const lastDateRef = useRef(todayStr())
  useEffect(() => {
    const check = () => {
      const d = todayStr()
      if (d !== lastDateRef.current) {
        lastDateRef.current = d
        load()
      }
    }
    const t = setInterval(check, 60 * 1000)
    const onVisible = () => { if (document.visibilityState === 'visible') check() }
    window.addEventListener('focus', onVisible)
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      clearInterval(t)
      window.removeEventListener('focus', onVisible)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [])

  const generate = async () => {
    setLoading(true)
    try {
      const r = await api.post('/daily-paper/generate')
      setPaper(r.data)
      toast('今日论文已生成')
      load()
    } catch (e) {
      toast(e.response?.data?.detail || '生成失败', 'error')
    } finally {
      setLoading(false)
    }
  }

  const rate = async k => {
    if (!paper) return
    if (paper.rating === k) { toast(`当前评价已是「${RATE_LABEL[k] || k}」`); return } // 同档再点保持原评价，不静默取消
    try {
      const r = await api.post(`/daily-paper/${paper.id}/rate`, { rating: k })
      setPaper(r.data)
    } catch (e) { toast(e.response?.data?.detail || '评价失败', 'error') }
  }

  const clearRate = async () => {
    if (!paper || !paper.rating) return
    try {
      const r = await api.post(`/daily-paper/${paper.id}/rate`, { rating: '' })
      setPaper(r.data)
      toast('已清除评价')
    } catch (e) { toast(e.response?.data?.detail || '评价失败', 'error') }
  }

  const markRead = async () => {
    if (!paper || paper.read) return
    const r = await api.post(`/daily-paper/${paper.id}/read`)
    setPaper(r.data)
    toast('已标记为已读')
  }

  const archive = async () => {
    if (!paper) return
    try {
      const r = await api.post(`/daily-paper/${paper.id}/archive`)
      if (r.data?.zotero_warning) {
        toast(r.data.zotero_warning, 'error')
      } else if (r.data?.zotero_key) {
        toast('已存入文献库，并同步到 Zotero')
      } else {
        toast('已存入文献库')
      }
      load()
    } catch (e) { toast(e.response?.data?.detail || '入库失败', 'error') }
  }

  const uploadPdf = async ev => {
    if (!paper) return
    const file = ev.target.files?.[0]
    ev.target.value = ''
    if (!file) return
    if (!file.name.toLowerCase().endsWith('.pdf')) return toast('只支持 PDF 文件', 'error')
    const fd = new FormData()
    fd.append('file', file)
    try {
      const r = await api.post(`/daily-paper/${paper.id}/pdf`, fd)
      setPaper(r.data)
      if (r.data?.zotero_warning) toast(r.data.zotero_warning, 'error')
      else toast(r.data?.zotero_pdf_key ? 'PDF 已上传并同步到 Zotero' : 'PDF 已上传')
      load()
    } catch (e) { toast(e.response?.data?.detail || '上传失败', 'error') }
  }

  const openSync = async () => {
    setSyncOpen(true)
    setSyncResult(null)
    setScan(null)
    setSyncLoading(true)
    try {
      const r = await api.get('/daily-paper/folder-scan')
      setScan(r.data)
      const sel = {}
      ;(r.data.files || []).forEach(f => { sel[f.filename] = f.paper_id ? String(f.paper_id) : '' })
      setSelection(sel)
    } catch (e) {
      toast(e.response?.data?.detail || '扫描文件夹失败', 'error')
    } finally {
      setSyncLoading(false)
    }
  }

  const setFileSel = (filename, val) => setSelection(s => ({ ...s, [filename]: val }))

  const doSync = async () => {
    if (!scan) return
    const items = (scan.files || [])
      .filter(f => selection[f.filename])
      .map(f => ({ filename: f.filename, paper_id: Number(selection[f.filename]) }))
    if (!items.length) return toast('请至少选择一个要同步的文件', 'error')
    setSyncing(true)
    try {
      const r = await api.post('/daily-paper/sync-folder', { items })
      setSyncResult(r.data)
      toast(`同步完成：推送题录 ${r.data.pushed} 篇 · 挂 PDF ${r.data.attached} 个${r.data.failed ? ` · 失败 ${r.data.failed}` : ''}`)
      load()
    } catch (e) {
      toast(e.response?.data?.detail || '同步失败', 'error')
    } finally {
      setSyncing(false)
    }
  }

  const addToday = async () => {
    if (!paper) return
    try {
      let litId = paper.literature_id
      if (!litId) {
        const r = await api.post(`/daily-paper/${paper.id}/archive`)
        litId = r.data.id
      }
      await api.post('/daily', {
        content: `读论文：${paper.title}`,
        kind: 'literature',
        source_id: litId,
        scheduled_date: todayStr(),
        quadrant: 'important_not',
        weight: 10,
      })
      toast('已加入今日清单')
      api.post(`/daily-paper/${paper.id}/read`).catch(() => {})
      load()
    } catch (e) { toast(e.response?.data?.detail || '加入失败', 'error') }
  }

  const origUrl = paper?.url || (paper?.doi ? `https://doi.org/${paper.doi}` : '')

  return (
    <div>
      <div className="page-header">
        <h1><span className="page-icon"><BookOpen size={22} strokeWidth={1.75} /></span>每日论文</h1>
        <div className="row">
          <span className="badge badge-info">每天一篇 · 红外小目标检测</span>
          <button className="btn btn-sm" onClick={openSync} title="扫描 daily_paper 文件夹，把里面的论文（含手动下载的）批量同步到 Zotero"><FolderOpen size={14} strokeWidth={1.8} /> 同步文件夹到 Zotero</button>
          <button className="btn btn-sm" onClick={generate} disabled={loading} title="重新生成今天的论文（当天已生成则直接返回）">{loading ? '生成中…' : (<><Sparkles size={14} strokeWidth={1.8} /> 生成今日论文</>)}</button>
        </div>
      </div>

      {!paper ? (
        <div className="card" style={{ textAlign: 'center', padding: 48 }}>
          <div className="empty-icon">📖</div>
          <div style={{ fontWeight: 700, marginBottom: 6 }}>今天还没有推荐论文</div>
          <div className="muted" style={{ marginBottom: 16, maxWidth: 480, margin: '0 auto 16px' }}>
            每天为你精选一篇红外小目标检测领域的高质量论文（优先新颖、引用高/评价高的），AI 生成中文导读，并自动下载 PDF 到工作台 daily_paper 文件夹。
          </div>
          <button className="btn btn-primary" onClick={generate} disabled={loading}>{loading ? '正在检索与生成…' : (<><Sparkles size={14} strokeWidth={1.8} /> 生成今日论文</>)}</button>
        </div>
      ) : (
        <div className="card dp-hero">
          <div className="row" style={{ justifyContent: 'space-between', marginBottom: 8, flexWrap: 'wrap', gap: 6 }}>
            <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
              <span className="badge badge-info">📅 {paper.paper_date}</span>
              {paper.year && <span className="badge badge-gray">{paper.year}</span>}
              {paper.citation_count
                ? <span className="badge badge-warn">📈 {paper.citation_count} 次引用</span>
                : <span className="badge badge-gray">最新/引用未知</span>}
              {paper.publication && <span className="badge badge-gray">{paper.publication}</span>}
              {paper.read && <span className="badge badge-success">✓ 已读</span>}
              {paper.pdf_file && <span className="badge badge-success">📄 已下载</span>}
              {paper.zotero_key && <span className="badge badge-success">🗂 已入 Zotero</span>}
            </div>
            <span className="badge badge-gray">{paper.source === 'arxiv' ? 'arXiv 来源' : 'OpenAlex 来源'}</span>
          </div>

          <h2 style={{ fontSize: 20, marginBottom: 6 }}>{paper.title}</h2>
          <div className="muted" style={{ marginBottom: 12 }}>
            {paper.authors?.join('、') || '—'}{paper.year ? `（${paper.year}）` : ''}
          </div>

          <div className="row" style={{ gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
            {paper.pdf_file
              ? <a className="btn btn-primary" href={`/api/daily-paper/${paper.id}/pdf`} target="_blank" rel="noreferrer"><FileText size={14} strokeWidth={1.8} /> 打开 PDF</a>
              : <span className="badge badge-gray">未找到开放 PDF</span>}
            <label className="btn" style={{ position: 'relative', overflow: 'hidden', cursor: 'pointer' }}>
              <Upload size={14} strokeWidth={1.8} /> 上传 PDF
              <input type="file" accept=".pdf" onChange={uploadPdf} style={{ position: 'absolute', inset: 0, opacity: 0, cursor: 'pointer' }} title="付费墙论文：在浏览器（校园网/图书馆权限）下好后上传，自动挂进 Zotero" />
            </label>
            {origUrl && <a className="btn" href={origUrl} target="_blank" rel="noreferrer"><Link2 size={14} strokeWidth={1.8} /> 原文链接</a>}
            <button className="btn" onClick={addToday}><BookPlus size={14} strokeWidth={1.8} /> 今天读</button>
            <button className="btn" onClick={archive}><Archive size={14} strokeWidth={1.8} /> 存入文献库</button>
            <button className="btn" onClick={markRead}><Check size={14} strokeWidth={1.8} /> 标记已读</button>
          </div>

          <div className="row" style={{ gap: 8, marginBottom: 12 }}>
            <span className="muted" style={{ fontSize: 13 }}>评价：</span>
            {RATE_OPTS.map(o => (
              <button key={o.key} className={`btn btn-sm ${paper.rating === o.key ? 'btn-primary' : ''}`} onClick={() => rate(o.key)}>
                {o.icon} {o.label}
              </button>
            ))}
            {paper.rating && <button className="btn btn-sm" onClick={clearRate} title="清除当前评价">清除</button>}
          </div>

          {(paper.summary || paper.why_read || paper.relation) && (
            <div className="dp-guide">
              {paper.summary && <div><b>📝 AI 导读</b>：{paper.summary}</div>}
              {paper.why_read && <div style={{ marginTop: 6 }}><b>💡 为什么值得读</b>：{paper.why_read}</div>}
              {paper.relation && <div style={{ marginTop: 6 }}><b>🎯 与你的方向</b>：{paper.relation}</div>}
            </div>
          )}

          {paper.abstract && (
            <div style={{ marginTop: 10 }}>
              <button className="btn btn-sm" onClick={() => setShowAbs(s => !s)}>{showAbs ? '收起摘要 ▴' : '展开摘要 ▾'}</button>
              {showAbs && <div className="dp-abstract">{paper.abstract}</div>}
            </div>
          )}
        </div>
      )}

      <div className="card" style={{ marginTop: 16 }}>
        <div className="card-title">📚 历史推荐</div>
        {history.length === 0 ? (
          <div className="muted" style={{ padding: '10px 0' }}>还没有历史记录，从今天开始养成每天读一篇的习惯吧。</div>
        ) : (
          history.map(h => (
            <div key={h.id} className="row dp-hist-row" style={{ padding: '10px 0', borderBottom: '1px solid var(--line)', gap: 10, alignItems: 'center' }}>
              <span className="badge badge-gray" style={{ whiteSpace: 'nowrap' }}>{h.paper_date}</span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{h.title}</div>
                <div className="muted" style={{ fontSize: 12 }}>
                  {h.authors?.[0] || ''}{h.year ? ` · ${h.year}` : ''}
                  {h.citation_count ? ` · ${h.citation_count} 引` : ''}
                  {h.read && ' · ✓已读'}
                  {h.rating && ` · 评价:${RATE_LABEL[h.rating] || h.rating}`}
                  {h.pdf_file && ' · 📄'}
                  {h.zotero_key && ' · 🗂已入Zotero'}
                </div>
              </div>
              {h.pdf_file && <a className="btn btn-sm" href={`/api/daily-paper/${h.id}/pdf`} target="_blank" rel="noreferrer" title="打开 PDF"><FileText size={14} strokeWidth={1.8} /></a>}
              {(h.url || h.doi) && <a className="btn btn-sm" href={h.url || `https://doi.org/${h.doi}`} target="_blank" rel="noreferrer" title="原文链接"><Link2 size={14} strokeWidth={1.8} /></a>}
            </div>
          ))
        )}
      </div>

      {syncOpen && (
        <div className="modal-mask" onClick={() => !syncing && setSyncOpen(false)}>
          <div className="modal" style={{ maxWidth: 720 }} onClick={e => e.stopPropagation()}>
            <div className="modal-title">📁 同步 daily_paper 文件夹到 Zotero</div>
            <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>扫描目录：{scan?.dir || '…'}</div>

            {syncLoading ? (
              <div className="muted" style={{ padding: '16px 0' }}>正在扫描文件夹…</div>
            ) : !scan ? null : !scan.configured ? (
              <div className="badge badge-warn" style={{ display: 'block', padding: 10 }}>
                未配置 Zotero API Key / User ID，无法同步，请先在设置页填写。
              </div>
            ) : (
              <>
                <div className="muted" style={{ fontSize: 13, marginBottom: 8 }}>
                  共 {scan.files.length} 个 PDF；自动匹配到的已默认勾选，未匹配的请在选择框里手动关联（不选=跳过）。
                </div>
                {scan.files.length === 0 ? (
                  <div className="muted" style={{ padding: '12px 0' }}>文件夹里没有 PDF。</div>
                ) : (
                  <div style={{ maxHeight: 360, overflow: 'auto', border: '1px solid var(--line)', borderRadius: 8 }}>
                    {scan.files.map(f => (
                      <div key={f.filename} style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '8px 10px', borderBottom: '1px solid var(--line)' }}>
                        <input
                          type="checkbox"
                          checked={!!selection[f.filename]}
                          onChange={e => {
                            const on = e.target.checked
                            setFileSel(f.filename, on ? (selection[f.filename] || (f.paper_id ? String(f.paper_id) : '')) : '')
                          }}
                        />
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={f.filename}>{f.filename}</div>
                          <div className="muted" style={{ fontSize: 11 }}>
                            {Math.round(f.size / 1024)} KB
                            {f.match === 'recorded' && ' · 已登记'}
                            {f.match === 'date' && ' · 按日期匹配'}
                            {f.match === 'title' && ' · 按标题匹配'}
                            {f.match === 'none' && ' · 未匹配'}
                            {f.already_in_zotero && f.already_has_pdf && f.recorded && ' · ✓已同步'}
                          </div>
                        </div>
                        <select
                          className="select"
                          style={{ maxWidth: 300 }}
                          value={selection[f.filename] || ''}
                          onChange={e => setFileSel(f.filename, e.target.value)}
                        >
                          <option value="">— 跳过 —</option>
                          {scan.candidates.map(c => (
                            <option key={c.id} value={c.id}>{c.paper_date} · {c.title.slice(0, 40)}</option>
                          ))}
                        </select>
                      </div>
                    ))}
                  </div>
                )}

                {syncResult && (
                  <div style={{ marginTop: 10, fontSize: 13 }}>
                    <b>结果</b>：推送题录 {syncResult.pushed} · 挂 PDF {syncResult.attached} · 补标签 {syncResult.tag_updated} · 失败 {syncResult.failed}
                    {syncResult.results?.some(r => r.error) && (
                      <ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>
                        {syncResult.results.filter(r => r.error).map((r, i) => (
                          <li key={i} className="muted" style={{ fontSize: 12 }}>{r.filename}：{r.error}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}

                <div className="modal-actions">
                  <button className="btn" onClick={() => setSyncOpen(false)} disabled={syncing}>关闭</button>
                  <button className="btn btn-primary" onClick={doSync} disabled={syncing}>
                    {syncing ? '同步中…' : (<><Upload size={14} strokeWidth={1.8} /> 开始同步到 Zotero</>)}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}