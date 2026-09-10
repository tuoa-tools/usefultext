import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Document, Line, PageDetail, Region } from '../api';
import EditorView from './EditorView';

const texts = ['first line of the page', 'second line of the page'];
const lines: Line[] = texts.map((text, index) => ({
  index,
  text,
  heading: false,
  para_break_before: false,
  furniture: false,
  regions: [index],
  corrected: null,
  corrected_at: null,
  origin: 'ocr',
  suspects: [],
}));
const regions: Region[] = texts.map((text, i) => ({
  text,
  conf: 0.99,
  bbox: [100, 100 + i * 60, 900, 140 + i * 60],
  clipped: false,
}));
const page: PageDetail = {
  id: 'p1',
  file: 'photos/a.jpg',
  label: 'a.jpg',
  page_index: 0,
  excluded: false,
  position: 1,
  added_at: '',
  replaced_from: null,
  sharpness: 90,
  blurry: false,
  thumb: '',
  read: {
    status: 'done',
    error: null,
    mean_conf: 0.98,
    low_conf: false,
    blurry: false,
    sharpness: 90,
    rotation: 0,
    columns: 1,
    printed_page: null,
    n_regions: 2,
    n_lines: 2,
    corrected: 0,
    stale: 0,
    suspects: 0,
    elapsed: 1,
    preview: { url: '/preview.jpg', width: 800, height: 1000 },
  },
  width: 1600,
  height: 2000,
  lines,
  regions,
  stale: [],
  suspects: 0,
};
const doc: Document = {
  id: 'd1',
  title: 'Doc',
  folder: '/lib/Doc',
  created_at: '',
  updated_at: '',
  status: 'done',
  total_pages: 1,
  included: 1,
  read: 1,
  errors: 0,
  low_conf: 0,
  blurry: 0,
  corrected_lines: 0,
  stale_corrections: 0,
  last_run: null,
  progress: null,
  settings: {},
  pages: [page],
  warnings: [],
  stray_files: [],
};

describe('EditorView', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('pins the preview column to the window height once a fresh page has loaded', async () => {
    // The frame only exists after the page arrives; measuring must start then, not on mount.
    Element.prototype.scrollIntoView = () => {}; // jsdom has none; the selected row calls it
    vi.stubGlobal(
      'ResizeObserver',
      class {
        observe() {}
        unobserve() {}
        disconnect() {}
      }
    );
    vi.stubGlobal(
      'matchMedia',
      vi.fn(() => ({ matches: true, addEventListener() {}, removeEventListener() {} }))
    );
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          new Response(JSON.stringify(page), { headers: { 'Content-Type': 'application/json' } })
        )
      )
    );
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <EditorView
          doc={doc}
          route={{ view: 'document', id: 'd1', tab: 'editor', pageId: 'p1' }}
          navigate={() => {}}
        />
      </QueryClientProvider>
    );
    expect(await screen.findByDisplayValue('first line of the page')).toBeInTheDocument();
    const frame = await screen.findByTestId('editor-frame');
    // jsdom: innerHeight 768, the frame's top at 0 → 768 − 16 of margin.
    await waitFor(() => expect(frame).toHaveStyle({ height: '752px' }));
  });
});
