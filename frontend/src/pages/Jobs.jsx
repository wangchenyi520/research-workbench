import React, { useEffect, useState } from 'react'
import api from '../api'
import { useToast } from '../components/Toast'
import { Briefcase, X } from 'lucide-react'

const STATUS = {
  applied: ['已投递', 'badge-gray'],
  online_test: ['笔试', 'badge-info'],
  interview1: ['一面', 'badge-warn'],
  interview2: ['二面', 'badge-warn'],
  interview3: ['三面', 'badge-warn'],
  hr: ['HR面', 'badge-primary'],
  offer: ['Offer', 'badge-success'],
  rejected: ['已结束', 'badge-danger'],
}
const FLOW = ['applied', 'online_test', 'interview1', 'interview2', 'interview3', 'hr', 'offer']
const STAGE_OPTIONS = ['online_test', 'interview1', 'interview2', 'interview3', 'hr']

function JobForm({ initial, onClose, onSaved }) {
  const [form, setForm] = useState({
    company: initial?.company || '',
    position: initial?.position || '',
    city: initial?.city || '',
    channel: initial?.channel || '',
    resume_version: initial?.resume_version || '',
    status: initial?.status || 'applied',
    applied_at: initial?.applied_at || '',
    notes: initial?.notes || '',
  })
  const toast = useToast()
  const set = k => v => setForm(f => ({ ...f, [k]: v }))
  const submit = async () => {
    if (!form.company.trim()) return toast('请输入公司', 'error')
    const payload = { ...form, applied_at: form.applied_at || null }
    try {
      if (initial?.id) await api.put(`/jobs/applications/${initial.id}`, payload)
      else await api.post('/jobs/applications', payload)
      onSaved(); onClose()
    } catch (e) { toast('保存失败', 'error') }
  }
  return (
    <div className="modal-mask" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <h3>{initial ? '编辑投递' : '新增投递'}</h3>
        <label className="label">公司 *</label>
        <input className="input" placeholder="如 字节跳动" value={form.company} onChange={e => set('company')(e.target.value)} />
        <div className="row">
          <div style={{ flex: 1 }}><label className="label">岗位</label><input className="input" placeholder="如 算法工程师/感知" value={form.position} onChange={e => set('position')(e.target.value)} /></div>
          <div style={{ flex: 1 }}><label className="label">城市</label><input className="input" placeholder="如 北京/上海" value={form.city} onChange={e => set('city')(e.target.value)} /></div>
        </div>
        <div className="row">
          <div style={{ flex: 1 }}><label className="label">渠道/内推人</label><input className="input" placeholder="如 学长内推/官网" value={form.channel} onChange={e => set('channel')(e.target.value)} /></div>
          <div style={{ flex: 1 }}><label className="label">简历版本</label><input className="input" placeholder="如 v2" value={form.resume_version} onChange={e => set('resume_version')(e.target.value)} /></div>
        </div>
        <div className="row">
          <div style={{ flex: 1 }}><label className="label">阶段</label>
            <select className="select" value={form.status} onChange={e => set('status')(e.target.value)}>
              {Object.keys(STATUS).map(s => <option key={s} value={s}>{STATUS[s][0]}</option>)}
            </select>
          </div>
          <div style={{ flex: 1 }}><label className="label">投递日期</label>
            <input type="date" className="input" value={form.applied_at} onChange={e => set('applied_at')(e.target.value)} />
          </div>
        </div>
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

function EventForm({ app, onClose, onSaved }) {
  const [form, setForm] = useState({ event_date: new Date().toISOString().slice(0, 10), stage: 'interview1', note: '' })
  const toast = useToast()
  const set = k => v => setForm(f => ({ ...f, [k]: v }))
  const submit = async () => {
    try {
      await api.post(`/jobs/applications/${app.id}/events`, form)
      onSaved(); onClose()
    } catch (e) { toast('保存失败', 'error') }
  }
  return (
    <div className="modal-mask" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <h3>添加时间线 · {app.company}</h3>
        <label className="label">阶段</label>
        <select className="select" value={form.stage} onChange={e => set('stage')(e.target.value)}>
          {STAGE_OPTIONS.map(s => <option key={s} value={s}>{STATUS[s][0]}</option>)}
        </select>
        <label className="label">日期</label>
        <input type="date" className="input" value={form.event_date} onChange={e => set('event_date')(e.target.value)} />
        <label className="label">记录（考了什么/进展）</label>
        <textarea className="textarea" value={form.note} onChange={e => set('note')(e.target.value)} />
        <div className="modal-actions">
          <button className="btn" onClick={onClose}>取消</button>
          <button className="btn btn-primary" onClick={submit}>添加</button>
        </div>
      </div>
    </div>
  )
}

export default function Jobs() {
  const [items, setItems] = useState([])
  const [stats, setStats] = useState(null)
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState(null)
  const [eventFor, setEventFor] = useState(null)
  const [expanded, setExpanded] = useState(null)
  const toast = useToast()

  const load = () => {
    api.get('/jobs/applications').then(r => setItems(r.data))
    api.get('/jobs/stats').then(r => setStats(r.data))
  }
  useEffect(load, [])

  const setStatus = async (a, s) => {
    await api.put(`/jobs/applications/${a.id}`, { status: s })
    load()
  }
  const del = async a => {
    if (!confirm(`删除投递「${a.company}」？`)) return
    await api.delete(`/jobs/applications/${a.id}`)
    toast('已删除'); load()
  }
  const delEvent = async (a, eid) => {
    if (!confirm('删除这条记录？')) return
    await api.delete(`/jobs/events/${eid}`)
    load()
  }

  return (
    <div>
      <div className="page-header">
        <h1><span className="page-icon"><Briefcase size={22} strokeWidth={1.75} /></span>求职投递</h1>
        <button className="btn btn-primary" onClick={() => setShowForm(true)}>+ 新增投递</button>
      </div>

      <div className="grid grid-4" style={{ marginBottom: 16 }}>
        <div className="stat-card stat-purple"><div className="stat-value">{stats?.total ?? '–'}</div><div className="stat-label">总投递</div></div>
        <div className="stat-card stat-blue"><div className="stat-value">{stats?.active ?? '–'}</div><div className="stat-label">进行中</div></div>
        <div className="stat-card stat-green"><div className="stat-value">{stats?.offer ?? '–'}</div><div className="stat-label">Offer</div></div>
        <div className="stat-card stat-orange"><div className="stat-value">{stats?.rejected ?? '–'}</div><div className="stat-label">已结束</div></div>
      </div>

      {stats?.pipeline && (
        <div className="card" style={{ marginBottom: 14 }}>
          <div className="row" style={{ gap: 0, alignItems: 'flex-end' }}>
            {stats.pipeline.map(p => (
              <div key={p.stage} style={{ flex: 1, textAlign: 'center' }}>
                <div className="stat-value" style={{ fontSize: 20 }}>{p.count}</div>
                <div className="muted" style={{ fontSize: 12 }}>{p.label}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {items.length === 0 && <div className="card empty">还没有投递记录，秋招加油！从意向公司开始吧</div>}

      {items.map(a => {
        const curIdx = FLOW.indexOf(a.status)
        return (
          <div className="card" key={a.id} style={{ marginBottom: 12 }}>
            <div className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div style={{ flex: 1 }}>
                <div className="row" style={{ gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                  <strong style={{ fontSize: 15 }}>{a.company}</strong>
                  <span className={`badge ${STATUS[a.status]?.[1] || 'badge-gray'}`}>{STATUS[a.status]?.[0] || a.status}</span>
                </div>
                <div className="muted" style={{ marginTop: 4 }}>
                  {[a.position, a.city, a.channel && `内推:${a.channel}`, a.resume_version && `简历${a.resume_version}`].filter(Boolean).join(' · ') || '—'}
                  {a.applied_at && ` · 投于 ${a.applied_at}`}
                </div>
              </div>
              <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
                <button className="btn btn-sm" onClick={() => setEventFor(a)}>+ 时间线</button>
                <button className="btn btn-sm" onClick={() => setEditing(a)}>编辑</button>
                <button className="btn btn-sm btn-danger" onClick={() => del(a)}>删除</button>
              </div>
            </div>

            <div className="paper-flow">
              {FLOW.map((s, i) => (
                <React.Fragment key={s}>
                  <div
                    className={`flow-node ${i <= curIdx ? 'done' : ''} ${i === curIdx ? 'current' : ''}`}
                    onClick={() => a.status !== 'rejected' && setStatus(a, s)}
                    title={`设为「${STATUS[s][0]}」`}
                  >
                    <span className="flow-dot" />
                    <span className="flow-label">{STATUS[s][0]}</span>
                  </div>
                  {i < FLOW.length - 1 && <div className={`flow-line ${i < curIdx ? 'done' : ''}`} />}
                </React.Fragment>
              ))}
            </div>
            <div className="row" style={{ gap: 6 }}>
              {a.status !== 'rejected' && <button className="btn btn-sm" onClick={() => setStatus(a, 'rejected')}>标记结束</button>}
              {a.status !== 'offer' && a.status !== 'rejected' && <button className="btn btn-sm btn-primary" onClick={() => setStatus(a, 'offer')}>标记 Offer</button>}
            </div>

            {a.notes && <div className="muted" style={{ marginTop: 8 }}>{a.notes}</div>}

            {a.events.length > 0 && (
              <div style={{ marginTop: 10 }}>
                <button className="btn btn-sm" onClick={() => setExpanded(expanded === a.id ? null : a.id)}>
                  {expanded === a.id ? '收起时间线' : `时间线 (${a.events.length})`}
                </button>
                {expanded === a.id && (
                  <div style={{ marginTop: 8, paddingLeft: 4 }}>
                    {a.events.map(e => (
                      <div key={e.id} className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
                        <div style={{ flex: 1 }}>
                          <div className="row" style={{ gap: 6, alignItems: 'center' }}>
                            <span className="badge badge-info">{STATUS[e.stage]?.[0] || e.stage}</span>
                            <span className="muted" style={{ fontSize: 12 }}>{e.event_date}</span>
                          </div>
                          {e.note && <div className="muted" style={{ marginTop: 2, fontSize: 13 }}>{e.note}</div>}
                        </div>
                        <button className="btn btn-sm" onClick={() => delEvent(a, e.id)}><X size={14} strokeWidth={1.8} /></button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )
      })}

      {showForm && <JobForm initial={null} onClose={() => setShowForm(false)} onSaved={load} />}
      {editing && <JobForm initial={editing} onClose={() => setEditing(null)} onSaved={load} />}
      {eventFor && <EventForm app={eventFor} onClose={() => setEventFor(null)} onSaved={load} />}
    </div>
  )
}
