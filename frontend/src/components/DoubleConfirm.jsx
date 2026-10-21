import { useEffect, useState } from 'react'

/**
 * 双重确认弹窗：所有写入 Self_analysis 手写文档的操作必须两步确认。
 * 第一步展示改动预览（children），第二步红色警告再确认。
 */
export default function DoubleConfirm({
  open,
  title = '同步到计划文档',
  desc,
  children,
  onCancel,
  onConfirm,
  busy = false,
  confirmLabel = '确定修改',
}) {
  const [step, setStep] = useState(1)

  useEffect(() => {
    if (open) setStep(1)
  }, [open])

  if (!open) return null

  return (
    <div className="modal-mask" onClick={busy ? undefined : onCancel}>
      <div className="modal" style={{ width: 760, maxWidth: '94vw' }} onClick={e => e.stopPropagation()}>
        {step === 1 ? (
          <>
            <h3>⚠️ {title}</h3>
            <div className="muted" style={{ marginBottom: 10 }}>
              {desc || '这会修改 Self_analysis 文件夹中的手写文档。写入前会自动备份到工作台 data/sa_backups/。'}
            </div>
            <div className="dc-preview">{children}</div>
            <div className="modal-actions">
              <button className="btn" onClick={onCancel} disabled={busy}>取消</button>
              <button className="btn btn-primary" onClick={() => setStep(2)} disabled={busy}>确定，继续</button>
            </div>
          </>
        ) : (
          <>
            <h3>🛑 再次确认修改手写文档</h3>
            <div style={{ marginBottom: 12, lineHeight: 1.8 }}>
              你确定要把以上改动写入 Self_analysis 里的手写文档吗？<br />
              <span className="muted">这是最后一次确认；写入前会自动备份，冲突行会被跳过并报告。</span>
            </div>
            <div className="modal-actions">
              <button className="btn" onClick={onCancel} disabled={busy}>取消</button>
              <button className="btn btn-danger" onClick={onConfirm} disabled={busy}>
                {busy ? '写入中…' : confirmLabel}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
