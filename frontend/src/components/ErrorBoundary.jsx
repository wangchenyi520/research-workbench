import React from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    console.error('ErrorBoundary caught:', error, info)
  }

  reset = () => {
    this.setState({ error: null })
    this.props.onReset?.()
  }

  render() {
    if (this.state.error) {
      return (
        <div className="card" style={{ maxWidth: 640, margin: '40px auto', textAlign: 'center' }}>
          <h2 style={{ marginBottom: 12, color: 'var(--danger)' }}>页面出错了</h2>
          <div className="muted" style={{ marginBottom: 16, wordBreak: 'break-all' }}>
            {String(this.state.error?.message || this.state.error)}
          </div>
          <div className="row" style={{ justifyContent: 'center', gap: 10 }}>
            <button className="btn btn-primary" onClick={this.reset}>返回首页</button>
            <button className="btn" onClick={() => window.location.reload()}>重新加载</button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}

export default function ErrorBoundaryWithLocation(props) {
  const location = useLocation()
  const navigate = useNavigate()
  return (
    <ErrorBoundary
      key={location.pathname}
      {...props}
      onReset={() => navigate('/')}
    />
  )
}
