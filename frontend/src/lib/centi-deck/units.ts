/**
 * Rewrites viewport-based CSS length units (`vh`, `vw`, `vmin`, `vmax`) in a slide's
 * HTML/CSS string into the container-query equivalents (`cqh`, `cqw`, `cqmin`, `cqmax`).
 *
 * Slide modules are mounted into `.centi-deck-slide`, which carries `container-type: size`.
 * This makes `100cqh` resolve to the slide container's own height rather than the browser
 * viewport — essential when the editor/thumbnail containers are smaller than the viewport.
 *
 * The regex only replaces lengths preceded by a digit boundary (`100vh`, `1.5vh`) and
 * followed by a non-identifier character, so it will not touch identifiers like `dvh`,
 * `lvh`, `svh`, arbitrary class names, or the bare word `vh`.
 */
const VIEWPORT_UNIT_PATTERN = /(\d(?:\.\d+)?)v(h|w|min|max)\b/g;

export function rewriteViewportUnits(input: string): string {
  if (!input) return input;
  return input.replace(VIEWPORT_UNIT_PATTERN, (_match, value: string, unit: string) => {
    return `${value}cq${unit}`;
  });
}
