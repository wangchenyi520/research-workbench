import { useEffect, useRef, useState } from 'react'
import { HeartPulse, Scale, CupSoda, Moon, Candy, Sparkles, Plus, Trash2, RefreshCw } from 'lucide-react'
import api, { todayStr } from '../api'
import { useToast } from '../components/Toast'

// 健康范围状态：≤上限=绿；≤2×上限=橙；再高=红（0 上限时 1 次即为略超）
const statusOf = (n, limit, kind) => {
  if (n <= limit) return { cls: 'badge-success', text: kind === 'drink' ? '在合理范围' : '正常范围' }
  if (n <= limit + Math.max(1, limit)) return { cls: 'badge-warn', text: kind === 'drink' ? '略超' : '略多' }
  return { cls: 'badge-danger', text: kind === 'drink' ? '明显超量' : '偏多' }
}

const SOURCE_LABEL = { food_db: '食品数据库', web: '网络检索', '': 'AI 知识' }
const CONF_LABEL = { high: '把握高', medium: '把握中', low: '把握低' }

export default function Life() {
  const toast = useToast()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  // 体重
  const [wDate, setWDate] = useState(todayStr())
  const [wInput, setWInput] = useState('')
  const [wBusy, setWBusy] = useState(false)

  // 饮品
  const [dName, setDName] = useState('')
  const [dVol, setDVol] = useState('')
  const [dDate, setDDate] = useState(todayStr())
  const [dSugar, setDSugar] = useState('')
  const [dFat, setDFat] = useState('')
  const [dCal, setDCal] = useState('')
  const [aiBusy, setAiBusy] = useState(false)
  const [aiInfo, setAiInfo] = useState(null)
  const [dBusy, setDBusy] = useState(false)

  // 夜间放松
  const [rDate, setRDate] = useState(todayStr())
  const [rBusy, setRBusy] = useState(false)

  // 健康范围（每周上限，行内可改）
  const [dLimit, setDLimit] = useState('3')
  const [rLimit, setRLimit] = useState('3')

  const lastDateRef = useRef(todayStr())

  const load = () => {
    api.get('/life/overview')
      .then(r => {
        setData(r.data)
        setDLimit(String(r.data.limits.drink_weekly))
        setRLimit(String(r.data.limits.relax_weekly))
      })
      .catch(e => toast(e.response?.data?.detail || '加载失败', 'error'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  // 跨天自动刷新（周统计口径随天变化；check 必须块体，见坑 #1）
  useEffect(() => {
    const timer = setInterval(() => {
      const d = todayStr()
      if (d !== lastDateRef.current) { lastDateRef.current = d; load() }
    }, 60000)
    const onFocus = () => {
      const d = todayStr()
      if (d !== lastDateRef.current) { lastDateRef.current = d; load() }
    }
    window.addEventListener('focus', onFocus)
    return () => { clearInterval(timer); window.removeEventListener('focus', onFocus) }
  }, [])

  const saveWeight = async () => {
    const w = parseFloat(wInput)
    if (!w || w < 20 || w > 500) return toast('请输入合理体重（20-500 斤）', 'error')
    setWBusy(true)
    try {
      await api.post('/self-analysis/weight', { weight: w, date: wDate })
      toast('已记录体重')
      setWInput('')
      load()
    } catch (e) {
      toast(e.response?.data?.detail || '保存失败', 'error')
    } finally {
      setWBusy(false)
    }
  }

  const analyzeDrink = async () => {
    const name = dName.trim()
    if (!name) return toast('先填写饮品名称，再让 AI 分析', 'error')
    setAiBusy(true)
    setAiInfo(null)
    try {
      const r = await api.post('/life/drinks/analyze', {
        name,
        volume_ml: dVol ? Number(dVol) : undefined,
      })
      setDSugar(String(r.data.sugar_g ?? ''))
      setDFat(String(r.data.fat_g ?? ''))
      setDCal(String(r.data.calories ?? ''))
      if (!dVol && r.data.volume_ml) setDVol(String(r.data.volume_ml))
      setAiInfo({ note: r.data.note, confidence: r.data.confidence, source: r.data.source })
      toast('AI 分析完成，可修改后保存')
    } catch (e) {
      toast(e.response?.data?.detail || 'AI 分析失败', 'error')
    } finally {
      setAiBusy(false)
    }
  }

  const saveDrink = async () => {
    const name = dName.trim()
    if (!name) return toast('请输入饮品名称', 'error')
    setDBusy(true)
    try {
      await api.post('/life/drinks', {
        name,
        date: dDate,
        volume_ml: Number(dVol) || 0,
        sugar_g: Number(dSugar) || 0,
        fat_g: Number(dFat) || 0,
        calories: Number(dCal) || 0,
        ai_analyzed: !!aiInfo,
        ai_note: aiInfo?.note || '',
      })
      toast('已记录饮品')
      setDName(''); setDVol(''); setDSugar(''); setDFat(''); setDCal(''); setAiInfo(null)
      load()
    } catch (e) {
      toast(e.response?.data?.detail || '保存失败', 'error')
    } finally {
      setDBusy(false)
    }
  }

  const delDrink = async id => {
    if (!window.confirm('删除这条饮品记录？')) return
    try {
      await api.delete(`/life/drinks/${id}`)
      toast('已删除')
      load()
    } catch (e) {
      toast(e.response?.data?.detail || '删除失败', 'error')
    }
  }

  const addRelax = async () => {
    setRBusy(true)
    try {
      await api.post('/life/relax', { date: rDate })
      toast('已记录一次')
      load()
    } catch (e) {
      toast(e.response?.data?.detail || '记录失败', 'error')
    } finally {
      setRBusy(false)
    }
  }

  const delRelax = async id => {
    if (!window.confirm('删除这条记录？')) return
    try {
      await api.delete(`/life/relax/${id}`)
      toast('已删除')
      load()
    } catch (e) {
      toast(e.response?.data?.detail || '删除失败', 'error')
    }
  }

  const saveLimit = async kind => {
    const raw = kind === 'drink' ? dLimit : rLimit
    const current = kind === 'drink' ? data?.limits?.drink_weekly : data?.limits?.relax_weekly
    const v = Math.max(0, Math.min(99, Number(raw) || 0))
    if (current === v) return
    try {
      const r = await api.put('/life/limits', { [kind === 'drink' ? 'drink_weekly' : 'relax_weekly']: v })
      setData(d => (d ? { ...d, limits: r.data.limits } : d))
      setDLimit(String(r.data.limits.drink_weekly))
      setRLimit(String(r.data.limits.relax_weekly))
      toast('健康范围已更新')
    } catch (e) {
      toast(e.response?.data?.detail || '保存失败', 'error')
      load()
    }
  }

  const limitEnter = fn => e => { if (e.key === 'Enter' && !e.nativeEvent.isComposing) { e.target.blur(); fn() } }

  if (loading && !data) return <div className="skeleton" style={{ height: 160, margin: 24 }} />

  const weight = data?.weight || {}
  const latest = weight.latest
  const prev = weight.prev
  const delta = latest && prev ? Math.round((latest.weight - prev.weight) * 10) / 10 : null
  const recs = (weight.records || []).slice(-14)
  const wMin = recs.length ? Math.min.apply(null, recs.map(r => r.weight)) : 0
  const wMax = recs.length ? Math.max.apply(null, recs.map(r => r.weight)) : 0
  // 柱高按「最小~最大」映射到 30%~100%（单条/无变化=60%，见「五.57」体重柱状图修复）
  const wPct = w => (wMax > wMin ? 30 + Math.round((70 * (w - wMin)) / (wMax - wMin)) : 60)

  const drinks = data?.drinks || {}
  const relax = data?.relax || {}
  const dSt = statusOf(drinks.week_count || 0, data?.limits?.drink_weekly ?? 3, 'drink')
  const rSt = statusOf(relax.week_count || 0, data?.limits?.relax_weekly ?? 3, 'relax')
  const daysElapsed = data
    ? Math.max(1, Math.round((new Date(data.today) - new Date(data.week_start)) / 86400000) + 1)
    : 1
  const sugarAvg = Math.round(((drinks.week_sugar || 0) / daysElapsed) * 10) / 10

  return (
    <div>
      <div className="page-header">
        <h1><span className="page-icon"><HeartPulse size={22} strokeWidth={1.75} /></span>生活记录</h1>
        <div className="row" style={{ gap: 8 }}>
          <span className="muted" style={{ fontSize: 12 }}>记录身体与生活的点滴，不评判，只观察</span>
          <button className="btn btn-sm" onClick={() => load()} title="刷新"><RefreshCw size={14} strokeWidth={1.8} /></button>
        </div>
      </div>

      <div className="grid grid-4">
        <div className="stat-card stat-purple">
          <span className="stat-icon"><Scale size={15} strokeWidth={2} /></span>
          <div className="stat-label">最新体重</div>
          <div className="stat-value">{latest ? latest.weight : '—'}<span className="muted"> 斤</span></div>
          <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>
            {latest ? latest.date.slice(5).replace('-', '/') : '还没有记录'}
            {delta !== null && ` · 较上次 ${delta > 0 ? '↑' : delta < 0 ? '↓' : ''}${Math.abs(delta)} 斤`}
          </div>
        </div>
        <div className="stat-card stat-blue">
          <span className="stat-icon"><CupSoda size={15} strokeWidth={2} /></span>
          <div className="stat-label">本周饮品</div>
          <div className="stat-value">{drinks.week_count || 0}<span className="muted"> 杯</span></div>
          <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>
            目标 ≤ {data?.limits?.drink_weekly ?? 3} 杯 · <span className={`badge ${dSt.cls}`}>{dSt.text}</span>
          </div>
        </div>
        <div className="stat-card stat-orange">
          <span className="stat-icon"><Moon size={15} strokeWidth={2} /></span>
          <div className="stat-label">本周夜间放松</div>
          <div className="stat-value">{relax.week_count || 0}<span className="muted"> 次</span></div>
          <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>
            目标 ≤ {data?.limits?.relax_weekly ?? 3} 次 · <span className={`badge ${rSt.cls}`}>{rSt.text}</span>
          </div>
        </div>
        <div className="stat-card stat-green">
          <span className="stat-icon"><Candy size={15} strokeWidth={2} /></span>
          <div className="stat-label">本周饮品糖分</div>
          <div className="stat-value">{Math.round(drinks.week_sugar || 0)}<span className="muted"> g</span></div>
          <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>
            ≈ {Math.round((drinks.week_sugar || 0) / 5)} 块方糖 · 日均 {sugarAvg}g（WHO 建议 ≤25g/天）
          </div>
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <div className="card-title">
          <span className="row" style={{ gap: 6, alignItems: 'center' }}>
            <Scale size={15} strokeWidth={1.8} /> 体重趋势
          </span>
          <span className="muted" style={{ fontSize: 12 }}>每周固定时间称 2-3 次更准</span>
        </div>
        <div className="row" style={{ gap: 8, marginBottom: 10, flexWrap: 'wrap' }}>
          <input className="input" type="date" style={{ width: 150 }} value={wDate} onChange={e => setWDate(e.target.value)} />
          <input className="input" type="number" step="0.1" style={{ width: 130 }} placeholder="体重（斤）"
            value={wInput} onChange={e => setWInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.nativeEvent.isComposing) saveWeight() }} />
          <button className="btn btn-primary" onClick={saveWeight} disabled={wBusy}><Plus size={14} strokeWidth={1.8} /> 记录</button>
          {latest && <span className="muted">最近：{latest.weight} 斤（{latest.date}）</span>}
        </div>
        {recs.length > 0 ? (
          <div className="life-weight-bars">
            {recs.map(r => (
              <div key={r.date} className="life-weight-bar" title={`${r.date} ${r.weight} 斤`}>
                <div style={{ height: `${wPct(r.weight)}%` }} />
              </div>
            ))}
          </div>
        ) : (
          <div className="muted" style={{ fontSize: 12 }}>还没有记录。目标：每周健身 3-4 次，持续减重。</div>
        )}
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <div className="card-title">
          <span className="row" style={{ gap: 8, alignItems: 'center' }}>
            <CupSoda size={15} strokeWidth={1.8} /> 饮品记录
            <span className={`badge ${dSt.cls}`}>{dSt.text}</span>
          </span>
          <span className="muted" style={{ fontSize: 12 }}>
            本周 {drinks.week_count || 0} / 上限 <input className="life-limit-input" type="number" min="0" max="99"
              value={dLimit} onChange={e => setDLimit(e.target.value)} onBlur={() => saveLimit('drink')}
              onKeyDown={limitEnter(() => saveLimit('drink'))} /> 杯（改动即保存）
          </span>
        </div>
        <div className="row" style={{ gap: 8, marginBottom: 8, flexWrap: 'wrap' }}>
          <input className="input" style={{ flex: '1 1 220px' }} placeholder="饮品名称，如：蜜雪冰城珍珠奶茶"
            value={dName} onChange={e => { setDName(e.target.value); setAiInfo(null) }} />
          <input className="input" type="number" style={{ width: 108 }} placeholder="容量 ml"
            value={dVol} onChange={e => setDVol(e.target.value)} />
          <input className="input" type="date" style={{ width: 150 }} value={dDate} onChange={e => setDDate(e.target.value)} />
        </div>
        <div className="row" style={{ gap: 8, marginBottom: 8, flexWrap: 'wrap' }}>
          <input className="input" type="number" step="0.1" style={{ width: 108 }} placeholder="糖 g（可选）"
            value={dSugar} onChange={e => setDSugar(e.target.value)} />
          <input className="input" type="number" step="0.1" style={{ width: 108 }} placeholder="脂肪 g（可选）"
            value={dFat} onChange={e => setDFat(e.target.value)} />
          <input className="input" type="number" style={{ width: 118 }} placeholder="热量 kcal（可选）"
            value={dCal} onChange={e => setDCal(e.target.value)} />
          <button className="btn" onClick={analyzeDrink} disabled={aiBusy} title="联网检索 + DeepSeek 分析糖分/脂肪/热量">
            <Sparkles size={14} strokeWidth={1.8} /> {aiBusy ? '分析中…' : 'AI 分析营养'}
          </button>
          <button className="btn btn-primary" onClick={saveDrink} disabled={dBusy}><Plus size={14} strokeWidth={1.8} /> 保存记录</button>
        </div>
        {aiInfo && (
          <div className="life-ai-note">
            <Sparkles size={13} strokeWidth={1.8} style={{ verticalAlign: '-2px' }} />{' '}
            {aiInfo.note || '已按常见规格估算'}
            <span className="muted" style={{ marginLeft: 8, fontSize: 12 }}>
              依据：{SOURCE_LABEL[aiInfo.source ?? ''] || 'AI 知识'} · {CONF_LABEL[aiInfo.confidence] || '把握中'} ·
              AI 估算仅供参考，可按包装营养表修正
            </span>
          </div>
        )}
        {(drinks.records || []).length > 0 ? (
          <div>
            {(drinks.records || []).slice(0, 12).map(x => (
              <div key={x.id} className="life-row">
                <span className="life-date">{x.date.slice(5).replace('-', '/')}</span>
                <span className="life-main" title={x.name}>{x.name}</span>
                <span className="muted" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>
                  {x.volume_ml ? `${x.volume_ml}ml · ` : ''}
                  {x.sugar_g || x.fat_g || x.calories
                    ? `糖 ${x.sugar_g}g · 脂 ${x.fat_g}g · ${Math.round(x.calories)}kcal`
                    : '未记录营养成分'}
                </span>
                {x.ai_analyzed && <span className="badge badge-info">AI</span>}
                <button className="life-del" title="删除" onClick={() => delDrink(x.id)}><Trash2 size={13} strokeWidth={1.8} /></button>
              </div>
            ))}
          </div>
        ) : (
          <div className="muted" style={{ fontSize: 12 }}>还没有记录。甜饮每周 2-3 杯在健康范围内；奶茶可直接点「AI 分析营养」。</div>
        )}
      </div>

      <div className="card life-relax" style={{ marginTop: 16 }}>
        <div className="card-title">
          <span className="row" style={{ gap: 8, alignItems: 'center' }}>
            <Moon size={15} strokeWidth={1.8} /> 夜间放松
            <span className={`badge ${rSt.cls}`}>{rSt.text}</span>
          </span>
          <span className="muted" style={{ fontSize: 12 }}>
            本周 {relax.week_count || 0} 次 · 本月 {relax.month_count || 0} 次 · 目标 ≤ <input className="life-limit-input"
              type="number" min="0" max="99" value={rLimit} onChange={e => setRLimit(e.target.value)}
              onBlur={() => saveLimit('relax')} onKeyDown={limitEnter(() => saveLimit('relax'))} /> 次/周（改动即保存）
          </span>
        </div>
        <div className="row" style={{ gap: 8, marginBottom: 10, flexWrap: 'wrap' }}>
          <input className="input" type="date" style={{ width: 150 }} value={rDate} onChange={e => setRDate(e.target.value)} />
          <button className="btn btn-primary" onClick={addRelax} disabled={rBusy}><Plus size={14} strokeWidth={1.8} /> 记录一次</button>
          <span className="muted" style={{ fontSize: 12 }}>正常的生理需求，适度无碍；若感觉影响睡眠或状态，再温和调整即可。</span>
        </div>
        {(relax.records || []).length > 0 ? (
          <div>
            {(relax.records || []).slice(0, 10).map(x => (
              <div key={x.id} className="life-row">
                <span className="life-date">{x.date.slice(5).replace('-', '/')}</span>
                <span className="life-main">{x.note || '—'}</span>
                <span className="muted" style={{ fontSize: 12 }}>{x.created_at ? x.created_at.slice(11, 16) : ''}</span>
                <button className="life-del" title="删除" onClick={() => delRelax(x.id)}><Trash2 size={13} strokeWidth={1.8} /></button>
              </div>
            ))}
          </div>
        ) : (
          <div className="muted" style={{ fontSize: 12 }}>还没有记录。点「记录一次」即可，无需填写任何内容。</div>
        )}
      </div>
    </div>
  )
}
