const ASCII_COLLATOR = new Intl.Collator("en", {
  numeric: true,
  sensitivity: "base",
});

const LAYOUT_NAME_COLLATOR = new Intl.Collator("zh-Hans-CN", {
  numeric: true,
  sensitivity: "base",
});

function parseTimestamp(iso: string): number | null {
  const timestamp = Date.parse(iso);
  return Number.isNaN(timestamp) ? null : timestamp;
}

export function compareLayoutNames(
  leftName: string,
  rightName: string,
  leftId: string,
  rightId: string,
): number {
  const nameDelta = LAYOUT_NAME_COLLATOR.compare(leftName, rightName);
  if (nameDelta !== 0) return nameDelta;
  return ASCII_COLLATOR.compare(leftId, rightId);
}

export function compareUpdatedAt(
  leftIso: string,
  rightIso: string,
  direction: "asc" | "desc" = "desc",
): number {
  const left = parseTimestamp(leftIso);
  const right = parseTimestamp(rightIso);

  if (left === null && right === null) {
    return direction === "desc"
      ? ASCII_COLLATOR.compare(rightIso, leftIso)
      : ASCII_COLLATOR.compare(leftIso, rightIso);
  }

  if (left === null) return 1;
  if (right === null) return -1;

  if (left !== right) {
    return direction === "desc" ? right - left : left - right;
  }

  return direction === "desc"
    ? ASCII_COLLATOR.compare(rightIso, leftIso)
    : ASCII_COLLATOR.compare(leftIso, rightIso);
}
