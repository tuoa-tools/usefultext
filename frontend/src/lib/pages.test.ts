import { describe, expect, it } from 'vitest';
import type { Page } from '../api';
import { moveItem, needsAttention, neighbourPage, nextNeedingAttention } from './pages';
import { lineBox } from './boxes';

function page(
  id: string,
  extra: Partial<Page> = {},
  read: Partial<NonNullable<Page['read']>> | null = null
): Page {
  const base: Page = {
    id,
    file: `photos/${id}.jpg`,
    label: `${id}.jpg`,
    page_index: 0,
    excluded: false,
    position: 1,
    added_at: '',
    replaced_from: null,
    sharpness: 90,
    blurry: false,
    thumb: '',
    read: null,
  };
  if (read) {
    base.read = {
      status: 'done',
      error: null,
      mean_conf: 0.98,
      low_conf: false,
      blurry: false,
      sharpness: 90,
      rotation: 0,
      columns: 1,
      printed_page: null,
      n_regions: 3,
      n_lines: 3,
      corrected: 0,
      stale: 0,
      suspects: 0,
      elapsed: 1,
      preview: null,
      ...read,
    };
  }
  return { ...base, ...extra };
}

describe('page helpers', () => {
  it('moves an item', () => {
    expect(moveItem(['a', 'b', 'c', 'd'], 0, 2)).toEqual(['b', 'c', 'a', 'd']);
    expect(moveItem(['a', 'b', 'c'], 2, 0)).toEqual(['c', 'a', 'b']);
    expect(moveItem(['a', 'b'], 5, 0)).toEqual(['a', 'b']);
  });
  it('finds pages needing attention, skipping excluded ones and wrapping round', () => {
    const pages = [
      page('a', {}, { low_conf: true }),
      page('b', {}, {}),
      page('c', { excluded: true }, { blurry: true }),
      page('d', {}, { stale: 1 }),
      page('e'),
      page('f', {}, { suspects: 2 }),
    ];
    expect(pages.map(needsAttention)).toEqual([true, false, true, true, false, true]);
    expect(nextNeedingAttention(pages, null, 1)?.id).toBe('a');
    expect(nextNeedingAttention(pages, 'a', 1)?.id).toBe('d');
    expect(nextNeedingAttention(pages, 'd', 1)?.id).toBe('f');
    expect(nextNeedingAttention(pages, 'f', 1)?.id).toBe('a');
    expect(nextNeedingAttention(pages, 'a', -1)?.id).toBe('f');
    expect(nextNeedingAttention([page('x')], null, 1)).toBeNull();
    expect(neighbourPage(pages, 'b', 1)?.id).toBe('d');
    expect(neighbourPage(pages, 'f', 1)).toBeNull();
    expect(neighbourPage(pages, 'a', -1)).toBeNull();
  });
  it('boxes a line from its regions', () => {
    const regions = [
      { text: 'a', conf: 0.9, bbox: [10, 10, 50, 20] as const, clipped: false },
      { text: 'b', conf: 0.9, bbox: [60, 5, 90, 25] as const, clipped: false },
    ].map((r) => ({ ...r, bbox: [...r.bbox] as [number, number, number, number] }));
    const line = {
      index: 0,
      text: 'a b',
      heading: false,
      para_break_before: false,
      furniture: false,
      regions: [0, 1],
      corrected: null,
      corrected_at: null,
      origin: 'ocr' as const,
      suspects: [],
    };
    expect(lineBox(line, regions)).toEqual([10, 5, 90, 25]);
    expect(lineBox({ ...line, regions: [] }, regions)).toBeNull();
  });
});
