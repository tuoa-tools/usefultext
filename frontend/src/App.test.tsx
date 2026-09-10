import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';

const health = {
  status: 'ok',
  version: '0.1.0',
  desktop: false,
  engine: { state: 'ready', error: null },
  library_dir: null,
  library_error: null,
  first_run: true,
  heif: true,
  heif_error: null,
  quit_requested: false,
  reading: 0,
};
const settings = {
  library_dir: null,
  add_mode: 'copy',
  add_modes: ['copy', 'move'],
  pdf_dpi: 200,
  min_page_conf: 0.7,
  blur_threshold: 65,
  default_library_dir: '/Users/someone/Documents/UsefulText',
  defaults: {},
};

function jsonResponse(body: unknown) {
  return Promise.resolve(
    new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } })
  );
}

function renderApp() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <App />
    </QueryClientProvider>
  );
}

describe('App', () => {
  beforeEach(() => {
    window.location.hash = '';
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith('/api/health')) return jsonResponse(health);
        if (url.endsWith('/api/settings')) return jsonResponse(settings);
        return jsonResponse({ detail: `unexpected ${url}` });
      })
    );
  });
  afterEach(() => vi.unstubAllGlobals());

  it('asks for a library folder on first run, pre-filled with the suggestion', async () => {
    renderApp();
    expect(await screen.findByText(/where should your library live/i)).toBeInTheDocument();
    const input = (await screen.findByLabelText('Library folder')) as HTMLInputElement;
    expect(input.value).toBe('/Users/someone/Documents/UsefulText');
    expect(screen.getByRole('button', { name: 'Use this folder' })).toBeEnabled();
    expect(screen.queryByText('Quit')).not.toBeInTheDocument(); // not desktop mode
  });
});
