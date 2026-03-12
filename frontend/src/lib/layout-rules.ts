export function getBulletWithIconsColumns(itemCount: number): number {
  return itemCount <= 3 ? 3 : 4;
}

export function getOutlineSlideColumns(sectionCount: number): number {
  return sectionCount >= 5 ? 3 : 2;
}
