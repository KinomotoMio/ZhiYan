const DEFAULT_LOADING_TITLE = "生成中...";
const MAX_LOADING_TITLE_CHARS = 18;

function stripSourceExtension(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) return "";
  return trimmed.replace(/\.[^/.]+$/, "").trim();
}

function stripPromptBoilerplate(text: string): string {
  return text
    .trim()
    .replace(/^[\"'“”‘’【】\[\]()]+|[\"'“”‘’【】\[\]()]+$/g, "")
    .replace(
      /^(?:请(?:帮我)?|帮我|麻烦|需要|想要|我要|我想|请你|请为我|为我|给我)?(?:基于以下内容|根据以下内容|围绕以下内容|结合以下内容)?(?:设计|准备|创建|生成|制作|输出|整理|撰写|写|做)(?:一份|一个|一套|一页|一组|一版|份|个|套)?/i,
      ""
    )
    .replace(
      /(?:的)?(?:演示文稿|演示稿|幻灯片|PPTX?|pptx?|汇报稿|汇报|分享稿|分享|报告|培训材料|方案)(?:初稿|草稿|大纲|内容)?$/i,
      ""
    )
    .replace(/(?:\d+\s*(?:页|slides?|pages?)\s*)+$/i, "")
    .trim()
    .replace(/的+$/g, "")
    .trim()
    .replace(/^[：:，,。；;、]+|[：:，,。；;、]+$/g, "");
}

export function compactLoadingTitle(
  input: string | null | undefined,
  fallback = DEFAULT_LOADING_TITLE
): string {
  const normalized = String(input ?? "")
    .replace(/\s+/g, " ")
    .trim();
  if (!normalized) return fallback;

  const firstLine =
    normalized
      .split(/\r?\n/)
      .map((part) => part.trim())
      .find(Boolean) ?? "";

  let candidate = firstLine || normalized;
  if (candidate.includes("关于")) {
    candidate = candidate.split("关于").pop() ?? candidate;
  } else if (candidate.includes("围绕")) {
    candidate = candidate.split("围绕").pop() ?? candidate;
  } else if (candidate.includes("聚焦")) {
    candidate = candidate.split("聚焦").pop() ?? candidate;
  } else if (/主题\s*[:：是为]/.test(candidate)) {
    candidate = candidate.split(/主题\s*[:：是为]/).pop() ?? candidate;
  }

  candidate = candidate.split(/[。！？!?；;，,\n]/, 1)[0]?.trim() ?? candidate;
  candidate = stripPromptBoilerplate(candidate);
  if (!candidate) {
    candidate = stripPromptBoilerplate(firstLine || normalized);
  }
  if (!candidate) return fallback;

  if (candidate.length <= MAX_LOADING_TITLE_CHARS) {
    return candidate;
  }
  return `${candidate.slice(0, MAX_LOADING_TITLE_CHARS).trimEnd()}...`;
}

export function buildLoadingTitle(input: {
  topic?: string | null;
  sourceNames?: string[] | null;
  fallback?: string;
}): string {
  const fallback = input.fallback ?? DEFAULT_LOADING_TITLE;
  const topicTitle = compactLoadingTitle(input.topic, "");
  if (topicTitle) return topicTitle;

  const sourceNames = (input.sourceNames ?? [])
    .map((name) => stripSourceExtension(String(name ?? "")))
    .filter(Boolean);
  if (sourceNames.length === 1) {
    return compactLoadingTitle(sourceNames[0], fallback);
  }
  if (sourceNames.length > 1) {
    return `基于${sourceNames.length}个来源生成`;
  }
  return fallback;
}

export function resolveGenerationRequestTitle(
  request:
    | {
        title?: string | null;
        topic?: string | null;
      }
    | null
    | undefined,
  fallback = DEFAULT_LOADING_TITLE
): string {
  const topicTitle = compactLoadingTitle(request?.topic, "");
  if (topicTitle) return topicTitle;
  return compactLoadingTitle(request?.title, fallback);
}

export { DEFAULT_LOADING_TITLE };
