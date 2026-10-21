import React, { useEffect, useState } from 'react'
import api from '../api'
import { CalendarDays, ChevronLeft, ChevronRight } from 'lucide-react'

const WEEKDAY = ['一', '二', '三', '四', '五', '六', '日']
const fmt = sec => {
  if (!sec) return '0'
  if (sec < 60) return '<1m'
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  return h > 0 ? `${h}h` : `${m}m`
}

export default function Calendar() {
  const now = new Date()
  const [month, setMonth] = useState(`${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`)
  const [view, setView] = useState('month')
  const [weekData, setWeekData] = useState(null)
  const [data, setData] = useState(null)
  const [detail, setDetail] = useState(null)
  // C22：今天高亮（本地日期，与 api.js todayStr 同口径）
  const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`

  const mondayOf = d => {
    const x = new Date(d)
    x.setDate(x.getDate() - (x.getDay() === 0 ? 6 : x.getDay() - 1))
    return `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, '0')}-${String(x.getDate()).padStart(2, '0')}`
  }
  const [weekStart, setWeekStart] = useState(mondayOf(now))

  useEffect(() => {
    if (view === 'month') {
      api.get('/stats/calendar', { params: { month } }).then(r => setData(r.data)).catch(() => {})
    } else {
      api.get('/stats/calendar-week', { params: { start: weekStart } }).then(r => setWeekData(r.data)).catch(() => {})
    }
  }, [view, month, weekStart])

  const changeMonth = delta => {
    const [y, m] = month.split('-').map(Number)
    const d = new Date(y, m - 1 + delta, 1)
    setMonth(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`)
  }
  const shiftWeek = delta => {
    const d = new Date(weekStart + 'T00:00:00')
    d.setDate(d.getDate() + delta * 7)
    setWeekStart(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`)
  }
  const goToday = () => {
    const n = new Date()
    setMonth(`${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, '0')}`)
    setWeekStart(mondayOf(n))
  }

  if (view === 'month' && !data) return <div className="skeleton" style={{ height: 420 }} />
  if (view === 'week' && !weekData) return <div className="skeleton" style={{ height: 420 }} />
  const blanks = data?.first_weekday ?? 0

  return (
    <div>
      <div className="page-header">
        <h1><span className="page-icon"><CalendarDays size={22} strokeWidth={1.75} /></span>日历</h1>
        <div className="row">
          <button className="btn btn-sm btn-primary" onClick={goToday}>今天</button>
          <button className={`btn btn-sm ${view === 'month' ? 'btn-primary' : ''}`} onClick={() => setView('month')}>月</button>
          <button className={`btn btn-sm ${view === 'week' ? 'btn-primary' : ''}`} onClick={() => setView('week')}>周</button>
          {view === 'month' ? (
            <>
              <button className="btn btn-sm" onClick={() => changeMonth(-1)}><ChevronLeft size={14} strokeWidth={1.8} /> 上月</button>
              <input type="month" className="input" style={{ width: 170 }} value={month} onChange={e => setMonth(e.target.value)} />
              <button className="btn btn-sm" onClick={() => changeMonth(1)}>下月 <ChevronRight size={14} strokeWidth={1.8} /></button>
            </>
          ) : (
            <>
              <button className="btn btn-sm" onClick={() => shiftWeek(-1)}><ChevronLeft size={14} strokeWidth={1.8} /> 上周</button>
              <span className="muted" style={{ fontSize: 13 }}>{weekStart} 起</span>
              <button className="btn btn-sm" onClick={() => shiftWeek(1)}>下周 <ChevronRight size={14} strokeWidth={1.8} /></button>
            </>
          )}
        </div>
      </div>

      {view === 'month' && (
        <div className="calendar-grid">
          {WEEKDAY.map(w => <div key={w} className="cal-weekday">{w}</div>)}
          {Array.from({ length: blanks }).map((_, i) => <div key={`b${i}`} className="cal-blank" />)}
          {data.days.map(d => (
            <div
              key={d.date}
              className={`cal-cell ${d.date === today ? 'today' : ''} ${d.seconds > 0 || d.checkins > 0 || d.pomodoros > 0 ? 'has-data' : ''}`}
              onClick={() => setDetail(d)}
            >
              <div className="cal-daynum">{d.day}</div>
              <div className="cal-info">
                {d.checkins > 0 && <span className="cal-dot green" title={`${d.checkins} 次打卡`} />}
                {d.pomodoros > 0 && <span className="cal-dot blue" title={`${d.pomodoros} 番茄`} />}
                {d.seconds > 0 && <span className="cal-time">{fmt(d.seconds)}</span>}
              </div>
              {d.due_tasks.length > 0 && <div className="cal-due">{d.due_tasks.length} 任务到期</div>}
              {d.reminders?.length > 0 && <div className="cal-due cal-rm">⏰ {d.reminders.length} 件提醒</div>}
            </div>
          ))}
        </div>
      )}

      {view === 'week' && (
        <div className="week-grid">
          {weekData.days.map(d => (
            <div key={d.date} className={`cal-cell week-cell ${d.date === today ? 'today' : ''} ${d.seconds > 0 || d.checkins > 0 || d.pomodoros > 0 || d.daily_items.length > 0 ? 'has-data' : ''}`} onClick={() => setDetail(d)}>
              <div className="cal-daynum">
                <span className="muted" style={{ fontSize: 11 }}>周{WEEKDAY[d.weekday]}</span> {d.date.slice(8)}
              </div>
              <div className="cal-info">
                {d.checkins > 0 && <span className="cal-dot green" title={`${d.checkins} 次打卡`} />}
                {d.pomodoros > 0 && <span className="cal-dot blue" title={`${d.pomodoros} 番茄`} />}
                {d.seconds > 0 && <span className="cal-time">{fmt(d.seconds)}</span>}
              </div>
              {d.due_tasks.length > 0 && <div className="cal-due">{d.due_tasks.length} 任务到期</div>}
              {d.reminders?.length > 0 && <div className="cal-due cal-rm">⏰ {d.reminders.length} 件提醒</div>}
              <div style={{ marginTop: 4 }}>
                {d.daily_items.map((it, i) => (
                  <div key={i} className={`week-item ${it.status === 'done' ? 'done' : ''}`}>
                    {it.time_range && <span className="muted" style={{ fontSize: 10 }}>{it.time_range} </span>}
                    {it.content}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {detail && (
        <div className="modal-mask" onClick={() => setDetail(null)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h3>{detail.date} 详情</h3>
            <div className="row" style={{ gap: 16, margin: '12px 0' }}>
              <div><div className="muted">投入</div><strong style={{ fontSize: 20 }}>{fmt(detail.seconds)}</strong></div>
              <div><div className="muted">番茄</div><strong style={{ fontSize: 20 }}>{detail.pomodoros}</strong></div>
              <div><div className="muted">打卡</div><strong style={{ fontSize: 20 }}>{detail.checkins}</strong></div>
            </div>
            <div className="card-title" style={{ marginTop: 8 }}>到期任务</div>
            {detail.due_tasks.length === 0 && <div className="muted">当天无到期任务</div>}
            {detail.due_tasks.map((t, i) => <div key={i} className="row" style={{ padding: '4px 0' }}><span>📌 {t}</span></div>)}
            {(detail.reminders?.length > 0) && (
              <>
                <div className="card-title" style={{ marginTop: 8 }}>琐事提醒</div>
                {detail.reminders.map((t, i) => <div key={i} className="row" style={{ padding: '4px 0' }}><span>⏰ {t}</span></div>)}
              </>
            )}
            <div className="modal-actions"><button className="btn" onClick={() => setDetail(null)}>关闭</button></div>
          </div>
        </div>
      )}
    </div>
  )
}
