import React, { useEffect, useRef, useState } from 'react'
import api from '../api'
import { useToast } from '../components/Toast'
import { parseQuickInput, weightToPriority } from '../utils/quickParse'
import { Sun, Check } from 'lucide-react'

// 全局快速添加：Ctrl+Shift+T 唤起，任意页直接加今日清单项或任务
export default function QuickAdd({ open, onClose }) {
  const [mode, setMode] = useState('daily') // daily=今日清单 / task=任务
  const [text, setText] = useState('')
  const inputRef = useRef(null)
  const toast = useToast()

  useEffect(() => {
    if (open) {
      setText('')
      setTimeout(() => inputRef.current?.focus(), 30)
    }
  }, [open])

  useEffect(() => {
    if (!open) return
    const onKey = e => {
      if (e.key === 'Escape') { onClose(); return }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  const submit = async () => {
    if (!text.trim()) return toast('请输入内容', 'error')
    const p = parseQuickInput(text)
    try {
      if (mode === 'daily') {
        await api.post('/daily', {
          content: p.content, kind: 'manual', quadrant: p.quadrant,
          weight: p.weight, pomodoros: p.pomodoros, time_range: p.time_range,
          due_date: p.due_date, scheduled_date: p.scheduled_date,
        })
        toast('已添加到今日清单')
      } else {
        await api.post('/tasks', {
          title: p.content, task_type: 'once', due_date: p.due_date || null,
          priority: weightToPriority(p.weight),
        })
        toast('已创建任务')
      }
      setText('')
      inputRef.current?.focus()
    } catch (e) {
      toast(e.response?.data?.detail || '添加失败', 'error')
    }
  }

  if (!open) return null
  return (
    <div className="modal-mask" style={{ alignItems: 'flex-start', paddingTop: '12vh' }} onClick={onClose}>
      <div className="modal" style={{ maxWidth: 560, padding: 14 }} onClick={e => e.stopPropagation()}>
        <div className="row" style={{ marginBottom: 8, gap: 6 }}>
          <button
            className={`btn btn-sm ${mode === 'daily' ? 'btn-primary' : ''}`}
            onClick={() => setMode('daily')}
          ><Sun size={14} strokeWidth={1.8} /> 今日清单</button>
          <button
            className={`btn btn-sm ${mode === 'task' ? 'btn-primary' : ''}`}
            onClick={() => setMode('task')}
          ><Check size={14} strokeWidth={1.8} /> 任务</button>
        </div>
        <input
          ref={inputRef}
          className="input"
          style={{ width: '100%', fontSize: 15 }}
          placeholder="⚡ 快速添加：如「明天下午3点写综述 p3 2个番茄」，回车即添加"
          value={text}
          onChange={e => setText(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter' && !e.nativeEvent.isComposing) submit()
          }}
        />
        <div className="muted" style={{ fontSize: 11, marginTop: 6, textAlign: 'center' }}>
          支持：今天/明天/X月X日 · 下午3点/15:00-16:00 · p1-5 优先级 · N个番茄 · 重要紧急/重要不紧急 等四象限词
          <br />Enter 添加（可连续添加）· Esc 关闭 · Ctrl+Shift+T 再次唤起
        </div>
      </div>
    </div>
  )
}