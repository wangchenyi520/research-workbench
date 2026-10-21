import React, { useEffect, useState } from 'react'
import api from '../api'
import { useToast } from '../components/Toast'
import { BarChart3, FlaskConical } from 'lucide-react'

const EMPTY = { title: '', dataset: '', model: '', baseline: '', status: 'running', notes: '', metrics: {} }

function ExpForm({ initial, onClose, onSaved }) {
  const [form, setForm] = useState({
    title: initial?.title || '',
    dataset: initial?.dataset || '',
    model: initial?.model || '',
    baseline: initial?.baseline || '',
    status: initial?.status || 'running',
    notes: initial?.notes || '',
    metrics: { ...(initial?.metrics || {}) },
  })
  const toast = useToast()
  const set = k => v => setForm(f => ({ ...f, [k]: v }))
  const setMetric = (k, v) => setForm(f => ({ ...f, metrics: { ...f.metrics, [k]: v } }))
  const addMetric = () => setMetric(`指标${Object.keys(form.metrics).length + 1}`, '')

  const submit = async () => {
    if (!form.title.trim()) return toast('请输入实验标题', 'error')
    // 过滤空指标
    const metrics = Object.fromEntries(Object.entries(form.metrics).filter(([, v]) => v !== '' && v !== undefined))
    const payload = { ...form, metrics }
    try {
      if (initial?.id) await api.put(`/research/experiments/${initial.id}`, payload)
      else await api.post('/research/experiments', payload)
      onSaved(); onClose()
    } catch (e) { toast('保存失败', 'error') }
  }

  return (
    <div className="modal-mask" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <h3>{initial ? '编辑实验' : '新建实验'}</h3>
        <label className="label">实验标题 *</label>
        <input className="input" value={form.title} onChange={e => set('title')(e.target.value)} />
        <div className="row">
          <div style={{ flex: 1 }}><label className="label">数据集</label><input className="input" placeholder="如 IRSTD-1k" value={form.dataset} onChange={e => set('dataset')(e.target.value)} /></div>
          <div style={{ flex: 1 }}><label className="label">模型/方法</label><input className="input" placeholder="如 DNANet" value={form.model} onChange={e => set('model')(e.target.value)} /></div>
        </div>
        <div className="row">
          <div style={{ flex: 1 }}><label className="label">对比基线</label><input className="input" placeholder="如 baseline" value={form.baseline} onChange={e => set('baseline')(e.target.value)} /></div>
          <div style={{ flex: 1 }}><label className="label">状态</label>
            <select className="select" value={form.status} onChange={e => set('status')(e.target.value)}>
              <option value="running">进行中</option>
              <option value="done">已完成</option>
            </select>
          </div>
        </div>
        <label className="label">指标（如 mAP、IoU）</label>
        {Object.entries(form.metrics).map(([k, v]) => (
          <div className="row" key={k} style={{ marginBottom: 6 }}>
            <input className="input" style={{ flex: 1 }} value={k} onChange={e => {
              const { [k]: _old, ...rest } = form.metrics
              setForm(f => ({ ...f, metrics: { ...rest, [e.target.value]: v } }))
            }} />
            <input className="input" style={{ flex: 1 }} value={v} onChange={e => setMetric(k, e.target.value)} />
            <button className="btn btn-sm btn-danger" onClick={() => { const { [k]: _d, ...rest } = form.metrics; setForm(f => ({ ...f, metrics: rest })) }}>×</button>
          </div>
        ))}
        <button className="btn btn-sm" onClick={addMetric}>+ 添加指标</button>
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

function Comparison({ items }) {
  if (items.length < 2) {
    return <div className="empty"><span className="empty-icon">📊</span>至少 2 个实验才能对比</div>
  }
  const allMetrics = [...new Set(items.flatMap(e => Object.keys(e.metrics || {})))]
  return (
    <table className="compare-table">
      <thead>
        <tr>
          <th>实验</th>
          {allMetrics.map(m => <th key={m}>{m}</th>)}
        </tr>
      </thead>
      <tbody>
        {items.map(e => (
          <tr key={e.id}>
            <td>{e.title} <span className="muted">({e.model || e.dataset})</span></td>
            {allMetrics.map(m => <td key={m}>{e.metrics?.[m] ?? '—'}</td>)}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export default function Experiments() {
  const [items, setItems] = useState([])
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState(null)
  const [compare, setCompare] = useState(false)
  const [selected, setSelected] = useState(new Set())
  const toast = useToast()

  const load = () => {
    api.get('/research/experiments').then(r => setItems(r.data))
  }
  useEffect(load, [])

  const toggleSelect = id => {
    setSelected(prev => {
      const n = new Set(prev)
      if (n.has(id)) n.delete(id)
      else n.add(id)
      return n
    })
  }

  const del = async e => {
    if (!confirm(`删除实验「${e.title}」？`)) return
    await api.delete(`/research/experiments/${e.id}`)
    toast('已删除'); load()
  }

  const compareItems = items.filter(e => selected.has(e.id))

  return (
    <div>
      <div className="page-header">
        <h1><span className="page-icon"><FlaskConical size={22} strokeWidth={1.75} /></span>实验记录</h1>
        <div className="row">
          <button className="btn" onClick={() => setCompare(!compare)} disabled={items.length < 2}>
            {compare ? '退出对比' : (<><BarChart3 size={14} strokeWidth={1.8} /> 结果对比</>)}
          </button>
          <button className="btn btn-primary" onClick={() => setShowForm(true)}>+ 新建实验</button>
        </div>
      </div>

      {compare && <Comparison items={compareItems} />}

      <div className="grid grid-2" style={{ marginTop: 16 }}>
        {items.map(e => (
          <div className="card exp-card" key={e.id} onClick={() => !compare && setEditing(e)}>
            <div className="row" style={{ justifyContent: 'space-between' }}>
              {compare ? (
                <label className="row" style={{ gap: 8 }}>
                  <input type="checkbox" checked={selected.has(e.id)} onChange={() => toggleSelect(e.id)} onClick={ev => ev.stopPropagation()} />
                  <strong>{e.title}</strong>
                </label>
              ) : (
                <strong>{e.title}</strong>
              )}
              <span className={`badge ${e.status === 'done' ? 'badge-success' : 'badge-info'}`}>{e.status === 'done' ? '已完成' : '进行中'}</span>
            </div>
            <div className="row" style={{ marginTop: 8, gap: 8, flexWrap: 'wrap' }}>
              {e.dataset && <span className="badge badge-gray">数据集: {e.dataset}</span>}
              {e.model && <span className="badge badge-gray">模型: {e.model}</span>}
              {e.baseline && <span className="badge badge-gray">基线: {e.baseline}</span>}
            </div>
            {Object.keys(e.metrics || {}).length > 0 && (
              <div className="exp-metrics">
                {Object.entries(e.metrics).map(([k, v]) => (
                  <div className="exp-metric" key={k}>
                    <span className="muted">{k}</span>
                    <strong>{v}</strong>
                  </div>
                ))}
              </div>
            )}
            {e.notes && <div className="muted" style={{ marginTop: 8 }}>{e.notes}</div>}
            {!compare && (
              <div className="row" style={{ marginTop: 10, gap: 6 }}>
                <button className="btn btn-sm" onClick={ev => { ev.stopPropagation(); setEditing(e) }}>编辑</button>
                <button className="btn btn-sm btn-danger" onClick={ev => { ev.stopPropagation(); del(e) }}>删除</button>
              </div>
            )}
          </div>
        ))}
        {items.length === 0 && <div className="card empty" style={{ gridColumn: '1 / -1' }}>还没有实验记录，记录你的数据集、模型和指标吧</div>}
      </div>

      {showForm && <ExpForm initial={null} onClose={() => setShowForm(false)} onSaved={() => { setShowForm(false); load() }} />}
      {editing && <ExpForm initial={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load() }} />}
    </div>
  )
}
