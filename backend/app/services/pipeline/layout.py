"""布局模板 — 预定义各 LayoutType 的组件位置

LLM 只负责内容决策，坐标/样式由此模块确定性映射。
"""

from app.models.slide import (
    Component,
    ComponentRole,
    ComponentType,
    LayoutType,
    Position,
    Slide,
    Style,
)

# 各 layout 的预定义插槽位置
LAYOUT_SLOTS: dict[str, dict[str, dict]] = {
    "title-slide": {
        "title": {
            "position": Position(x=10, y=28, width=80, height=15),
            "style": Style(fontSize=36, fontWeight="bold", textAlign="center"),
            "role": ComponentRole.TITLE,
        },
        "subtitle": {
            "position": Position(x=20, y=52, width=60, height=8),
            "style": Style(fontSize=18, color="#666666", textAlign="center"),
            "role": ComponentRole.SUBTITLE,
        },
    },
    "title-content": {
        "title": {
            "position": Position(x=5, y=3, width=90, height=10),
            "style": Style(fontSize=28, fontWeight="bold"),
            "role": ComponentRole.TITLE,
        },
        "body": {
            "position": Position(x=5, y=18, width=90, height=72),
            "style": Style(fontSize=18),
            "role": ComponentRole.BODY,
        },
    },
    "title-content-image": {
        "title": {
            "position": Position(x=5, y=3, width=90, height=10),
            "style": Style(fontSize=28, fontWeight="bold"),
            "role": ComponentRole.TITLE,
        },
        "body": {
            "position": Position(x=5, y=18, width=50, height=72),
            "style": Style(fontSize=18),
            "role": ComponentRole.BODY,
        },
        "image": {
            "position": Position(x=58, y=18, width=37, height=72),
            "style": Style(),
            "role": ComponentRole.ILLUSTRATION,
        },
    },
    "two-column": {
        "title": {
            "position": Position(x=5, y=3, width=90, height=10),
            "style": Style(fontSize=28, fontWeight="bold"),
            "role": ComponentRole.TITLE,
        },
        "body": {
            "position": Position(x=5, y=18, width=43, height=72),
            "style": Style(fontSize=16),
            "role": ComponentRole.BODY,
        },
        "body_right": {
            "position": Position(x=52, y=18, width=43, height=72),
            "style": Style(fontSize=16),
            "role": ComponentRole.BODY,
        },
    },
    "section-header": {
        "title": {
            "position": Position(x=10, y=32, width=80, height=15),
            "style": Style(fontSize=36, fontWeight="bold", textAlign="center"),
            "role": ComponentRole.TITLE,
        },
        "subtitle": {
            "position": Position(x=15, y=55, width=70, height=10),
            "style": Style(fontSize=18, color="#666666", textAlign="center"),
            "role": ComponentRole.SUBTITLE,
        },
    },
    "image-full": {
        "image": {
            "position": Position(x=0, y=0, width=100, height=85),
            "style": Style(),
            "role": ComponentRole.ILLUSTRATION,
        },
        "caption": {
            "position": Position(x=5, y=87, width=90, height=10),
            "style": Style(fontSize=14, color="#999999", textAlign="center"),
            "role": ComponentRole.CAPTION,
        },
    },
    "blank": {
        "body": {
            "position": Position(x=5, y=5, width=90, height=90),
            "style": Style(fontSize=18),
            "role": ComponentRole.BODY,
        },
    },
}


def build_slide_from_content(
    slide_number: int,
    title: str,
    layout_type: str,
    body_text: str | None = None,
    speaker_notes: str | None = None,
    needs_image: bool = False,
    image_description: str | None = None,
) -> Slide:
    """将 LLM 内容决策转换为带完整坐标的 Slide 对象"""

    layout_key = layout_type if layout_type in LAYOUT_SLOTS else "title-content"
    slots = LAYOUT_SLOTS[layout_key]
    components: list[Component] = []
    comp_idx = 0

    # 标题组件
    if "title" in slots:
        slot = slots["title"]
        comp_idx += 1
        components.append(
            Component(
                id=f"comp-{slide_number}-{comp_idx}",
                type=ComponentType.TEXT,
                role=slot["role"],
                content=title,
                position=slot["position"],
                style=slot["style"],
            )
        )

    # 正文组件
    if "body" in slots and body_text:
        slot = slots["body"]
        comp_idx += 1
        components.append(
            Component(
                id=f"comp-{slide_number}-{comp_idx}",
                type=ComponentType.TEXT,
                role=slot["role"],
                content=body_text,
                position=slot["position"],
                style=slot["style"],
            )
        )

    # 副标题（用于 title-slide 和 section-header）
    if "subtitle" in slots:
        slot = slots["subtitle"]
        subtitle_content = None
        if layout_key == "title-slide":
            subtitle_content = "由知演 AI 智能生成"
        elif layout_key == "section-header" and body_text:
            subtitle_content = body_text
        if subtitle_content:
            comp_idx += 1
            components.append(
                Component(
                    id=f"comp-{slide_number}-{comp_idx}",
                    type=ComponentType.TEXT,
                    role=slot["role"],
                    content=subtitle_content,
                    position=slot["position"],
                    style=slot["style"],
                )
            )

    # 图片占位组件
    if needs_image and "image" in slots:
        slot = slots["image"]
        comp_idx += 1
        components.append(
            Component(
                id=f"comp-{slide_number}-{comp_idx}",
                type=ComponentType.IMAGE,
                role=slot["role"],
                content=image_description or "配图占位",
                position=slot["position"],
                style=slot["style"],
            )
        )

    # two-column 右侧列
    if "body_right" in slots and body_text:
        # 如果 body_text 包含分隔符则拆分左右
        parts = body_text.split("\n---\n", 1)
        if len(parts) == 2:
            # 更新左侧内容
            for comp in components:
                if comp.role == ComponentRole.BODY:
                    comp.content = parts[0].strip()
                    break
            slot = slots["body_right"]
            comp_idx += 1
            components.append(
                Component(
                    id=f"comp-{slide_number}-{comp_idx}",
                    type=ComponentType.TEXT,
                    role=slot["role"],
                    content=parts[1].strip(),
                    position=slot["position"],
                    style=slot["style"],
                )
            )

    return Slide(
        slideId=f"slide-{slide_number}",
        layoutType=layout_key,
        components=components,
        speakerNotes=speaker_notes,
    )
