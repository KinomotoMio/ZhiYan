export function getBulletWithIconsColumns(itemCount: number): number {
  return itemCount <= 3 ? 3 : 4;
}
