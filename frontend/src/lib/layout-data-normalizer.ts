export interface LayoutNormalizeResult {
  data: Record<string, unknown>;
  recoverable: boolean;
  changed: boolean;
  reason: string | null;
}

const DEFAULT_LEFT_HEADING = "要点 A";
const DEFAULT_RIGHT_HEADING = "要点 B";
const DEFAULT_FILLER = "内容生成中";
const OUTLINE_FALLBACK_TITLES = ["背景", "分析", "方案", "结论", "实施", "总结"] as const;
const BULLET_PLACEHOLDER_TITLE = "内容暂未就绪";
const BULLET_PLACEHOLDER_MESSAGE = "该页正在生成或已回退，可稍后重试。";

type RecordLike = Record<string, unknown>;

function isRecordLike(value: unknown): value is RecordLike {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function asText(value: unknown, fallback = ""): string {
  if (typeof value === "string") {
    const text = value.trim();
    if (text) return text;
  }
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return fallback;
}

function extractTextItemsFromText(rawText: string): string[] {
  const lines = rawText
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  if (lines.length === 0) return [];

  const items: string[] = [];
  for (const line of lines) {
    if (line.startsWith("|")) {
      const cells = line
        .replace(/^\|/, "")
        .replace(/\|$/, "")
        .split("|")
        .map((cell) => cleanMarkdownText(cell));
      for (const cell of cells) {
        if (shouldKeepCell(cell)) {
          items.push(cell);
        }
      }
      continue;
    }

    const cleaned = cleanMarkdownText(line);
    if (shouldKeepCell(cleaned)) {
      items.push(cleaned);
    }
  }

  return Array.from(new Set(items));
}

function cleanMarkdownText(raw: string): string {
  return raw
    .replace(/^\s*[-*•+]\s*/, "")
    .replace(/^\s*\d+[.)]\s*/, "")
    .replace(/^\|+|\|+$/g, "")
    .replace(/\*\*/g, "")
    .replace(/__/g, "")
    .replace(/`/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function shouldKeepCell(text: string): boolean {
  if (!text) return false;
  if (/^[-:]+$/.test(text)) return false;
  if (text === "栏目" || text === "新增内容") return false;
  return true;
}

function normalizeIcon(value: unknown): RecordLike | null {
  if (isRecordLike(value)) {
    const query = asText(value.query);
    if (query) return { query };
  }
  if (typeof value === "string" && value.trim()) return { query: value.trim() };
  return null;
}

function isPlaceholderText(text: string): boolean {
  return ["内容生成中", "待补充", "自动回退生成"].includes(text.trim());
}

function normalizeStatus(raw: unknown): RecordLike | null {
  if (!isRecordLike(raw)) return null;
  const title = asText(raw.title, BULLET_PLACEHOLDER_TITLE);
  const message = asText(raw.message, BULLET_PLACEHOLDER_MESSAGE);
  return { title, message };
}

function normalizeBulletWithIcons(data: RecordLike): LayoutNormalizeResult {
  const title = asText(data.title, "要点概览");
  const rawItems = Array.isArray(data.items) ? data.items : [];
  const items: RecordLike[] = [];

  for (const rawItem of rawItems) {
    if (!isRecordLike(rawItem)) continue;
    const itemTitle = asText(rawItem.title);
    const itemDescription = asText(rawItem.description);
    const text = itemTitle || itemDescription;

    if (!text) continue;

    const repeatedPlaceholder =
      itemTitle &&
      itemDescription &&
      itemTitle === itemDescription &&
      isPlaceholderText(itemTitle);
    if (repeatedPlaceholder) {
      continue;
    }

    const icon = normalizeIcon(rawItem.icon) ?? { query: "star" };
    items.push({
      icon,
      title: itemTitle || text.slice(0, 25),
      description: itemDescription || text,
    });
  }

  const explicitStatus = normalizeStatus(data.status);
  const inferredStatus =
    items.length === 0
      ? {
          title: BULLET_PLACEHOLDER_TITLE,
          message: BULLET_PLACEHOLDER_MESSAGE,
        }
      : null;

  const repaired: RecordLike = {
    title,
    items,
  };
  const status = explicitStatus ?? inferredStatus;
  if (status) {
    repaired.status = status;
  }

  const changed = JSON.stringify(repaired) !== JSON.stringify(data);
  return {
    data: repaired,
    recoverable: true,
    changed,
    reason: changed ? "normalize bullet-with-icons fallback state" : null,
  };
}

function extractTextItems(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  const items: string[] = [];
  for (const item of value) {
    if (typeof item === "string") {
      items.push(...extractTextItemsFromText(item));
      continue;
    }
    if (!isRecordLike(item)) continue;
    let text =
      asText(item.text) ||
      asText(item.title) ||
      asText(item.label) ||
      asText(item.description);
    if (!text) {
      const challenge = asText(item.challenge);
      const outcome = asText(item.outcome);
      text = challenge && outcome ? `${challenge} / ${outcome}` : challenge || outcome;
    }
    if (text) items.push(text);
  }
  return items;
}

function splitTwoColumns(items: string[]): [string[], string[]] {
  const midpoint = Math.max(1, Math.ceil(items.length / 2));
  const left = items.slice(0, midpoint);
  const right = items.slice(midpoint);
  return [
    left.length > 0 ? left : [DEFAULT_FILLER],
    right.length > 0 ? right : [DEFAULT_FILLER],
  ];
}

function normalizeCompareColumn(raw: unknown, fallbackHeading: string): RecordLike | null {
  if (typeof raw === "string" && raw.trim()) {
    const items = extractTextItemsFromText(raw);
    if (items.length === 0) return null;
    return {
      heading: fallbackHeading,
      items,
    };
  }
  if (!isRecordLike(raw)) return null;
  const heading = asText(raw.heading) || asText(raw.title) || fallbackHeading;
  const items = extractTextItems(raw.items);
  const column: RecordLike = {
    heading,
    items: items.length > 0 ? items : [DEFAULT_FILLER],
  };
  const icon = normalizeIcon(raw.icon);
  if (icon) column.icon = icon;
  return column;
}

function normalizeTwoColumnCompare(data: RecordLike): LayoutNormalizeResult {
  const title = asText(data.title, "对比分析");

  let left = normalizeCompareColumn(data.left, DEFAULT_LEFT_HEADING);
  let right = normalizeCompareColumn(data.right, DEFAULT_RIGHT_HEADING);
  if (!left && !right) {
    left = normalizeCompareColumn(data.challenge, DEFAULT_LEFT_HEADING);
    right = normalizeCompareColumn(data.outcome, DEFAULT_RIGHT_HEADING);
  }

  if (!left && !right) {
    const items = extractTextItems(data.items);
    if (items.length === 0) {
      return { data, recoverable: false, changed: false, reason: "missing two-column data" };
    }
    const [leftItems, rightItems] = splitTwoColumns(items);
    const repaired: RecordLike = {
      title,
      left: { heading: DEFAULT_LEFT_HEADING, items: leftItems },
      right: { heading: DEFAULT_RIGHT_HEADING, items: rightItems },
    };
    return { data: repaired, recoverable: true, changed: true, reason: "repair from items" };
  }

  const repaired: RecordLike = {
    title,
    left: left ?? { heading: DEFAULT_LEFT_HEADING, items: [DEFAULT_FILLER] },
    right: right ?? { heading: DEFAULT_RIGHT_HEADING, items: [DEFAULT_FILLER] },
  };
  const changed = JSON.stringify(repaired) !== JSON.stringify(data);
  return { data: repaired, recoverable: true, changed, reason: changed ? "normalize compare shape" : null };
}

function normalizeOutlineSection(value: unknown, index: number): RecordLike | null {
  if (typeof value === "string") {
    const title = asText(value);
    if (!title) return null;
    return { title };
  }

  if (!isRecordLike(value)) return null;

  const title =
    asText(value.title) ||
    asText(value.text) ||
    asText(value.label) ||
    asText(value.heading) ||
    asText(value.name);
  const description = asText(value.description) || asText(value.summary) || asText(value.detail);

  if (!title && !description) return null;

  const section: RecordLike = {
    title: title || OUTLINE_FALLBACK_TITLES[index] || `章节 ${index + 1}`,
  };
  if (description) {
    section.description = description;
  }
  return section;
}

function normalizeOutlineSlide(data: RecordLike): LayoutNormalizeResult {
  const title = asText(data.title, "目录");
  const subtitle = asText(data.subtitle);
  const sourceSections = Array.isArray(data.sections)
    ? data.sections
    : Array.isArray(data.items)
      ? data.items
      : [];

  const sections: RecordLike[] = [];
  for (const [index, section] of sourceSections.entries()) {
    const normalized = normalizeOutlineSection(section, index);
    if (normalized) {
      sections.push(normalized);
    }
  }

  const repairedSections = sections.slice(0, 6);
  while (repairedSections.length < 4) {
    const index = repairedSections.length;
    repairedSections.push({ title: OUTLINE_FALLBACK_TITLES[index] || `章节 ${index + 1}` });
  }

  const repaired: RecordLike = {
    title,
    sections: repairedSections,
  };
  if (subtitle) {
    repaired.subtitle = subtitle;
  }

  const changed = JSON.stringify(repaired) !== JSON.stringify(data);
  return {
    data: repaired,
    recoverable: true,
    changed,
    reason: changed ? "normalize outline shape" : null,
  };
}

function normalizeTableInfo(data: RecordLike): LayoutNormalizeResult {
  const headers = extractTextItems(data.headers).length > 0
    ? extractTextItems(data.headers)
    : extractTextItems(data.columns);

  const rowsRaw = data.rows;
  const rows: string[][] = [];
  if (Array.isArray(rowsRaw)) {
    for (const row of rowsRaw) {
      if (Array.isArray(row)) {
        rows.push(row.map((cell) => asText(cell)));
      } else if (isRecordLike(row)) {
        const currentHeaders = headers.length > 0
          ? headers
          : Object.keys(row).map((key) => asText(key)).filter(Boolean);
        if (currentHeaders.length > 0) {
          rows.push(currentHeaders.map((header) => asText(row[header])));
        }
      }
    }
  }

  const resolvedHeaders = headers.length > 0
    ? headers
    : (rows[0] ? rows[0].map((_, i) => `列 ${i + 1}`) : []);
  if (resolvedHeaders.length === 0 || rows.length === 0) {
    return { data, recoverable: false, changed: false, reason: "invalid table shape" };
  }

  const normalizedRows = rows.map((row) => {
    if (row.length < resolvedHeaders.length) {
      return [...row, ...Array.from({ length: resolvedHeaders.length - row.length }, () => "")];
    }
    return row.slice(0, resolvedHeaders.length);
  });

  const repaired: RecordLike = {
    title: asText(data.title, "信息表"),
    headers: resolvedHeaders,
    rows: normalizedRows,
  };
  const caption = asText(data.caption);
  if (caption) repaired.caption = caption;
  const changed = JSON.stringify(repaired) !== JSON.stringify(data);
  return { data: repaired, recoverable: true, changed, reason: changed ? "normalize table shape" : null };
}

function extractSideItems(side: unknown): string[] {
  if (!isRecordLike(side)) return [];
  return extractTextItems(side.items);
}

function normalizeChallengeOutcome(data: RecordLike): LayoutNormalizeResult {
  const pairs: Array<{ challenge: string; outcome: string }> = [];
  const rawItems = data.items;
  if (Array.isArray(rawItems)) {
    for (const row of rawItems) {
      if (isRecordLike(row)) {
        const challenge = asText(row.challenge);
        const outcome = asText(row.outcome);
        if (challenge || outcome) {
          pairs.push({
            challenge: challenge || DEFAULT_FILLER,
            outcome: outcome || "待补充",
          });
        }
      } else if (typeof row === "string" && row.trim()) {
        pairs.push({ challenge: row.trim(), outcome: "待补充" });
      }
    }
  }

  if (pairs.length === 0) {
    const challenges = extractSideItems(data.challenge);
    const outcomes = extractSideItems(data.outcome);
    const count = Math.max(challenges.length, outcomes.length);
    for (let i = 0; i < count; i += 1) {
      pairs.push({
        challenge: challenges[i] || DEFAULT_FILLER,
        outcome: outcomes[i] || "待补充",
      });
    }
  }

  if (pairs.length === 0) {
    return { data, recoverable: false, changed: false, reason: "invalid challenge-outcome shape" };
  }

  const repaired: RecordLike = {
    title: asText(data.title, "问题与方案"),
    items: pairs,
  };
  const changed = JSON.stringify(repaired) !== JSON.stringify(data);
  return { data: repaired, recoverable: true, changed, reason: changed ? "normalize challenge shape" : null };
}

function normalizeIntroSlide(data: RecordLike): LayoutNormalizeResult {
  const repaired: RecordLike = {
    title: asText(data.title, "未命名演示"),
  };
  const subtitle = asText(data.subtitle);
  if (subtitle) repaired.subtitle = subtitle;
  const author = asText(data.author) || asText(data.presenter);
  if (author) repaired.author = author;
  const date = asText(data.date);
  if (date) repaired.date = date;

  const changed = JSON.stringify(repaired) !== JSON.stringify(data);
  return { data: repaired, recoverable: true, changed, reason: changed ? "normalize intro shape" : null };
}

function normalizeQuoteSlide(data: RecordLike): LayoutNormalizeResult {
  const quote = asText(data.quote) || asText(data.title);
  if (!quote) {
    return { data, recoverable: false, changed: false, reason: "missing quote text" };
  }

  const repaired: RecordLike = { quote };
  const author = asText(data.author) || asText(data.attribution);
  if (author) repaired.author = author;
  const context = asText(data.context);
  if (context) repaired.context = context;

  const changed = JSON.stringify(repaired) !== JSON.stringify(data);
  return { data: repaired, recoverable: true, changed, reason: changed ? "normalize quote shape" : null };
}

function normalizeThankYou(data: RecordLike): LayoutNormalizeResult {
  const repaired: RecordLike = {
    title: asText(data.title, "谢谢"),
  };
  const subtitle = asText(data.subtitle);
  if (subtitle) repaired.subtitle = subtitle;
  const contact = asText(data.contact) || asText(data.contact_info);
  if (contact) repaired.contact = contact;

  const changed = JSON.stringify(repaired) !== JSON.stringify(data);
  return { data: repaired, recoverable: true, changed, reason: changed ? "normalize thank-you shape" : null };
}

export function normalizeLayoutData(layoutId: string, data: Record<string, unknown>): LayoutNormalizeResult {
  if (layoutId === "intro-slide") {
    return normalizeIntroSlide(data);
  }
  if (layoutId === "bullet-with-icons") {
    return normalizeBulletWithIcons(data);
  }
  if (layoutId === "outline-slide") {
    return normalizeOutlineSlide(data);
  }
  if (layoutId === "quote-slide") {
    return normalizeQuoteSlide(data);
  }
  if (layoutId === "thank-you") {
    return normalizeThankYou(data);
  }
  if (layoutId === "two-column-compare") {
    return normalizeTwoColumnCompare(data);
  }
  if (layoutId === "table-info") {
    return normalizeTableInfo(data);
  }
  if (layoutId === "challenge-outcome") {
    return normalizeChallengeOutcome(data);
  }
  return { data, recoverable: true, changed: false, reason: null };
}
