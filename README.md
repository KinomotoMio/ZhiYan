# 知演 ZhiYan — 部署指南（内部）

## 环境要求

- Python 3.12–3.13（后端）
- Node.js + [pnpm](https://pnpm.io) >=10.0.0（前端）
- [uv](https://docs.astral.sh/uv/)（Python 包管理器）

## 1. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入 LLM API Key 及其他配置
```

## 2. 启动后端

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

## 3. 启动前端

```bash
cd frontend
pnpm install
pnpm dev        # 开发模式，访问 http://localhost:3000
# 生产模式: pnpm build && pnpm start
```
