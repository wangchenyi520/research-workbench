import React, { useEffect, useState } from 'react'
import { HashRouter, Navigate, Route, Routes, useNavigate, useLocation } from 'react-router-dom'
import api from './api'
import Today from './pages/Today'
import AiCenter from './pages/AiCenter'
import Dashboard from './pages/Dashboard'
import Tasks from './pages/Tasks'
import Goals from './pages/Goals'
import Notes from './pages/Notes'
import Literature from './pages/Literature'
import Settings from './pages/Settings'
import Review from './pages/Review'
import Search from './pages/Search'
import StudyLog from './pages/StudyLog'
import Experiments from './pages/Experiments'
import Papers from './pages/Papers'
import OJ from './pages/OJ'
import Interview from './pages/Interview'
import Jobs from './pages/Jobs'
import Reports from './pages/Reports'
import Calendar from './pages/Calendar'
import Meeting from './pages/Meeting'
import Tags from './pages/Tags'
import Chat from './pages/Chat'
import Reminders from './pages/Reminders'
import Attendance from './pages/Attendance'
import Life from './pages/Life'
import DailyPaper from './pages/DailyPaper'
import BattlePlan from './pages/BattlePlan'
import { ToastProvider, useToast } from './components/Toast'
import ErrorBoundary from './components/ErrorBoundary'
import CommandPalette from './components/CommandPalette'
import QuickAdd from './components/QuickAdd'
import ActiveTaskPill from './components/ActiveTaskPill'
import WindowChrome from './components/TitleBar'
import { accentVars } from './utils/color'
import {
  Sun, Bell, MapPin, HeartPulse, LayoutDashboard, CheckSquare, Target, Folder, CalendarDays, RotateCcw,
  BarChart3, FlaskConical, MessagesSquare, NotebookPen, FileText, BookOpen, Rocket, Code2, Flag,
  Library, Briefcase, BookMarked, TrendingUp, Sparkles, MessageSquare, Search as SearchIcon,
  Tag, Settings as SettingsIcon, LibraryBig, Bot,
  Moon, Palette, ChevronDown, ChevronRight,
} from 'lucide-react'

export const ACCENTS = ['purple', 'blue', 'green', 'orange', 'pink', 'red']

const NAV = [
  { path: '/today', label: '今日', icon: Sun },
  { path: '/reminders', label: '提醒事项', icon: Bell },
  { path: '/attendance', label: '考勤', icon: MapPin },
  { path: '/life', label: '生活记录', icon: HeartPulse },
  { path: '/dashboard', label: '仪表盘', icon: LayoutDashboard },
  { path: '/tasks', label: '任务', icon: CheckSquare },
  { path: '/goals', label: '规划', icon: Target },
  { path: '/battle-plan', label: '作战计划', icon: Flag },
  { id: 'review', label: '复盘报告', icon: Folder, children: [
    { path: '/calendar', label: '日历', icon: CalendarDays },
    { path: '/review', label: '周复盘', icon: RotateCcw },
    { path: '/reports', label: '报告', icon: BarChart3 },
    { path: '/experiments', label: '实验记录', icon: FlaskConical },
    { path: '/meeting', label: '组会纪要', icon: MessagesSquare },
  ] },
  { path: '/notes', label: '笔记', icon: NotebookPen },
  { path: '/papers', label: '论文进度', icon: FileText },
  { path: '/daily-paper', label: '每日论文', icon: BookOpen },
  { id: 'career', label: '大厂冲刺', icon: Rocket, children: [
    { path: '/oj', label: '刷题记录', icon: Code2 },
    { path: '/interview', label: '面试八股', icon: Library },
    { path: '/jobs', label: '求职投递', icon: Briefcase },
  ] },
  { id: 'knowledge', label: '知识库', icon: LibraryBig, children: [
    { path: '/literature', label: '文献', icon: BookMarked },
    { path: '/studylog', label: '学习轨迹', icon: TrendingUp },
    { path: '/search', label: '搜索', icon: SearchIcon },
    { path: '/tags', label: '标签', icon: Tag },
  ] },
  { id: 'aitools', label: 'AI 工具', icon: Bot, children: [
    { path: '/ai', label: 'AI 中心', icon: Sparkles },
    { path: '/chat', label: 'AI 助手', icon: MessageSquare },
  ] },
  { path: '/settings', label: '设置', icon: SettingsIcon },
]

function NavIcon({ I, size = 16 }) {
  const C = I
  return <C size={size} strokeWidth={1.75} />
}

function Sidebar({ theme, setTheme, accent, setAccent, effectiveTheme }) {
  const navigate = useNavigate()
  const location = useLocation()
  const [openGroups, setOpenGroups] = useState({})

  // 当前路由所在的分组自动展开，方便定位
  useEffect(() => {
    const g = NAV.find(n => n.children && n.children.some(c => c.path === location.pathname))
    if (g) setOpenGroups(s => (s[g.id] ? s : { ...s, [g.id]: true }))
  }, [location.pathname])

  const renderItem = (n, sub = false) => (
    <button
      key={n.path}
      data-label={n.label}
      className={`nav-item ${sub ? 'nav-sub-item' : ''} ${location.pathname === n.path ? 'active' : ''}`}
      onClick={() => navigate(n.path)}
    >
      <span className="nav-icon"><NavIcon I={n.icon} /></span>
      <span className="nav-label">{n.label}</span>
    </button>
  )

  const renderGroup = g => {
    const open = !!openGroups[g.id]
    const activeInGroup = g.children.some(c => c.path === location.pathname)
    return (
      <div key={g.id} className="nav-group">
        <button
          className={`nav-item nav-group-head ${open ? 'open' : ''} ${activeInGroup ? 'active' : ''}`}
          onClick={() => setOpenGroups(s => ({ ...s, [g.id]: !s[g.id] }))}
          title={g.label}
          data-label={g.label}
        >
          <span className="nav-icon"><NavIcon I={g.icon} /></span>
          <span className="nav-label">{g.label}</span>
          <span className="nav-arrow">{open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}</span>
        </button>
        {open && <div className="nav-group-children">{g.children.map(c => renderItem(c, true))}</div>}
      </div>
    )
  }

  return (
    <div className="sidebar">
      <div className="logo">
        <img className="logo-img" src="/icon.png" alt="" />
        <span className="logo-col">
          <span className="logo-text">研究生工作台</span>
          <span className="logo-ver">v2.1 · 本地科研</span>
        </span>
      </div>
      {NAV.map(n => (n.children ? renderGroup(n) : renderItem(n)))}
      <div className="sidebar-footer">
        <button
          className="side-quick"
          title={theme === 'auto' ? `跟随系统（当前${effectiveTheme === 'light' ? '浅色' : '暗色'}），点击切换` : (effectiveTheme === 'light' ? '切换到暗色' : '切换到浅色')}
          onClick={() => setTheme(effectiveTheme === 'light' ? 'dark' : 'light')}
        >
          {effectiveTheme === 'light' ? <Moon size={15} strokeWidth={1.8} /> : <Sun size={15} strokeWidth={1.8} />}
        </button>
        <button
          className="side-quick"
          title="切换主题色系"
          onClick={() => setAccent(a => ACCENTS[(ACCENTS.indexOf(a) + 1) % ACCENTS.length])}
        >
          <Palette size={15} strokeWidth={1.8} />
        </button>
      </div>
    </div>
  )
}

function Shell() {
  // ③ 暗色跟随系统：wb_theme 存 light/dark/auto；无手动设置（auto）时跟随 OS prefers-color-scheme
  const [theme, setTheme] = useState(localStorage.getItem('wb_theme') || 'auto')
  const [osDark, setOsDark] = useState(() => typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-color-scheme: dark)').matches)
  const [accent, setAccent] = useState(localStorage.getItem('wb_accent') || 'purple')
  // 自定义主题色（accent='custom' 时生效，十六进制）
  const [customAccent, setCustomAccent] = useState(localStorage.getItem('wb_accent_custom') || '#6a56e8')
  const [fontSize, setFontSize] = useState(Number(localStorage.getItem('wb_font') || 14))
  const [fontFamily, setFontFamily] = useState(localStorage.getItem('wb_font_family') || 'system')
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [quickOpen, setQuickOpen] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()
  const toast = useToast()
  const effectiveTheme = theme === 'auto' ? (osDark ? 'dark' : 'light') : theme

  // 监听系统主题变化：auto 模式下实时跟随
  useEffect(() => {
    const mq = window.matchMedia?.('(prefers-color-scheme: dark)')
    if (!mq) return
    const fn = e => setOsDark(e.matches)
    mq.addEventListener('change', fn)
    return () => mq.removeEventListener('change', fn)
  }, [])

  useEffect(() => {
    const root = document.documentElement
    root.setAttribute('data-theme', effectiveTheme)
    root.setAttribute('data-accent', accent)
    root.setAttribute('data-font', fontFamily)
    root.style.setProperty('--font-scale', `${fontSize}px`)
    // 自定义主题色：直接覆盖 CSS 变量（-soft 按明暗主题派生）；切回预设时清除
    if (accent === 'custom') {
      const vars = accentVars(customAccent, effectiveTheme)
      root.style.setProperty('--primary', vars.primary)
      root.style.setProperty('--primary-soft', vars.soft)
      root.style.setProperty('--info', vars.primary)
    } else {
      root.style.removeProperty('--primary')
      root.style.removeProperty('--primary-soft')
      root.style.removeProperty('--info')
    }
    localStorage.setItem('wb_theme', theme)
    localStorage.setItem('wb_accent', accent)
    localStorage.setItem('wb_accent_custom', customAccent)
    localStorage.setItem('wb_font', String(fontSize))
    localStorage.setItem('wb_font_family', fontFamily)
  }, [theme, accent, customAccent, fontSize, fontFamily, effectiveTheme])

  // 全局网络/服务端错误提示（由 api.js 拦截器触发）
  useEffect(() => {
    const onErr = e => toast(e.detail?.msg || '请求失败', 'error')
    window.addEventListener('api-error', onErr)
    return () => window.removeEventListener('api-error', onErr)
  }, [])

  useEffect(() => {
    const onKey = e => {
      // Esc 关闭通用弹窗（在输入框聚焦时也要生效，故放在 tag 判断之前；
      // 遮罩 onClick 即各弹窗自己的关闭逻辑，命令面板/快速添加自带 Esc 处理，重复关闭无副作用）
      if (e.key === 'Escape') {
        const mask = document.querySelector('.modal-mask')
        if (mask) { e.preventDefault(); mask.click() }
        return
      }
      const tag = e.target?.tagName
      const type = (e.target?.type || '').toLowerCase()
      // 文本输入/下拉/可编辑区放行（避免打字误触全局快捷键）；复选框/单选/按钮等非文本控件不拦截
      const isTextEntry = tag === 'TEXTAREA' || tag === 'SELECT'
        || (tag === 'INPUT' && !['checkbox', 'radio', 'button', 'submit', 'file', 'range', 'color'].includes(type))
        || e.target?.isContentEditable
      if (isTextEntry) return
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'p') {
        e.preventDefault()
        setPaletteOpen(o => !o)
        return
      }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        navigate('/search')
      }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'n') {
        e.preventDefault()
        navigate('/notes?new=1')
      }
      // ④ 全局快速添加：Ctrl+Shift+T 任意页唤起
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === 't') {
        e.preventDefault()
        setQuickOpen(true)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [navigate])

  return (
    <div className="app-shell">
      <WindowChrome />
      <div className="app">
        <Sidebar theme={theme} setTheme={setTheme} accent={accent} setAccent={setAccent} effectiveTheme={effectiveTheme} />
        <main className="main">
        <ErrorBoundary>
          <div key={location.pathname} className="page-anim">
            <Routes>
              <Route path="/" element={<Navigate to="/today" replace />} />
              <Route path="/today" element={<Today />} />
              <Route path="/reminders" element={<Reminders />} />
              <Route path="/attendance" element={<Attendance />} />
              <Route path="/life" element={<Life />} />
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/tasks" element={<Tasks />} />
              <Route path="/goals" element={<Goals />} />
              <Route path="/battle-plan" element={<BattlePlan />} />
              <Route path="/calendar" element={<Calendar />} />
              <Route path="/review" element={<Review />} />
              <Route path="/reports" element={<Reports />} />
              <Route path="/notes" element={<Notes />} />
              <Route path="/experiments" element={<Experiments />} />
              <Route path="/papers" element={<Papers />} />
              <Route path="/daily-paper" element={<DailyPaper />} />
              <Route path="/oj" element={<OJ />} />
              <Route path="/interview" element={<Interview />} />
              <Route path="/jobs" element={<Jobs />} />
              <Route path="/literature" element={<Literature />} />
              <Route path="/meeting" element={<Meeting />} />
              <Route path="/studylog" element={<StudyLog />} />
              <Route path="/ai" element={<AiCenter />} />
            <Route path="/chat" element={<Chat />} />
<Route path="/search" element={<Search />} />
            <Route path="/tags" element={<Tags />} />
            <Route path="/settings" element={<Settings setTheme={setTheme} theme={theme} accent={accent} setAccent={setAccent} customAccent={customAccent} setCustomAccent={setCustomAccent} fontSize={fontSize} setFontSize={setFontSize} fontFamily={fontFamily} setFontFamily={setFontFamily} />} />
            </Routes>
          </div>
        </ErrorBoundary>
      </main>
      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        pages={NAV.flatMap(n => (n.children ? n.children : [n]))}
        onNavigate={navigate}
        onAction={a => { if (a === 'new-note') navigate('/notes'); if (a === 'new-task') navigate('/tasks') }}
      />
      <QuickAdd open={quickOpen} onClose={() => setQuickOpen(false)} />
      <ActiveTaskPill />
      </div>
    </div>
  )
}

export default function App() {
  return (
    <ToastProvider>
      <HashRouter>
        <Shell />
      </HashRouter>
    </ToastProvider>
  )
}