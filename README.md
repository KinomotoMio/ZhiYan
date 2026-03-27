# 知演 ZhiYan

知演（ZhiYan）是一个面向演示文稿生产场景的 AI PPT 生成系统。它围绕“素材整理 -> 大纲规划 -> 内容生成 -> 编辑预览 -> 导出分享”这条链路设计，帮助团队把零散资料快速整理成可展示、可编辑、可交付的演示稿。

当前仓库包含完整的前后端实现：

- `frontend/`：基于 Next.js 的创作与编辑界面
- `backend/`：基于 FastAPI 的生成、导出与会话服务
- `data/`：本地工作区数据、会话产物与临时文件

## 核心能力

- 多来源素材接入：支持上传文件、导入 URL、粘贴文本作为生成输入
- 会话式创作流程：按会话组织素材、规划记录和演示产物，便于持续迭代
- AI 生成与规划：先梳理大纲，再确认生成，减少“一次性黑盒出稿”
- 双产出模式：支持结构化 HTML 演示与 Slidev Markdown deck
- 可编辑结果页：生成后可继续修改内容、预览演示并回看历史结果
- 导出交付：支持导出 `PPTX` 与 `PDF`
- 分享播放：支持生成公开分享链接，便于外部查看
- 演讲辅助：支持生成 speaker notes，并可基于 TTS 生成讲稿音频

## 适用场景

- 汇报型 PPT：周报、月报、项目复盘、经营分析
- 提案型 PPT：方案介绍、产品发布、客户提案、培训材料
- 内容重组型 PPT：把网页、文档、笔记等素材整理成可讲述的演示结构

## 系统架构

```text
frontend (Next.js 16 / React 19)
  -> 会话创建、素材管理、规划确认、编辑预览、导出分享
  -> backend API (FastAPI)
       -> 素材解析与工作区管理
       -> 生成任务 / SSE 事件流
       -> HTML / Slidev 演示产出
       -> PPTX / PDF 导出
       -> speaker notes / TTS 音频
```

后端以 `/api/v1` 提供核心能力，前端通过 `NEXT_PUBLIC_API_URL` 与其通信。本地开发默认地址：

- 前端：[http://localhost:3000](http://localhost:3000)
- 后端：[http://localhost:8000](http://localhost:8000)
- 健康检查：[http://localhost:8000/health](http://localhost:8000/health)

## 快速开始

### 1. 准备依赖

- Python `3.12` 或 `3.13`
- Node.js
- `pnpm >= 10`
- `uv`

### 2. 配置环境变量

```bash
cp .env.example .env
```

至少需要配置一组可用的大模型 API Key。若需要生成演讲者录音，再额外配置 TTS 相关参数。

常用配置项：

- 模型选择：`DEFAULT_MODEL`、`STRONG_MODEL`、`VISION_MODEL`、`FAST_MODEL`
- LLM Key：`OPENAI_API_KEY`、`ANTHROPIC_API_KEY`、`GOOGLE_API_KEY`、`DEEPSEEK_API_KEY`、`OPENROUTER_API_KEY`
- TTS：`TTS_PROVIDER`、`TTS_API_KEY`、`TTS_BASE_URL`、`TTS_MODEL`、`TTS_VOICE_ID`
- 前端后端联调：`NEXT_PUBLIC_API_URL`

示例中的默认模型配置使用 OpenAI；如果你切换到其他 provider，请同步调整模型标识格式。

### 3. 启动后端

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

### 4. 启动前端

```bash
cd frontend
pnpm install
pnpm dev
```

浏览器访问 [http://localhost:3000](http://localhost:3000) 即可开始使用。

## 推荐使用流程

1. 在首页创建一个新会话
2. 为当前会话添加素材：文件、链接或文本
3. 在创建页确认大纲与生成方向
4. 启动生成任务，等待演示内容产出
5. 在编辑页继续调整内容与结构
6. 按需导出 `PPTX` / `PDF` 或生成分享链接

## 环境变量说明

根目录的 [`.env.example`](./.env.example) 提供了完整模板。这里列出最关键的几项：

| 变量 | 作用 |
| --- | --- |
| `OPENAI_API_KEY` 等 | 配置大模型 provider 凭证 |
| `DEFAULT_MODEL` | 默认生成模型 |
| `STRONG_MODEL` | 更强生成模型，适合复杂任务 |
| `VISION_MODEL` | 视觉相关任务使用的模型 |
| `NEXT_PUBLIC_API_URL` | 前端访问后端 API 的基础地址 |
| `TTS_API_KEY` | speaker notes 转语音所需凭证 |

如果没有配置 TTS，核心生成流程仍可正常使用，但“录音生成”能力会不可用。

## 常用开发命令

### 后端

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000
uv run pytest
```

### 前端

```bash
cd frontend
pnpm install
pnpm dev
pnpm build
pnpm test
pnpm lint
```

## 项目结构

```text
ZhiYan/
├─ backend/                # FastAPI 服务、生成编排、导出逻辑
│  ├─ app/api/v1/          # API 路由
│  ├─ app/services/        # 生成、导出、Slidev、speaker notes 等核心服务
│  ├─ app/models/          # 领域模型
│  └─ tests/               # 后端测试
├─ frontend/               # Next.js 应用
│  ├─ src/app/             # 页面入口
│  ├─ src/components/      # UI 组件与编辑器视图
│  ├─ src/lib/             # API 封装、状态管理、导出逻辑
│  └─ scripts/             # 前端辅助脚本
├─ data/                   # 工作区数据、生成结果、临时产物
├─ docs/                   # 架构决策、布局设计与工程文档
├─ shared/                 # 前后端共享资源
└─ .env.example            # 环境变量模板
```

## 技术栈

- 前端：Next.js 16、React 19、TypeScript、Zustand、TanStack Query
- 后端：FastAPI、Pydantic、PydanticAI、LiteLLM、Uvicorn
- 生成与导出：Slidev、python-pptx、Playwright

## 开发说明

- 前后端默认分开启动，本地通过 `NEXT_PUBLIC_API_URL` 联调
- 前端在 `dev`、`build`、`test`、`lint` 前会自动同步布局元数据
- 后端启动时会初始化会话存储，并定期清理过期上传文件
- `data/` 目录会承载本地运行产生的部分状态与产物，开发时建议保留

## 常见问题

### 1. 启动后前端无法请求后端

确认 `.env` 中的 `NEXT_PUBLIC_API_URL` 指向实际后端地址，并检查后端是否已监听 `8000` 端口。

### 2. 可以只配置一个模型 provider 吗？

可以。只要至少有一组可用的模型配置，核心生成流程即可运行。

### 3. 为什么录音功能不可用？

通常是 `TTS_API_KEY` 未配置，或 `TTS_PROVIDER` / `TTS_BASE_URL` 与当前服务不匹配。

## 文档与补充资料

- 根环境变量模板：[`.env.example`](./.env.example)
- 前端工程入口：[`frontend/package.json`](./frontend/package.json)
- 后端工程入口：[`backend/pyproject.toml`](./backend/pyproject.toml)
- 补充设计文档：[`docs/`](./docs)

## License

如需开源或商用说明，请在此处补充正式 License 信息。
