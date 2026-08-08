# Peach / 桃子求职陪练 Agent

桃子是一个求职面试陪练 + 心理搭子 + 成长教练。当前版本先实现 PRD 的核心 MVP：求职画像、每日一练、模拟面试、面后复盘、成长档案和搭子聊天。

## 技术栈

- 前端：React + TypeScript + Vite
- 后端：FastAPI + SQLAlchemy Async
- 数据库：PostgreSQL + pgvector
- 缓存预留：Redis
- LLM：DeepSeek OpenAI-compatible API，默认模型 `deepseek-v4-flash`

## 本地启动

一键启动前后端：

```bash
cd /Users/shihuiyang/work/0802/peach
./start-dev.sh
```

如果前后端已经在 `8000` / `5173` 端口运行，脚本会直接给访问链接，不重复启动。需要强制重启时：

```bash
./start-dev.sh --restart
```

确认 PostgreSQL 和 Redis 已启动：

```bash
conda activate peach
pg_ctl -D .local/postgres -l .local/postgres/server.log start
redis-server --daemonize yes
```

启动后端：

```bash
cd /Users/shihuiyang/work/0802/peach
conda activate peach
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

启动前端：

```bash
cd /Users/shihuiyang/work/0802/peach/frontend
pnpm dev
```

访问：

- 前端：http://localhost:5173
- 后端健康检查：http://localhost:8000/api/health
- API 文档：http://localhost:8000/docs

## 当前功能

- `POST /api/profile`：保存用户求职画像，并生成个性化备战计划
- `GET /api/dashboard`：读取首页所需的 check-in、成长档案和历史记录
- `POST /api/practice`：提交每日一练回答，生成评分和反馈
- `POST /api/interviews`：发起一场模拟面试
- `POST /api/interviews/{id}/answer`：提交模拟面试回答并获得追问
- `POST /api/interviews/{id}/finish`：结束模拟面试并生成报告
- `POST /api/review`：真实面试后的情绪疏导与复盘
- `POST /api/chat`：和桃子进行陪伴式聊天

## 隐私边界

`GET /api/dashboard` 页面加载接口只使用本地数据库生成默认任务，不会自动把简历或求职画像发送给外部模型。DeepSeek 调用只发生在用户主动提交画像、练习回答、模拟面试回答、面后复盘或聊天消息时。

## 腾讯云部署方向

- 前端构建后可部署到 COS + CDN，或由 CVM 上的 Nginx 托管。
- 后端建议容器化后部署到 CVM、轻量应用服务器或 TKE。
- 线上数据库建议使用腾讯云 PostgreSQL；文件存储后续接 COS。
- API Key 只放在后端环境变量中，前端不持有模型密钥。
