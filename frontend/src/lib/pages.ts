import type { Page } from '../api';

/** A copy of `list` with the item at `from` moved to `to`. */
export function moveItem<T>(list: readonly T[], from: number, to: number): T[] {
  const out = [...list];
  if (from < 0 || from >= out.length || to < 0 || to >= out.length) return out;
  const [item] = out.splice(from, 1);
  out.splice(to, 0, item);
  return out;
}

export function includedPages(pages: readonly Page[]): Page[] {
  return pages.filter((p) => !p.excluded);
}

/** A page a person should look at: read poorly, blurry, failed, or carrying stale corrections. */
export function needsAttention(page: Page): boolean {
  const r = page.read;
  if (!r) return false;
  return r.status === 'error' || r.low_conf || r.blurry || r.stale > 0 || r.suspects > 0;
}

/** The next (or previous) included page needing attention after `fromId`, wrapping round. */
export function nextNeedingAttention(
  pages: readonly Page[],
  fromId: string | null,
  direction: 1 | -1
): Page | null {
  const list = includedPages(pages);
  if (list.length === 0) return null;
  const start = fromId ? list.findIndex((p) => p.id === fromId) : -1;
  for (let step = 1; step <= list.length; step++) {
    const i = (start + step * direction + list.length * step) % list.length;
    if (needsAttention(list[i]) && list[i].id !== fromId) return list[i];
  }
  return null;
}

/** The neighbouring included page, or null at either end. */
export function neighbourPage(
  pages: readonly Page[],
  fromId: string | null,
  direction: 1 | -1
): Page | null {
  const list = includedPages(pages);
  const i = fromId ? list.findIndex((p) => p.id === fromId) : -1;
  const j = i + direction;
  return j >= 0 && j < list.length ? list[j] : null;
}
