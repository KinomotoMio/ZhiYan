/**
 * 确定性中间件 — Slide JSON → reveal.js HTML
 *
 * 将组件化 JSON 数据转换为 reveal.js 兼容的 section HTML。
 * 不含任何 LLM 调用，纯确定性转换。
 */

import type { Component, Slide, Presentation, Style } from "@/types/slide";

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

function slideToSection(slide: Slide): string {
  const components = slide.components.map(componentToHTML).join("\n    ");
  const notes = slide.speakerNotes
    ? `\n    <aside class="notes">${slide.speakerNotes}</aside>`
    : "";

  return `  <section data-slide-id="${slide.slideId}" style="position: relative; width: 100%; height: 100%;">
    ${components}${notes}
  </section>`;
}

export function presentationToRevealHTML(pres: Presentation): string {
  const sections = pres.slides.map(slideToSection).join("\n\n");

  return `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <title>${pres.title}</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/reveal.js@5/dist/reveal.css" />
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/reveal.js@5/dist/theme/white.css" />
  <style>
    .reveal section { text-align: left; }
    .reveal h2 { margin: 0; }
    .reveal ul { list-style: disc; padding-left: 1.5em; margin: 0; }
    .reveal p { margin: 0.3em 0; }
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
      width: 960,
      height: 540,
      margin: 0.04,
    });
  <\/script>
</body>
</html>`;
}

export function slideToRevealSection(slide: Slide): string {
  return slideToSection(slide);
}
