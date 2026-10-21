import React from 'react'
import { useToast } from './Toast'

const extractText = node => {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(extractText).join('')
  if (node && node.props) return extractText(node.props.children)
  return ''
}

export default function MdCodeBlock({ children }) {
  const toast = useToast()
  const code = extractText(children)
  return (
    <div className="code-block">
      <button
        className="code-copy"
        onClick={() => {
          navigator.clipboard?.writeText(code)
          toast('代码已复制')
        }}
      >
        ⧉ 复制
      </button>
      <pre>{children}</pre>
    </div>
  )
}