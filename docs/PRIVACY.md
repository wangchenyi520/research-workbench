# 数据与隐私

工作台的默认假设是：**数据属于你，留在你的机器上**。没有账号系统、没有遥测、
没有云端同步。下面列出它会写什么、什么时候联网。

## 本地数据清单

| 位置 | 内容 | 是否进 Git |
| --- | --- | --- |
| `backend/data/workbench.db` | 任务、目标、笔记、文献元数据、设置、统计 | 否 |
| `backend/data/images/` | 笔记图片 | 否 |
| `backend/data/attachments/` | 附件 | 否 |
| `backend/data/pdfs/` | 文献 PDF | 否 |
| `backend/data/audio/` | 语音录入 | 否 |
| `backend/data/backups/` | 自动备份 | 否 |
| `backend/data/logs/` | 运行日志 | 否 |
| `backend/data/whisper-models/` | 本地语音模型 | 否 |
| `daily_paper/` | 每日论文 PDF | 否 |
| `backend/data/pill_*.json` | 桌面胶囊偏好 | 否 |

`.gitignore` 已排除 `backend/data/`、`*.db`、`*.log`、`.env` 和前端构建产物。
提交 PR 前请确认 `git status` 没有这些文件。

## 网络请求

工作台只在以下情况发起网络请求：

| 功能 | 目标 | 发送内容 | 是否必需 |
| --- | --- | --- | --- |
| AI 总结 / 规划 / 对话 / 每日整理 | DeepSeek API | 你选中的文本、提示词、科研画像 | 否，需自行配置 Key |
| 文献同步 | Zotero API | API Key、User ID、同步请求 | 否，需自行配置 |
| 每日论文检索 | OpenAlex | 检索词 | 否，可关闭 |
| 论文 PDF 下载 | 出版商 / 开放获取站点 | 论文 URL | 否，用户主动触发 |
| 语音转写 | 本地 faster-whisper | 音频不离开本机；首次下载模型需要联网 | 否 |

除此之外没有埋点、崩溃上报、远程配置或“检查更新”。

## API Key

- DeepSeek Key 和 Zotero Key 存在本地 SQLite 的 `settings` 表。
- Windows 上使用 DPAPI（`CryptProtectData`）加密，密文以 `enc:` 开头。
- 设置页读取时只返回掩码（如 `sk-a****1234`），不会把明文发回前端。
- 非 Windows 环境会回退为明文存储；不要在共享机器上这样使用。
- 如果怀疑泄露：立刻在 DeepSeek / Zotero 后台吊销 Key，再在设置页填入新 Key。

## 备份

- 默认每天自动备份到 `backend/data/backups/`，保留 14 份。
- 备份是完整 SQLite 文件，包含你的数据；请像保护原库一样保护备份。
- 设置页可以手动导出备份；导出文件不要提交到 Git 或公开网盘。

## 删除数据

1. 关闭工作台（`stop.bat`，桌面模式从托盘退出）。
2. 删除 `backend/data/`（或你在 `.env` 中配置的自定义数据目录）。
3. 删除 `daily_paper/`（如果使用过每日论文下载）。
4. 如需彻底清理，删除整个项目目录。

删除前建议先导出需要保留的笔记或备份。

## 第三方政策

工作台不控制第三方服务的数据处理方式。使用前请阅读：

- DeepSeek：<https://platform.deepseek.com>
- Zotero：<https://www.zotero.org/support/privacy>
- OpenAlex：<https://openalex.org>

如果你所在机构对数据出境、API 使用或文献版权有要求，请先确认合规性。
