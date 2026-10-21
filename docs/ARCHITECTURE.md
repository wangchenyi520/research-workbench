# 架构说明

## 总览

```
frontend/                  React + Vite
  src/pages/               功能页面
  src/components/          通用组件
  src/api.js               Axios 客户端（/api 代理到后端）
        │
        │ HTTP 127.0.0.1:8000
        ▼
backend/app/
  main.py                  FastAPI 入口、路由注册、静态文件挂载
  routers/                 各功能 API
  services/                业务逻辑、第三方集成、桌面组件
  models.py                SQLAlchemy 模型
  schemas.py               Pydantic 请求/响应模型
  migrate.py               增量迁移
  database.py              引擎与会话
  config.py                本地路径、环境变量
        │
        ▼
backend/data/workbench.db  SQLite（单文件）
backend/data/              图片、附件、PDF、音频、备份、日志
```

桌面模式在同一个后端外面套一层 `pywebview`：

```
desktop.py → 启动 uvicorn 线程 → 打开 127.0.0.1:8000 窗口
           → pystray 托盘 → 关闭窗口时最小化
           → 悬浮清单 / 番茄钟 / 四个桌面胶囊
```

## 后端分层

### `main.py`

- 创建 `FastAPI` 应用和 lifespan。
- 启动时执行数据库建表、增量迁移、提醒调度器、自动备份、桌面组件恢复。
- 注册所有 router。
- 提供 `/api/health`。
- 未匹配的 `/api/*` 返回 404，避免落到前端静态文件。
- 如果 `frontend/dist` 存在，挂载为静态站点。

### `routers/`

每个文件对应一组 API，例如：

| Router | 职责 |
| --- | --- |
| `tasks.py` | 任务 CRUD、看板排序、子任务、循环任务 |
| `goals.py` | 目标金字塔、里程碑 |
| `notes.py` | Markdown 笔记、文件夹、图片、双向链接 |
| `literature.py` | Zotero 同步、AI 总结、标签、BibTeX |
| `daily.py` / `daily_paper.py` | 今日清单、每日论文 |
| `reviews.py` | 周复盘 / 报告 |
| `stats.py` | 仪表盘统计、热力图、趋势 |
| `attendance.py` | 考勤计时与月度统计 |
| `reminders.py` | 提醒事项与调度 |
| `pomodoro.py` / `free_pomodoro.py` | 任务番茄钟、自由番茄钟 |
| `settings.py` | 设置、API Key 掩码、自启动 |
| `backup.py` | 导出 / 导入 / 自动备份 |
| `voice.py` | 本地 Whisper 语音转写 |
| `self_analysis.py` | Markdown 规划文件夹读写 |
| `checklist_widget.py` / `attendance_pill.py` / `reminder_pill.py` | 桌面悬浮组件 |

### `services/`

非 HTTP 的业务逻辑集中在这里：

- `deepseek.py`：DeepSeek API 封装；
- `zotero.py`：Zotero 在线 API 增量同步；
- `paper_sources.py`：OpenAlex 检索；
- `whisper_service.py`：faster-whisper 本地转写；
- `reminder.py`：提醒调度器；
- `backups.py`：自动备份与清理；
- `secure.py`：Windows DPAPI 加解密；
- `active_sessions.py`：异常退出后的计时恢复；
- `pill_window.py` / `*_pill.py` / `*_widget.py`：桌面悬浮窗；
- `window_chrome.py`：无边框窗口与拖动/缩放；
- `mem_trim.py`：长时间运行的内存回收。

### 数据模型

核心表（示例，不完整）：

- `settings`：键值设置；敏感值加密存储。
- `goals` / `milestones`：目标层级与里程碑。
- `tasks` / `task_subtasks` / `checkins` / `time_logs`：任务、子任务、打卡、计时。
- `free_pomodoros`：自由番茄钟的权威计时状态。
- 笔记、文献、复盘、提醒、考勤等表由对应 router/service 使用。

新增字段通过 `migrate.py` 做增量迁移；不要要求用户删库重建。

## 前端

- `src/App.jsx`：路由、主题、字体、全局快捷键、侧边栏。
- `src/pages/`：每个功能一个页面，页面自己管理数据加载和交互。
- `src/components/`：Toast、命令面板、快速添加、错误边界、Markdown 代码块等。
- `src/api.js`：Axios 实例，统一 baseURL 和错误处理。
- `src/styles.css`：主题变量、布局、组件样式；主题色通过 CSS 变量切换。
- `vite.config.js`：开发服务器把 `/api` 代理到 `127.0.0.1:8000`。

前端不直接访问 SQLite 或第三方 API；所有请求都经过后端，便于做密钥保护
和本地数据边界。

## 桌面壳

`desktop.py`：

- 启动 uvicorn 线程（`127.0.0.1:8000`）；
- 用 pywebview 打开窗口；
- 用 pystray 常驻托盘；
- 关闭窗口时隐藏而不是退出；
- 恢复上次打开的悬浮组件。

`services/pill_window.py` 提供可复用的无边框置顶窗口；四个胶囊和悬浮清单/
番茄钟都基于它。窗口位置、颜色、透明度存在本地设置或 `backend/data/*.json`。

## 典型请求流

### 快速添加任务

```
Today 页面输入自然语言
  → POST /api/tasks/quick-add
  → tasks router 解析标题/日期/优先级
  → SQLAlchemy 写入 tasks
  → 返回任务，前端刷新今日清单
```

### 文献同步

```
Literature 页面点击同步
  → POST /api/literature/sync
  → zotero service 读取设置中的 Key/User ID
  → 分页拉取 Zotero 条目
  → upsert 本地文献表
  → 返回新增/更新数量
```

### 每日论文

```
DailyPaper 页面
  → GET /api/daily-paper/today
  → paper_sources 调 OpenAlex
  → 可选 DeepSeek 生成中文导览
  → 返回候选论文
  → 用户一键加入今日清单 / Zotero
```

### 桌面胶囊

```
Settings 打开胶囊
  → POST /api/attendance-pill/control {action: show}
  → service 创建置顶窗口
  → 窗口内按钮调用后端计时 API
  → 关闭时隐藏并保存偏好
```

## 扩展点

- **新增页面**：`src/pages/` 加组件，`App.jsx` 加路由和侧边栏项。
- **新增 API**：`routers/` 加文件，`main.py` 注册；复杂逻辑放 `services/`。
- **新增持久化**：`models.py` 加表/字段，`migrate.py` 加增量迁移，`schemas.py`
  加请求/响应模型。
- **新增第三方服务**：放 `services/`，密钥走 `settings` + `secure`，网络调用
  必须可选、可关闭、写进 `docs/PRIVACY.md`。
- **新增桌面组件**：复用 `pill_window.py`，不要直接操作 Win32 窗口句柄。

## 安全边界

- 后端只监听 `127.0.0.1`，默认没有鉴权；**不要暴露到公网**。
- 前端和后端共享同一台机器，API 不做多用户隔离。
- API Key 只在后端解密使用，前端只拿到掩码。
- `backend/data/` 是用户数据边界，永远不进 Git。
- 第三方请求只在用户主动使用对应功能时发生。
