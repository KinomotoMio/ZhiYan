"""文档 3 层模型 — 结构化存储上传文档的多层信息

Layer 1: 身份（~100 tokens，始终加载）— id, title, source_type, metadata
Layer 2: 摘要（~200-500 tokens，规划阶段加载）— description, key_topics, structure_outline
Layer 3: 原始内容（已自动规范化）— raw_content
"""

from pydantic import BaseModel, Field


class DocumentMeta(BaseModel):
    """AI 生成的文档元数据（Layer 1+2，由 document_meta_generator Agent 填充）"""

    title: str = Field(description="文档的有意义标题（非文件名乱码）")
    description: str = Field(description="100 字以内的内容摘要")
    key_topics: list[str] = Field(description="3-5 个核心话题标签")
    structure_outline: str = Field(
        default="",
        description="文档结构大纲（标题层级摘要）",
    )


class DocumentLayer(BaseModel):
    """文档 3 层完整模型"""

    # Layer 1: 身份
    id: str
    title: str = Field(description="AI 生成的有意义标题")
    source_type: str = Field(description="pdf/docx/pptx/url/text")
    file_name: str = Field(description="原始文件名")
    metadata: dict = Field(
        default_factory=dict,
        description="size, page_count, language, upload_time, estimated_tokens",
    )

    # Layer 2: 摘要
    description: str = Field(default="", description="AI 生成的内容摘要")
    key_topics: list[str] = Field(default_factory=list, description="核心话题标签")
    structure_outline: str = Field(default="", description="文档结构大纲")

    # Layer 3: 原始内容（已自动规范化）
    raw_content: str = Field(default="", description="MarkItDown 输出 + 正则规范化")

    def get_layer12_summary(self) -> str:
        """获取 Layer 1+2 的文本摘要，供 Outline Agent 使用"""
        topics = ", ".join(self.key_topics) if self.key_topics else "未分类"
        return (
            f"[{self.id}] {self.title}\n"
            f"类型: {self.source_type} | 文件: {self.file_name}\n"
            f"摘要: {self.description}\n"
            f"话题: {topics}\n"
            f"结构: {self.structure_outline}"
        )

    def get_content(self) -> str:
        """获取内容"""
        return self.raw_content
