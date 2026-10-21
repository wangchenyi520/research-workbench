// 自然语言快速解析：如「明天下午3点写综述 p3 2个番茄」→ 结构字段
// 供今日页快速添加 / ItemForm 一句话解析 / 全局快速添加（Ctrl+Shift+T）共用
export function parseQuickInput(text) {
  let t = (text || '').trim()
  const res = { content: t, due_date: null, scheduled_date: null, quadrant: 'important_urgent', weight: 12, pomodoros: 0, time_range: '' }
  if (!t) return res
  const iso = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  const today = new Date()
  const next = n => new Date(today.getTime() + n * 86400000)
  const cnHour = (prefix, h) => {
    let v = Number(h)
    if ((prefix === '下午' || prefix === '晚上') && v < 12) v += 12
    return v
  }
  const qmap = [
    [/重要紧急|紧急重要/, 'important_urgent'],
    [/重要不紧急/, 'important_not'],
    [/紧急不重要/, 'not_urgent_important'],
    [/不重要不紧急|不重要/, 'not_important_not'],
  ]
  for (const [re, q] of qmap) {
    if (re.test(t)) { res.quadrant = q; t = t.replace(re, ''); break }
  }
  // 显式截止：截止今天/明天/后天/X月X日 → due_date
  let m = t.match(/截止\s*(今天|明天|后天|大后天|(\d{1,2})月(\d{1,2})日)/)
  if (m) {
    if (m[1] === '今天') res.due_date = iso(today)
    else if (m[1] === '明天') res.due_date = iso(next(1))
    else if (m[1] === '后天') res.due_date = iso(next(2))
    else if (m[1] === '大后天') res.due_date = iso(next(3))
    else {
      const d = new Date(today.getFullYear(), Number(m[2]) - 1, Number(m[3]))
      if (d < today) d.setFullYear(d.getFullYear() + 1)
      res.due_date = iso(d)
    }
    t = t.replace(m[0], '')
  }
  // 裸日期词：今天/明天/后天（作为计划日 scheduled_date，不设截止）
  if (!res.due_date) {
    m = t.match(/今天|明天|后天|大后天/)
    if (m) {
      res.scheduled_date = iso(next({ 今天: 0, 明天: 1, 后天: 2, 大后天: 3 }[m[0]]))
      t = t.replace(m[0], '')
    }
  }
  // 时间段：中文「X点到Y点」/「下午X点」/ HH:MM-HH:MM
  m = t.match(/(下午|晚上|上午)?(\d{1,2})\s*(?:点|时)\s*(?:到|至|~|-)\s*(下午|晚上|上午)?(\d{1,2})\s*(?:点|时)/)
  let startH = null, endH = null
  if (m) {
    startH = cnHour(m[1], m[2])
    endH = cnHour(m[3], m[4])
    t = t.replace(m[0], '')
  } else {
    m = t.match(/(下午|晚上|上午)?(\d{1,2})\s*(?:点|时)/)
    if (m) {
      startH = cnHour(m[1], m[2])
      endH = Math.min(startH + 1, 23)
      t = t.replace(m[0], '')
    }
  }
  m = t.match(/(\d{1,2}:\d{2})\s*[-~至]\s*(\d{1,2}:\d{2})/)
  if (m) {
    res.time_range = `${m[1]}-${m[2]}`
    t = t.replace(m[0], '')
  } else if (startH != null) {
    res.time_range = `${String(startH).padStart(2, '0')}:00-${String(endH).padStart(2, '0')}:00`
  }
  const pomo = t.match(/(\d+)\s*个番茄|🍅\s*×?\s*(\d+)/)
  if (pomo) { res.pomodoros = Number(pomo[1] || pomo[2]); t = t.replace(pomo[0], '') }
  const p = t.match(/p([1-5])|优先级\s*([1-5])/)
  if (p) {
    const lv = Number(p[1] || p[2])
    res.weight = [8, 15, 25, 35, 50][lv - 1]
    t = t.replace(p[0], '')
  }
  res.content = t.replace(/\s+/g, ' ').replace(/[，,、\s]+$/, '').trim()
  return res
}

// 清单权重 → 任务优先级 1-5（parseQuickInput 的 weight 映射反推）
export function weightToPriority(weight) {
  return { 8: 1, 15: 2, 25: 3, 35: 4, 50: 5 }[weight] || 2
}