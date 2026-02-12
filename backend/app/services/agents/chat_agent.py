"""Chat Agent — 对话 + Skill 触发"""

_agent = None


def get_chat_agent():
    """延迟创建 Agent"""
    global _agent
    if _agent is None:
        from pydantic_ai import Agent

        _agent = Agent(
            model="openai:gpt-4o-mini",
            instructions=(
                "你是知演（ZhiYan）的 AI 助手，帮助用户优化和调整演示文稿。\n"
                "你可以：\n"
                "- 回答关于演示文稿内容的问题\n"
                "- 根据用户指令修改特定幻灯片\n"
                "- 当用户使用 /command 触发 Skill 时，协调执行\n\n"
                "回复使用中文，专业术语保留英文。保持简洁友好。"
            ),
        )
    return _agent


def __getattr__(name):
    if name == "chat_agent":
        return get_chat_agent()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
