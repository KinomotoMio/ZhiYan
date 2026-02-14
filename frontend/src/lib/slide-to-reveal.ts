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

function contentDataToHTML(layoutId: string, data: Record<string, unknown>): string {
  // Existing contentData serializers are intentionally permissive for mixed legacy payloads.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const d = data as Record<string, any>;

  switch (layoutId) {
    case "intro-slide":
      return `
        <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;text-align:center;padding:60px;">
          <h1 style="font-size:56px;font-weight:bold;color:var(--primary-color,#3b82f6);margin-bottom:24px;">${escapeHtml(d.title || "")}</h1>
          ${d.subtitle ? `<p style="font-size:28px;color:#6b7280;margin-bottom:40px;">${escapeHtml(d.subtitle)}</p>` : ""}
          ${d.presenter ? `<p style="font-size:20px;color:#9ca3af;">${escapeHtml(d.presenter)}</p>` : ""}
          ${d.date ? `<p style="font-size:18px;color:#9ca3af;">${escapeHtml(d.date)}</p>` : ""}
        </div>`;

    case "section-header":
      return `
        <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;text-align:center;padding:80px;">
          ${d.section_number ? `<span style="font-size:20px;color:var(--primary-color,#3b82f6);margin-bottom:16px;">${escapeHtml(String(d.section_number))}</span>` : ""}
          <h2 style="font-size:48px;font-weight:bold;margin-bottom:20px;">${escapeHtml(d.title || "")}</h2>
          ${d.subtitle ? `<p style="font-size:24px;color:#6b7280;">${escapeHtml(d.subtitle)}</p>` : ""}
        </div>`;

    case "bullet-with-icons": {
      const items = (d.items || []) as Array<{ text: string; description?: string }>;
      return `
        <div style="padding:60px 80px;height:100%;display:flex;flex-direction:column;">
          <h2 style="font-size:40px;font-weight:bold;margin-bottom:40px;">${escapeHtml(d.title || "")}</h2>
          <div style="display:grid;grid-template-columns:repeat(${Math.min(items.length, 4)},1fr);gap:32px;flex:1;">
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
      const steps = (d.items || d.steps || []) as Array<{ text: string; description?: string }>;
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
      const bullets = (d.bullets || []) as Array<{ text: string }>;
      return `
        <div style="padding:60px 80px;height:100%;display:flex;flex-direction:column;">
          <h2 style="font-size:40px;font-weight:bold;margin-bottom:32px;">${escapeHtml(d.title || "")}</h2>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:40px;flex:1;">
            <div style="background:#f9fafb;border:1px dashed #d1d5db;border-radius:8px;display:flex;align-items:center;justify-content:center;color:#9ca3af;">[图表]</div>
            <div style="display:flex;flex-direction:column;justify-content:center;gap:16px;">
              ${bullets.map((b) => `<p style="font-size:20px;">• ${escapeHtml(b.text)}</p>`).join("")}
            </div>
          </div>
        </div>`;
    }

    case "table-info": {
      const columns = (d.columns || []) as string[];
      const rows = (d.rows || []) as Array<Record<string, string>>;
      return `
        <div style="padding:60px 80px;height:100%;display:flex;flex-direction:column;">
          <h2 style="font-size:40px;font-weight:bold;margin-bottom:32px;">${escapeHtml(d.title || "")}</h2>
          <table style="width:100%;border-collapse:collapse;font-size:18px;">
            <thead><tr>
              ${columns.map((c) => `<th style="text-align:left;padding:12px 16px;border-bottom:2px solid var(--primary-color,#3b82f6);font-weight:600;">${escapeHtml(c)}</th>`).join("")}
            </tr></thead>
            <tbody>
              ${rows.map((row) => `<tr>${columns.map((c) => `<td style="padding:12px 16px;border-bottom:1px solid #e5e7eb;">${escapeHtml(String(row[c] || ""))}</td>`).join("")}</tr>`).join("")}
            </tbody>
          </table>
        </div>`;
    }

    case "two-column-compare": {
      const left = d.left as { title: string; items: Array<{ text: string }> } | undefined;
      const right = d.right as { title: string; items: Array<{ text: string }> } | undefined;
      return `
        <div style="padding:60px 80px;height:100%;display:flex;flex-direction:column;">
          <h2 style="font-size:40px;font-weight:bold;margin-bottom:32px;">${escapeHtml(d.title || "")}</h2>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:48px;flex:1;">
            <div>
              <h3 style="font-size:24px;font-weight:600;margin-bottom:20px;color:var(--primary-color,#3b82f6);">${escapeHtml(left?.title || "")}</h3>
              ${(left?.items || []).map((item) => `<p style="font-size:18px;margin-bottom:12px;">• ${escapeHtml(item.text)}</p>`).join("")}
            </div>
            <div>
              <h3 style="font-size:24px;font-weight:600;margin-bottom:20px;color:var(--primary-color,#3b82f6);">${escapeHtml(right?.title || "")}</h3>
              ${(right?.items || []).map((item) => `<p style="font-size:18px;margin-bottom:12px;">• ${escapeHtml(item.text)}</p>`).join("")}
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

    case "quote-slide":
      return `
        <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;text-align:center;padding:80px 120px;">
          <p style="font-size:36px;font-style:italic;color:#374151;line-height:1.5;">"${escapeHtml(d.quote || "")}"</p>
          ${d.attribution ? `<p style="font-size:20px;color:#9ca3af;margin-top:32px;">— ${escapeHtml(d.attribution)}</p>` : ""}
        </div>`;

    case "bullet-icons-only": {
      const features = (d.items || d.features || []) as Array<{ text: string; description?: string }>;
      return `
        <div style="padding:60px 80px;height:100%;display:flex;flex-direction:column;">
          <h2 style="font-size:40px;font-weight:bold;margin-bottom:40px;">${escapeHtml(d.title || "")}</h2>
          <div style="display:grid;grid-template-columns:repeat(${Math.min(features.length, 4)},1fr);gap:32px;flex:1;align-items:center;">
            ${features.map((f) => `
              <div style="text-align:center;padding:20px;">
                <p style="font-size:20px;font-weight:600;">${escapeHtml(f.text)}</p>
                ${f.description ? `<p style="font-size:15px;color:#6b7280;margin-top:8px;">${escapeHtml(f.description)}</p>` : ""}
              </div>
            `).join("")}
          </div>
        </div>`;
    }

    case "challenge-outcome": {
      const challenge = d.challenge as { title: string; items: Array<{ text: string }> } | undefined;
      const outcome = d.outcome as { title: string; items: Array<{ text: string }> } | undefined;
      return `
        <div style="padding:60px 80px;height:100%;display:flex;flex-direction:column;">
          <h2 style="font-size:40px;font-weight:bold;margin-bottom:32px;">${escapeHtml(d.title || "")}</h2>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:48px;flex:1;">
            <div style="background:#fef2f2;border-radius:12px;padding:32px;">
              <h3 style="font-size:24px;font-weight:600;color:#dc2626;margin-bottom:20px;">${escapeHtml(challenge?.title || "挑战")}</h3>
              ${(challenge?.items || []).map((item) => `<p style="font-size:18px;margin-bottom:10px;">• ${escapeHtml(item.text)}</p>`).join("")}
            </div>
            <div style="background:#f0fdf4;border-radius:12px;padding:32px;">
              <h3 style="font-size:24px;font-weight:600;color:#16a34a;margin-bottom:20px;">${escapeHtml(outcome?.title || "方案")}</h3>
              ${(outcome?.items || []).map((item) => `<p style="font-size:18px;margin-bottom:10px;">• ${escapeHtml(item.text)}</p>`).join("")}
            </div>
          </div>
        </div>`;
    }

    case "thank-you":
      return `
        <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;text-align:center;padding:80px;">
          <h1 style="font-size:56px;font-weight:bold;color:var(--primary-color,#3b82f6);margin-bottom:24px;">${escapeHtml(d.title || "谢谢")}</h1>
          ${d.subtitle ? `<p style="font-size:24px;color:#6b7280;margin-bottom:40px;">${escapeHtml(d.subtitle)}</p>` : ""}
          ${d.contact_info ? `<p style="font-size:18px;color:#9ca3af;">${escapeHtml(d.contact_info)}</p>` : ""}
        </div>`;

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
    content = slide.components.map(componentToHTML).join("\n    ");
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
