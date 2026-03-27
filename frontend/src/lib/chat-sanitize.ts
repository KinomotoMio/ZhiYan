const THINK_BLOCK_RE = /<think\b[^>]*>[\s\S]*?<\/think>/gi;
const THINK_LINE_RE = /^\s*<\/?think\b[^>]*>\s*$/gim;
const THINK_INLINE_RE = /<\/?think\b[^>]*>/gi;

export function sanitizeAssistantText(content: string): string {
  return String(content || "")
    .replace(THINK_BLOCK_RE, "")
    .replace(THINK_LINE_RE, "")
    .replace(THINK_INLINE_RE, "")
    .replace(/<thinking>/gi, "")
    .replace(/<\/thinking>/gi, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}
