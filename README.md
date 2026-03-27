# 知演 ZhiYan — 部署指南（内部）

## 环境要求

- Python 3.12–3.13（后端）
- Node.js + [pnpm](https://pnpm.io) >=10.0.0（前端）
- [uv](https://docs.astral.sh/uv/)（Python 包管理器）

## 1. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入 LLM API Key、MiniMax TTS Key 及其他配置
```

关键配置：

- 文本生成模型：`DEFAULT_MODEL`、`STRONG_MODEL`、`VISION_MODEL`、`FAST_MODEL`
- 文本模型密钥：`OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY` / `DEEPSEEK_API_KEY` / `OPENROUTER_API_KEY`
- 演讲者注解朗读：`TTS_PROVIDER=minimax`、`TTS_API_KEY`、`TTS_BASE_URL`、`TTS_MODEL=speech-2.8-hd`、`TTS_VOICE_ID`

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
