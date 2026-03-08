/**
 * Deterministic transform: Slide JSON -> reveal.js HTML.
 * Converts structured slide data into reveal.js-compatible section HTML.
 * Supports both layoutId/contentData payloads and legacy component payloads.
 */
import { getLayoutIconNode } from "@/lib/layout-icons";
import { normalizeLayoutData } from "@/lib/layout-data-normalizer";
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

function renderIconBadge(query: string, size: number, boxSize: number): string {
  return `
    <div style="width:${boxSize}px;height:${boxSize}px;border-radius:${Math.round(boxSize * 0.28)}px;background:${primaryMix(10)};display:flex;align-items:center;justify-content:center;margin-bottom:16px;color:var(--primary-color,#3b82f6);flex-shrink:0;">
      ${renderIconSvg(query, size)}
    </div>`;
}

function renderSimpleImagePlaceholder(prompt: string, extraStyle = ""): string {
  return `
    <div style="${extraStyle}background:#f3f4f6;display:flex;flex-direction:column;align-items:center;justify-content:center;color:#9ca3af;overflow:hidden;">
      <div style="opacity:0.5;margin-bottom:8px;line-height:0;">${renderIconSvg("image", 40)}</div>
      <span style="font-size:13px;opacity:0.7;text-align:center;padding:0 24px;">${escapeHtml(prompt)}</span>
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

  return {
    left: {
      heading: left.heading,
      items: left.items.length > 0 ? left.items : ["Content unavailable"],
      iconQuery: left.iconQuery,
    },
    right: {
      heading: right.heading,
      items: right.items.length > 0 ? right.items : ["Content unavailable"],
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
        pairs.push({
          challenge: asText(rec.challenge, "Content unavailable"),
          outcome: asText(rec.outcome, "Pending"),
        });
      } else if (typeof entry === "string" && entry.trim()) {
        pairs.push({ challenge: entry.trim(), outcome: "Pending" });
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
  const count = Math.max(challengeItems.length, outcomeItems.length);
  for (let i = 0; i < count; i += 1) {
    pairs.push({
      challenge: challengeItems[i] || "Content unavailable",
      outcome: outcomeItems[i] || "Pending",
    });
  }
  return pairs.length > 0 ? pairs : [{ challenge: "Content unavailable", outcome: "Pending" }];
}

function contentDataToHTML(layoutId: string, data: Record<string, unknown>): string {
  const d = data as Record<string, unknown>;

  switch (layoutId) {
    case "intro-slide": {
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

    case "section-header": {
      return `
        <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;padding:0 96px;text-align:center;">
          <div style="width:48px;height:4px;border-radius:9999px;background:var(--primary-color,#3b82f6);margin-bottom:32px;"></div>
          <h2 style="font-size:44px;font-weight:700;line-height:1.3;color:var(--background-text,#111827);margin:0 0 16px;max-width:800px;">${escapeHtml(asText(d.title))}</h2>
          ${asText(d.subtitle) ? `<p style="font-size:20px;line-height:1.5;color:${backgroundTextMix(50)};margin:0;max-width:600px;">${escapeHtml(asText(d.subtitle))}</p>` : ""}
        </div>`;
    }

    case "bullet-with-icons": {
      const raw = Array.isArray(d.items) ? d.items : [];
      const columns = Math.min(Math.max(raw.length, 1), 4);
      return `
        <div style="display:flex;flex-direction:column;height:100%;padding:56px 64px;">
          <h2 style="font-size:36px;font-weight:700;line-height:1.3;color:var(--background-text,#111827);margin:0 0 40px;">${escapeHtml(asText(d.title))}</h2>
          <div style="display:grid;grid-template-columns:repeat(${columns},minmax(0,1fr));gap:32px;flex:1;">
            ${raw.map((item) => {
              const record = item as Record<string, unknown>;
              const icon = record.icon && typeof record.icon === "object" ? (record.icon as Record<string, unknown>) : null;
              const query = asText(icon?.query, itemText(item) || "star");
              return `
                <div style="display:flex;flex-direction:column;align-items:flex-start;">
                  ${renderIconBadge(query, 28, 56)}
                  <h3 style="font-size:20px;font-weight:600;line-height:1.4;color:var(--background-text,#111827);margin:0 0 8px;">${escapeHtml(itemText(item))}</h3>
                  <p style="font-size:16px;line-height:1.5;color:${backgroundTextMix(60)};margin:0;">${escapeHtml(itemDescription(item))}</p>
                </div>`;
            }).join("")}
          </div>
        </div>`;
    }

    case "numbered-bullets": {
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

    case "metrics-slide": {
      const metrics = Array.isArray(d.metrics) ? d.metrics : [];
      const columns = metrics.length === 2 ? 2 : metrics.length === 3 ? 3 : 4;
      return `
        <div style="display:flex;flex-direction:column;height:100%;padding:56px 64px;">
          <h2 style="font-size:36px;font-weight:700;line-height:1.3;color:var(--background-text,#111827);margin:0 0 40px;">${escapeHtml(asText(d.title))}</h2>
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
          </div>
        </div>`;
    }

    case "metrics-with-image": {
      const metrics = Array.isArray(d.metrics) ? d.metrics : [];
      const image = d.image && typeof d.image === "object" ? (d.image as Record<string, unknown>) : {};
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
            ${url ? renderImageFill(url, asText(image.alt) || asText(image.prompt), "") : renderSimpleImagePlaceholder(asText(image.prompt), "height:100%;")}
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
      const url = sanitizeImageSrc(image.url);
      const bullets = Array.isArray(d.bullets) ? d.bullets.map((bullet) => asText(bullet)).filter(Boolean) : [];
      return `
        <div style="display:flex;height:100%;">
          <div style="width:48%;flex-shrink:0;overflow:hidden;border-top-right-radius:24px;border-bottom-right-radius:24px;">
            ${url ? renderImageFill(url, asText(image.alt) || asText(image.prompt), "") : renderSimpleImagePlaceholder(asText(image.prompt), "height:100%;")}
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

    case "quote-slide": {
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
      const cols = items.length <= 4 ? 4 : items.length <= 6 ? 3 : 4;
      return `
        <div style="display:flex;flex-direction:column;height:100%;padding:56px 64px;">
          <h2 style="font-size:36px;font-weight:700;line-height:1.3;color:var(--background-text,#111827);margin:0 0 40px;">${escapeHtml(asText(d.title))}</h2>
          <div style="display:grid;grid-template-columns:repeat(${cols},minmax(0,1fr));gap:32px;align-items:center;flex:1;">
            ${items.map((item) => {
              const record = item as Record<string, unknown>;
              const icon = record.icon && typeof record.icon === "object" ? (record.icon as Record<string, unknown>) : null;
              const query = asText(icon?.query, itemText(item) || "star");
              const label = asText(record.label) || itemText(item);
              return `
                <div style="display:flex;flex-direction:column;align-items:center;text-align:center;">
                  <div style="width:64px;height:64px;border-radius:16px;background:${primaryMix(10)};display:flex;align-items:center;justify-content:center;margin-bottom:16px;color:var(--primary-color,#3b82f6);flex-shrink:0;">
                    ${renderIconSvg(query, 32)}
                  </div>
                  <span style="font-size:16px;font-weight:600;line-height:1.5;color:var(--background-text,#111827);">${escapeHtml(label)}</span>
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

    case "thank-you": {
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

function slideToSection(slide: Slide): string {
  const useNewLayout = !!(slide.layoutId && slide.contentData);

  let content: string;
  if (useNewLayout) {
    content = renderLayoutContent(slide.layoutId!, slide.contentData as Record<string, unknown>);
  } else {
    content = (slide.components ?? []).map(componentToHTML).join("\n    ");
  }

  const notes = slide.speakerNotes
    ? `\n    <aside class="notes">${escapeHtml(slide.speakerNotes)}</aside>`
    : "";

  return `  <section data-slide-id="${escapeAttribute(slide.slideId)}">
    <div class="slide-shell">
      ${content}${notes}
    </div>
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

    const focusRevealSurface = () => {
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
      const { h } = deck.getIndices();
      window.parent.postMessage(
        { type: 'reveal-preview-slidechange', slideIndex: h },
        window.location.origin
      );
    };

    deck.on('ready', () => {
      notifySlideChange();
      window.requestAnimationFrame(focusRevealSurface);
    });
    deck.on('slidechanged', notifySlideChange);

    deck.initialize({
      hash: true,
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
