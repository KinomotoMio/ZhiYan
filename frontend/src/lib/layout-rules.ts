export function getBulletWithIconsColumns(itemCount: number): number {
  return itemCount <= 3 ? 3 : 4;
}

export function getOutlineSlideColumns(sectionCount: number): number {
  return sectionCount >= 5 ? 3 : 2;
}

export function isBulletIconsOnlyCompact(itemCount: number): boolean {
  return itemCount >= 7;
}
