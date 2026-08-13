# Peach / 桃子求职陪练 Agent

桃子是一个面向求职者的 AI 面试搭子。它不是单纯聊天框，而是会围绕用户档案、简历、知识库、历史面试和长期记忆，主动规划下一步，并在用户确认后执行档案、简历、知识库和模拟面试相关动作。

## 核心能力

- 问问桃子：对话式求职助手，支持文件上传解析、工具动作审批、历史对话、复制和多轮上下文。
- 沉浸式语音面试：优先使用独立 FunASR Runtime 2-pass Streaming ASR 实时识别，浏览器 Web Speech 兜底；浏览器 TTS 朗读面试官问题，支持静音、打断、重播、语速调节、手动结束和文字面试切换。
- 模拟面试流程：从自我介绍开始，逐步进入经历深挖、岗位理解、证据质量、压力追问和收尾准备，后端用 checklist 控制面试完成度。
- 面试复盘报告：面试结束后生成岗位、综合分、等级、同类百分位、多维评价、建议和问题回顾，并归档到个人档案。
- 个人档案：沉淀完整简历、实习经历、项目经历、教育背景、个人技能、竞赛经历和历史面试复盘。
- 求职知识库：支持个人资料上传、链接解析、资料编辑、资料级 AI 摘要/优化/提题，并支持基于知识库问答。
- 长期记忆：按账号隔离记忆，提取稳定求职目标、偏好、能力信号、薄弱点和面试模式，让 Agent 越用越了解用户。
- Demo 账号系统：暂时只需要用户名，不需要密码；数据按用户名对应的 profile id 隔离。

## 技术栈

- 前端：React 19 + TypeScript + Vite
- 后端：FastAPI + SQLAlchemy Async
- 数据库：SQLite demo fallback；生产可切 PostgreSQL
- LLM：DeepSeek OpenAI-compatible API，默认模型 `deepseek-v4-flash`
- 文件解析：PDF、DOC/DOCX、Markdown、HTML
- 语音：FunASR Runtime 2-pass Streaming ASR + 浏览器 Web Speech fallback + SpeechSynthesis

## 目录结构

```text
backend/                 FastAPI 后端
  app/api/routes.py      REST API、账号隔离、面试、知识库、健康检查
  app/mcp_server.py      Streamable HTTP MCP 工具入口
  app/services/agent.py  LLM persona、工具规划、面试官、报告生成
  app/services/memory.py 长期记忆检索、提取、去重和裁剪
  app/services/file_parser.py 文件和链接解析
frontend/                React 前端
asr/                     FunASR 2-pass Streaming ASR 独立服务
scripts/                 提交和开发辅助脚本
docker-compose.yml       容器化一键启动
```

## 环境变量

复制 `.env.example` 为 `.env`，至少配置：

```bash
DATABASE_URL=sqlite+aiosqlite:///./data/peach-local.db
SYNC_DATABASE_URL=sqlite:///./data/peach-local.db
DEEPSEEK_API_KEY=your_deepseek_api_key_here
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
CORS_ORIGINS=["http://localhost:5173","http://127.0.0.1:5173"]
LOCAL_ASR_WS_URL=        # 可选，本地 FunASR 网关地址，如 ws://127.0.0.1:10096/asr
```

本地 demo 默认可以直接使用 SQLite，不需要先安装 PostgreSQL。生产部署如需持久化和并发能力，可改为：

```bash
DATABASE_URL=postgresql+asyncpg://peach:password@host:5432/peach
SYNC_DATABASE_URL=postgresql://peach:password@host:5432/peach
```

不要把真实 `.env` 打进源码 ZIP。

## 本地启动

```bash
cd /Users/shihuiyang/work/0802/peach
./start-dev.sh
```

强制重启：

```bash
./start-dev.sh --restart
```

访问：

- 前端：http://localhost:5173
- 后端：http://localhost:8000
- API 文档：http://localhost:8000/docs
- 基础健康检查：http://localhost:8000/api/health
- 深度健康检查：http://localhost:8000/api/health/deep
- Agent 能力说明：http://localhost:8000/api/capabilities
- MCP 本地地址：http://localhost:8000/mcp/

如需启用本地 FunASR 2-pass ASR，先启动独立 ASR 容器：

```bash
docker compose up --build asr
LOCAL_ASR_WS_URL=ws://127.0.0.1:10096/asr ./start-dev.sh --restart
```

未配置或连接失败时，前端会自动回退到浏览器 Web Speech。

## Docker 启动

适合评测方快速验证交付性：

```bash
cd /Users/shihuiyang/work/0802/peach
DEEPSEEK_API_KEY=your_key docker compose up --build
```

访问：

- 前端：http://localhost:8080
- 后端：http://localhost:8000/api/health
- ASR：http://localhost:10096/health

FunASR 服务按 4 vCPU / 8GB 资源上限配置，默认参数为 `FUNASR_DECODER_THREADS=3`、`FUNASR_IO_THREADS=1`、`FUNASR_MODEL_THREADS=1`、`OMP_NUM_THREADS=1`。云端部署建议将 `peach-asr` 作为独立 CloudBase Run 服务，端口 `8080`，最小实例数设为 `1`，前端构建变量配置为：

```bash
VITE_ASR_WS_URL=wss://<your-peach-asr-domain>/asr
```

如果没有配置 `DEEPSEEK_API_KEY`，系统仍会用确定性 fallback 跑通主流程，但动态评测 AI 能力建议提供有效 key。

## 核心 API

- `POST /api/accounts`：创建 demo 账号
- `POST /api/accounts/login`：登录 demo 账号
- `POST /api/accounts/reset`：重置当前账号数据
- `GET /api/dashboard`：读取当前账号画像、成长、面试和记忆摘要
- `GET /api/capabilities`：返回 Agent 能力、工具和安全边界
- `GET /api/health/deep`：检查数据库、LLM 配置、文件解析、记忆和运行环境
- `POST /api/agent/actions`：LLM 规划回复和待审批工具动作
- `POST /api/agent/actions/execute`：执行用户确认后的工具动作
- `POST /api/interviews`：创建模拟面试
- `POST /api/interviews/{id}/answer`：提交回答并获得下一题
- `POST /api/interviews/{id}/finish`：结束面试并生成报告
- `POST /api/knowledge/upload`：上传文件并加入知识库
- `POST /api/knowledge/link`：解析链接并加入知识库
- `GET /api/memories` / `DELETE /api/memories/{id}`：查看和删除长期记忆

## MCP 评测入口

后端已提供 Streamable HTTP MCP，部署后公网地址格式为：

```text
https://<your-cloudbase-run-domain>/mcp/
```

当前核心工具：

- `peach_chat`：个性化求职咨询，并更新长期记忆
- `peach_start_interview`：创建模拟面试
- `peach_answer_interview`：推进面试问答
- `peach_finish_interview`：结束面试并生成复盘报告
- `peach_generate_resume`：基于档案、知识库和记忆生成简历
- `peach_profile_snapshot`：只读查看账号隔离后的档案、记忆和最近面试

提交前建议用官方 MCP client 验证：

```bash
python scripts/verify_mcp.py --url https://<your-cloudbase-run-domain>/mcp/ --call-tool
```

预期输出包含 `MCP initialize: ok`、完整工具列表，以及 `peach_profile_snapshot` 返回的 `{"ok": true, ...}`。

## 测试与质量检查

```bash
python -m compileall backend/app
pytest
pnpm --dir frontend lint
pnpm --dir frontend build
python scripts/verify_mcp.py --url http://127.0.0.1:8000/mcp/ --call-tool
```

当前测试覆盖：

- 文件解析的 Markdown / HTML 基础抽取
- 长期记忆内容过滤和上下文压缩
- 面试进度 checklist 和最小轮数约束
- MCP 工具注册和 CloudBase Streamable HTTP 挂载配置
- 工具动作白名单和用户名归一化

## 比赛源码 ZIP

请用脚本生成提交包，避免把 `.env`、`.local`、`node_modules`、构建产物和本地数据库打进去：

```bash
./scripts/build_submission_zip.sh
```

输出文件在：

```text
dist-submission/peach-agent-submission.zip
```

脚本使用 `git archive`，只打包 Git 已跟踪文件。生成前请先确认重要改动已提交。

## 隐私与安全边界

- 前端不持有模型 API Key。
- 工具动作默认需要用户确认后才执行。
- 用户数据、知识库、面试和长期记忆均按当前账号对应的 `profile.id` 查询，不跨用户检索。
- 长期记忆提取会过滤密码、验证码、身份证、银行卡、token、api key、secret 等敏感信息。
- 页面加载不会自动把简历或档案发送给外部模型；LLM 调用发生在用户主动对话、上传、练习、面试或确认工具动作时。

## 已知边界

- 当前 demo 账号只有用户名，没有密码和正式鉴权；正式上线前需要接入登录态和权限校验。
- 本地默认 SQLite 方便评测快速启动；正式上线建议使用 PostgreSQL 或腾讯云托管数据库。
- 语音识别优先走独立 FunASR 2-pass ASR，连接失败时回退浏览器 Web Speech；TTS 仍使用浏览器 SpeechSynthesis，效果取决于浏览器支持度。
