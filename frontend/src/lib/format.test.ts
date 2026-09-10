import { describe, expect, it } from 'vitest';
import { formatEta, plural, quality, statusLabel } from './format';

describe('format', () => {
  it('turns seconds into words', () => {
    expect(formatEta(null)).toBe('');
    expect(formatEta(20)).toBe('under a minute left');
    expect(formatEta(70)).toBe('about a minute left');
    expect(formatEta(400)).toBe('about 7 minutes left');
  });
  it('labels statuses in plain words and never says accuracy', () => {
    expect(statusLabel('new')).toBe('Not read yet');
    expect(statusLabel('running')).toBe('Reading');
    expect(quality(0.987)).toBe('0.99');
    expect(plural(1, 'page')).toBe('1 page');
    expect(plural(3, 'page')).toBe('3 pages');
  });
});
