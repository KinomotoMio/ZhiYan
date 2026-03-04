/**
 * 确定性中间件 — Slide JSON → reveal.js HTML
 *
 * 将组件化 JSON 数据转换为 reveal.js 兼容的 section HTML。
 * 支持新版 layoutId + contentData 和旧版 components 双模式。
 * 不含任何 LLM 调用，纯确定性转换。
 */

import type { Component, Slide, Presentation, Style } from "@/types/slide";

// ---------- 旧版 Component → HTML ----------

function styleToCSS(style?: Style): string {
  if (!style) return "";
  const parts: string[] = [];
  if (style.fontSize) parts.push(`font-size: ${style.fontSize}px`);
  if (style.fontWeight) parts.push(`font-weight: ${style.fontWeight}`);
  if (style.fontStyle) parts.push(`font-style: ${style.fontStyle}`);
  if (style.color) parts.push(`color: ${style.color}`);
  if (style.backgroundColor)
    parts.push(`background-color: ${style.backgroundColor}`);
  if (style.textAlign) parts.push(`text-align: ${style.textAlign}`);
  if (style.opacity !== undefined) parts.push(`opacity: ${style.opacity}`);
  return parts.join("; ");
}

function componentToHTML(comp: Component): string {
  const posStyle = [
    `position: absolute`,
    `left: ${comp.position.x}%`,
    `top: ${comp.position.y}%`,
    `width: ${comp.position.width}%`,
    `height: ${comp.position.height}%`,
  ].join("; ");

  const contentStyle = styleToCSS(comp.style);
  const fullStyle = `${posStyle}; ${contentStyle}`;

  switch (comp.type) {
    case "text": {
      const tag = comp.role === "title" ? "h2" : "div";
      const content = (comp.content || "")
        .split("\n")
        .map((line) => {
          if (line.startsWith("• ") || line.startsWith("- ")) {
            return `<li>${line.slice(2)}</li>`;
          }
          return `<p>${line}</p>`;
        })
        .join("\n");

      const hasListItems = content.includes("<li>");
      const wrappedContent = hasListItems
        ? `<ul>${content}</ul>`
        : content;

      return `<${tag} style="${fullStyle}">${wrappedContent}</${tag}>`;
    }
    case "image":
      return `<img src="${comp.content || ""}" alt="${comp.role}" style="${fullStyle}; object-fit: contain;" />`;
    case "chart":
      return `<div style="${fullStyle}" class="chart-placeholder" data-chart='${JSON.stringify(comp.chartData || {})}'>[图表]</div>`;
    case "shape":
      return `<div style="${fullStyle}">${comp.content || ""}</div>`;
    default:
      return "";
  }
}

// ---------- 新版 contentData → HTML ----------

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
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
    return { heading, items };
  };

  let left = normalize(data.left, "要点 A");
  let right = normalize(data.right, "要点 B");
  if (left.items.length === 0 && right.items.length === 0) {
    left = normalize(data.challenge, "要点 A");
    right = normalize(data.outcome, "要点 B");
  }
  return {
    left: { heading: left.heading, items: left.items.length > 0 ? left.items : ["内容生成中"] },
    right: { heading: right.heading, items: right.items.length > 0 ? right.items : ["内容生成中"] },
  };
}

function challengeOutcomePairs(data: Record<string, unknown>) {
  const pairs: Array<{ challenge: string; outcome: string }> = [];
  if (Array.isArray(data.items)) {
    for (const entry of data.items) {
      if (entry && typeof entry === "object") {
        const rec = entry as Record<string, unknown>;
        pairs.push({
          challenge: asText(rec.challenge, "内容生成中"),
          outcome: asText(rec.outcome, "待补充"),
        });
      } else if (typeof entry === "string" && entry.trim()) {
        pairs.push({ challenge: entry.trim(), outcome: "待补充" });
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
      challenge: challengeItems[i] || "内容生成中",
      outcome: outcomeItems[i] || "待补充",
    });
  }
  return pairs.length > 0 ? pairs : [{ challenge: "内容生成中", outcome: "待补充" }];
}

function contentDataToHTML(layoutId: string, data: Record<string, unknown>): string {
  // Existing contentData serializers are intentionally permissive for mixed legacy payloads.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const d = data as Record<string, any>;

  switch (layoutId) {
    case "intro-slide": {
      const author = asText(d.author) || asText(d.presenter);
      const date = asText(d.date);
      const meta = [author, date].filter(Boolean).join(" · ");
      return `
        <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;text-align:center;padding:60px;">
          <h1 style="font-size:56px;font-weight:bold;color:var(--primary-color,#3b82f6);margin-bottom:24px;">${escapeHtml(d.title || "")}</h1>
          ${d.subtitle ? `<p style="font-size:28px;color:#6b7280;margin-bottom:40px;">${escapeHtml(d.subtitle)}</p>` : ""}
          ${meta ? `<p style="font-size:18px;color:#9ca3af;">${escapeHtml(meta)}</p>` : ""}
        </div>`;
    }

    case "section-header":
      return `
        <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;text-align:center;padding:80px;">
          ${d.section_number ? `<span style="font-size:20px;color:var(--primary-color,#3b82f6);margin-bottom:16px;">${escapeHtml(String(d.section_number))}</span>` : ""}
          <h2 style="font-size:48px;font-weight:bold;margin-bottom:20px;">${escapeHtml(d.title || "")}</h2>
          ${d.subtitle ? `<p style="font-size:24px;color:#6b7280;">${escapeHtml(d.subtitle)}</p>` : ""}
        </div>`;

    case "bullet-with-icons": {
      const raw = (d.items || []) as unknown[];
      const items = raw.map((item) => ({
        text: itemText(item),
        description: itemDescription(item),
      }));
      return `
        <div style="padding:60px 80px;height:100%;display:flex;flex-direction:column;">
          <h2 style="font-size:40px;font-weight:bold;margin-bottom:40px;">${escapeHtml(d.title || "")}</h2>
          <div style="display:grid;grid-template-columns:repeat(${Math.min(Math.max(items.length, 1), 4)},1fr);gap:32px;flex:1;">
            ${items.map((item) => `
              <div style="padding:24px;">
                <p style="font-size:22px;font-weight:600;margin-bottom:8px;">${escapeHtml(item.text)}</p>
                ${item.description ? `<p style="font-size:16px;color:#6b7280;">${escapeHtml(item.description)}</p>` : ""}
              </div>
            `).join("")}
          </div>
        </div>`;
    }

    case "numbered-bullets": {
      const raw = (d.items || d.steps || []) as unknown[];
      const steps = raw.map((item) => ({
        text: itemText(item),
        description: itemDescription(item),
      }));
      return `
        <div style="padding:60px 80px;height:100%;display:flex;flex-direction:column;">
          <h2 style="font-size:40px;font-weight:bold;margin-bottom:40px;">${escapeHtml(d.title || "")}</h2>
          <div style="display:flex;flex-direction:column;gap:24px;">
            ${steps.map((item, i) => `
              <div style="display:flex;gap:20px;align-items:flex-start;">
                <span style="font-size:28px;font-weight:bold;color:var(--primary-color,#3b82f6);min-width:40px;">${i + 1}</span>
                <div>
                  <p style="font-size:22px;font-weight:600;">${escapeHtml(item.text)}</p>
                  ${item.description ? `<p style="font-size:16px;color:#6b7280;margin-top:4px;">${escapeHtml(item.description)}</p>` : ""}
                </div>
              </div>
            `).join("")}
          </div>
        </div>`;
    }

    case "metrics-slide": {
      const metrics = (d.metrics || []) as Array<{ value: string; label: string; description?: string }>;
      return `
        <div style="padding:60px 80px;height:100%;display:flex;flex-direction:column;">
          <h2 style="font-size:40px;font-weight:bold;margin-bottom:48px;">${escapeHtml(d.title || "")}</h2>
          <div style="display:grid;grid-template-columns:repeat(${Math.min(metrics.length, 4)},1fr);gap:40px;flex:1;align-items:center;">
            ${metrics.map((m) => `
              <div style="text-align:center;padding:24px;">
                <p style="font-size:48px;font-weight:bold;color:var(--primary-color,#3b82f6);">${escapeHtml(m.value)}</p>
                <p style="font-size:20px;font-weight:600;margin-top:12px;">${escapeHtml(m.label)}</p>
                ${m.description ? `<p style="font-size:15px;color:#6b7280;margin-top:8px;">${escapeHtml(m.description)}</p>` : ""}
              </div>
            `).join("")}
          </div>
        </div>`;
    }

    case "metrics-with-image": {
      const metrics2 = (d.metrics || []) as Array<{ value: string; label: string }>;
      return `
        <div style="display:grid;grid-template-columns:1fr 1fr;height:100%;">
          <div style="padding:60px;display:flex;flex-direction:column;justify-content:center;">
            <h2 style="font-size:36px;font-weight:bold;margin-bottom:32px;">${escapeHtml(d.title || "")}</h2>
            ${metrics2.map((m) => `
              <div style="margin-bottom:20px;">
                <span style="font-size:36px;font-weight:bold;color:var(--primary-color,#3b82f6);">${escapeHtml(m.value)}</span>
                <span style="font-size:18px;color:#6b7280;margin-left:12px;">${escapeHtml(m.label)}</span>
              </div>
            `).join("")}
          </div>
          <div style="background:#f3f4f6;display:flex;align-items:center;justify-content:center;color:#9ca3af;">
            [图片]
          </div>
        </div>`;
    }

    case "chart-with-bullets": {
      const bullets = (d.bullets || []) as unknown[];
      return `
        <div style="padding:60px 80px;height:100%;display:flex;flex-direction:column;">
          <h2 style="font-size:40px;font-weight:bold;margin-bottom:32px;">${escapeHtml(d.title || "")}</h2>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:40px;flex:1;">
            <div style="background:#f9fafb;border:1px dashed #d1d5db;border-radius:8px;display:flex;align-items:center;justify-content:center;color:#9ca3af;">[图表]</div>
            <div style="display:flex;flex-direction:column;justify-content:center;gap:16px;">
              ${bullets.map((b) => `<p style="font-size:20px;">• ${escapeHtml(itemText(b))}</p>`).join("")}
            </div>
          </div>
        </div>`;
    }

    case "table-info": {
      const { headers, rows } = tableShape(data);
      return `
        <div style="padding:60px 80px;height:100%;display:flex;flex-direction:column;">
          <h2 style="font-size:40px;font-weight:bold;margin-bottom:32px;">${escapeHtml(d.title || "")}</h2>
          <table style="width:100%;border-collapse:collapse;font-size:18px;">
            <thead><tr>
              ${headers.map((c) => `<th style="text-align:left;padding:12px 16px;border-bottom:2px solid var(--primary-color,#3b82f6);font-weight:600;">${escapeHtml(c)}</th>`).join("")}
            </tr></thead>
            <tbody>
              ${rows.map((row) => `<tr>${row.map((cell) => `<td style="padding:12px 16px;border-bottom:1px solid #e5e7eb;">${escapeHtml(cell)}</td>`).join("")}</tr>`).join("")}
            </tbody>
          </table>
        </div>`;
    }

    case "two-column-compare": {
      const { left, right } = compareColumns(data);
      return `
        <div style="padding:60px 80px;height:100%;display:flex;flex-direction:column;">
          <h2 style="font-size:40px;font-weight:bold;margin-bottom:32px;">${escapeHtml(d.title || "")}</h2>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:48px;flex:1;">
            <div>
              <h3 style="font-size:24px;font-weight:600;margin-bottom:20px;color:var(--primary-color,#3b82f6);">${escapeHtml(left.heading)}</h3>
              ${left.items.map((item) => `<p style="font-size:18px;margin-bottom:12px;">• ${escapeHtml(item)}</p>`).join("")}
            </div>
            <div>
              <h3 style="font-size:24px;font-weight:600;margin-bottom:20px;color:var(--primary-color,#3b82f6);">${escapeHtml(right.heading)}</h3>
              ${right.items.map((item) => `<p style="font-size:18px;margin-bottom:12px;">• ${escapeHtml(item)}</p>`).join("")}
            </div>
          </div>
        </div>`;
    }

    case "image-and-description":
      return `
        <div style="display:grid;grid-template-columns:1fr 1fr;height:100%;">
          <div style="background:#f3f4f6;display:flex;align-items:center;justify-content:center;color:#9ca3af;">[图片]</div>
          <div style="padding:60px;display:flex;flex-direction:column;justify-content:center;">
            <h2 style="font-size:36px;font-weight:bold;margin-bottom:20px;">${escapeHtml(d.title || "")}</h2>
            <p style="font-size:20px;color:#4b5563;line-height:1.6;">${escapeHtml(d.description || "")}</p>
          </div>
        </div>`;

    case "timeline": {
      const events = (d.events || d.items || []) as Array<{ date: string; title: string; description?: string }>;
      return `
        <div style="padding:60px 80px;height:100%;display:flex;flex-direction:column;">
          <h2 style="font-size:40px;font-weight:bold;margin-bottom:40px;">${escapeHtml(d.title || "")}</h2>
          <div style="display:flex;gap:32px;flex:1;align-items:center;">
            ${events.map((e) => `
              <div style="flex:1;text-align:center;padding:20px;">
                <p style="font-size:16px;color:var(--primary-color,#3b82f6);font-weight:600;">${escapeHtml(e.date || "")}</p>
                <p style="font-size:20px;font-weight:600;margin-top:8px;">${escapeHtml(e.title)}</p>
                ${e.description ? `<p style="font-size:15px;color:#6b7280;margin-top:4px;">${escapeHtml(e.description)}</p>` : ""}
              </div>
            `).join("")}
          </div>
        </div>`;
    }

    case "quote-slide": {
      const author = asText(d.author) || asText(d.attribution);
      const context = asText(d.context);
      const meta = [author, context].filter(Boolean).join(" · ");
      return `
        <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;text-align:center;padding:80px 120px;">
          <p style="font-size:36px;font-style:italic;color:#374151;line-height:1.5;">"${escapeHtml(d.quote || "")}"</p>
          ${meta ? `<p style="font-size:20px;color:#9ca3af;margin-top:32px;">— ${escapeHtml(meta)}</p>` : ""}
        </div>`;
    }

    case "bullet-icons-only": {
      const features = (d.items || d.features || []) as unknown[];
      return `
        <div style="padding:60px 80px;height:100%;display:flex;flex-direction:column;">
          <h2 style="font-size:40px;font-weight:bold;margin-bottom:40px;">${escapeHtml(d.title || "")}</h2>
          <div style="display:grid;grid-template-columns:repeat(${Math.min(Math.max(features.length, 1), 4)},1fr);gap:32px;flex:1;align-items:center;">
            ${features.map((f) => `
              <div style="text-align:center;padding:20px;">
                <p style="font-size:20px;font-weight:600;">${escapeHtml(itemText(f))}</p>
                ${itemDescription(f) ? `<p style="font-size:15px;color:#6b7280;margin-top:8px;">${escapeHtml(itemDescription(f))}</p>` : ""}
              </div>
            `).join("")}
          </div>
        </div>`;
    }

    case "challenge-outcome": {
      const pairs = challengeOutcomePairs(data);
      return `
        <div style="padding:60px 80px;height:100%;display:flex;flex-direction:column;">
          <h2 style="font-size:40px;font-weight:bold;margin-bottom:32px;">${escapeHtml(d.title || "")}</h2>
          <div style="display:flex;flex-direction:column;gap:14px;">
            ${pairs.map((pair) => `
              <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;">
                <div style="background:#fef2f2;border-radius:10px;padding:14px 16px;color:#b91c1c;">${escapeHtml(pair.challenge)}</div>
                <div style="background:#f0fdf4;border-radius:10px;padding:14px 16px;color:#15803d;">${escapeHtml(pair.outcome)}</div>
              </div>
            `).join("")}
          </div>
        </div>`;
    }

    case "thank-you": {
      const contact = asText(d.contact) || asText(d.contact_info);
      return `
        <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;text-align:center;padding:80px;">
          <h1 style="font-size:56px;font-weight:bold;color:var(--primary-color,#3b82f6);margin-bottom:24px;">${escapeHtml(d.title || "谢谢")}</h1>
          ${d.subtitle ? `<p style="font-size:24px;color:#6b7280;margin-bottom:40px;">${escapeHtml(d.subtitle)}</p>` : ""}
          ${contact ? `<p style="font-size:18px;color:#9ca3af;">${escapeHtml(contact)}</p>` : ""}
        </div>`;
    }

    default:
      return `<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#9ca3af;">未知布局: ${escapeHtml(layoutId)}</div>`;
  }
}

// ---------- Slide → Section ----------

function slideToSection(slide: Slide): string {
  const useNewLayout = !!(slide.layoutId && slide.contentData);

  let content: string;
  if (useNewLayout) {
    content = contentDataToHTML(slide.layoutId!, slide.contentData as Record<string, unknown>);
  } else {
    content = (slide.components ?? []).map(componentToHTML).join("\n    ");
  }

  const notes = slide.speakerNotes
    ? `\n    <aside class="notes">${escapeHtml(slide.speakerNotes)}</aside>`
    : "";

  return `  <section data-slide-id="${slide.slideId}" style="position: relative; width: 100%; height: 100%;">
    ${content}${notes}
  </section>`;
}

export function presentationToRevealHTML(pres: Presentation): string {
  const sections = pres.slides.map(slideToSection).join("\n\n");

  return `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <title>${escapeHtml(pres.title)}</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/reveal.js@5/dist/reveal.css" />
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/reveal.js@5/dist/theme/white.css" />
  <style>
    :root {
      --primary-color: ${pres.theme?.primaryColor || "#3b82f6"};
      --primary-text: #ffffff;
      --background-color: ${pres.theme?.backgroundColor || "#ffffff"};
      --background-text: #111827;
    }
    .reveal section { text-align: left; }
    .reveal h1, .reveal h2, .reveal h3 { margin: 0; }
    .reveal ul { list-style: disc; padding-left: 1.5em; margin: 0; }
    .reveal p { margin: 0.3em 0; }
    .reveal table { border-collapse: collapse; }
  </style>
</head>
<body>
  <div class="reveal">
    <div class="slides">
${sections}
    </div>
  </div>
  <script src="https://cdn.jsdelivr.net/npm/reveal.js@5/dist/reveal.js"><\/script>
  <script>
    Reveal.initialize({
      hash: true,
      width: 1280,
      height: 720,
      margin: 0.04,
    });
  <\/script>
</body>
</html>`;
}

export function slideToRevealSection(slide: Slide): string {
  return slideToSection(slide);
}
