import { describe, expect, it } from 'vitest';
import { parseRoute, routeHash } from './route';

describe('routes', () => {
  it('parses and prints every shape', () => {
    expect(parseRoute('')).toEqual({ view: 'library' });
    expect(parseRoute('#/')).toEqual({ view: 'library' });
    expect(parseRoute('#/doc/abc')).toEqual({
      view: 'document',
      id: 'abc',
      tab: 'pages',
      pageId: undefined,
    });
    expect(parseRoute('#/doc/abc/editor/p1')).toEqual({
      view: 'document',
      id: 'abc',
      tab: 'editor',
      pageId: 'p1',
    });
    expect(parseRoute('#/doc/abc/nonsense')).toMatchObject({ tab: 'pages' });
    expect(routeHash({ view: 'library' })).toBe('#/');
    expect(routeHash({ view: 'document', id: 'abc', tab: 'export' })).toBe('#/doc/abc/export');
    expect(routeHash({ view: 'document', id: 'abc', tab: 'editor', pageId: 'p1' })).toBe(
      '#/doc/abc/editor/p1'
    );
  });
});
