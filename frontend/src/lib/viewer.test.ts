import { describe, expect, it } from 'vitest';
import { lineFit, pageFit, viewport } from './viewer';

describe('viewer', () => {
  it('fits the whole page on its limiting side', () => {
    expect(pageFit(1000, 2000, 500, 500)).toBe(0.25);
    expect(pageFit(2000, 1000, 500, 500)).toBe(0.25);
  });

  it('fits a line to the panel width with a margin, never past 0.35 of the page', () => {
    // A full-width line: 1.1× its width plus 2% of the page exceeds the page → the page width.
    expect(lineFit([100, 0, 1900, 40], 2000, 700)).toBeCloseTo(700 / 2000);
    // A two-word heading: the floor at 35% of the page width.
    expect(lineFit([900, 0, 1100, 40], 2000, 700)).toBeCloseTo(1);
    // A column-width line: its own width plus the margins.
    expect(lineFit([100, 0, 900, 40], 2000, 700)).toBeCloseTo(700 / 920);
  });

  it('centres a page smaller than the panel and clamps a larger one to its edges', () => {
    expect(viewport(0.25, 1000, 2000, 500, 600, [500, 1000])).toEqual({
      scale: 0.25,
      left: -500,
      top: -200,
    });
    expect(viewport(1, 1000, 2000, 500, 600, [900, 1950])).toEqual({
      scale: 1,
      left: 500,
      top: 1400,
    });
    expect(viewport(1, 1000, 2000, 500, 600, [500, 1000])).toEqual({
      scale: 1,
      left: 250,
      top: 700,
    });
  });
});
