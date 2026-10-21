# 安装与运行

## 1. 环境要求

| 组件 | 版本 | 说明 |
| --- | --- | --- |
| Windows | 10 / 11 | 当前主要支持 Windows |
| Python | 3.10+ | 后端、桌面壳、脚本 |
| Node.js | 18+ | 前端构建 |
| Git | 任意较新版本 | 克隆仓库 |

桌面模式还需要 **Microsoft Edge WebView2 Runtime**。Windows 10/11 通常已自带；
如果桌面窗口空白，安装 WebView2 Runtime 后重试。

## 2. 一键安装

```bat
git clone https://github.com/wangchenyi520/research-workbench.git
cd research-workbench
setup.bat
```

脚本会：

1. 创建 `.venv`；
2. 安装 `backend/requirements.txt`；
3. 安装 `desktop-requirements.txt`；
4. 在 `frontend/` 执行 `npm ci` 和 `npm run build`。

首次安装会下载 PyTorch 之外的依赖；`faster-whisper` 体积较大，请预留磁盘空间。

## 3. 启动

```bat
start.bat          :: 浏览器模式
start_desktop.bat  :: 桌面模式（托盘常驻）
stop.bat           :: 停止 8000 端口的后端
```

浏览器模式访问 <http://127.0.0.1:8000>。桌面模式关闭窗口后最小化到托盘，
从托盘菜单退出。

## 4. 手动安装

```bat
python -m venv .venv
.venv\Scripts\activate

pip install -r backend\requirements.txt
pip install -r desktop-requirements.txt

cd frontend
npm ci
npm run build
cd ..

start.bat
```

开发模式：

```bat
:: 终端 1：后端热重载
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000

:: 终端 2：前端热更新
cd frontend
npm run dev
```

前端开发服务器默认把 `/api` 代理到 `127.0.0.1:8000`。

## 5. 首次配置

打开「设置」：

### DeepSeek（可选）

1. 在 <https://platform.deepseek.com> 注册并创建 API Key；
2. 粘贴到「DeepSeek API Key」；
3. 保存后 AI 总结、规划、对话、每日整理才会工作。

不配置也能使用任务、笔记、文献同步、统计等非 AI 功能。

### Zotero（可选）

1. 打开 Zotero 桌面版 → 设置 → 高级 → 生成 API Key；
2. 在 Zotero 设置页找到 User ID；
3. 填入工作台设置页。

工作台通过 Zotero **在线 API** 增量同步，不依赖 Zotero 本地端口。

### 每日论文（可选）

默认检索词是 `infrared small target detection`，可在设置页改成你的研究方向。
该功能使用 OpenAlex 公共 API，需要联网。

### Self_analysis 规划文件夹（可选）

如果你有一组 Markdown 规划文档（`plan/*.md`、`复盘/*.md`），把文件夹路径填到
设置页，作战计划页会递归读取并结构化解析。**该功能只读**；回写会先备份并二次确认。

## 6. 数据位置

默认：

```
backend/data/
  workbench.db          SQLite 主库
  images/               笔记图片
  attachments/          附件
  pdfs/                 文献 PDF
  audio/                语音录入
  backups/              自动备份（默认保留 14 份）
  logs/                 运行日志
daily_paper/            每日论文 PDF（可用环境变量覆盖）
```

可通过 `.env` 覆盖：

```bat
copy .env.example .env
```

```ini
WORKBENCH_DATA=C:\Users\you\WorkbenchData
WORKBENCH_DB=C:\Users\you\WorkbenchData\workbench.db
WORKBENCH_DAILY_PAPER_DIR=C:\Users\you\WorkbenchData\daily_paper
```

路径建议使用绝对路径。修改后重启后端。

## 7. 常见问题

**`python` 不是内部或外部命令**
安装 Python 3.10+，勾选 “Add Python to PATH”，重新打开终端。

**`npm` 不是内部或外部命令**
安装 Node.js 18+，重新打开终端；或只跑后端，跳过前端构建（但浏览器模式没有界面）。

**8000 端口被占用**

```bat
stop.bat
```

或修改 `start.bat`、`desktop.py` 中的端口，并同步修改 `frontend/vite.config.js`
的代理目标。

**页面空白 / 只有 API**
没有构建前端。运行：

```bat
cd frontend
npm ci
npm run build
```

**桌面窗口空白**
安装 Microsoft Edge WebView2 Runtime；确认 `desktop-requirements.txt` 已安装。

**语音转写第一次很慢**
`faster-whisper` 首次使用会下载模型到 `backend/data/whisper-models/`，需要联网和磁盘空间。

**Zotero 同步 403 / 401**
检查 API Key 是否只读、User ID 是否正确；确认 Key 有 library read 权限。

**DeepSeek 401 / 402**
检查 Key 是否有效、账户是否有余额。

**数据库被锁**
不要同时开浏览器模式和桌面模式的两个后端；用 `stop.bat` 停掉旧进程再启动。

## 8. 更新

```bat
git pull
setup.bat
```

数据库迁移在启动时自动执行，且设计为增量迁移；升级前建议在设置页手动导出备份。

## 9. 卸载

关闭程序后删除整个项目目录即可。若把数据放在自定义目录，单独删除该目录。
