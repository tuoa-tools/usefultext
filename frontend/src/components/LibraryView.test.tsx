import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import LibraryView from './LibraryView';

const documents = [
  {
    id: 'a1',
    title: 'Our Iceberg Is Melting',
    folder: '/lib/Our Iceberg Is Melting',
    created_at: '2026-09-10T00:00:00Z',
    updated_at: '2026-09-10T00:00:00Z',
    status: 'paused',
    total_pages: 6,
    included: 6,
    read: 4,
    errors: 0,
    low_conf: 1,
    blurry: 2,
    corrected_lines: 3,
    stale_corrections: 0,
    last_run: null,
    progress: null,
  },
  {
    id: 'b2',
    title: 'Empty one',
    folder: '/lib/Empty one',
    created_at: '',
    updated_at: '',
    status: 'new',
    total_pages: 0,
    included: 0,
    read: 0,
    errors: 0,
    low_conf: 0,
    blurry: 0,
    corrected_lines: 0,
    stale_corrections: 0,
    last_run: null,
    progress: null,
  },
];

describe('LibraryView', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('lists documents with their status, counts and things to look at', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          new Response(JSON.stringify({ library_dir: '/lib', documents }), {
            headers: { 'Content-Type': 'application/json' },
          })
        )
      )
    );
    const onOpen = vi.fn();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <LibraryView onOpen={onOpen} />
      </QueryClientProvider>
    );
    expect(await screen.findByText('Our Iceberg Is Melting')).toBeInTheDocument();
    expect(screen.getByText('Partly read')).toBeInTheDocument();
    expect(screen.getByText(/4 of 6 pages read/)).toBeInTheDocument();
    expect(screen.getByText(/3 pages to look at/)).toBeInTheDocument();
    expect(screen.getByText(/3 lines corrected/)).toBeInTheDocument();
    expect(screen.getByText('No pages yet')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Remove from library' })).toHaveLength(2);
    screen.getByText('Our Iceberg Is Melting').click();
    expect(onOpen).toHaveBeenCalledWith('a1');
  });
});
