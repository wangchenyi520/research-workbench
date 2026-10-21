import React, { useEffect, useRef, useState } from 'react'
import api, { todayStr } from '../api'
import { useToast } from '../components/Toast'
import { hexToHsl, hslToHex } from '../utils/color'
import { Settings as SettingsIcon, Check, Eraser, FileText, FlaskConical, Monitor, Moon, Package, Pencil, Save, Sun, Timer, Trash2, Upload } from 'lucide-react'

function Toggle({ on, onChange }) {
  return (
    <button type="button" className="toggle" data-on={String(on)} onClick={() => onChange(!on)}>
      <span className="toggle-track" />
      <span>{on ? '开' : '关'}</span>
    </button>
  )
}

// 桌面胶囊（四个迷你小条）+ 页面内「进行中任务」小条：开关 + 独立背景色/透明度
// （设置项 cap_{key}_bg / cap_{key}_opacity；「进行中任务」是页面内组件，开关存 localStorage）
const CAPS = [
  { key: 'checklist', label: '今日清单', defaultBg: '', defaultOp: null },
  { key: 'attendance', label: '考勤', defaultBg: '#ffffff', defaultOp: 100 },
  { key: 'reminder', label: '提醒', defaultBg: '#ffffff', defaultOp: 100 },
  { key: 'pomodoro', label: '番茄钟', defaultBg: '#1f1f33', defaultOp: 97 },
  { key: 'active', label: '进行中任务', defaultBg: '', defaultOp: null },
]
const CAP_PRESETS = [
  ['#ffffff', '白', false],
  ['#fbf9f4', '暖白', false],
  ['#eef2f7', '淡蓝', false],
  ['#1f1f33', '深蓝黑', true],
  ['#26241f', '墨黑', true],
]

// 自定义主题色：三根滑杆（色相/饱和度/明度）+ 色号输入，拖动实时生效
function AccentPicker({ hex, onChange }) {
  const { h, s, l } = hexToHsl(hex)
  const [text, setText] = useState(hex)
  useEffect(() => { setText(hex) }, [hex])
  const apply = (nh, ns, nl) => onChange(hslToHex(nh, ns, nl))
  const commit = () => {
    const m = /^#?([0-9a-fA-F]{6})$/.exec(text.trim())
    if (m) onChange('#' + m[1].toLowerCase())
    else setText(hex)
  }
  return (
    <div className="accent-picker">
      <div className="accent-picker-head">
        <span className="accent-preview" style={{ background: hex }} />
        <span className="muted" style={{ fontSize: 12 }}>拖动滑杆或输入色号（六位十六进制），实时生效；可在上方切换明暗查看效果</span>
      </div>
      <div className="accent-slider-row">
        <span className="accent-slider-label">色相</span>
        <input type="range" className="accent-slider accent-slider-hue" min="0" max="360" value={h}
          onChange={e => apply(Number(e.target.value), s, l)} />
        <span className="accent-slider-val">{h}°</span>
      </div>
      <div className="accent-slider-row">
        <span className="accent-slider-label">饱和度</span>
        <input type="range" className="accent-slider accent-slider-sat" min="0" max="100" value={s}
          style={{ background: `linear-gradient(90deg, hsl(${h} 0% ${l}%), hsl(${h} 100% ${l}%))` }}
          onChange={e => apply(h, Number(e.target.value), l)} />
        <span className="accent-slider-val">{s}%</span>
      </div>
      <div className="accent-slider-row">
        <span className="accent-slider-label">明度</span>
        <input type="range" className="accent-slider accent-slider-light" min="0" max="100" value={l}
          style={{ background: `linear-gradient(90deg, #000, hsl(${h} ${s}% 50%), #fff)` }}
          onChange={e => apply(h, s, Number(e.target.value))} />
        <span className="accent-slider-val">{l}%</span>
      </div>
      <div className="row" style={{ gap: 8, alignItems: 'center', marginTop: 6 }}>
        <input className="input accent-hex" style={{ width: 110 }} value={text} placeholder="#6a56e8"
          onChange={e => setText(e.target.value)} onBlur={commit}
          onKeyDown={e => { if (e.key === 'Enter' && !e.nativeEvent.isComposing) commit() }} />
        <span className="muted" style={{ fontSize: 12 }}>当前主题色：{hex}</span>
      </div>
    </div>
  )
}

export default function Settings({ setTheme, theme, accent, setAccent, customAccent, setCustomAccent, fontSize, setFontSize, fontFamily, setFontFamily }) {
  const [s, setS] = useState({})
  const [autostart, setAutostart] = useState(false)
  const [saved, setSaved] = useState(false)
  const [editMode, setEditMode] = useState({})
  const toast = useToast()
  // 文本类输入防抖：连续输入只发一次 PUT，避免每敲一个字符都写库
  const saveTimers = useRef({})
  const [profile, setProfileState] = useState({ direction: '', methods: '', stage: '', goal: '', writing_style: '' })

  const setProfile = (key, value) => {
    const next = { ...profile, [key]: value }
    setProfileState(next)
    clearTimeout(saveTimers.current['research_profile'])
    saveTimers.current['research_profile'] = setTimeout(() => {
      api.put('/settings/research_profile', { value: JSON.stringify(next) }).catch(() => toast('画像保存失败', 'error'))
    }, 400)
  }

  // 桌面胶囊：开关状态（清单/考勤/提醒；番茄由悬浮钟控制；进行中任务存 localStorage），8 秒轮询与外部操作同步
  const [capSel, setCapSel] = useState('checklist')
  const [capOn, setCapOn] = useState({ checklist: false, attendance: false, reminder: false, active: localStorage.getItem('wb_active_pill') !== '0' })
  useEffect(() => {
    const loadCaps = () => {
      api.get('/checklist-widget/state').then(r => setCapOn(v => ({ ...v, checklist: !!r.data.active }))).catch(() => {})
      api.get('/attendance-pill/state').then(r => setCapOn(v => ({ ...v, attendance: !!r.data.active }))).catch(() => {})
      api.get('/reminder-pill/state').then(r => setCapOn(v => ({ ...v, reminder: !!r.data.active }))).catch(() => {})
      setCapOn(v => ({ ...v, active: localStorage.getItem('wb_active_pill') !== '0' }))
    }
    loadCaps()
    const iv = setInterval(loadCaps, 8000)
    return () => clearInterval(iv)
  }, [])

  const toggleCap = async (key, v) => {
    try {
      if (key === 'active') {
        // 页面内组件：localStorage 持久化 + 自定义事件即时通知（无后端窗口）
        localStorage.setItem('wb_active_pill', v ? '1' : '0')
        window.dispatchEvent(new Event('wb-active-pill'))
        setCapOn(s => ({ ...s, active: v }))
        toast(v ? '已显示「进行中任务」胶囊（页面右下角）' : '已关闭「进行中任务」胶囊')
        return
      }
      if (key === 'checklist') {
        if (v) {
          await api.post('/checklist-widget/start')
          const st = await api.get('/checklist-widget/state')
          if (!st.data.minimized) await api.post('/checklist-widget/control', { action: 'minimize' })
        } else {
          await api.post('/checklist-widget/control', { action: 'hide' })
        }
      } else if (key === 'attendance') {
        await api.post('/attendance-pill/control', { action: v ? 'show' : 'hide' })
      } else if (key === 'reminder') {
        await api.post('/reminder-pill/control', { action: v ? 'show' : 'hide' })
      }
      setCapOn(s => ({ ...s, [key]: v }))
      toast(v ? '胶囊已打开（可拖动到任意位置）' : '胶囊已关闭')
    } catch (e) {
      toast(e.response?.data?.detail || '操作失败', 'error')
    }
  }

  const ACCENTS = [
    ['purple', '紫'], ['blue', '蓝'], ['green', '绿'], ['orange', '橙'], ['pink', '粉'], ['red', '红'],
  ]

  const SENSITIVE = ['deepseek_api_key', 'zotero_api_key']
  const isMasked = v => typeof v === 'string' && v.includes('****')

  useEffect(() => {
    api.get('/settings').then(r => {
      setS(r.data)
      try {
        const p = JSON.parse(r.data.research_profile || '{}')
        setProfileState({ direction: p.direction || '', methods: p.methods || '', stage: p.stage || '', goal: p.goal || '', writing_style: p.writing_style || '' })
      } catch (e) {}
    })
    api.get('/settings/autostart').then(r => setAutostart(r.data.enabled)).catch(() => {})
  }, [])

  const set = (key, value) => {
    // C3：掩码串/空值防护——掩码不可直接提交（会静默丢改动），清空敏感 Key 需确认
    if (SENSITIVE.includes(key) && typeof value === 'string' && value.includes('****')) return
    if (SENSITIVE.includes(key) && value === '' && isMasked(s[key]) && !confirm('确定要清空已保存的 Key 吗？')) return
    setS(prev => ({ ...prev, [key]: value }))
    if (key === 'theme') {
      setTheme(value)
      document.documentElement.setAttribute('data-theme', value)
      localStorage.setItem('wb_theme', value)
    }
    clearTimeout(saveTimers.current[key])
    saveTimers.current[key] = setTimeout(async () => {
      try {
        await api.put(`/settings/${key}`, { value })
        setSaved(true)
        setTimeout(() => setSaved(false), 1500)
      } catch (e) { toast('保存失败', 'error') }
    }, 400)
  }

  // C3：掩码态只读，点「修改」进入可编辑态（清空显示、输入新 Key 即保存）
  const startEdit = key => {
    setEditMode(m => ({ ...m, [key]: true }))
    setS(prev => ({ ...prev, [key]: '' }))
  }

  const toggleAutostart = async () => {
    try {
      const r = await api.post('/settings/autostart', { enabled: !autostart })
      setAutostart(r.data.enabled)
      toast(r.data.enabled ? '已开启开机自启' : '已关闭开机自启')
    } catch (e) { toast('设置开机自启失败', 'error') }
  }

  const backup = async () => {
    try {
      const r = await api.get('/backup/export', { responseType: 'blob' })
      const url = URL.createObjectURL(r.data)
      const a = document.createElement('a')
      a.href = url
      a.download = `workbench_backup_${todayStr()}.db`
      a.click()
      URL.revokeObjectURL(url)
      toast('备份文件已下载')
    } catch (e) { toast('备份失败', 'error') }
  }

  // ② CSV 导出：后端生成 UTF-8 BOM CSV，前端 Blob 下载（Excel 直接打开不乱码）
  const downloadCsv = async (path, filename) => {
    try {
      const r = await api.get(path, { responseType: 'blob' })
      const url = URL.createObjectURL(r.data)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.click()
      URL.revokeObjectURL(url)
      toast(`已导出 ${filename}`)
    } catch (e) { toast('导出失败', 'error') }
  }

  const restoreRef = useRef(null)
  const onRestore = async e => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    if (!confirm('导入存档为合并模式：已存在的记录会保留，仅补入缺失记录。确定导入？')) return
    try {
      const fd = new FormData()
      fd.append('file', file)
      const r = await api.post('/backup/restore', fd)
      toast(`导入完成：新增 ${r.data.restored} 条，跳过 ${r.data.skipped} 条${r.data.errors ? `，失败 ${r.data.errors} 条` : ''}`)
    } catch (err) {
      toast(err.response?.data?.detail || '导入失败', 'error')
    }
  }

  return (
    <div>
      <div className="page-header">
        <h1><span className="page-icon"><SettingsIcon size={22} strokeWidth={1.75} /></span>设置</h1>
        {saved && <span className="badge badge-success">已保存</span>}
      </div>

      <div className="settings-grid">
        <div className="card">
          <div className="card-title">AI 配置</div>
          <label className="label">DeepSeek API Key</label>
          <div className="row" style={{ gap: 6 }}>
            <input
              className="input"
              type="password"
              placeholder={editMode.deepseek_api_key ? '输入新的 API Key 后自动保存' : 'sk-...'}
              readOnly={isMasked(s.deepseek_api_key) && !editMode.deepseek_api_key}
              value={s.deepseek_api_key || ''}
              onChange={e => set('deepseek_api_key', e.target.value)}
            />
            {isMasked(s.deepseek_api_key) && !editMode.deepseek_api_key && (
              <button className="btn btn-sm" onClick={() => startEdit('deepseek_api_key')}><Pencil size={14} strokeWidth={1.8} /> 修改</button>
            )}
          </div>
          <div className="muted" style={{ marginTop: 6 }}>
            {isMasked(s.deepseek_api_key) && !editMode.deepseek_api_key ? (
              '已保存（掩码显示），点击「修改」可更换 Key。'
            ) : (
              <>前往 <a href="https://platform.deepseek.com" target="_blank" rel="noreferrer">platform.deepseek.com</a> 注册获取，用于 AI 总结/写作/任务建议。</>
            )}
          </div>

          <label className="label" style={{ marginTop: 16 }}>Zotero API Key</label>
          <div className="row" style={{ gap: 6 }}>
            <input
              className="input"
              type="password"
              placeholder={editMode.zotero_api_key ? '输入新的 API Key 后自动保存' : 'Zotero API Key'}
              readOnly={isMasked(s.zotero_api_key) && !editMode.zotero_api_key}
              value={s.zotero_api_key || ''}
              onChange={e => set('zotero_api_key', e.target.value)}
            />
            {isMasked(s.zotero_api_key) && !editMode.zotero_api_key && (
              <button className="btn btn-sm" onClick={() => startEdit('zotero_api_key')}><Pencil size={14} strokeWidth={1.8} /> 修改</button>
            )}
          </div>
          <label className="label">Zotero User ID</label>
          <input className="input" placeholder="例如 12345678" value={s.zotero_user_id || ''} onChange={e => set('zotero_user_id', e.target.value)} />
          <div className="muted" style={{ marginTop: 6 }}>
            Zotero → 设置 → 高级 → API 中生成 Key，User ID 也在那里查看。
          </div>
        </div>

        <div className="card">
          <div className="card-title">科研画像（AI 会贴合这些背景提供建议）</div>
            <label className="label">研究方向</label>
            <input className="input" placeholder="如 红外小目标检测" value={profile.direction} onChange={e => setProfile('direction', e.target.value)} />
            <label className="label">常用方法 / 工具</label>
            <input className="input" placeholder="如 DNANet、注意力机制、PyTorch" value={profile.methods} onChange={e => setProfile('methods', e.target.value)} />
            <label className="label">当前阶段</label>
            <input className="input" placeholder="如 研一：复现 SOTA、补基础" value={profile.stage} onChange={e => setProfile('stage', e.target.value)} />
            <label className="label">毕业 / 近期目标</label>
            <input className="input" placeholder="如 2029 前发表论文并毕业" value={profile.goal} onChange={e => setProfile('goal', e.target.value)} />
            <label className="label">写作偏好</label>
            <input className="input" placeholder="如 中文学术风格、结构清晰" value={profile.writing_style} onChange={e => setProfile('writing_style', e.target.value)} />
            <div className="muted" style={{ marginTop: 8 }}>保存后自动注入规划助手、每日整理、文献问答、知识库问答等 AI 功能。</div>
          </div>

          <div className="card">
            <div className="card-title">系统</div>
            <div className="setting-row">
              <span>任务截止提醒</span>
              <Toggle on={s.reminder_enabled !== 'false'} onChange={v => set('reminder_enabled', String(v))} />
            </div>
            <div className="muted">DDL 提前 3 天、1 天、当天各提醒一次（Windows 通知）</div>
            <div className="setting-row">
              <span>自动备份</span>
              <Toggle on={s.auto_backup_enabled !== 'false'} onChange={v => set('auto_backup_enabled', String(v))} />
            </div>
            <div className="muted">每天自动备份数据库，保留最近 14 份</div>
            <div className="setting-row">
              <span>开机自启</span>
              <Toggle on={autostart} onChange={toggleAutostart} />
            </div>
            <div className="muted">开机自动启动桌面版并常驻后台</div>
          </div>

          <div className="card">
            <div className="card-title">周复盘提醒</div>
            <div className="row">
              <select className="select" style={{ flex: 1 }} value={s.review_reminder_day || '6'} onChange={e => set('review_reminder_day', e.target.value)}>
                {[['0', '周一'], ['1', '周二'], ['2', '周三'], ['3', '周四'], ['4', '周五'], ['5', '周六'], ['6', '周日']].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
              <input type="time" className="input" style={{ flex: 1 }} value={s.review_reminder_time || '20:00'} onChange={e => set('review_reminder_time', e.target.value)} />
            </div>
          </div>

          <div className="card">
            <div className="card-title">考勤</div>
            <div className="row">
              <span className="muted" style={{ flex: 1 }}>单次在岗超过该时长弹桌面提醒（小时，0 = 关闭）：</span>
              <input type="number" min="0" max="48" step="0.5" className="input" style={{ width: 90 }}
                value={s.attendance_remind_hours ?? '12'}
                onChange={e => set('attendance_remind_hours', e.target.value)} />
            </div>
            <div className="muted">用于提醒你忘记点「离开」；考勤页同时会显示异常提示，可手动修正任意一天的到岗/离开时间。</div>
          </div>

          <div className="card">
            <div className="card-title">今日清单 & 晚间视角</div>
            <div className="setting-row">
              <span>每日 AI 自动整理今日清单</span>
              <Toggle on={s.daily_ai_enabled !== 'false'} onChange={v => set('daily_ai_enabled', String(v))} />
            </div>
            <div className="muted">每天进入「今日」页时自动用 AI 生成今日任务（结合 Self_analysis 作战计划的阶段/周目标/固定节奏）</div>
            <div className="setting-row">
              <span>AI 任务自动加入今日清单</span>
              <Toggle on={s.daily_ai_auto_land !== 'false'} onChange={v => set('daily_ai_auto_land', String(v))} />
            </div>
            <div className="muted">开启后 AI 生成的今日任务直接落进清单（带时间段，可删改）；关闭则只给建议、手动采纳</div>
            <div className="setting-row">
              <span>晚间视角（默认显示完成情况）</span>
              <Toggle on={s.evening_view_enabled === 'true'} onChange={v => set('evening_view_enabled', String(v))} />
            </div>
            <div className="row" style={{ marginTop: 8 }}>
              <span className="muted" style={{ flex: 1 }}>连续 N 天有产出 → 今日页提示「奖励自己」（默认 7）：</span>
              <input type="number" min="1" max="30" className="input" style={{ width: 90 }} value={s.reward_streak_threshold || 7} onChange={e => set('reward_streak_threshold', e.target.value)} />
            </div>
            <div className="row" style={{ marginTop: 8 }}>
              <span className="muted" style={{ flex: 1 }}>晚于该时间进入「今日」默认显示完成情况：</span>
              <input type="time" className="input" style={{ width: 130 }} value={s.evening_view_time || '22:00'} onChange={e => set('evening_view_time', e.target.value)} />
            </div>
            <label className="label">Self_analysis 规划文件夹路径</label>
            <input className="input" value={s.self_analysis_path || ''} onChange={e => set('self_analysis_path', e.target.value)} placeholder="如 C:\Users\you\Research\Self_analysis" />
            <div className="muted">递归读取 plan/ 与 复盘/ 里的 md 文档，结构化提取当前阶段 / 本周目标 / 检查点 / 固定节奏，供 AI 与「作战计划」页使用</div>
          </div>

          <div className="card">
            <div className="card-title">桌面清单（悬浮小窗）</div>
            <label className="label">背景颜色</label>
            <div className="row" style={{ gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              {[['#ffffff', '白', false], ['#fbf9f4', '暖白', false], ['#eef2f7', '淡蓝', false], ['#1f1f33', '深蓝黑', true], ['#26241f', '墨黑', true]].map(([hex, label, dark]) => {
                const cur = (s.checklist_widget_bg || '#ffffff').toLowerCase()
                return (
                  <button
                    key={hex}
                    className={`swatch ${cur === hex ? 'active' : ''}`}
                    style={{ background: hex, color: dark ? '#fff' : '#3b3b3b' }}
                    title={label}
                    onClick={() => set('checklist_widget_bg', hex)}
                  >
                    {cur === hex ? <Check size={12} /> : ''}
                  </button>
                )
              })}
              <input
                type="color"
                title="自定义背景色"
                style={{ width: 40, height: 30, padding: 2, border: '1px solid var(--border)', borderRadius: 8, background: 'var(--card)', cursor: 'pointer' }}
                value={s.checklist_widget_bg || '#ffffff'}
                onChange={e => set('checklist_widget_bg', e.target.value)}
              />
              <span className="muted" style={{ fontSize: 12 }}>{s.checklist_widget_bg || '#ffffff'}</span>
            </div>
            <label className="label">背景效果</label>
            <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
              {[['solid', '实色'], ['frost', '磨砂半透明'], ['transparent', '背景纯透明']].map(([k, l]) => (
                <button
                  key={k}
                  className={`btn btn-sm ${(s.checklist_widget_bg_mode || 'solid') === k ? 'btn-primary' : ''}`}
                  onClick={() => {
                    set('checklist_widget_bg_mode', k)
                    if (k === 'frost') set('checklist_widget_opacity', '45')
                    if (k === 'solid') set('checklist_widget_opacity', '100')
                  }}
                >
                  {l}
                </button>
              ))}
            </div>
            <label className="label">透明度：{Number(s.checklist_widget_opacity || 100)}%</label>
            <input
              type="range" min="30" max="100" step="5"
              value={Number(s.checklist_widget_opacity || 100)}
              style={{ width: '100%', opacity: s.checklist_widget_bg_mode === 'transparent' ? 0.4 : 1 }}
              disabled={s.checklist_widget_bg_mode === 'transparent'}
              onChange={e => set('checklist_widget_opacity', e.target.value)}
            />
            <div className="muted">实色=白卡；磨砂半透明=整个小窗半透明（桌面透出，文字略淡）；背景纯透明=去掉卡片底色、只留文字/勾选框/输入条（深色壁纸下自动加文字描边）。颜色与效果实时同步到桌面悬浮清单（需先在今日页点「桌面清单」打开，约 4 秒内生效）。</div>
          </div>

          <div className="card">
            <div className="card-title">桌面胶囊</div>
            <div className="muted">桌面上的四个迷你小条（逐像素抗锯齿渲染，边缘光滑）+ 页面右下角的「进行中任务」小条。每个可单独打开/关闭（桌面胶囊还可改颜色与透明度）；不想看时全部关掉即可，界面保持干净。</div>
            <div className="row" style={{ gap: 6, flexWrap: 'wrap', margin: '10px 0' }}>
              {CAPS.map(c => (
                <button key={c.key} className={`btn btn-sm ${capSel === c.key ? 'btn-primary' : ''}`} onClick={() => setCapSel(c.key)}>
                  {c.label}{c.key !== 'pomodoro' && !capOn[c.key] ? '（关）' : ''}
                </button>
              ))}
            </div>
            {(() => {
              const cap = CAPS.find(c => c.key === capSel)
              const bgVal = (s[`cap_${capSel}_bg`] ?? '') || cap.defaultBg
              const opRaw = s[`cap_${capSel}_opacity`]
              const opVal = Number(opRaw || (capSel === 'checklist' ? (s.checklist_widget_opacity || 100) : cap.defaultOp))
              if (capSel === 'active') {
                return (
                  <>
                    <div className="setting-row">
                      <span>在页面右下角显示「进行中任务」胶囊</span>
                      <Toggle on={!!capOn.active} onChange={v => toggleCap('active', v)} />
                    </div>
                    <div className="muted" style={{ marginTop: 8 }}>
                      这是页面内的小条（跟随界面主题，不占桌面）：有进行中任务时显示，可快捷完成 / 暂停 / 跳转到任务页；没有进行中任务时自动隐藏。不需要时关掉即可。
                    </div>
                  </>
                )
              }
              return (
                <>
                  {capSel === 'pomodoro' ? (
                    <div className="muted" style={{ marginBottom: 8 }}>番茄胶囊由悬浮钟控制：计时中点时钟左上角的「—」缩成胶囊，点胶囊展开；无计时时自动隐藏（颜色/透明度仍可在此设置）。</div>
                  ) : (
                    <div className="setting-row">
                      <span>在桌面显示「{cap.label}」胶囊</span>
                      <Toggle on={!!capOn[capSel]} onChange={v => toggleCap(capSel, v)} />
                    </div>
                  )}
                  <label className="label">背景颜色{capSel === 'checklist' ? '（未单独设置时跟随「桌面清单」小窗）' : ''}</label>
                  <div className="row" style={{ gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                    {CAP_PRESETS.map(([hex, label, dark]) => (
                      <button
                        key={hex}
                        className={`swatch ${bgVal.toLowerCase() === hex ? 'active' : ''}`}
                        style={{ background: hex, color: dark ? '#fff' : '#3b3b3b' }}
                        title={label}
                        onClick={() => set(`cap_${capSel}_bg`, hex)}
                      >
                        {bgVal.toLowerCase() === hex ? <Check size={12} /> : ''}
                      </button>
                    ))}
                    <input
                      type="color"
                      title="自定义背景色"
                      style={{ width: 40, height: 30, padding: 2, border: '1px solid var(--border)', borderRadius: 8, background: 'var(--card)', cursor: 'pointer' }}
                      value={bgVal || '#ffffff'}
                      onChange={e => set(`cap_${capSel}_bg`, e.target.value)}
                    />
                    <span className="muted" style={{ fontSize: 12 }}>{bgVal || '跟随小窗'}</span>
                    <button className="btn btn-sm" onClick={() => { set(`cap_${capSel}_bg`, ''); set(`cap_${capSel}_opacity`, '') }}>恢复默认</button>
                  </div>
                  <label className="label">透明度：{opVal}%</label>
                  <input
                    type="range" min="30" max="100" step="5"
                    value={opVal}
                    style={{ width: '100%' }}
                    onChange={e => set(`cap_${capSel}_opacity`, e.target.value)}
                  />
                  <div className="muted">颜色与透明度约 4 秒内同步到桌面胶囊；胶囊可拖动到任意位置（会被记住），点击胶囊本体执行对应操作（打开页面 / 暂停番茄 / 到位离开等）。</div>
                </>
              )
            })()}
          </div>

          <div className="card">
            <div className="card-title">阅读计划 & 每日晨报</div>
            <div className="row" style={{ marginBottom: 8 }}>
              <span className="muted" style={{ flex: 1 }}>每周阅读目标（篇，0 = 关闭）：</span>
              <input type="number" min="0" max="30" className="input" style={{ width: 90 }} value={s.reading_goal_per_week || 0} onChange={e => set('reading_goal_per_week', e.target.value)} />
            </div>
            <div className="muted" style={{ marginBottom: 10 }}>在「文献」页显示本周已读进度条；置「已读」的文献自动计入。</div>
            <div className="setting-row">
              <span>每日晨报（桌面通知）</span>
              <Toggle on={s.daily_brief_enabled === 'true'} onChange={v => set('daily_brief_enabled', String(v))} />
            </div>
            <div className="row">
              <span className="muted" style={{ flex: 1 }}>发送时间：</span>
              <input type="time" className="input" style={{ width: 130 }} value={s.daily_brief_time || '08:00'} onChange={e => set('daily_brief_time', e.target.value)} />
            </div>
            <div className="muted" style={{ marginTop: 8 }}>每天到点通知今日待办 / 顺延欠账 / 到期任务 / 本周目标</div>
          </div>

          <div className="card">
            <div className="card-title">每日论文推荐</div>
            <div className="setting-row">
              <span>自动生成每日论文推荐</span>
              <Toggle on={s.daily_paper_enabled !== 'false'} onChange={v => set('daily_paper_enabled', String(v))} />
            </div>
            <div className="setting-row">
              <span>自动存入 Zotero（题录 + PDF 附件）</span>
              <Toggle on={s.daily_paper_zotero !== 'false'} onChange={v => set('daily_paper_zotero', String(v))} />
            </div>
            <div className="muted" style={{ marginBottom: 10 }}>首次打开工作台自动精选一篇红外小目标检测论文（OpenAlex 真实引用数 + AI 中文导读），生成桌面通知，并自动下载 PDF 到工作台 daily_paper 文件夹。关闭后不再自动生成。</div>
            <div className="muted" style={{ marginBottom: 10 }}>生成后自动把论文创建到 Zotero 集合「红外小目标检测每日论文推荐」（需在下方已配置 Zotero API Key / User ID）；关闭后仍可手动点「存入文献库」或「上传 PDF」补推。</div>
            <div className="row">
              <span className="muted" style={{ flex: 1 }}>论文保存文件夹：</span>
              <span className="badge badge-info">daily_paper（项目根目录）</span>
            </div>
          </div>

          <div className="card">
            <div className="card-title">外观</div>
            <div className="row">
              <button className={`btn ${theme === 'light' ? 'btn-primary' : ''}`} onClick={() => setTheme('light')}><Sun size={14} strokeWidth={1.8} /> 浅色</button>
              <button className={`btn ${theme === 'dark' ? 'btn-primary' : ''}`} onClick={() => setTheme('dark')}><Moon size={14} strokeWidth={1.8} /> 暗色</button>
              <button className={`btn ${theme === 'auto' ? 'btn-primary' : ''}`} onClick={() => setTheme('auto')}><Monitor size={14} strokeWidth={1.8} /> 跟随系统</button>
            </div>
            <div className="muted" style={{ marginTop: 6 }}>{theme === 'auto' ? '跟随操作系统明暗，可在侧边栏底部随时手动切换' : '手动模式（可在侧边栏底部随时切换）'}</div>
            <label className="label">主题色系</label>
            <div className="row" style={{ gap: 8, alignItems: 'center' }}>
              {ACCENTS.map(([key, label]) => (
                <button
                  key={key}
                  className={`swatch ${accent === key ? 'active' : ''}`}
                  data-color={key}
                  title={label}
                  onClick={() => setAccent(key)}
                >
                  {accent === key ? <Check size={12} /> : ''}
                </button>
              ))}
              <button
                className={`swatch swatch-custom ${accent === 'custom' ? 'active' : ''}`}
                title="自定义颜色（拖动滑杆 / 输入色号）"
                onClick={() => setAccent('custom')}
              >
                {accent === 'custom' ? <Check size={12} /> : ''}
              </button>
            </div>
            {accent === 'custom' && <AccentPicker hex={customAccent} onChange={setCustomAccent} />}
            <label className="label">字体大小：{fontSize}px</label>
            <input type="range" min="12" max="18" step="1" value={fontSize} style={{ width: '100%' }} onChange={e => setFontSize(Number(e.target.value))} />
            <label className="label">字体风格</label>
            <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
              {[['system', '系统'], ['mono', '等宽'], ['serif', '衬线'], ['kaiti', '楷书'], ['xingshu', '行书'], ['xingkai', '行楷']].map(([key, label]) => (
                <button
                  key={key}
                  className={`btn ${fontFamily === key ? 'btn-primary' : ''}`}
                  onClick={() => setFontFamily(key)}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          <div className="card">
            <div className="card-title">快捷键</div>
            <div className="setting-row">
              <span><kbd>Ctrl</kbd> + <kbd>K</kbd> 全局搜索</span>
              <span className="muted" style={{ fontSize: 12 }}>搜索任务 / 笔记 / 文献 / 目标</span>
            </div>
            <div className="setting-row">
              <span><kbd>Ctrl</kbd> + <kbd>N</kbd> 新建笔记</span>
              <span className="muted" style={{ fontSize: 12 }}>跳转到笔记页</span>
            </div>
            <div className="setting-row">
              <span><kbd>Ctrl</kbd> + <kbd>P</kbd> 命令面板</span>
              <span className="muted" style={{ fontSize: 12 }}>搜索页面 / 打开笔记 / 快捷动作</span>
            </div>
            <div className="setting-row">
              <span><kbd>Ctrl</kbd> + <kbd>Shift</kbd> + <kbd>T</kbd> 全局快速添加</span>
              <span className="muted" style={{ fontSize: 12 }}>任意页快速加入今日清单或创建任务</span>
            </div>
            <div className="setting-row">
              <span><kbd>Esc</kbd> 关闭弹窗</span>
              <span className="muted" style={{ fontSize: 12 }}>命令面板 / 快速添加 / 各弹窗</span>
            </div>
            <div className="setting-row">
              <span><kbd>↑</kbd> <kbd>↓</kbd> + <kbd>Enter</kbd> 选择</span>
              <span className="muted" style={{ fontSize: 12 }}>命令面板 / 下拉列表内选择</span>
            </div>
            <div className="muted" style={{ marginTop: 6 }}>输入框聚焦时全局快捷键不生效（避免与打字冲突）。</div>
          </div>

          <div className="card">
            <div className="card-title">番茄钟默认时长</div>
            <div className="row">
              <input type="number" className="input" style={{ flex: 1 }} value={s.pomodoro_minutes || 25} onChange={e => set('pomodoro_minutes', e.target.value)} />
              <span className="muted">分钟工作</span>
              <input type="number" className="input" style={{ flex: 1 }} value={s.break_minutes || 5} onChange={e => set('break_minutes', e.target.value)} />
              <span className="muted">分钟休息</span>
            </div>
          </div>

          <div className="card">
            <div className="card-title">数据备份 & 导出</div>
            <div className="muted" style={{ marginBottom: 10 }}>备份导出 SQLite 数据库 / JSON 存档；CSV 可用 Excel 直接打开。</div>
            <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
              <button className="btn btn-primary" onClick={backup}><Package size={14} strokeWidth={1.8} /> 一键导出备份</button>
              <button className="btn" onClick={async () => {
                try {
                  const r = await api.get('/backup/archive', { responseType: 'blob' })
                  const url = URL.createObjectURL(r.data)
                  const a = document.createElement('a'); a.href = url
                  a.download = `workbench_archive_${todayStr()}.json`; a.click()
                  URL.revokeObjectURL(url); toast('全量存档已导出')
                } catch (e) { toast('存档失败', 'error') }
              }}><Save size={14} strokeWidth={1.8} /> 全量 JSON 存档</button>
              <button className="btn" onClick={async () => {
                try {
                  const r = await api.post('/backup/vacuum')
                  toast(`数据库已优化（${(r.data.size / 1024).toFixed(0)} KB）`)
                } catch (e) { toast('优化失败', 'error') }
              }}><Eraser size={14} strokeWidth={1.8} /> 数据库优化(VACUUM)</button>
              <input ref={restoreRef} type="file" accept=".json,application/json" style={{ display: 'none' }} onChange={onRestore} />
              <button className="btn" onClick={() => restoreRef.current?.click()}><Upload size={14} strokeWidth={1.8} /> 导入存档</button>
              <button className="btn btn-danger" onClick={async () => {
                if (!confirm('将清理未引用的图片、临时音频和过期备份，确定？')) return
                try {
                  const r = await api.post('/maintenance/cleanup')
                  const c = r.data.cleaned
                  toast(`已清理：图片 ${c.images}、音频 ${c.audio}、备份 ${c.backups}`)
                } catch (e) { toast('清理失败', 'error') }
              }}><Trash2 size={14} strokeWidth={1.8} /> 存储清理</button>
            </div>
            <div className="card-title" style={{ marginTop: 14 }}>数据导出（Excel .xlsx）</div>
            <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
              <button className="btn" onClick={() => downloadCsv('/export/tasks', `workbench_tasks_${todayStr()}.xlsx`)}><FileText size={14} strokeWidth={1.8} /> 任务完成记录 Excel</button>
              <button className="btn" onClick={() => downloadCsv('/export/timelogs', `workbench_timelogs_${todayStr()}.xlsx`)}><Timer size={14} strokeWidth={1.8} /> 计时 / 番茄 Excel</button>
              <button className="btn" onClick={() => downloadCsv('/export/experiments', `workbench_experiments_${todayStr()}.xlsx`)}><FlaskConical size={14} strokeWidth={1.8} /> 实验指标 Excel</button>
            </div>
          </div>
      </div>
    </div>
  )
}
