import { describe, expect, it } from 'vitest';
import { filesFromInput, isSupported, stem, suggestTitle } from './files';

describe('files', () => {
  it('knows what the pipeline can read', () => {
    expect(isSupported('IMG_0042.JPG')).toBe(true);
    expect(isSupported('scan.pdf')).toBe(true);
    expect(isSupported('notes.txt')).toBe(false);
    expect(isSupported('.DS_Store')).toBe(false);
    expect(stem('IMG_0042.jpg')).toBe('IMG_0042');
  });
  it('suggests a title from the folder, the single file, or the count', () => {
    const jpg = (name: string) => new File([''], name, { type: 'image/jpeg' });
    expect(suggestTitle({ files: [jpg('a.jpg')], folder: 'Our Iceberg' })).toBe('Our Iceberg');
    expect(suggestTitle({ files: [jpg('Contract page 1.jpg')], folder: null })).toBe(
      'Contract page 1'
    );
    const day = new Date(2026, 8, 10);
    expect(suggestTitle({ files: [jpg('a.jpg'), jpg('b.jpg')], folder: null }, day)).toMatch(
      /^2 pages, /
    );
  });
  it('keeps supported files from an input, sorted naturally', () => {
    const list = [
      new File([''], 'page_10.jpg'),
      new File([''], 'page_2.jpg'),
      new File([''], 'notes.txt'),
    ];
    const got = filesFromInput(list as unknown as FileList);
    expect(got.files.map((f) => f.name)).toEqual(['page_2.jpg', 'page_10.jpg']);
    expect(got.folder).toBeNull();
  });
});
