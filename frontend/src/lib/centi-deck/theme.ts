import type { CentiDeckTheme } from "./types";

/**
 * Apply a centi-deck theme to a container element by setting CSS custom
 * properties. Returns a cleanup function that restores previous values.
 *
 * Theme keys are passed through verbatim (e.g. `--brand: "#7c3aed"`). Keys
 * starting with `--` become CSS custom properties; other keys are written as
 * dataset attributes under `data-centi-*`.
 */
export function applyCentiDeckTheme(
  container: HTMLElement,
  theme: CentiDeckTheme | null | undefined
): () => void {
  if (!theme) return () => {};

  const previousCustomProps: Array<[string, string]> = [];
  const previousDataset: Array<[string, string | undefined]> = [];

  for (const [key, value] of Object.entries(theme)) {
    if (value == null) continue;
    const stringValue = String(value);
    if (key.startsWith("--")) {
      previousCustomProps.push([key, container.style.getPropertyValue(key)]);
      container.style.setProperty(key, stringValue);
    } else {
      const datasetKey = key.replace(/[^a-zA-Z0-9-]/g, "").replace(/^-+/, "");
      if (!datasetKey) continue;
      previousDataset.push([datasetKey, container.dataset[datasetKey]]);
      container.dataset[datasetKey] = stringValue;
    }
  }

  return () => {
    for (const [key, previousValue] of previousCustomProps) {
      if (previousValue) {
        container.style.setProperty(key, previousValue);
      } else {
        container.style.removeProperty(key);
      }
    }
    for (const [key, previousValue] of previousDataset) {
      if (previousValue === undefined) {
        delete container.dataset[key];
      } else {
        container.dataset[key] = previousValue;
      }
    }
  };
}
