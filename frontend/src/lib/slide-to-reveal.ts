/**
 * Deterministic transform: Slide JSON -> reveal.js HTML.
 * Converts structured slide data into reveal.js-compatible section HTML.
 * Supports both layoutId/contentData payloads and legacy component payloads.
 */
import { getLayoutIconNode } from "@/lib/layout-icons";
import { getImagePlaceholderCopy } from "@/lib/image-source";
import {
  getBulletIconsOnlyLayoutTokens,
  getBulletWithIconsCardsLayoutTokens,
  getBulletWithIconsLayoutTokens,
} from "@/lib/icon-card-layout-tokens";
import { normalizeLayoutData } from "@/lib/layout-data-normalizer";
import { normalizeSlideSceneBackground } from "@/lib/scene-background";
import {
  getSceneBackgroundRenderModel,
  styleMapToCss,
} from "@/lib/scene-background-renderer";
import {
  CONTENT_GENERATING,
  PENDING_SUPPLEMENT,
  STATUS_MESSAGE,
  STATUS_TITLE,
  areAllFallbackPlaceholders,
  canonicalizeFallbackText,
  getBulletFallbackStatus,
} from "@/lib/fallback-semantics";
import type { Component, Presentation, Slide, Style } from "@/types/slide";

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;");
}

function escapeAttribute(str: string): string {
  return escapeHtml(str).replace(/'/g, "&#39;");
}

function attributesToHtml(attributes: Record<string, string>): string {
  return Object.entries(attributes)
    .map(([key, value]) => `${key}="${escapeAttribute(value)}"`)
    .join(" ");
}

function normalizeFiniteNumber(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function sanitizeCssColor(value: unknown, fallback = ""): string {
  if (typeof value !== "string") return fallback;
  const color = value.trim();
  if (!color) return fallback;

  const hex = /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/;
  const rgb = /^rgba?\((?:\s*\d{1,3}%?\s*,){2}\s*\d{1,3}%?(?:\s*,\s*(?:0|1|0?\.\d+))?\s*\)$/;
  const hsl = /^hsla?\(\s*\d{1,3}(?:deg|rad|turn)?\s*,\s*\d{1,3}%\s*,\s*\d{1,3}%(?:\s*,\s*(?:0|1|0?\.\d+))?\s*\)$/;

  if (hex.test(color) || rgb.test(color) || hsl.test(color)) {
    return color;
  }

  return fallback;
}

function sanitizeImageSrc(value: unknown): string {
  if (typeof value !== "string") return "";
  const src = value.trim();
  if (!src) return "";

  if (src.startsWith("/") || src.startsWith("./") || src.startsWith("../") || src.startsWith("blob:")) {
    return src;
  }

  if (/^https?:\/\//i.test(src)) return src;
  if (/^data:image\//i.test(src)) return src;
  return "";
}

function sanitizeFontWeight(value: unknown): string {
  if (typeof value !== "string") return "";
  const fontWeight = value.trim();
  return /^(?:normal|bold|bolder|lighter|[1-9]00)$/.test(fontWeight)
    ? fontWeight
    : "";
}

function sanitizeFontStyle(value: unknown): string {
  if (typeof value !== "string") return "";
  const fontStyle = value.trim();
  return /^(?:normal|italic|oblique)$/.test(fontStyle) ? fontStyle : "";
}

function renderBulletStatusPanel(
  title: string,
  status: { title: string; message: string },
): string {
  return `
    <div style="display:flex;flex-direction:column;height:100%;padding:56px 64px;">
      <h2 style="font-size:36px;font-weight:700;line-height:1.3;color:var(--background-text,#111827);margin:0 0 40px;">${escapeHtml(title)}</h2>
      <div style="display:flex;flex:1;align-items:center;justify-content:center;">
        <div style="max-width:720px;border:1px solid #fde68a;border-radius:24px;background:#fffbeb;padding:36px 40px;text-align:center;box-shadow:0 10px 30px rgba(15,23,42,0.06);">
          <div style="margin:0 auto 16px;width:56px;height:56px;border-radius:18px;background:#fef3c7;color:#d97706;display:flex;align-items:center;justify-content:center;font-size:28px;font-weight:700;">!</div>
          <h3 style="font-size:24px;font-weight:700;line-height:1.3;color:var(--background-text,#111827);margin:0;">${escapeHtml(status.title)}</h3>
          <p style="font-size:17px;line-height:1.6;color:${backgroundTextMix(70)};margin:12px 0 0;">${escapeHtml(status.message)}</p>
        </div>
      </div>
    </div>`;
}

function styleToCSS(style?: Style): string {
  if (!style) return "";
  const parts: string[] = [];

  const fontSize = normalizeFiniteNumber(style.fontSize, Number.NaN);
  if (Number.isFinite(fontSize)) parts.push(`font-size: ${fontSize}px`);

  const fontWeight = sanitizeFontWeight(style.fontWeight);
  if (fontWeight) parts.push(`font-weight: ${fontWeight}`);

  const fontStyle = sanitizeFontStyle(style.fontStyle);
  if (fontStyle) parts.push(`font-style: ${fontStyle}`);

  const color = sanitizeCssColor(style.color);
  if (color) parts.push(`color: ${color}`);

  const backgroundColor = sanitizeCssColor(style.backgroundColor);
  if (backgroundColor) parts.push(`background-color: ${backgroundColor}`);

  if (style.textAlign) parts.push(`text-align: ${style.textAlign}`);

  const opacity = normalizeFiniteNumber(style.opacity, Number.NaN);
  if (Number.isFinite(opacity)) parts.push(`opacity: ${opacity}`);

  return parts.join("; ");
}

function componentToHTML(comp: Component): string {
  const posStyle = [
    "position: absolute",
    `left: ${normalizeFiniteNumber(comp.position.x)}%`,
    `top: ${normalizeFiniteNumber(comp.position.y)}%`,
    `width: ${normalizeFiniteNumber(comp.position.width)}%`,
    `height: ${normalizeFiniteNumber(comp.position.height)}%`,
  ].join("; ");

  const contentStyle = styleToCSS(comp.style);
  const fullStyle = `${posStyle}; ${contentStyle}`;

  switch (comp.type) {
    case "text": {
      const tag = comp.role === "title" ? "h2" : "div";
      const content = (comp.content || "")
        .split("\n")
        .map((line) => {
          if (line.startsWith("\u2022 ") || line.startsWith("- ")) {
            return `<li>${escapeHtml(line.slice(2))}</li>`;
          }
          return `<p>${escapeHtml(line)}</p>`;
        })
        .join("\n");

      const hasListItems = content.includes("<li>");
      const wrappedContent = hasListItems ? `<ul>${content}</ul>` : content;
      return `<${tag} style="${escapeAttribute(fullStyle)}">${wrappedContent}</${tag}>`;
    }
    case "image":
      return `<img src="${escapeAttribute(sanitizeImageSrc(comp.content || ""))}" alt="${escapeAttribute(comp.role)}" style="${escapeAttribute(`${fullStyle}; object-fit: contain;`)}" />`;
    case "chart":
      return `<div style="${escapeAttribute(fullStyle)}" class="chart-placeholder" data-chart="${escapeAttribute(JSON.stringify(comp.chartData || {}))}">[chart]</div>`;
    case "shape":
      return `<div style="${escapeAttribute(fullStyle)}">${escapeHtml(comp.content || "")}</div>`;
    default:
      return "";
  }
}

function asText(value: unknown, fallback = ""): string {
  if (typeof value === "string") {
    const text = value.trim();
    if (text) return text;
  }
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return fallback;
}

function itemText(value: unknown): string {
  if (typeof value === "string") return value.trim();
  if (!value || typeof value !== "object") return "";
  const row = value as Record<string, unknown>;
  return (
    asText(row.text) ||
    asText(row.title) ||
    asText(row.label) ||
    asText(row.challenge) ||
    asText(row.outcome)
  );
}

function itemDescription(value: unknown): string {
  if (!value || typeof value !== "object") return "";
  const row = value as Record<string, unknown>;
  return asText(row.description);
}

function primaryMix(percent: number): string {
  return `color-mix(in srgb, var(--primary-color,#3b82f6) ${percent}%, transparent)`;
}

function backgroundTextMix(percent: number): string {
  return `color-mix(in srgb, var(--background-text,#111827) ${percent}%, transparent)`;
}

function formatEmPadding(top: number, horizontal: number, bottom: number): string {
  return `${top}em ${horizontal}em ${bottom}em`;
}

function renderIconSvg(query: string, size = 24): string {
  const iconNode = getLayoutIconNode(query);
  const children = iconNode
    .map(([tagName, attrs]) => {
      const attrString = Object.entries(attrs)
        .filter(([key]) => key !== "key")
        .map(([key, value]) => `${key}="${escapeAttribute(value)}"`)
        .join(" ");
      return `<${tagName} ${attrString}></${tagName}>`;
    })
    .join("");

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${children}</svg>`;
}

function renderSimpleImagePlaceholder(title: string, detail = "", extraStyle = ""): string {
  return `
    <div style="${extraStyle}background:#f3f4f6;display:flex;flex-direction:column;align-items:center;justify-content:center;color:#9ca3af;overflow:hidden;">
      <div style="opacity:0.5;margin-bottom:8px;line-height:0;">${renderIconSvg("image", 40)}</div>
      <span style="font-size:13px;font-weight:600;opacity:0.8;text-align:center;padding:0 24px;">${escapeHtml(title)}</span>
      ${detail ? `<span style="font-size:12px;opacity:0.7;text-align:center;padding:4px 24px 0;">${escapeHtml(detail)}</span>` : ""}
    </div>`;
}

function renderImageFill(url: string, alt: string, extraStyle = ""): string {
  return `<img src="${escapeAttribute(url)}" alt="${escapeAttribute(alt)}" style="${extraStyle}width:100%;height:100%;object-fit:cover;display:block;" />`;
}

function tableShape(data: Record<string, unknown>): { headers: string[]; rows: string[][] } {
  const headersRaw = Array.isArray(data.headers)
    ? data.headers
    : Array.isArray(data.columns)
      ? data.columns
      : [];
  const headers = headersRaw.map((h) => asText(h)).filter(Boolean);

  const rows: string[][] = [];
  if (Array.isArray(data.rows)) {
    for (const row of data.rows) {
      if (Array.isArray(row)) {
        const cells = row.map((cell) => asText(cell));
        while (cells.length < headers.length) cells.push("");
        rows.push(cells.slice(0, headers.length));
      } else if (row && typeof row === "object") {
        const rec = row as Record<string, unknown>;
        rows.push(headers.map((header) => asText(rec[header])));
      }
    }
  }

  if (headers.length === 0 && Array.isArray(data.rows)) {
    const firstObj = data.rows.find((row) => row && typeof row === "object" && !Array.isArray(row)) as Record<string, unknown> | undefined;
    if (firstObj) {
      headers.push(...Object.keys(firstObj).map((k) => asText(k)).filter(Boolean));
      rows.length = 0;
      for (const row of data.rows) {
        if (row && typeof row === "object" && !Array.isArray(row)) {
          const rec = row as Record<string, unknown>;
          rows.push(headers.map((header) => asText(rec[header])));
        }
      }
    }
  }

  return { headers, rows };
}

function compareColumns(data: Record<string, unknown>) {
  const normalize = (raw: unknown, fallback: string) => {
    const source = raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
    const heading = asText(source.heading) || asText(source.title) || fallback;
    const itemsRaw = Array.isArray(source.items) ? source.items : [];
    const items = itemsRaw.map((item) => itemText(item)).filter(Boolean);
    const iconSource = source.icon && typeof source.icon === "object" ? (source.icon as Record<string, unknown>) : null;
    const iconQuery = iconSource ? asText(iconSource.query) : "";
    return { heading, items, iconQuery };
  };

  let left = normalize(data.left, "Point A");
  let right = normalize(data.right, "Point B");
  if (left.items.length === 0 && right.items.length === 0) {
    left = normalize(data.challenge, "Point A");
    right = normalize(data.outcome, "Point B");
  }

  const canonicalizeColumns = areAllFallbackPlaceholders([...left.items, ...right.items]);
  const leftItems = canonicalizeColumns
    ? left.items.map(canonicalizeFallbackText)
    : left.items;
  const rightItems = canonicalizeColumns
    ? right.items.map(canonicalizeFallbackText)
    : right.items;

  return {
    left: {
      heading: left.heading,
      items: leftItems.length > 0 ? leftItems : [CONTENT_GENERATING],
      iconQuery: left.iconQuery,
    },
    right: {
      heading: right.heading,
      items: rightItems.length > 0 ? rightItems : [CONTENT_GENERATING],
      iconQuery: right.iconQuery,
    },
  };
}

function challengeOutcomePairs(data: Record<string, unknown>) {
  const pairs: Array<{ challenge: string; outcome: string }> = [];
  if (Array.isArray(data.items)) {
    for (const entry of data.items) {
      if (entry && typeof entry === "object") {
        const rec = entry as Record<string, unknown>;
        const challenge = asText(rec.challenge, CONTENT_GENERATING);
        const outcome = asText(rec.outcome, PENDING_SUPPLEMENT);
        const placeholderOnlyRow = areAllFallbackPlaceholders([challenge, outcome]);
        pairs.push({
          challenge: placeholderOnlyRow ? canonicalizeFallbackText(challenge) : challenge,
          outcome: placeholderOnlyRow ? canonicalizeFallbackText(outcome) : outcome,
        });
      } else if (typeof entry === "string" && entry.trim()) {
        const text = entry.trim();
        pairs.push({
          challenge: text,
          outcome: PENDING_SUPPLEMENT,
        });
      }
    }
  }

  if (pairs.length > 0) return pairs;

  const challenge = data.challenge && typeof data.challenge === "object"
    ? (data.challenge as Record<string, unknown>)
    : {};
  const outcome = data.outcome && typeof data.outcome === "object"
    ? (data.outcome as Record<string, unknown>)
    : {};
  const challengeItems = Array.isArray(challenge.items)
    ? challenge.items.map((item) => itemText(item)).filter(Boolean)
    : [];
  const outcomeItems = Array.isArray(outcome.items)
    ? outcome.items.map((item) => itemText(item)).filter(Boolean)
    : [];
  const canonicalizeSides = areAllFallbackPlaceholders([...challengeItems, ...outcomeItems]);
  const count = Math.max(challengeItems.length, outcomeItems.length);
  for (let i = 0; i < count; i += 1) {
    pairs.push({
      challenge: canonicalizeSides
        ? canonicalizeFallbackText(challengeItems[i] || CONTENT_GENERATING)
        : challengeItems[i] || CONTENT_GENERATING,
      outcome: canonicalizeSides
        ? canonicalizeFallbackText(outcomeItems[i] || PENDING_SUPPLEMENT)
        : outcomeItems[i] || PENDING_SUPPLEMENT,
    });
  }
  return pairs.length > 0 ? pairs : [{ challenge: CONTENT_GENERATING, outcome: PENDING_SUPPLEMENT }];
}


function splitOutlineSections<T>(sections: T[]): [T[], T[]] {
  const midpoint = Math.ceil(sections.length / 2);
  return [sections.slice(0, midpoint), sections.slice(midpoint)];
}

const OUTLINE_RAIL_SINGLE_COLUMN_MAX = 3;

function splitOutlineRailSections<T>(sections: T[]): [T[], T[]] {
  if (sections.length <= OUTLINE_RAIL_SINGLE_COLUMN_MAX) {
    return [sections, []];
  }
  return splitOutlineSections(sections);
}

function renderOutlineColumn(column: Array<Record<string, unknown>>, startIndex: number): string {
  if (column.length === 0) return "";

  return `
    <div style="flex:1;display:grid;grid-template-rows:repeat(${column.length},minmax(0,1fr));gap:24px;min-height:0;">
      ${column.map((section, index) => {
        const sectionIndex = startIndex + index;
        const title = asText(section.title, `Section ${sectionIndex + 1}`);
        const description = asText(section.description);
        return `
          <article style="border-top:1px solid ${backgroundTextMix(12)};padding-top:18px;display:flex;gap:20px;">
            <div style="width:48px;flex-shrink:0;padding-top:4px;">
              <div style="font-size:13px;font-weight:700;letter-spacing:0.18em;color:var(--primary-color,#3b82f6);">${String(sectionIndex + 1).padStart(2, "0")}</div>
            </div>
            <div style="min-width:0;">
              <h3 style="font-size:28px;font-weight:600;line-height:1.05;color:var(--background-text,#111827);margin:0;letter-spacing:-0.04em;">${escapeHtml(title)}</h3>
              ${description ? `<p style="font-size:15px;line-height:1.6;color:${backgroundTextMix(58)};margin:12px 0 0;max-width:420px;">${escapeHtml(description)}</p>` : ""}
            </div>
          </article>`;
      }).join("")}
    </div>`;
}

function renderOutlineRailColumn(
  column: Array<Record<string, unknown>>,
  startIndex: number,
  dense: boolean,
): string {
  if (column.length === 0) return "";

  return `
    <div style="position:relative;display:grid;grid-template-rows:repeat(${column.length},minmax(0,1fr));gap:20px;min-height:0;">
      <div style="position:absolute;left:22px;top:12px;bottom:12px;width:1px;background:#e2e8f0;"></div>
      ${column
        .map((section, index) => {
          const sectionIndex = startIndex + index;
          const title = asText(section.title, `Section ${sectionIndex + 1}`);
          const description = asText(section.description);
          return `
            <article style="position:relative;display:flex;gap:20px;min-height:0;">
              <div style="position:relative;z-index:1;display:flex;height:44px;width:44px;flex-shrink:0;align-items:center;justify-content:center;border-radius:9999px;background:var(--primary-color,#3b82f6);font-size:14px;font-weight:700;color:#ffffff;box-shadow:0 1px 2px rgba(15,23,42,0.12);">
                ${String(sectionIndex + 1).padStart(2, "0")}
              </div>
              <div style="min-width:0;border:1px solid #f1f5f9;border-radius:16px;background:#f8fafc;padding:${dense ? "12px 16px" : "16px 20px"};">
                <h3 style="font-size:${dense ? "20px" : "23px"};font-weight:700;line-height:1.2;color:var(--background-text,#111827);margin:0;">${escapeHtml(title)}</h3>
                ${description ? `<p style="font-size:${dense ? "13px" : "14px"};line-height:1.6;color:#475569;margin:8px 0 0;">${escapeHtml(description)}</p>` : ""}
              </div>
            </article>`;
        })
        .join("")}
    </div>`;
}
function contentDataToHTML(layoutId: string, data: Record<string, unknown>): string {
  const d = data as Record<string, unknown>;

  switch (layoutId) {
    case "intro-slide":
    case "intro-slide-left": {
      const author = asText(d.author) || asText(d.presenter);
      const date = asText(d.date);
      const meta = [author, date].filter(Boolean);
      return `
        <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;padding:0 80px;text-align:center;">
          <h1 style="font-size:52px;font-weight:700;line-height:1.2;color:var(--background-text,#111827);margin:0 0 16px;max-width:900px;">${escapeHtml(asText(d.title))}</h1>
          ${asText(d.subtitle) ? `<p style="font-size:24px;line-height:1.5;color:${backgroundTextMix(60)};margin:0 0 40px;max-width:700px;">${escapeHtml(asText(d.subtitle))}</p>` : ""}
          ${meta.length > 0 ? `<div style="display:flex;align-items:center;gap:16px;font-size:16px;color:${backgroundTextMix(40)};">${meta.map((item) => `<span>${escapeHtml(item)}</span>`).join("<span>/</span>")}</div>` : ""}
        </div>`;
    }

    case "section-header":
    case "section-header-side": {
      return `
        <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;padding:0 96px;text-align:center;">
          <div style="width:48px;height:4px;border-radius:9999px;background:var(--primary-color,#3b82f6);margin-bottom:32px;"></div>
          <h2 style="font-size:44px;font-weight:700;line-height:1.3;color:var(--background-text,#111827);margin:0 0 16px;max-width:800px;">${escapeHtml(asText(d.title))}</h2>
          ${asText(d.subtitle) ? `<p style="font-size:20px;line-height:1.5;color:${backgroundTextMix(50)};margin:0;max-width:600px;">${escapeHtml(asText(d.subtitle))}</p>` : ""}
        </div>`;
    }

    case "outline-slide": {
      const sections = Array.isArray(d.sections)
        ? d.sections.filter((section): section is Record<string, unknown> => !!section && typeof section === "object")
        : [];
      const [leftColumn, rightColumn] = splitOutlineSections(sections);
      return `
        <div style="display:flex;flex-direction:column;height:100%;padding:56px 64px;">
          <div style="display:flex;align-items:flex-end;gap:40px;">
            <div style="max-width:560px;">
              <div style="width:64px;height:6px;border-radius:9999px;background:var(--primary-color,#3b82f6);margin-bottom:20px;"></div>
              <h2 style="font-size:42px;font-weight:700;line-height:1.12;letter-spacing:-0.045em;color:var(--background-text,#111827);margin:0 0 16px;">${escapeHtml(asText(d.title))}</h2>
              ${asText(d.subtitle) ? `<p style="font-size:17px;line-height:1.6;color:${backgroundTextMix(60)};margin:0;max-width:520px;">${escapeHtml(asText(d.subtitle))}</p>` : ""}
            </div>
            <div style="height:1px;flex:1;background:${backgroundTextMix(12)};margin-bottom:12px;"></div>
          </div>
          <div style="display:flex;gap:56px;flex:1;margin-top:48px;">
            ${renderOutlineColumn(leftColumn, 0)}
            ${renderOutlineColumn(rightColumn, leftColumn.length)}
          </div>
        </div>`;
    }
    case "outline-slide-rail": {
      const sections = Array.isArray(d.sections)
        ? d.sections.filter((section): section is Record<string, unknown> => !!section && typeof section === "object")
        : [];
      const [leftColumn, rightColumn] = splitOutlineRailSections(sections);
      const isMultiColumn = rightColumn.length > 0;
      return `
        <div style="display:flex;height:100%;padding:56px 64px;background:linear-gradient(160deg,var(--slide-bg-start,#ffffff) 0%,var(--slide-bg-end,#f8fafc) 100%);color:var(--background-text,#111827);">
          <div style="display:flex;width:100%;gap:48px;">
            <section style="width:38%;flex-shrink:0;">
              <div style="margin-bottom:20px;font-size:12px;font-weight:600;letter-spacing:0.2em;text-transform:uppercase;color:var(--primary-color,#3b82f6);">Chapter Rail</div>
              <h2 style="font-size:42px;font-weight:800;line-height:1.08;letter-spacing:-0.05em;color:var(--background-text,#111827);margin:0;">${escapeHtml(asText(d.title))}</h2>
              ${asText(d.subtitle) ? `<p style="font-size:17px;line-height:1.65;color:#475569;margin:20px 0 0;">${escapeHtml(asText(d.subtitle))}</p>` : ""}
            </section>
            <section style="flex:1;border:1px solid #e2e8f0;border-radius:32px;background:#ffffff;padding:32px;box-shadow:0 1px 3px rgba(15,23,42,0.08);">
              <div style="${isMultiColumn ? "display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:24px;" : ""}height:100%;min-height:0;">
                ${renderOutlineRailColumn(leftColumn, 0, isMultiColumn)}
                ${isMultiColumn ? renderOutlineRailColumn(rightColumn, leftColumn.length, isMultiColumn) : ""}
              </div>
            </section>
          </div>
        </div>`;
    }
    case "bullet-with-icons": {
      const raw = Array.isArray(d.items) ? d.items : [];
      const fallbackStatus = getBulletFallbackStatus();
      const status =
        d.status && typeof d.status === "object"
          ? {
              title: asText((d.status as Record<string, unknown>).title, STATUS_TITLE),
              message: asText((d.status as Record<string, unknown>).message, STATUS_MESSAGE),
            }
          : raw.length === 0
            ? fallbackStatus
            : null;
      if (status && raw.length === 0) {
        return renderBulletStatusPanel(asText(d.title), status);
      }

      const tokens = getBulletWithIconsLayoutTokens(raw.length);
      return `
        <div style="display:flex;flex-direction:column;height:100%;padding:${tokens.outerPaddingY}px ${tokens.outerPaddingX}px;">
          <h2 style="font-size:${tokens.titleFontSize}px;font-weight:700;line-height:${tokens.titleLineHeight};color:var(--background-text,#111827);margin:0 0 ${tokens.titleMarginBottom}px;">${escapeHtml(asText(d.title))}</h2>
          <div style="display:grid;grid-template-columns:repeat(${tokens.columns},minmax(0,1fr));column-gap:${tokens.gridColumnGap}px;flex:1;min-height:0;">
            ${raw.map((item, index) => {
              const row = item && typeof item === "object" ? item as Record<string, unknown> : {};
              const icon = row.icon && typeof row.icon === "object" ? row.icon as Record<string, unknown> : {};
              const query = asText(icon.query, itemText(item) || "star");
              return `
                <div style="position:relative;display:flex;flex-direction:column;height:100%;min-height:0;padding-left:${tokens.itemPaddingLeft}px;">
                  <div style="position:absolute;left:0;top:50%;transform:translateY(-50%);width:1px;height:${tokens.dividerHeight};background-color:${backgroundTextMix(12)};"></div>
                  <div style="display:flex;flex-direction:column;justify-content:center;flex:1;min-height:0;padding:${tokens.itemPaddingY}px 0;">
                    <div style="display:flex;align-items:center;justify-content:center;width:${tokens.iconShellSize}px;height:${tokens.iconShellSize}px;border-radius:9999px;background:${primaryMix(12)};color:var(--primary-color,#3b82f6);margin-bottom:16px;flex-shrink:0;">
                      ${renderIconSvg(query, tokens.iconGlyphSize)}
                    </div>
                    <h3 style="font-size:${tokens.titleItemFontSize}px;font-weight:700;line-height:${tokens.titleItemLineHeight};letter-spacing:${tokens.titleLetterSpacing};color:var(--primary-color,#3b82f6);margin:0 0 8px;min-width:0;">
                        <span style="display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;padding-top:${tokens.titleSafetyPaddingTop}px;padding-bottom:${tokens.titleSafetyPaddingBottom}px;">
                          <span style="background:${primaryMix(7)};border-radius:3px;padding:${formatEmPadding(tokens.titleHighlightPaddingTopEm, tokens.titleHighlightPaddingXEm, tokens.titleHighlightPaddingBottomEm)};box-decoration-break:clone;-webkit-box-decoration-break:clone;">
                          ${escapeHtml(itemText(item))}
                        </span>
                      </span>
                    </h3>
                    ${itemDescription(item)
                      ? `<p style="font-size:${tokens.descriptionFontSize}px;line-height:${tokens.descriptionLineHeight};color:${backgroundTextMix(72)};margin:0;max-width:240px;">
                          <span style="display:-webkit-box;-webkit-line-clamp:${tokens.descriptionLineClamp};-webkit-box-orient:vertical;overflow:hidden;">
                            ${escapeHtml(itemDescription(item))}
                          </span>
                        </p>`
                      : ""}
                    <div style="padding-top:${tokens.indexPaddingTop}px;font-size:${tokens.indexFontSize}px;font-weight:400;line-height:${tokens.indexLineHeight};letter-spacing:-0.06em;color:var(--background-text,#111827);">
                      ${String(index + 1).padStart(2, "0")}
                    </div>
                  </div>
                </div>`;
            }).join("")}
          </div>
        </div>`;
    }

    case "bullet-with-icons-cards": {
      const raw = Array.isArray(d.items) ? d.items : [];
      const fallbackStatus = getBulletFallbackStatus();
      const status =
        d.status && typeof d.status === "object"
          ? {
              title: asText((d.status as Record<string, unknown>).title, STATUS_TITLE),
              message: asText((d.status as Record<string, unknown>).message, STATUS_MESSAGE),
            }
          : raw.length === 0
            ? fallbackStatus
            : null;
      if (status && raw.length === 0) {
        return renderBulletStatusPanel(asText(d.title), status);
      }

      const tokens = getBulletWithIconsCardsLayoutTokens();
      return `
        <div style="display:flex;flex-direction:column;height:100%;padding:${tokens.outerPaddingY}px ${tokens.outerPaddingX}px;background:linear-gradient(180deg,var(--slide-bg-start,#ffffff) 0%,var(--slide-bg-end,#f8fafc) 100%);color:var(--background-text,#111827);">
          <h2 style="font-size:${tokens.titleFontSize}px;font-weight:800;line-height:${tokens.titleLineHeight};letter-spacing:${tokens.titleLetterSpacing};margin:0 0 ${tokens.titleMarginBottom}px;max-width:${tokens.titleMaxWidth}px;">
            ${escapeHtml(asText(d.title))}
          </h2>
          <div style="display:grid;grid-template-columns:repeat(${tokens.gridColumns},minmax(0,1fr));gap:${tokens.gridGap}px;flex:1;">
            ${raw.map((item, index) => {
              const row = item && typeof item === "object" ? item as Record<string, unknown> : {};
              const icon = row.icon && typeof row.icon === "object" ? row.icon as Record<string, unknown> : {};
              const query = asText(icon.query, itemText(item) || "star");
              return `
                <article style="display:flex;flex-direction:column;min-height:0;border:1px solid #e2e8f0;border-radius:${tokens.cardRadius}px;background:#ffffff;padding:${tokens.cardPadding}px;box-shadow:0 1px 3px rgba(15,23,42,0.08);">
                  <div style="display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:${tokens.cardHeaderMarginBottom}px;">
                    <div style="display:flex;align-items:center;justify-content:center;width:${tokens.iconShellSize}px;height:${tokens.iconShellSize}px;border-radius:16px;background:${primaryMix(12)};color:var(--primary-color,#3b82f6);">
                      ${renderIconSvg(query, tokens.iconGlyphSize)}
                    </div>
                    <div style="font-size:12px;font-weight:600;line-height:1;text-transform:uppercase;letter-spacing:${tokens.indexLetterSpacing};color:#94a3b8;">
                      ${String(index + 1).padStart(2, "0")}
                    </div>
                  </div>
                  <h3 style="font-size:${tokens.cardTitleFontSize}px;font-weight:700;line-height:${tokens.cardTitleLineHeight};margin:0;max-width:360px;">
                    <span style="display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;padding-top:${tokens.cardTitleSafetyPaddingTop}px;padding-bottom:${tokens.cardTitleSafetyPaddingBottom}px;">
                      ${escapeHtml(itemText(item))}
                    </span>
                  </h3>
                  <p style="margin:${tokens.descriptionMarginTop}px 0 0;font-size:${tokens.descriptionFontSize}px;line-height:${tokens.descriptionLineHeight};color:#475569;">
                    ${escapeHtml(itemDescription(item))}
                  </p>
                </article>`;
            }).join("")}
          </div>
        </div>`;
    }

    case "numbered-bullets":
    case "numbered-bullets-track": {
      const raw = Array.isArray(d.items) ? d.items : Array.isArray(d.steps) ? d.steps : [];
      return `
        <div style="display:flex;flex-direction:column;height:100%;padding:56px 64px;">
          <h2 style="font-size:36px;font-weight:700;line-height:1.3;color:var(--background-text,#111827);margin:0 0 40px;">${escapeHtml(asText(d.title))}</h2>
          <div style="display:flex;flex-direction:column;gap:24px;flex:1;">
            ${raw.map((item, index) => `
              <div style="display:flex;align-items:flex-start;gap:20px;">
                <div style="width:40px;height:40px;border-radius:9999px;background:var(--primary-color,#3b82f6);display:flex;align-items:center;justify-content:center;flex-shrink:0;">
                  <span style="font-size:18px;font-weight:700;color:var(--primary-text,#ffffff);">${index + 1}</span>
                </div>
                <div style="padding-top:4px;">
                  <h3 style="font-size:22px;font-weight:600;line-height:1.4;color:var(--background-text,#111827);margin:0 0 4px;">${escapeHtml(itemText(item))}</h3>
                  <p style="font-size:16px;line-height:1.5;color:${backgroundTextMix(60)};margin:0;">${escapeHtml(itemDescription(item))}</p>
                </div>
              </div>`).join("")}
          </div>
        </div>`;
    }

    case "metrics-slide":
    case "metrics-slide-band": {
      const metrics = Array.isArray(d.metrics) ? d.metrics : [];
      const columns = metrics.length <= 1 ? 1 : metrics.length === 2 ? 2 : metrics.length === 3 ? 3 : 4;
      const conclusion = asText(d.conclusion);
      const conclusionBrief = asText(d.conclusionBrief);
      const hasExecutiveSummary = Boolean(conclusion || conclusionBrief);
      return `
        <div style="display:flex;flex-direction:column;height:100%;padding:56px 64px;">
          <h2 style="font-size:36px;font-weight:700;line-height:1.3;color:var(--background-text,#111827);margin:0 0 ${hasExecutiveSummary ? "24px" : "40px"};">${escapeHtml(asText(d.title))}</h2>
          ${hasExecutiveSummary ? `
            <div style="margin-bottom:32px;border-radius:28px;border:1px solid ${primaryMix(15)};background:linear-gradient(135deg,${primaryMix(10)},rgba(255,255,255,0.92));padding:32px 40px;">
              ${conclusion ? `<p style="font-size:32px;font-weight:700;line-height:1.2;color:var(--background-text,#111827);margin:0;">${escapeHtml(conclusion)}</p>` : ""}
              ${conclusionBrief ? `<p style="font-size:17px;line-height:1.6;color:${backgroundTextMix(70)};margin:${conclusion ? "16px" : "0"} 0 0;max-width:960px;">${escapeHtml(conclusionBrief)}</p>` : ""}
            </div>
            <div style="display:grid;grid-template-columns:repeat(${columns},minmax(0,1fr));gap:24px;align-items:stretch;flex:1;">
              ${metrics.map((metric) => {
                const row = metric as Record<string, unknown>;
                return `
                  <div style="display:flex;flex-direction:column;min-height:168px;padding:20px 24px;border-radius:16px;background:${primaryMix(5)};">
                    <span style="font-size:40px;font-weight:800;line-height:1.1;color:var(--primary-color,#3b82f6);margin-bottom:8px;">${escapeHtml(asText(row.value))}</span>
                    <span style="font-size:17px;font-weight:600;line-height:1.35;color:var(--background-text,#111827);margin-bottom:${asText(row.description) ? "4px" : "0"};">${escapeHtml(asText(row.label))}</span>
                    ${asText(row.description) ? `<span style="font-size:13px;line-height:1.5;color:${backgroundTextMix(60)};">${escapeHtml(asText(row.description))}</span>` : ""}
                  </div>`;
              }).join("")}
            </div>` : `
            <div style="display:grid;grid-template-columns:repeat(${columns},minmax(0,1fr));gap:32px;align-items:center;flex:1;">
              ${metrics.map((metric) => {
                const row = metric as Record<string, unknown>;
                return `
                  <div style="display:flex;flex-direction:column;align-items:center;text-align:center;padding:24px;border-radius:16px;background:${primaryMix(5)};">
                    <span style="font-size:48px;font-weight:800;line-height:1.1;color:var(--primary-color,#3b82f6);margin-bottom:8px;">${escapeHtml(asText(row.value))}</span>
                    <span style="font-size:18px;font-weight:600;line-height:1.4;color:var(--background-text,#111827);margin-bottom:${asText(row.description) ? "4px" : "0"};">${escapeHtml(asText(row.label))}</span>
                    ${asText(row.description) ? `<span style="font-size:14px;line-height:1.5;color:${backgroundTextMix(50)};">${escapeHtml(asText(row.description))}</span>` : ""}
                  </div>`;
              }).join("")}
            </div>`}
        </div>`;
    }

    case "metrics-with-image": {
      const metrics = Array.isArray(d.metrics) ? d.metrics : [];
      const image = d.image && typeof d.image === "object" ? (d.image as Record<string, unknown>) : {};
      const placeholder = getImagePlaceholderCopy(image);
      const url = sanitizeImageSrc(image.url);
      return `
        <div style="display:flex;height:100%;">
          <div style="display:flex;flex-direction:column;flex:1;padding:56px;">
            <h2 style="font-size:36px;font-weight:700;line-height:1.3;color:var(--background-text,#111827);margin:0 0 40px;">${escapeHtml(asText(d.title))}</h2>
            <div style="display:flex;flex-direction:column;gap:24px;flex:1;justify-content:center;">
              ${metrics.map((metric) => {
                const row = metric as Record<string, unknown>;
                return `
                  <div style="display:flex;align-items:center;gap:16px;padding:20px;border-radius:12px;background:${primaryMix(5)};">
                    <span style="font-size:40px;font-weight:800;color:var(--primary-color,#3b82f6);width:128px;text-align:center;flex-shrink:0;">${escapeHtml(asText(row.value))}</span>
                    <div>
                      <span style="display:block;font-size:18px;font-weight:600;line-height:1.4;color:var(--background-text,#111827);">${escapeHtml(asText(row.label))}</span>
                      ${asText(row.description) ? `<span style="font-size:14px;line-height:1.5;color:${backgroundTextMix(50)};">${escapeHtml(asText(row.description))}</span>` : ""}
                    </div>
                  </div>`;
              }).join("")}
            </div>
          </div>
          <div style="width:45%;flex-shrink:0;overflow:hidden;background:#f3f4f6;">
            ${url ? renderImageFill(url, asText(image.alt) || asText(image.prompt) || "Image", "") : renderSimpleImagePlaceholder(placeholder.title, placeholder.detail, "height:100%;")}
          </div>
        </div>`;
    }
    case "chart-with-bullets": {
      const bullets = Array.isArray(d.bullets) ? d.bullets : [];
      const chart = d.chart && typeof d.chart === "object" ? (d.chart as Record<string, unknown>) : {};
      const labels = Array.isArray(chart.labels) ? chart.labels.map((label) => asText(label)).filter(Boolean) : [];
      return `
        <div style="display:flex;flex-direction:column;height:100%;padding:56px 64px;">
          <h2 style="font-size:36px;font-weight:700;line-height:1.3;color:var(--background-text,#111827);margin:0 0 32px;">${escapeHtml(asText(d.title))}</h2>
          <div style="display:flex;gap:40px;flex:1;">
            <div style="flex:1;border-radius:16px;background:#f9fafb;border:1px solid #e5e7eb;display:flex;flex-direction:column;align-items:center;justify-content:center;color:#9ca3af;">
              <div style="margin-bottom:12px;line-height:0;color:#d1d5db;">${renderIconSvg("chart", 64)}</div>
              <span style="font-size:14px;">${escapeHtml(asText(chart.chartType || chart.chart_type, "Chart"))} 图表</span>
              ${labels.length > 0 ? `<span style="font-size:12px;color:#cbd5e1;margin-top:4px;">${escapeHtml(labels.join(", "))}</span>` : ""}
            </div>
            <div style="width:40%;display:flex;flex-direction:column;justify-content:center;gap:20px;">
              ${bullets.map((bullet) => `
                <div style="display:flex;align-items:flex-start;gap:12px;">
                  <div style="width:8px;height:8px;border-radius:9999px;background:var(--primary-color,#3b82f6);margin-top:10px;flex-shrink:0;"></div>
                  <p style="font-size:18px;line-height:1.5;color:${backgroundTextMix(80)};margin:0;">${escapeHtml(asText((bullet as Record<string, unknown>).text) || itemText(bullet))}</p>
                </div>`).join("")}
            </div>
          </div>
        </div>`;
    }

    case "table-info": {
      const { headers, rows } = tableShape(data);
      return `
        <div style="display:flex;flex-direction:column;height:100%;padding:56px 64px;">
          <h2 style="font-size:36px;font-weight:700;line-height:1.3;color:var(--background-text,#111827);margin:0 0 32px;">${escapeHtml(asText(d.title))}</h2>
          <div style="display:flex;flex-direction:column;flex:1;">
            <div style="border-radius:12px;border:1px solid #e5e7eb;overflow:hidden;">
              <table style="width:100%;border-collapse:collapse;table-layout:fixed;">
                <thead>
                  <tr style="background:var(--primary-color,#3b82f6);">
                    ${headers.map((header) => `<th style="font-size:16px;font-weight:600;padding:14px 20px;color:var(--primary-text,#ffffff);text-align:left;">${escapeHtml(header)}</th>`).join("")}
                  </tr>
                </thead>
                <tbody>
                  ${rows.map((row, index) => `
                    <tr style="background:${index % 2 === 0 ? "#ffffff" : "#f9fafb"};">
                      ${row.map((cell) => `<td style="font-size:15px;padding:12px 20px;color:${backgroundTextMix(80)};border-top:1px solid #f3f4f6;">${escapeHtml(cell)}</td>`).join("")}
                    </tr>`).join("")}
                </tbody>
              </table>
            </div>
            ${asText(d.caption) ? `<p style="font-size:13px;line-height:1.5;color:${backgroundTextMix(40)};margin:12px 0 0;text-align:center;">${escapeHtml(asText(d.caption))}</p>` : ""}
          </div>
        </div>`;
    }

    case "two-column-compare": {
      const { left, right } = compareColumns(data);
      return `
        <div style="display:flex;flex-direction:column;height:100%;padding:56px 64px;">
          <h2 style="font-size:36px;font-weight:700;line-height:1.3;color:var(--background-text,#111827);margin:0 0 32px;">${escapeHtml(asText(d.title))}</h2>
          <div style="display:flex;gap:32px;flex:1;">
            ${[left, right].map((column) => `
              <div style="flex:1;border-radius:16px;background:${primaryMix(5)};padding:32px;">
                <div style="display:flex;align-items:center;gap:12px;margin-bottom:24px;">
                  ${column.iconQuery ? `<div style="line-height:0;color:var(--primary-color,#3b82f6);">${renderIconSvg(column.iconQuery, 24)}</div>` : ""}
                  <h3 style="font-size:24px;font-weight:700;line-height:1.3;color:var(--background-text,#111827);margin:0;">${escapeHtml(column.heading)}</h3>
                </div>
                <div style="display:flex;flex-direction:column;gap:16px;">
                  ${column.items.map((item) => `
                    <div style="display:flex;align-items:flex-start;gap:12px;">
                      <div style="width:8px;height:8px;border-radius:9999px;background:var(--primary-color,#3b82f6);margin-top:10px;flex-shrink:0;"></div>
                      <p style="font-size:17px;line-height:1.5;color:${backgroundTextMix(70)};margin:0;">${escapeHtml(item)}</p>
                    </div>`).join("")}
                </div>
              </div>`).join("")}
          </div>
        </div>`;
    }

    case "image-and-description": {
      const image = d.image && typeof d.image === "object" ? (d.image as Record<string, unknown>) : {};
      const placeholder = getImagePlaceholderCopy(image);
      const url = sanitizeImageSrc(image.url);
      const bullets = Array.isArray(d.bullets) ? d.bullets.map((bullet) => asText(bullet)).filter(Boolean) : [];
      return `
        <div style="display:flex;height:100%;">
          <div style="width:48%;flex-shrink:0;overflow:hidden;border-top-right-radius:24px;border-bottom-right-radius:24px;">
            ${url ? renderImageFill(url, asText(image.alt) || asText(image.prompt) || "Image", "") : renderSimpleImagePlaceholder(placeholder.title, placeholder.detail, "height:100%;")}
          </div>
          <div style="display:flex;flex-direction:column;justify-content:center;flex:1;padding:56px;">
            <h2 style="font-size:36px;font-weight:700;line-height:1.3;color:var(--background-text,#111827);margin:0 0 24px;">${escapeHtml(asText(d.title))}</h2>
            <p style="font-size:18px;line-height:1.7;color:${backgroundTextMix(70)};margin:0 0 24px;">${escapeHtml(asText(d.description))}</p>
            ${bullets.length > 0 ? `
              <div style="display:flex;flex-direction:column;gap:12px;">
                ${bullets.map((bullet) => `
                  <div style="display:flex;align-items:flex-start;gap:12px;">
                    <div style="width:8px;height:8px;border-radius:9999px;background:var(--primary-color,#3b82f6);margin-top:10px;flex-shrink:0;"></div>
                    <span style="font-size:16px;line-height:1.6;color:${backgroundTextMix(60)};">${escapeHtml(bullet)}</span>
                  </div>`).join("")}
              </div>` : ""}
          </div>
        </div>`;
    }

    case "timeline": {
      const events = Array.isArray(d.events) ? d.events : Array.isArray(d.items) ? d.items : [];
      const eventWidth = events.length > 0 ? 100 / events.length : 100;
      return `
        <div style="display:flex;flex-direction:column;height:100%;padding:56px 64px;">
          <h2 style="font-size:36px;font-weight:700;line-height:1.3;color:var(--background-text,#111827);margin:0 0 40px;">${escapeHtml(asText(d.title))}</h2>
          <div style="display:flex;align-items:center;flex:1;">
            <div style="position:relative;display:flex;align-items:flex-start;justify-content:space-between;width:100%;">
              <div style="position:absolute;top:20px;left:20px;right:20px;height:2px;background:${primaryMix(20)};"></div>
              ${events.map((event, index) => {
                const row = event as Record<string, unknown>;
                return `
                  <div style="position:relative;display:flex;flex-direction:column;align-items:center;text-align:center;width:${eventWidth}%;">
                    <div style="width:40px;height:40px;border-radius:9999px;background:var(--primary-color,#3b82f6);display:flex;align-items:center;justify-content:center;margin-bottom:16px;z-index:1;flex-shrink:0;">
                      <span style="font-size:14px;font-weight:700;color:var(--primary-text,#ffffff);">${index + 1}</span>
                    </div>
                    <span style="font-size:14px;font-weight:700;line-height:1.4;color:var(--primary-color,#3b82f6);margin-bottom:8px;">${escapeHtml(asText(row.date))}</span>
                    <h3 style="font-size:17px;font-weight:600;line-height:1.4;color:var(--background-text,#111827);margin:0 0 4px;padding:0 8px;">${escapeHtml(asText(row.title))}</h3>
                    ${asText(row.description) ? `<p style="font-size:13px;line-height:1.4;color:${backgroundTextMix(50)};margin:0;padding:0 12px;max-width:192px;">${escapeHtml(asText(row.description))}</p>` : ""}
                  </div>`;
              }).join("")}
            </div>
          </div>
        </div>`;
    }

    case "quote-slide":
    case "quote-banner": {
      const author = asText(d.author) || asText(d.attribution);
      const context = asText(d.context);
      return `
        <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;padding:0 96px;">
          <div style="font-size:80px;line-height:1;color:${primaryMix(20)};margin-bottom:8px;">&ldquo;</div>
          <blockquote style="font-size:30px;font-weight:500;line-height:1.6;color:var(--background-text,#111827);text-align:center;max-width:850px;margin:0 0 24px;">${escapeHtml(asText(d.quote))}</blockquote>
          ${(author || context) ? `
            <div style="display:flex;align-items:center;gap:12px;">
              <div style="width:32px;height:2px;background:${primaryMix(30)};"></div>
              <span style="font-size:16px;line-height:1.5;color:${backgroundTextMix(50)};">${escapeHtml(author)}${author && context ? " / " : ""}${escapeHtml(context)}</span>
            </div>` : ""}
        </div>`;
    }
    case "bullet-icons-only": {
      const items = Array.isArray(d.items) ? d.items : Array.isArray(d.features) ? d.features : [];
      const tokens = getBulletIconsOnlyLayoutTokens(items.length);
      return `
        <div style="display:flex;flex-direction:column;height:100%;padding:${tokens.outerPaddingY}px ${tokens.outerPaddingX}px;">
          <h2 style="font-size:${tokens.titleFontSize}px;font-weight:700;line-height:${tokens.titleLineHeight};color:var(--background-text,#111827);margin:0 0 ${tokens.titleMarginBottom}px;">${escapeHtml(asText(d.title))}</h2>
          <div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));column-gap:${tokens.gridColumnGap}px;row-gap:${tokens.gridRowGap}px;align-content:center;flex:1;min-height:0;">
            ${items.map((item, index) => {
              const record = item as Record<string, unknown>;
              const icon = record.icon && typeof record.icon === "object" ? (record.icon as Record<string, unknown>) : null;
              const query = asText(icon?.query, itemText(item) || "star");
              const label = asText(record.label) || itemText(item);
              return `
                <div style="position:relative;display:flex;align-items:center;min-height:${tokens.cardMinHeight}px;overflow:hidden;border-radius:28px;background:color-mix(in srgb, var(--background-text,#111827) 3%, white);padding:${tokens.cardPaddingY}px ${tokens.cardPaddingX}px;">
                  <div style="position:absolute;left:${tokens.accentLeft}px;top:50%;width:${tokens.accentWidth}px;height:${tokens.accentHeight}px;border-radius:16px;background:${primaryMix(16)};transform:translateY(-50%) skewX(-22deg);"></div>
                  <div style="position:relative;z-index:1;width:${tokens.iconAnchorSize}px;height:${tokens.iconAnchorSize}px;border-radius:${tokens.iconAnchorRadius}px;border:1px solid ${primaryMix(14)};background:#fff;box-shadow:0 12px 32px rgba(15,23,42,0.08);display:flex;align-items:center;justify-content:center;color:var(--primary-color,#3b82f6);flex-shrink:0;">
                    ${renderIconSvg(query, tokens.iconGlyphSize)}
                  </div>
                  <div style="position:relative;z-index:1;min-width:0;margin-left:24px;">
                    <div style="font-size:12px;font-weight:700;letter-spacing:0.24em;line-height:1;color:${backgroundTextMix(42)};margin-bottom:8px;">${String(index + 1).padStart(2, "0")}</div>
                    <div style="font-size:${tokens.labelFontSize}px;font-weight:700;line-height:${tokens.labelLineHeight};letter-spacing:-0.04em;color:var(--background-text,#111827);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;padding-top:${tokens.labelSafetyPaddingTop}px;padding-bottom:${tokens.labelSafetyPaddingBottom}px;">
                      ${escapeHtml(label)}
                    </div>
                  </div>
                </div>`;
            }).join("")}
          </div>
        </div>`;
    }

    case "challenge-outcome": {
      const pairs = challengeOutcomePairs(data);
      return `
        <div style="display:flex;flex-direction:column;height:100%;padding:56px 64px;">
          <h2 style="font-size:36px;font-weight:700;line-height:1.3;color:var(--background-text,#111827);margin:0 0 32px;">${escapeHtml(asText(d.title))}</h2>
          <div style="display:flex;flex-direction:column;gap:20px;justify-content:center;flex:1;">
            ${pairs.map((pair) => `
              <div style="display:flex;align-items:stretch;gap:16px;">
                <div style="flex:1;border-radius:12px;background:#fef2f2;padding:20px;display:flex;align-items:flex-start;gap:12px;">
                  <div style="line-height:0;color:#f87171;flex-shrink:0;">${renderIconSvg("warning", 20)}</div>
                  <span style="font-size:17px;line-height:1.5;color:rgba(185,28,28,0.8);">${escapeHtml(pair.challenge)}</span>
                </div>
                <div style="display:flex;align-items:center;flex-shrink:0;">
                  <div style="width:32px;height:2px;background:${primaryMix(30)};"></div>
                  <div style="width:0;height:0;border-top:4px solid transparent;border-bottom:4px solid transparent;border-left:8px solid ${primaryMix(30)};"></div>
                </div>
                <div style="flex:1;border-radius:12px;background:#f0fdf4;padding:20px;display:flex;align-items:flex-start;gap:12px;">
                  <div style="line-height:0;color:#22c55e;flex-shrink:0;">${renderIconSvg("check", 20)}</div>
                  <span style="font-size:17px;line-height:1.5;color:rgba(21,128,61,0.8);">${escapeHtml(pair.outcome)}</span>
                </div>
              </div>`).join("")}
          </div>
        </div>`;
    }

    case "thank-you":
    case "thank-you-contact": {
      const contact = asText(d.contact) || asText(d.contact_info);
      return `
        <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;padding:0 96px;text-align:center;">
          <div style="width:64px;height:4px;border-radius:9999px;background:var(--primary-color,#3b82f6);margin-bottom:40px;"></div>
          <h1 style="font-size:56px;font-weight:800;line-height:1.2;color:var(--background-text,#111827);margin:0 0 24px;">${escapeHtml(asText(d.title, "Thanks"))}</h1>
          ${asText(d.subtitle) ? `<p style="font-size:22px;line-height:1.5;color:${backgroundTextMix(50)};margin:0 0 16px;max-width:600px;">${escapeHtml(asText(d.subtitle))}</p>` : ""}
          ${contact ? `<p style="font-size:16px;line-height:1.5;color:var(--primary-color,#3b82f6);margin:0;">${escapeHtml(contact)}</p>` : ""}
        </div>`;
    }

    default:
      return `<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#9ca3af;">Unknown layout: ${escapeHtml(layoutId)}</div>`;
  }
}

function renderLayoutContent(layoutId: string, data: Record<string, unknown>): string {
  const normalized = normalizeLayoutData(layoutId, data);
  if (!normalized.recoverable) {
    return `
      <div style="display:flex;align-items:center;justify-content:center;height:100%;padding:48px;text-align:center;color:#6b7280;">
        Slide data is unavailable in presentation mode.
      </div>`;
  }

  return contentDataToHTML(layoutId, normalized.data);
}

function renderSceneBackgroundFrame(content: string, slide: Slide): string {
  const renderModel = getSceneBackgroundRenderModel(slide.background);
  if (!renderModel) {
    return `<div class="slide-shell"><div class="slide-content">${content}</div></div>`;
  }

  const frameAttributes = attributesToHtml(renderModel.attributes);
  const frameStyle = escapeAttribute(styleMapToCss(renderModel.frameStyle));
  const contentStyle = escapeAttribute(styleMapToCss(renderModel.contentStyle));
  const layers = renderModel.layers
    .map(
      (layer) =>
        `<div aria-hidden="true" data-scene-layer="${escapeAttribute(layer.key)}" style="${escapeAttribute(styleMapToCss(layer.style))}"></div>`
    )
    .join("");

  return `<div class="slide-shell" ${frameAttributes} style="${frameStyle}">${layers}<div class="slide-content" style="${contentStyle}">${content}</div></div>`;
}

function slideToSection(slide: Slide): string {
  const normalizedSlide = normalizeSlideSceneBackground(slide);
  const useNewLayout = !!(normalizedSlide.layoutId && normalizedSlide.contentData);

  let content: string;
  if (useNewLayout) {
    content = renderLayoutContent(
      normalizedSlide.layoutId!,
      normalizedSlide.contentData as Record<string, unknown>
    );
  } else {
    content = (normalizedSlide.components ?? []).map(componentToHTML).join("\n    ");
  }

  const notes = normalizedSlide.speakerNotes
    ? `\n    <aside class="notes">${escapeHtml(normalizedSlide.speakerNotes)}</aside>`
    : "";

  return `  <section data-slide-id="${escapeAttribute(normalizedSlide.slideId)}">
    ${renderSceneBackgroundFrame(content, normalizedSlide)}${notes}
  </section>`;
}

export function presentationToRevealHTML(pres: Presentation): string {
  const sections = pres.slides.map(slideToSection).join("\n\n");
  const primaryColor = sanitizeCssColor(pres.theme?.primaryColor, "#3b82f6");
  const backgroundColor = sanitizeCssColor(pres.theme?.backgroundColor, "#ffffff");
  return `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <title>${escapeHtml(pres.title)}</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/reveal.js@5/dist/reveal.css" />
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/reveal.js@5/dist/theme/white.css" />
  <style>
    html, body {
      width: 100%;
      height: 100%;
      margin: 0;
      overflow: hidden;
      background: ${backgroundColor};
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
    }
    :root {
      --primary-color: ${primaryColor};
      --primary-text: #ffffff;
      --background-color: ${backgroundColor};
      --background-text: #111827;
    }
    .reveal {
      width: 100%;
      height: 100%;
      color: var(--background-text);
    }
    .reveal .slides {
      text-align: left;
    }
    .reveal .slides section {
      box-sizing: border-box;
      width: 100%;
      height: 100%;
      padding: 0 !important;
      min-height: 100%;
      top: 0 !important;
      text-align: left;
    }
    .reveal .slides section .slide-shell {
      position: relative;
      width: 100%;
      height: 100%;
      box-sizing: border-box;
      background: var(--background-color);
      overflow: hidden;
      isolation: isolate;
    }
    .reveal .slides section .slide-content {
      position: relative;
      z-index: 1;
      width: 100%;
      height: 100%;
    }
    .reveal .slides section .slide-content,
    .reveal .slides section .slide-content *,
    .reveal .slides section .slide-content *::before,
    .reveal .slides section .slide-content *::after {
      box-sizing: border-box;
    }
    .reveal h1, .reveal h2, .reveal h3, .reveal p, .reveal blockquote {
      margin: 0;
    }
    .reveal ul {
      list-style: disc;
      padding-left: 1.5em;
      margin: 0;
    }
    .reveal table {
      border-collapse: collapse;
    }
    .reveal img,
    .reveal svg {
      display: block;
      max-width: 100%;
    }
    html[data-preview-mode="thumbnail"] .reveal .controls,
    html[data-preview-mode="thumbnail"] .reveal .progress,
    html[data-preview-mode="thumbnail"] .reveal .slide-number {
      display: none !important;
    }
  </style>
</head>
<body>
  <div class="reveal" tabindex="-1">
    <div class="slides">
${sections}
    </div>
  </div>
  <script src="https://cdn.jsdelivr.net/npm/reveal.js@5/dist/reveal.js"><\/script>
  <script>
    const revealElement = document.querySelector('.reveal');
    const deck = new Reveal(revealElement);
    const embeddedPreview =
      window.__ZY_REVEAL_PREVIEW__ && typeof window.__ZY_REVEAL_PREVIEW__ === 'object'
        ? window.__ZY_REVEAL_PREVIEW__
        : {};
    const query = new URLSearchParams(window.location.search);
    const requestedSlide = Number.parseInt(
      String(embeddedPreview.slide ?? query.get('slide') ?? '0'),
      10
    );
    const initialSlide = Number.isFinite(requestedSlide) ? Math.max(0, requestedSlide) : 0;
    const requestedMode = embeddedPreview.mode ?? query.get('mode');
    const previewMode = requestedMode === 'thumbnail' ? 'thumbnail' : 'interactive';
    const isInteractive = previewMode === 'interactive';
    document.documentElement.dataset.previewMode = previewMode;

    const focusRevealSurface = () => {
      if (!isInteractive) return;
      try {
        window.focus();
      } catch {
        // Ignore focus failures in browsers that block it during load.
      }

      try {
        revealElement?.focus({ preventScroll: true });
      } catch {
        try {
          revealElement?.focus();
        } catch {
          // Ignore focus failures for locked-down environments.
        }
      }
    };

    const notifySlideChange = () => {
      if (!isInteractive) return;
      const { h } = deck.getIndices();
      window.parent.postMessage(
        { type: 'reveal-preview-slidechange', slideIndex: h },
        window.location.origin
      );
    };

    deck.on('ready', () => {
      if (initialSlide > 0) {
        deck.slide(initialSlide);
      } else {
        notifySlideChange();
      }
      if (isInteractive) {
        window.requestAnimationFrame(focusRevealSurface);
      }
    });
    if (isInteractive) {
      deck.on('slidechanged', notifySlideChange);
    }

    deck.initialize({
      hash: false,
      width: 1280,
      height: 720,
      margin: 0,
      center: false,
      embedded: true,
    });
  </script>
</body>
</html>`;
}

export function slideToRevealSection(slide: Slide): string {
  return slideToSection(slide);
}
