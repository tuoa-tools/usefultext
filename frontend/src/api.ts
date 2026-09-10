/** Types and calls for UsefulText's API (app/main.py). Field names follow the JSON exactly. */

export interface Engine {
  state: 'idle' | 'loading' | 'ready' | 'failed';
  error: string | null;
  load_seconds?: number;
}

export interface Health {
  status: 'ok';
  version: string;
  desktop: boolean;
  engine: Engine;
  library_dir: string | null;
  library_error: string | null;
  /** No library folder chosen yet: show the picker before anything else. */
  first_run: boolean;
  heif: boolean;
  heif_error: string | null;
  quit_requested: boolean;
  /** Documents queued or being read right now. */
  reading: number;
}

export type AddMode = 'copy' | 'move';
/** How pages are laid out when read: split at a clear gutter, or always one column. */
export type Columns = 'auto' | '1';

export interface AppSettings {
  library_dir: string | null;
  add_mode: AddMode;
  add_modes: AddMode[];
  pdf_dpi: number;
  min_page_conf: number;
  blur_threshold: number;
  columns: Columns;
  default_library_dir: string;
  /** The pipeline's calibrated defaults, for "reset" hints. */
  defaults: Record<string, unknown>;
}

export type DocStatus = 'new' | 'paused' | 'done' | 'error' | 'queued' | 'running';

export interface LastPage {
  id: string;
  label: string;
  status: 'done' | 'error';
  resumed: boolean;
  mean_conf: number;
  low_conf: boolean;
  blurry: boolean;
  rotation: number;
  error: string | null;
}

export interface Progress {
  doc_id: string;
  status: 'queued' | 'running';
  done: number;
  total: number;
  current: string | null;
  started_at: number | null;
  eta_seconds: number | null;
  last_page: LastPage | null;
  force: boolean;
}

export interface LastRun {
  finished_at: number;
  error: string | null;
  processed?: number;
  resumed?: number;
  failed?: number;
  stopped_early?: boolean;
  elapsed?: number;
}

export interface DocumentSummary {
  id: string;
  title: string;
  folder: string;
  created_at: string;
  updated_at: string;
  status: DocStatus;
  /** Every page in the list, excluded ones included ("pages" itself is the list on a Document). */
  total_pages: number;
  included: number;
  read: number;
  errors: number;
  low_conf: number;
  blurry: number;
  corrected_lines: number;
  stale_corrections: number;
  last_run: LastRun | null;
  progress: Progress | null;
}

export interface Preview {
  url: string;
  width: number;
  height: number;
}

export interface PageRead {
  status: 'done' | 'error';
  error: string | null;
  /** Read quality: the engine's certainty, never "accuracy". */
  mean_conf: number;
  low_conf: boolean;
  blurry: boolean;
  sharpness: number;
  rotation: number;
  /** Text columns found on the page; 2 or more means it was read column by column. */
  columns: number;
  printed_page: number | null;
  n_regions: number;
  n_lines: number;
  corrected: number;
  stale: number;
  /** Words the dictionary does not know, on the text as shown. Flags only. */
  suspects: number;
  elapsed: number;
  preview: Preview | null;
}

export interface Page {
  id: string;
  file: string;
  label: string;
  page_index: number;
  excluded: boolean;
  /** 1-based among the included pages; null when excluded. */
  position: number | null;
  added_at: string;
  replaced_from: string | null;
  sharpness: number | null;
  blurry: boolean | null;
  thumb: string;
  read: PageRead | null;
}

export type WarningKind = 'retake' | 'duplicate' | 'printed_duplicate' | 'printed_gap';

export interface JobWarning {
  kind: WarningKind;
  message: string;
  pages: number[];
}

export interface Document extends DocumentSummary {
  settings: Record<string, number | string>;
  pages: Page[];
  warnings: JobWarning[];
  stray_files: string[];
}

export interface Suspect {
  word: string;
  /** Character offsets into the line's shown text (the correction if there is one). */
  start: number;
  end: number;
}

export interface Line {
  index: number;
  /** What the OCR read; never changed. */
  text: string;
  heading: boolean;
  para_break_before: boolean;
  furniture: boolean;
  regions: number[];
  /** A person's text for this line, or null. */
  corrected: string | null;
  corrected_at: string | null;
  origin: 'ocr' | 'human';
  suspects: Suspect[];
}

export interface Region {
  text: string;
  conf: number;
  /** [x0, y0, x1, y1] in full-resolution pixels of the upright page. */
  bbox: [number, number, number, number];
  clipped: boolean;
}

export interface StaleCorrection {
  index: number;
  text: string;
  ocr: string;
  at: string;
}

export interface PageDetail extends Page {
  width?: number;
  height?: number;
  lines: Line[];
  regions: Region[];
  stale: StaleCorrection[];
  /** How many suspect words the page has in all. */
  suspects: number;
}

const API_BASE = import.meta.env.VITE_API_URL ?? '';

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

/** FastAPI puts a string in `detail` for our errors and a list of {msg} for validation errors. */
async function errorDetail(res: Response): Promise<string> {
  try {
    const data = (await res.json()) as { detail?: unknown };
    const detail = data.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((e: { msg?: string }) => (e.msg ?? '').replace(/^Value error, /, ''))
        .filter(Boolean)
        .join('; ');
    }
  } catch {
    // not JSON - fall through
  }
  return `Request failed (${res.status})`;
}

/** The launch secret, handed to the page by the desktop window (app/window.py's bridge) and
 *  sent as a header on every call; a browser tab relies on the cookie the launch URL set. */
let nativeToken: string | null = null;
export function setNativeToken(token: string | null): void {
  nativeToken = token;
}
function withAuth(headers?: Record<string, string>): Record<string, string> | undefined {
  if (!nativeToken) return headers;
  return { ...(headers ?? {}), 'x-usefultext-token': nativeToken };
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: withAuth(body === undefined ? undefined : { 'Content-Type': 'application/json' }),
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw new ApiError(await errorDetail(res), res.status);
  return (await res.json()) as T;
}

async function requestText(path: string): Promise<string> {
  const res = await fetch(`${API_BASE}${path}`, { headers: withAuth() });
  if (!res.ok) throw new ApiError(await errorDetail(res), res.status);
  return await res.text();
}

// --- app ---
export const getHealth = () => request<Health>('GET', '/api/health');
export const getSettings = () => request<AppSettings>('GET', '/api/settings');
export const saveSettings = (body: Partial<Omit<AppSettings, 'add_modes' | 'defaults'>>) =>
  request<AppSettings>('PUT', '/api/settings', body);
export const quitApp = () => request<{ ok: true }>('POST', '/api/quit');

// --- library ---
export const getLibrary = () =>
  request<{ library_dir: string; documents: DocumentSummary[] }>('GET', '/api/library');
export const createDocument = (title: string) =>
  request<DocumentSummary>('POST', '/api/library', { title });
/** The folder goes to the OS trash; the UI confirms first. */
export const removeDocument = (id: string) =>
  request<{ ok: true; trashed: string }>('DELETE', `/api/library/${id}`);
export const revealDocument = (id: string) =>
  request<{ ok: true; path: string }>('POST', `/api/library/${id}/reveal`);

// --- a document ---
export const getDocument = (id: string) => request<Document>('GET', `/api/documents/${id}`);
export const updateDocument = (
  id: string,
  body: {
    title?: string;
    pdf_dpi?: number;
    min_page_conf?: number;
    blur_threshold?: number;
    columns?: Columns;
  }
) => request<Document>('PUT', `/api/documents/${id}`, body);

/** The drop zone: the browser sends the bytes, so this is always a copy. */
export async function addFiles(
  id: string,
  files: File[],
  replace?: string
): Promise<Document & { added: string[] }> {
  const form = new FormData();
  for (const f of files) form.append('files', f, f.name);
  if (replace) form.append('replace', replace);
  const res = await fetch(`${API_BASE}/api/documents/${id}/files`, {
    method: 'POST',
    body: form,
    headers: withAuth(),
  });
  if (!res.ok) throw new ApiError(await errorDetail(res), res.status);
  return (await res.json()) as Document & { added: string[] };
}

/** Files or a folder named by path; the only route where "move instead" is possible. */
export const addPath = (id: string, path: string, move: boolean | null, replace?: string) =>
  request<Document & { added: string[] }>('POST', `/api/documents/${id}/add-path`, {
    path,
    move,
    replace: replace ?? null,
  });

/** Photos already in the folder but not in the document become pages (no copy). */
export const adoptFiles = (id: string, files: string[]) =>
  request<Document & { added: string[] }>('POST', `/api/documents/${id}/pages/adopt`, { files });

/** The whole list, in order; pages left out are dropped from the document. */
export const setPages = (id: string, pages: { id: string; excluded: boolean }[]) =>
  request<Document & { removed: string[] }>('PUT', `/api/documents/${id}/pages`, { pages });
export const sortPages = (id: string, by: 'name' | 'time' | 'printed') =>
  request<Document & { notes: string[] }>('POST', `/api/documents/${id}/pages/sort`, { by });

export const startDocument = (id: string, force = false) =>
  request<{ ok: true; status: 'queued' }>('POST', `/api/documents/${id}/start`, { force });
export const pauseDocument = (id: string) =>
  request<{ ok: true }>('POST', `/api/documents/${id}/pause`);
export const resumeDocument = (id: string) =>
  request<{ ok: true; status: 'queued' }>('POST', `/api/documents/${id}/resume`);

// --- a page ---
export const getPage = (id: string, pageId: string) =>
  request<PageDetail>('GET', `/api/documents/${id}/pages/${pageId}`);
export const correctLine = (id: string, pageId: string, index: number, text: string) =>
  request<Line>('PUT', `/api/documents/${id}/pages/${pageId}/lines/${index}`, { text });
export const revertLine = (id: string, pageId: string, index: number) =>
  request<Line>('DELETE', `/api/documents/${id}/pages/${pageId}/lines/${index}`);

// --- exports ---
export type ExportKind = 'md' | 'txt' | 'jsonl' | 'csv' | 'pages.zip' | 'docx';
export const exportUrl = (id: string, kind: ExportKind) =>
  `${API_BASE}/api/documents/${id}/export/${kind}`;
/** Copy-all: the pages' text with nothing else, corrections applied. */
export const getPlainText = (id: string) =>
  requestText(`/api/documents/${id}/export/txt?plain=true`);

// --- the spellcheck ignore list ---
export const getDictionary = () => request<{ words: string[] }>('GET', '/api/dictionary');
export const saveDictionary = (words: string[]) =>
  request<{ words: string[] }>('PUT', '/api/dictionary', { words });
/** "Ignore": these words are fine, in every document of this library. */
export const addToDictionary = (words: string[]) =>
  request<{ words: string[] }>('POST', '/api/dictionary', { words });
