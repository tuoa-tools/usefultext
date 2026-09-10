import { describe, expect, it } from 'vitest';
import { baseName, nativeDialogs, titleForPaths } from './native';

describe('native dialogs', () => {
  it('is absent in a browser tab', () => {
    expect(nativeDialogs()).toBeNull();
  });

  it('names a document after the folder or file chosen', () => {
    expect(baseName('/Users/adam/Pictures/Our Iceberg/')).toBe('Our Iceberg');
    expect(baseName('C:\\Scans\\IMG_0042.JPG')).toBe('IMG_0042.JPG');
    expect(titleForPaths(['/scans/Our Iceberg'])).toBe('Our Iceberg');
    expect(titleForPaths(['/scans/IMG_0042.JPG'])).toBe('IMG_0042');
    expect(titleForPaths(['/scans/Draft v1.2'])).toBe('Draft v1.2');
    const day = new Date(2026, 8, 10);
    expect(titleForPaths(['/a.jpg', '/b.jpg', '/c.jpg'], day)).toMatch(/^3 pages, /);
  });
});
