import React, { useState } from 'react'
import { Copy, Check } from 'lucide-react'

export default function CopyBtn({ text, className }) {
  const [ok, setOk] = useState(false)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text || '')
      setOk(true)
      setTimeout(() => setOk(false), 1500)
    } catch (e) { /* clipboard 不可用时静默 */ }
  }
  return (
    <button className={`btn btn-sm ${className || ''}`} onClick={copy} disabled={!text}>
      {ok ? <><Check size={14} strokeWidth={1.8} /> 已复制</> : <><Copy size={14} strokeWidth={1.8} /> 复制</>}
    </button>
  )
}