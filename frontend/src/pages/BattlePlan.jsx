import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Flag, RefreshCw, Upload, Sparkles, Target, FileText, ClipboardList, BookOpen, Pencil } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import api from '../api'
import { useToast } from '../components/Toast'
import CopyBtn from '../components/CopyBtn'
import DoubleConfirm from '../components/DoubleConfirm'
import MdCodeBlock from '../components/MdCodeBlock'

const KIND_LABEL = {
  check: '勾选', update: '修改', delete: '删除', append: '新增', progress: '进度表',
  task_check: '任务勾选', task_update: '任务修改', task_delete: '任务移除', task_append: '任务新增',
  task_block_create: '任务块', task_md: '文档→工作台',
}
const KIND_BADGE = {
  check: 'badge-success', update: 'badge-info', delete: 'badge-danger', append: 'badge-warn', progress: 'badge-primary',
  task_check: 'badge-success', task_update: 'badge-info', task_delete: 'badge-danger', task_append: 'badge-warn',
  task_block_create: 'badge-primary', task_md: 'badge-success',
}
const PART_LABEL = {
  milestones: 'M1-M6 里程碑',
  goals: '周目标 + 三主线',
  skills: '技能栈（03/04 路径）',
  daily: '逐日任务清单',
  life: '提醒与健身习惯',
}

function daysBetween(a, b) {
  return Math.round((new Date(b) - new Date(a)) / 86400000)
}

const DOC_MD_COMPONENTS = {
  pre: ({ children }) => <MdCodeBlock>{children}</MdCodeBlock>,
}

export default function BattlePlan() {
  const toast = useToast()
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  const [importOpen, setImportOpen] = useState(false)
  const [importPreview, setImportPreview] = useState(null)
  const [importParts, setImportParts] = useState(['milestones', 'goals', 'skills', 'daily', 'life'])
  const [includePast, setIncludePast] = useState(false)
  const [importing, setImporting] = useState(false)

  const [syncPreview, setSyncPreview] = useState(null)
  const [syncConfirm, setSyncConfirm] = useState(false)
  const [syncExclude, setSyncExclude] = useState([])
  const [syncing, setSyncing] = useState(false)

  const [reportOpen, setReportOpen] = useState(false)
  const [reportDraft, setReportDraft] = useState('')
  const [reportLoading, setReportLoading] = useState(false)

  const [docsOpen, setDocsOpen] = useState(false)
  const [docList, setDocList] = useState([])
  const [doc, setDoc] = useState(null)
  const [docEditing, setDocEditing] = useState(false)
  const [docDraft, setDocDraft] = useState('')
  const [docLoading, setDocLoading] = useState(false)
  const [docSaving, setDocSaving] = useState(false)

  const load = () => {
    setLoading(true)
    api.get('/self-analysis/overview')
      .then(r => setData(r.data))
      .catch(e => toast(e.response?.data?.detail || '加载失败', 'error'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const fetchImportPreview = async (parts, past) => {
    try {
      const r = await api.post('/self-analysis/import', { parts, apply: false, include_past: past })
      setImportPreview(r.data)
    } catch (e) {
      toast(e.response?.data?.detail || '预览失败', 'error')
      setImportOpen(false)
    }
  }

  const openImport = () => {
    setImportOpen(true)
    setImportPreview(null)
    fetchImportPreview(importParts, includePast)
  }

  const togglePart = p => {
    const next = importParts.includes(p) ? importParts.filter(x => x !== p) : [...importParts, p]
    setImportParts(next)
    if (next.length) fetchImportPreview(next, includePast)
    else setImportPreview(null)
  }

  const togglePast = () => {
    const next = !includePast
    setIncludePast(next)
    fetchImportPreview(importParts, next)
  }

  const doImport = async () => {
    if (!importParts.length) return toast('请至少勾选一类内容', 'error')
    setImporting(true)
    try {
      const r = await api.post('/self-analysis/import', { parts: importParts, apply: true, include_past: includePast })
      const t = r.data.totals
      toast(`导入完成：新建 ${t.created} 项，跳过 ${t.skipped} 项（已存在的不会重复创建）`)
      setImportOpen(false)
      load()
    } catch (e) {
      toast(e.response?.data?.detail || '导入失败', 'error')
    } finally {
      setImporting(false)
    }
  }

  const openSync = async () => {
    try {
      const r = await api.get('/self-analysis/sync-preview')
      const chs = r.data.changes || []
      if (!chs.length) return toast('没有需要同步的改动（工作台与计划文档一致）')
      setSyncPreview(r.data)
      setSyncExclude([])
      setSyncConfirm(true)
    } catch (e) {
      toast(e.response?.data?.detail || '获取改动失败', 'error')
    }
  }

  const doSync = async () => {
    setSyncing(true)
    try {
      const r = await api.post('/self-analysis/sync', { exclude: syncExclude })
      const sk = r.data.skipped?.length || 0
      toast(`已同步 ${r.data.applied} 处改动到计划文档${sk ? `，冲突跳过 ${sk} 处（已备份）` : '（已自动备份）'}`)
      setSyncConfirm(false)
      setSyncPreview(null)
      load()
    } catch (e) {
      toast(e.response?.data?.detail || '同步失败', 'error')
    } finally {
      setSyncing(false)
    }
  }

  const genReport = async () => {
    setReportOpen(true)
    setReportDraft('')
    setReportLoading(true)
    try {
      const r = await api.post('/ai/advisor-report')
      setReportDraft(r.data.draft)
    } catch (e) {
      toast(e.response?.data?.detail || '生成失败，请确认已配置 DeepSeek Key', 'error')
      setReportOpen(false)
    } finally {
      setReportLoading(false)
    }
  }

  const openDocs = async () => {
    setDocsOpen(true)
    setDocList([])
    setDoc(null)
    setDocEditing(false)
    try {
      const r = await api.get('/self-analysis/docs')
      setDocList(r.data.files || [])
    } catch (e) {
      toast(e.response?.data?.detail || '加载文档列表失败', 'error')
    }
  }

  const openDoc = async path => {
    setDocLoading(true)
    try {
      const r = await api.get('/self-analysis/docs/content', { params: { path } })
      setDoc(r.data)
      setDocEditing(false)
      setDocDraft('')
    } catch (e) {
      toast(e.response?.data?.detail || '读取失败', 'error')
    } finally {
      setDocLoading(false)
    }
  }

  const saveDoc = async force => {
    if (!doc) return
    setDocSaving(true)
    try {
      const r = await api.put('/self-analysis/docs/content', {
        path: doc.path, content: docDraft, base_mtime: doc.mtime, force: !!force,
      })
      toast(`已保存 ${r.data.path}（已自动备份）`)
      setDoc(d => ({ ...d, content: docDraft, mtime: r.data.mtime, size: r.data.size }))
      setDocEditing(false)
    } catch (e) {
      if (e.response?.status === 409 && !force) {
        const yes = window.confirm('这个文件刚被其他程序修改过。\n\n继续保存会覆盖那边的改动（写前会自动备份，可恢复）。\n\n确定强制覆盖吗？')
        if (yes) {
          setDocSaving(false)
          return saveDoc(true)
        }
      } else {
        toast(e.response?.data?.detail || '保存失败', 'error')
      }
    } finally {
      setDocSaving(false)
    }
  }

  const fmtMtime = m => {
    if (!m) return ''
    const d = new Date(m * 1000)
    const p2 = n => String(n).padStart(2, '0')
    return `${d.getMonth() + 1}/${d.getDate()} ${p2(d.getHours())}:${p2(d.getMinutes())}`
  }

  if (loading && !data) return <div className="skeleton" style={{ height: 360 }} />

  if (data && !data.configured) {
    return (
      <div>
        <div className="page-header">
          <h1><span className="page-icon"><Flag size={22} strokeWidth={1.75} /></span>作战计划</h1>
        </div>
        <div className="card empty" style={{ marginTop: 24 }}>
          <div style={{ marginBottom: 12 }}>还没有配置 Self_analysis 规划文件夹路径。</div>
          <button className="btn btn-primary" onClick={() => navigate('/settings')}>去设置页配置</button>
        </div>
      </div>
    )
  }

  const live = (data && data.live) || {}
  const phase = data && data.phase
  const week = data && data.week
  const todayStr = data && data.today
  const phaseTotal = phase && phase.start && phase.end ? daysBetween(phase.start, phase.end) + 1 : 0
  const phaseElapsed = phase && phase.start && todayStr ? Math.max(0, Math.min(phaseTotal, daysBetween(phase.start, todayStr) + 1)) : 0
  const phasePct = phaseTotal ? Math.round((phaseElapsed / phaseTotal) * 100) : 0
  const ckpts = (data && data.checkpoints) || []
  const skills = live.skills || []
  const oj = live.oj || {}
  const papers = live.papers || []
  const weekStat = live.week || {}
  const lit = live.literature || {}
  const goalList = live.goals || []
  const fmtSec = s => {
    s = s || 0
    const h = Math.floor(s / 3600)
    const m = Math.floor((s % 3600) / 60)
    return h ? `${h}h ${m}m` : `${m}m`
  }
  const lineGoal = ln => {
    const base = ln.name.split('（')[0]
    return goalList.find(g => g.title.includes(base))
  }

  return (
    <div className="bp-page">
      <div className="page-header">
        <h1><span className="page-icon"><Flag size={22} strokeWidth={1.75} /></span>作战计划</h1>
        <div className="row" style={{ gap: 8 }}>
          <button className="btn" onClick={() => load()} title="刷新"><RefreshCw size={14} strokeWidth={1.8} /> 刷新</button>
          <button className="btn" onClick={openDocs}><BookOpen size={14} strokeWidth={1.8} /> 计划文档</button>
          <button className="btn" onClick={openImport}><Upload size={14} strokeWidth={1.8} /> 导入到工作台</button>
          <button className="btn btn-primary" onClick={openSync}><ClipboardList size={14} strokeWidth={1.8} /> 同步到计划文档</button>
          <button className="btn" onClick={genReport}><Sparkles size={14} strokeWidth={1.8} /> 导师周报草稿</button>
        </div>
      </div>

      {phase && (
        <div className="card bp-hero">
          <div className="row" style={{ alignItems: 'flex-end', gap: 16 }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div className="muted">当前阶段</div>
              <div style={{ fontSize: 22, fontWeight: 800 }}>
                {phase.id} · {phase.title || ''}
                <span className="badge badge-primary" style={{ marginLeft: 10 }}>{phase.range}</span>
              </div>
              {phase.goal && <div className="muted" style={{ marginTop: 4 }}>阶段目标：{phase.goal}</div>}
            </div>
            <div style={{ textAlign: 'right' }}>
              <div className="muted">阶段进度</div>
              <div style={{ fontSize: 22, fontWeight: 800, color: 'var(--primary)' }}>{phasePct}%</div>
              <div className="muted" style={{ fontSize: 12 }}>第 {phaseElapsed}/{phaseTotal} 天</div>
            </div>
          </div>
          <div className="bp-phase-bar"><div style={{ width: `${phasePct}%` }} /></div>
          {week && (
            <div className="bp-week">
              <span className="badge badge-warn">本周 第{week.n}周（{week.range}）</span>
              <div className="muted" style={{ fontSize: 13, marginTop: 6 }}>
                📄 论文线：{week.paper || '—'}
              </div>
              <div className="muted" style={{ fontSize: 13 }}>⚙️ 技术线：{week.tech || '—'}</div>
            </div>
          )}
        </div>
      )}

      {ckpts.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="card-title">里程碑检查点（M1-M6）<span className="muted" style={{ fontSize: 12, marginLeft: 8 }}>来自作战计划 · 达不到就调整</span></div>
          <div className="bp-checkpoints">
            {ckpts.map(c => {
              const dl = c.date && todayStr ? daysBetween(todayStr, c.date) : null
              const passed = dl !== null && dl < 0
              const isNext = !passed && ckpts.find(x => x.date && daysBetween(todayStr, x.date) >= 0) === c
              return (
                <div key={c.id} className={`bp-ckpt ${isNext ? 'next' : ''} ${passed ? 'passed' : ''}`}>
                  <div className="bp-ckpt-id">{c.id}</div>
                  <div className="bp-ckpt-date muted">{c.date_text}{dl !== null ? (dl >= 0 ? ` · 剩 ${dl} 天` : ` · 已过 ${-dl} 天`) : ''}</div>
                  <div className="bp-ckpt-text">{c.content}</div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      <div className="bp-lines" style={{ marginTop: 16 }}>
        {((data && data.lines) || []).map(ln => {
          const g = lineGoal(ln)
          return (
            <div className="card bp-line-card" key={ln.name}>
              <div className="card-title">🎯 {ln.name}</div>
              <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>{ln.desc}</div>
              {g && (
                <div className="bp-goal-bar">
                  <div className="row" style={{ justifyContent: 'space-between' }}>
                    <span style={{ fontSize: 12 }}>{g.title.length > 22 ? g.title.slice(0, 22) + '…' : g.title}</span>
                    <span className="muted" style={{ fontSize: 12 }}>{Math.round(g.progress)}%</span>
                  </div>
                  <div className="bp-bar"><div style={{ width: `${Math.min(100, g.progress)}%` }} /></div>
                </div>
              )}
              {ln.desc.includes('文献') && (
                <div className="muted" style={{ fontSize: 12 }}>文献：本周读 {lit.read_week || 0} 篇 · 在读 {lit.reading || 0} 篇 · 库内共 {lit.total || 0} 篇</div>
              )}
              {ln.desc.includes('PyTorch') && (
                <div className="muted" style={{ fontSize: 12 }}>刷题：已 AC {oj.ac || 0} 题（本周 {oj.week || 0}）· 连续 {oj.streak || 0} 天</div>
              )}
            </div>
          )
        })}
      </div>

      <div className="grid" style={{ gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', marginTop: 16 }}>
        <div className="stat-card stat-purple"><span className="stat-icon"><Target size={15} strokeWidth={2} /></span><div className="stat-label">刷题 AC</div><div className="stat-value">{oj.ac || 0} 题</div></div>
        <div className="stat-card stat-blue"><span className="stat-icon"><RefreshCw size={15} strokeWidth={2} /></span><div className="stat-label">连续产出</div><div className="stat-value">{live.reward_streak || 0} 天</div></div>
        <div className="stat-card stat-green"><span className="stat-icon"><FileText size={15} strokeWidth={2} /></span><div className="stat-label">本周投入</div><div className="stat-value" style={{ fontSize: 24 }}>{fmtSec(weekStat.focus_seconds)}</div></div>
        <div className="stat-card stat-orange"><span className="stat-icon"><ClipboardList size={15} strokeWidth={2} /></span><div className="stat-label">本周完成</div><div className="stat-value">{weekStat.tasks_done || 0} 项</div></div>
      </div>

      <div className="grid grid-2" style={{ marginTop: 16 }}>
        <div className="card">
          <div className="card-title">技能进度（导入后可在此看，也可到今日页编辑）</div>
          {skills.length === 0 && <div className="muted">还没有技能栈，点右上角「导入到工作台」把 03/04 学习路径导入</div>}
          {skills.map(s => (
            <div key={s.id} style={{ marginBottom: 10 }}>
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <span style={{ fontWeight: 600, fontSize: 13 }}>{s.name}</span>
                <span className="muted" style={{ fontSize: 12 }}>{s.progress}%</span>
              </div>
              <div className="bp-bar"><div style={{ width: `${Math.min(100, s.progress)}%` }} /></div>
              <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>
                {s.stages.map(x => `${x.name}${x.progress ? ` ${x.progress}%` : ''}`).join(' · ')}
              </div>
            </div>
          ))}
        </div>

        <div className="card">
          <div className="card-title">每日固定节奏 & 本周铁律</div>
          {((data && data.rhythm) || []).map(r => (
            <div className="row" style={{ gap: 10, padding: '4px 0', fontSize: 13 }} key={r.time}>
              <span className="badge badge-info">{r.time}</span>
              <span>{r.what}</span>
            </div>
          ))}
          {((data && data.iron_rules) || []).length > 0 && (
            <div style={{ marginTop: 10 }}>
              <div className="muted" style={{ fontWeight: 700, fontSize: 13, marginBottom: 4 }}>本周铁律</div>
              {data.iron_rules.map((r, i) => <div key={i} style={{ fontSize: 13, padding: '2px 0' }}>· {r}</div>)}
            </div>
          )}
        </div>
      </div>

      <div style={{ marginTop: 16 }}>
        <div className="card">
          <div className="card-title">复盘历史（复盘/ · plan/复盘/）</div>
          {((data && data.reviews) || []).length === 0 && (
            <div className="muted" style={{ fontSize: 12 }}>还没有复盘文件。周日晚在「周复盘」页填写后，可一键导出到 plan/复盘/第X周.md。</div>
          )}
          {((data && data.reviews) || []).map(f => (
            <div key={f} style={{ fontSize: 13, padding: '4px 0', borderBottom: '1px solid var(--border)' }}>📄 {f}</div>
          ))}
        </div>
      </div>

      {importOpen && (
        <div className="modal-mask" onClick={() => !importing && setImportOpen(false)}>
          <div className="modal" style={{ width: 720, maxWidth: '94vw' }} onClick={e => e.stopPropagation()}>
            <h3>📥 导入作战计划到工作台</h3>
            <div className="muted" style={{ marginBottom: 10 }}>
              把 Self_analysis 的计划结构导入为工作台实体（只读 md，不会修改你的文件）。重复导入时已存在的项会自动跳过。
            </div>
            <div className="row" style={{ flexWrap: 'wrap', gap: 12, marginBottom: 10 }}>
              {Object.entries(PART_LABEL).map(([p, label]) => (
                <label key={p} className="row" style={{ gap: 6, cursor: 'pointer', fontSize: 13 }}>
                  <input type="checkbox" checked={importParts.includes(p)} onChange={() => togglePart(p)} /> {label}
                </label>
              ))}
            </div>
            <label className="row" style={{ gap: 6, cursor: 'pointer', fontSize: 13, marginBottom: 10 }}>
              <input type="checkbox" checked={includePast} onChange={togglePast} />
              包含已过去日期的任务（默认不导入，避免一次性出现大量「待补」）
            </label>
            {importPreview && (
              <div className="dc-preview">
                {Object.entries(importPreview.parts).map(([p, v]) => (
                  <div key={p} style={{ marginBottom: 8 }}>
                    <div style={{ fontWeight: 600, fontSize: 13 }}>
                      {PART_LABEL[p] || p}：将新建 <span style={{ color: 'var(--primary)' }}>{v.count}</span> 项，跳过 {v.skipped.length} 项
                    </div>
                    {(v.created || []).slice(0, 4).map((x, i) => (
                      <div key={i} className="muted" style={{ fontSize: 12, marginLeft: 10 }}>
                        · {typeof x === 'string' ? x : (x.title || x.name || x.content)} {x.date ? `（${x.date}）` : ''}
                      </div>
                    ))}
                    {v.created.length > 4 && <div className="muted" style={{ fontSize: 12, marginLeft: 10 }}>… 等 {v.created.length} 项</div>}
                  </div>
                ))}
              </div>
            )}
            {!importPreview && <div className="muted">正在预览…</div>}
            <div className="modal-actions">
              <button className="btn" onClick={() => setImportOpen(false)} disabled={importing}>取消</button>
              <button className="btn btn-primary" onClick={doImport} disabled={importing || !importPreview}>
                {importing ? '导入中…' : '确认导入'}
              </button>
            </div>
          </div>
        </div>
      )}

      <DoubleConfirm
        open={syncConfirm}
        title="同步改动到计划文档"
        desc="以下是工作台与计划文档的差异，将写回 Self_analysis（取消勾选可排除某项）。写入前自动备份。"
        onCancel={() => { if (!syncing) { setSyncConfirm(false); setSyncPreview(null) } }}
        onConfirm={doSync}
        busy={syncing}
      >
        {(syncPreview && syncPreview.changes || []).map(ch => (
          <label key={ch.key} className={`dc-item ${syncExclude.includes(ch.key) ? 'off' : ''}`}>
            <input type="checkbox" checked={!syncExclude.includes(ch.key)}
              onChange={() => setSyncExclude(s => s.includes(ch.key) ? s.filter(x => x !== ch.key) : [...s, ch.key])} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div className="row" style={{ gap: 6, alignItems: 'center' }}>
                <span className={`badge ${KIND_BADGE[ch.kind] || 'badge-gray'}`}>{KIND_LABEL[ch.kind] || ch.kind}</span>
                <span style={{ fontWeight: 600, fontSize: 13 }}>{ch.title}</span>
              </div>
              <div className="muted" style={{ fontSize: 11 }}>{ch.file}{ch.section ? ` · ${ch.section}` : ''}</div>
              {ch.kind !== 'progress' && (
                <div className="dc-diff">
                  <div className="dc-before">{ch.kind === 'append' || ch.kind === 'task_append' ? '（新增行）' : (ch.before || '（无）')}</div>
                  <div className="dc-after" style={{ whiteSpace: 'pre-wrap' }}>{ch.after || '（删除该行）'}</div>
                </div>
              )}
            </div>
          </label>
        ))}
        {(syncPreview && syncPreview.skipped || []).length > 0 && (
          <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>
            ⚠️ {syncPreview.skipped.length} 处冲突将自动跳过（找不到对应行或被手动改过）：{syncPreview.skipped.slice(0, 3).map(s => s.title).join('、')}…
          </div>
        )}
      </DoubleConfirm>

      {reportOpen && (
        <div className="modal-mask" onClick={() => !reportLoading && setReportOpen(false)}>
          <div className="modal" style={{ width: 720, maxWidth: '94vw' }} onClick={e => e.stopPropagation()}>
            <h3>📮 导师周报草稿（本周数据自动汇总）</h3>
            {reportLoading && <div className="muted">AI 正在汇总本周进展…</div>}
            {!reportLoading && (
              <>
                <textarea className="input" style={{ width: '100%', height: 300, lineHeight: 1.7, fontFamily: 'inherit' }}
                  value={reportDraft} onChange={e => setReportDraft(e.target.value)} />
                <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>可直接修改后复制发给导师（周五发送）。</div>
              </>
            )}
            <div className="modal-actions">
              <button className="btn" onClick={() => setReportOpen(false)} disabled={reportLoading}>关闭</button>
              {!reportLoading && reportDraft && <CopyBtn text={reportDraft} />}
            </div>
          </div>
        </div>
      )}

      {docsOpen && (
        <div className="modal-mask" onClick={() => !docSaving && setDocsOpen(false)}>
          <div className="modal" style={{ width: 1040, maxWidth: '96vw' }} onClick={e => e.stopPropagation()}>
            <h3><BookOpen size={18} strokeWidth={1.8} /> 计划文档（Self_analysis）</h3>
            <div className="muted" style={{ marginBottom: 10 }}>
              直接查看和编辑手写计划文档，保存即写回文件夹原文件（保存前自动备份到 data/sa_backups/）。
            </div>
            <div className="sa-doc-layout">
              <div className="sa-doc-list">
                {docList.length === 0 && <div className="muted" style={{ fontSize: 12, padding: 8 }}>没有找到 md 文件</div>}
                {docList.map(f => (
                  <button key={f.path} className={`sa-doc-item ${doc && doc.path === f.path ? 'active' : ''}`}
                    onClick={() => openDoc(f.path)} title={f.path}>
                    <span className="sa-doc-item-name">{f.name}</span>
                    <span className="sa-doc-item-dir muted">{f.dir ? `${f.dir}/` : '·'} {fmtMtime(f.mtime)}</span>
                  </button>
                ))}
              </div>
              <div className="sa-doc-main">
                {!doc && !docLoading && <div className="muted" style={{ padding: 20 }}>← 从左侧选择一个文档</div>}
                {docLoading && <div className="skeleton" style={{ flex: 1, minHeight: 200 }} />}
                {doc && !docLoading && (
                  <>
                    <div className="row" style={{ justifyContent: 'space-between', marginBottom: 8, gap: 8 }}>
                      <span style={{ fontSize: 13, fontWeight: 600, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{doc.path}</span>
                      <div className="row" style={{ gap: 8, flex: '0 0 auto' }}>
                        {!docEditing ? (
                          <button className="btn btn-sm" onClick={() => { setDocEditing(true); setDocDraft(doc.content) }}>
                            <Pencil size={14} strokeWidth={1.8} /> 编辑
                          </button>
                        ) : (
                          <>
                            <button className="btn btn-sm" onClick={() => setDocEditing(false)} disabled={docSaving}>取消</button>
                            <button className="btn btn-sm btn-primary" onClick={() => saveDoc(false)} disabled={docSaving}>
                              {docSaving ? '保存中…' : '保存'}
                            </button>
                          </>
                        )}
                      </div>
                    </div>
                    {docEditing ? (
                      <textarea className="textarea sa-doc-editor" value={docDraft} spellCheck={false}
                        onChange={e => setDocDraft(e.target.value)} />
                    ) : (
                      <div className="sa-doc-preview md-body">
                        <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}
                          components={DOC_MD_COMPONENTS}>{doc.content}</ReactMarkdown>
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>
            <div className="modal-actions">
              <button className="btn" onClick={() => setDocsOpen(false)} disabled={docSaving}>关闭</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
