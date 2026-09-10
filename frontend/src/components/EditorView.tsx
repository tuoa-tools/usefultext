import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  RotateCcw,
  SkipBack,
  SkipForward,
} from 'lucide-react';
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react';
import {
  addToDictionary,
  correctLine,
  getPage,
  revertLine,
  type Document,
  type Line,
  type PageDetail,
  type Suspect,
} from '../api';
import { lineBox } from '../lib/boxes';
import { plural } from '../lib/format';
import {
  clamp,
  lineFit,
  pageFit,
  viewport,
  ZOOM_MAX,
  ZOOM_MIN,
  ZOOM_STEP,
  type Preset,
} from '../lib/viewer';
import { includedPages, needsAttention, neighbourPage, nextNeedingAttention } from '../lib/pages';
import type { Route } from '../lib/route';
import ErrorText from './ErrorText';
import IconButton from './IconButton';
import { PageChips } from './PagesView';

type DocRoute = Extract<Route, { view: 'document' }>;

export default function EditorView({
  doc,
  route,
  navigate,
}: {
  doc: Document;
  route: DocRoute;
  navigate: (r: Route) => void;
}) {
  const included = includedPages(doc.pages).filter((p) => p.read?.status === 'done');
  const first = nextNeedingAttention(doc.pages, null, 1) ?? included[0] ?? null;
  const pageId = route.pageId ?? first?.id ?? null;
  const go = (id: string) => navigate({ view: 'document', id: doc.id, tab: 'editor', pageId: id });
  const current = doc.pages.find((p) => p.id === pageId) ?? null;
  const [jump, setJump] = useState<'first' | 'last' | null>(null);

  useEffect(() => {
    if (!route.pageId && first) go(first.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [route.pageId, first?.id]);

  if (!pageId || !current) return <p className="text-slate-600">No page has been read yet.</p>;
  const prev = neighbourPage(doc.pages, pageId, -1);
  const next = neighbourPage(doc.pages, pageId, 1);
  const prevFlag = nextNeedingAttention(doc.pages, pageId, -1);
  const nextFlag = nextNeedingAttention(doc.pages, pageId, 1);
  const flagged = doc.pages.filter((p) => !p.excluded && needsAttention(p)).length;
  const withSuspects = includedPages(doc.pages).filter((p) => (p.read?.suspects ?? 0) > 0);
  /** "Next suspect" past the end of this page: the next page with suspects, wrapping round. */
  const jumpPage = (direction: 1 | -1) => {
    if (withSuspects.length === 0) return;
    const i = withSuspects.findIndex((p) => p.id === pageId);
    const target = withSuspects[(i + direction + withSuspects.length) % withSuspects.length];
    if (target.id === pageId) return;
    setJump(direction === 1 ? 'first' : 'last');
    go(target.id);
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 rounded-xl bg-white p-2 shadow-sm">
        <IconButton
          icon={SkipBack}
          label="Previous page to look at"
          onClick={() => prevFlag && go(prevFlag.id)}
          disabled={!prevFlag}
        />
        <IconButton
          icon={ChevronLeft}
          label="Previous page"
          onClick={() => prev && go(prev.id)}
          disabled={!prev}
        />
        <select
          aria-label="Page"
          className="min-w-0 flex-1 rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
          value={pageId}
          onChange={(e) => go(e.target.value)}
        >
          {includedPages(doc.pages).map((p) => (
            <option key={p.id} value={p.id} disabled={!p.read}>
              {p.position}. {p.label}
              {p.read?.printed_page != null ? ` (printed p. ${p.read.printed_page})` : ''}
              {needsAttention(p) ? ' ⚠' : ''}
              {p.read ? '' : ' – not read yet'}
            </option>
          ))}
        </select>
        <IconButton
          icon={ChevronRight}
          label="Next page"
          onClick={() => next && go(next.id)}
          disabled={!next}
        />
        <IconButton
          icon={SkipForward}
          label="Next page to look at"
          onClick={() => nextFlag && go(nextFlag.id)}
          disabled={!nextFlag}
        />
        <span className="w-full text-xs text-slate-500 sm:w-auto">
          {flagged === 0 ? 'No pages need a look.' : `${plural(flagged, 'page')} to look at.`}
        </span>
      </div>
      <PageEditor
        key={pageId}
        docId={doc.id}
        pageId={pageId}
        jump={jump}
        onJumped={() => setJump(null)}
        onPastEnd={jumpPage}
        suspectPages={withSuspects.length}
      />
    </div>
  );
}

/** A suspect's place on the page: which line, and which of that line's suspects. */
interface Spot {
  line: number;
  n: number;
}

function spots(page: PageDetail): Spot[] {
  return page.lines.flatMap((ln) => ln.suspects.map((_, n) => ({ line: ln.index, n })));
}

function PageEditor({
  docId,
  pageId,
  jump,
  onJumped,
  onPastEnd,
  suspectPages,
}: {
  docId: string;
  pageId: string;
  jump: 'first' | 'last' | null;
  onJumped: () => void;
  onPastEnd: (direction: 1 | -1) => void;
  suspectPages: number;
}) {
  const qc = useQueryClient();
  const page = useQuery({
    queryKey: ['page', docId, pageId],
    queryFn: () => getPage(docId, pageId),
  });
  const [selected, setSelected] = useState<number | null>(null);
  const [spot, setSpot] = useState<Spot | null>(null);
  const [focusTick, setFocusTick] = useState(0); // bumped when the keyboard moves between lines
  const [frameRef, frameHeight] = useViewportHeight();
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['page', docId, pageId] });
    qc.invalidateQueries({ queryKey: ['document', docId] });
  };
  const save = useMutation({
    mutationFn: ({ index, text }: { index: number; text: string }) =>
      correctLine(docId, pageId, index, text),
    onSuccess: invalidate,
  });
  const revert = useMutation({
    mutationFn: (index: number) => revertLine(docId, pageId, index),
    onSuccess: invalidate,
  });
  const ignore = useMutation({
    mutationFn: (word: string) => addToDictionary([word]),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['dictionary'] });
      qc.invalidateQueries({ queryKey: ['page', docId] });
      qc.invalidateQueries({ queryKey: ['document', docId] });
    },
  });

  const all = page.data ? spots(page.data) : [];
  // Arriving from "next suspect" on another page: land on this page's first (or last) suspect.
  if (jump && page.data) {
    const target = jump === 'first' ? all[0] : all[all.length - 1];
    if (target) {
      setSpot(target);
      setSelected(target.line);
    }
    onJumped();
  }
  const step = (direction: 1 | -1) => {
    if (all.length === 0) return onPastEnd(direction);
    const i = spot ? all.findIndex((s) => s.line === spot.line && s.n === spot.n) : -1;
    const j = i + direction;
    if (j < 0 || j >= all.length) {
      if (suspectPages > 1) return onPastEnd(direction);
      const wrapped = all[(j + all.length) % all.length];
      setSpot(wrapped);
      setSelected(wrapped.line);
      return;
    }
    setSpot(all[j]);
    setSelected(all[j].line);
  };

  if (page.isError) return <ErrorText error={page.error} />;
  if (!page.data) return <p className="text-slate-500">Loading…</p>;
  const p = page.data;
  if (!p.read || p.read.status !== 'done')
    return <p className="text-slate-600">This page has not been read yet.</p>;
  const shownLines = p.lines.filter((ln) => !ln.furniture);
  const selectedLine = selected ?? shownLines[0]?.index ?? null;
  const moveTo = (index: number) => {
    setSelected(index);
    setSpot(null);
    setFocusTick((t) => t + 1);
  };
  /** The neighbouring line in the list, for arrow keys at a line's top or bottom. */
  const moveBy = (from: number, direction: 1 | -1) => {
    const order = p.lines.map((ln) => ln.index);
    const i = order.indexOf(from) + direction;
    if (i >= 0 && i < order.length) moveTo(order[i]);
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-medium">{p.label}</span>
        <PageChips page={p} />
        <span className="ml-auto text-xs text-slate-500">
          {save.isPending
            ? 'Saving…'
            : save.isSuccess || revert.isSuccess
              ? 'Saved'
              : 'Changes save as you type'}
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-2 rounded-xl bg-white p-2 text-sm shadow-sm">
        <IconButton
          icon={ChevronsLeft}
          label="Previous suspect word"
          onClick={() => step(-1)}
          disabled={all.length === 0 && suspectPages === 0}
        />
        <IconButton
          icon={ChevronsRight}
          label="Next suspect word"
          onClick={() => step(1)}
          disabled={all.length === 0 && suspectPages === 0}
        />
        <span className="text-slate-600">
          {all.length === 0
            ? suspectPages > 0
              ? 'No suspect words on this page; some on other pages.'
              : 'No suspect words.'
            : `${plural(all.length, 'suspect word')} on this page — words the dictionary doesn’t know: a misread, a name, or fine as it is.`}
        </span>
      </div>
      <ErrorText error={save.error ?? revert.error ?? ignore.error} />
      {p.stale.length > 0 && (
        <details className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900">
          <summary className="cursor-pointer font-medium">
            {plural(p.stale.length, 'earlier correction')} no longer match
            {p.stale.length === 1 ? 'es' : ''} this page’s text — worth a look
          </summary>
          <ul className="mt-1 list-disc space-y-0.5 pl-5">
            {p.stale.map((s) => (
              <li key={s.index}>
                line {s.index + 1}: you wrote “{s.text}” for “{s.ocr}”
              </li>
            ))}
          </ul>
        </details>
      )}
      {/* On a wide screen the two columns take exactly the height left under the toolbars
          and the text scrolls inside its own box, so the page itself never scrolls: the
          navigation and the picture stay put while the text moves. */}
      <div
        ref={frameRef}
        data-testid="editor-frame"
        className="grid gap-4 lg:grid-cols-2"
        style={frameHeight ? { height: frameHeight } : undefined}
      >
        <PageViewer page={p} selected={selectedLine} onSelect={moveTo} />
        <LineList
          page={p}
          selected={selectedLine}
          spot={spot}
          focusTick={focusTick}
          onSelect={(i) => {
            setSelected(i);
            if (spot && spot.line !== i) setSpot(null);
          }}
          onMove={moveBy}
          onSave={(index, text) => save.mutate({ index, text })}
          onRevert={(index) => revert.mutate(index)}
          onIgnore={(word) => ignore.mutate(word)}
        />
      </div>
    </div>
  );
}

/** The height left between an element's top and the bottom of the window, on wide
 *  screens (null on narrow ones, where the page scrolls as usual). Re-measured when
 *  the window or the layout above changes. Takes a callback ref: the frame is only
 *  rendered once the page has loaded, so the measuring starts when it appears, not
 *  when the component mounts. */
function useViewportHeight(): [(el: HTMLDivElement | null) => void, number | null] {
  const [el, setEl] = useState<HTMLDivElement | null>(null);
  const [value, setValue] = useState<number | null>(null);
  useEffect(() => {
    if (!el) return;
    const wide = window.matchMedia('(min-width: 1024px)');
    const measure = () => {
      if (!wide.matches) {
        setValue(null);
        return;
      }
      const top = el.getBoundingClientRect().top + window.scrollY;
      setValue(Math.max(360, window.innerHeight - top - 16));
    };
    const frame = window.requestAnimationFrame(measure);
    const ro = new ResizeObserver(measure);
    ro.observe(document.body);
    window.addEventListener('resize', measure);
    wide.addEventListener('change', measure);
    return () => {
      window.cancelAnimationFrame(frame);
      ro.disconnect();
      window.removeEventListener('resize', measure);
      wide.removeEventListener('change', measure);
    };
  }, [el]);
  return [setEl, value];
}

const VIEW_KEY = 'usefultext.viewer';

interface ViewChoice {
  preset: Preset;
  /** Magnification over the preset's fit. */
  zoom: number;
}

/** The last preset and zoom, remembered per browser. */
function storedView(): ViewChoice {
  try {
    const raw = JSON.parse(localStorage.getItem(VIEW_KEY) ?? '') as Partial<ViewChoice>;
    const zoom = Number(raw.zoom);
    return {
      preset: raw.preset === 'page' ? 'page' : 'line',
      zoom: zoom >= ZOOM_MIN && zoom <= ZOOM_MAX ? zoom : 1,
    };
  } catch {
    return { preset: 'line', zoom: 1 };
  }
}

const viewerButton = 'rounded px-1.5 py-0.5 text-xs shadow disabled:opacity-40';
const viewerPlain = `${viewerButton} bg-white/85 text-slate-700 hover:bg-white`;
const viewerActive = `${viewerButton} bg-blue-600 text-white`;

/** The photo, in one panel that fills the column. "Page" fits the whole page; "Line"
 *  fits the selected line's width (a line or so of context either side, at most about
 *  three times the page fit); +/− zoom from either. The view keeps the selected line
 *  centred, so moving through the lines moves the picture, and clicking a box selects
 *  that line at any zoom. */
function PageViewer({
  page,
  selected,
  onSelect,
}: {
  page: PageDetail;
  selected: number | null;
  onSelect: (i: number) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });
  const [view, setView] = useState<ViewChoice>(storedView);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => setSize({ w: el.clientWidth, h: el.clientHeight });
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const boxes = useMemo(
    () => page.lines.map((ln) => lineBox(ln, page.regions)),
    [page.lines, page.regions]
  );
  const preview = page.read?.preview;
  const pageW = page.width ?? 1;
  const pageH = page.height ?? 1;
  const at = page.lines.findIndex((ln) => ln.index === selected);
  const box = at >= 0 ? boxes[at] : null;
  const choose = (next: ViewChoice) => {
    setView(next);
    try {
      localStorage.setItem(VIEW_KEY, JSON.stringify(next));
    } catch {
      /* a private window, or storage blocked: the choice just isn't remembered */
    }
  };
  const zoomBy = (factor: number) =>
    choose({ ...view, zoom: clamp(view.zoom * factor, ZOOM_MIN, ZOOM_MAX) });
  const pick = (preset: Preset) => choose({ preset, zoom: 1 });

  const panelClass = 'relative min-h-[45vh] overflow-hidden rounded-xl bg-white shadow-sm';
  if (!preview) {
    return (
      <div ref={ref} className={`${panelClass} flex items-center justify-center`}>
        <p className="text-sm text-slate-500">No preview for this page.</p>
      </div>
    );
  }
  const lineMode = view.preset === 'line' && box !== null;
  const fit =
    size.w > 0 && size.h > 0
      ? lineMode
        ? lineFit(box, pageW, size.w)
        : pageFit(pageW, pageH, size.w, size.h)
      : 0;
  const scale = fit * view.zoom;
  const centre: [number, number] = box
    ? [(box[0] + box[2]) / 2, (box[1] + box[3]) / 2]
    : [pageW / 2, pageH / 2];
  const vp = viewport(scale, pageW, pageH, size.w, size.h, centre);
  const placed = {
    width: pageW * scale,
    height: pageH * scale,
    left: -vp.left * scale,
    top: -vp.top * scale,
  };
  return (
    <div ref={ref} className={panelClass}>
      {scale > 0 && (
        <>
          <img
            src={preview.url}
            alt={`Page ${page.position}`}
            className="absolute max-w-none"
            style={placed}
          />
          {/* The boxes are in page pixels; the viewBox scales them with the image. */}
          <svg
            viewBox={`0 0 ${pageW} ${pageH}`}
            preserveAspectRatio="none"
            className="absolute"
            style={placed}
          >
            {boxes.map((b, i) =>
              b ? (
                <rect
                  key={i}
                  x={b[0]}
                  y={b[1]}
                  width={b[2] - b[0]}
                  height={b[3] - b[1]}
                  className={`cursor-pointer ${
                    selected === page.lines[i].index
                      ? 'fill-blue-500/25 stroke-blue-600'
                      : page.lines[i].origin === 'human'
                        ? 'fill-transparent stroke-blue-400/70'
                        : page.lines[i].suspects.length > 0
                          ? 'fill-amber-300/20 stroke-amber-500'
                          : 'fill-transparent stroke-amber-500/40'
                  }`}
                  strokeWidth={2}
                  vectorEffect="non-scaling-stroke"
                  onClick={() => onSelect(page.lines[i].index)}
                />
              ) : null
            )}
          </svg>
        </>
      )}
      <div className="absolute top-1.5 right-1.5 flex items-center gap-1">
        <button
          type="button"
          aria-pressed={view.preset === 'page'}
          title="Fit the whole page"
          className={view.preset === 'page' ? viewerActive : viewerPlain}
          onClick={() => pick('page')}
        >
          Page
        </button>
        <button
          type="button"
          aria-pressed={view.preset === 'line'}
          disabled={!box}
          title={box ? 'Fit the selected line' : 'Select a line first'}
          className={view.preset === 'line' ? viewerActive : viewerPlain}
          onClick={() => pick('line')}
        >
          Line
        </button>
        <button
          type="button"
          aria-label="Zoom out"
          title="Zoom out"
          disabled={view.zoom <= ZOOM_MIN}
          className={viewerPlain}
          onClick={() => zoomBy(1 / ZOOM_STEP)}
        >
          −
        </button>
        {view.zoom !== 1 && (
          <span className="rounded bg-white/85 px-1 text-xs text-slate-700 shadow">
            ×{view.zoom.toFixed(1)}
          </span>
        )}
        <button
          type="button"
          aria-label="Zoom in"
          title="Zoom in"
          disabled={view.zoom >= ZOOM_MAX}
          className={viewerPlain}
          onClick={() => zoomBy(ZOOM_STEP)}
        >
          +
        </button>
      </div>
    </div>
  );
}

function LineList({
  page,
  selected,
  spot,
  focusTick,
  onSelect,
  onMove,
  onSave,
  onRevert,
  onIgnore,
}: {
  page: PageDetail;
  selected: number | null;
  spot: Spot | null;
  focusTick: number;
  onSelect: (i: number) => void;
  onMove: (from: number, direction: 1 | -1) => void;
  onSave: (index: number, text: string) => void;
  onRevert: (index: number) => void;
  onIgnore: (word: string) => void;
}) {
  return (
    <ol className="min-h-0 space-y-1.5 overflow-y-auto rounded-xl bg-white p-3 shadow-sm">
      {page.lines.map((ln) => (
        <LineRow
          key={ln.index}
          line={ln}
          selected={selected === ln.index}
          focusTick={selected === ln.index ? focusTick : 0}
          focusSuspect={spot && spot.line === ln.index ? (ln.suspects[spot.n] ?? null) : null}
          onSelect={() => onSelect(ln.index)}
          onMove={(d) => onMove(ln.index, d)}
          onSave={(t) => onSave(ln.index, t)}
          onRevert={() => onRevert(ln.index)}
          onIgnore={onIgnore}
        />
      ))}
    </ol>
  );
}

function LineRow({
  line,
  selected,
  focusTick,
  focusSuspect,
  onSelect,
  onMove,
  onSave,
  onRevert,
  onIgnore,
}: {
  line: Line;
  selected: boolean;
  /** Non-zero, and changed, when the keyboard moved onto this line: take focus. */
  focusTick: number;
  /** A suspect to put the cursor on (from "next suspect"). */
  focusSuspect: Suspect | null;
  onSelect: () => void;
  onMove: (direction: 1 | -1) => void;
  onSave: (text: string) => void;
  onRevert: () => void;
  onIgnore: (word: string) => void;
}) {
  const shown = line.corrected ?? line.text;
  const [value, setValue] = useState(shown);
  const [lastShown, setLastShown] = useState(shown);
  if (shown !== lastShown) {
    // The saved text changed underneath (a revert, or another tab): show it.
    setLastShown(shown);
    setValue(shown);
  }
  const timer = useRef<number | null>(null);
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    if (selected) ref.current?.scrollIntoView({ block: 'nearest' });
  }, [selected]);
  useEffect(() => {
    if (focusTick > 0 && ref.current && document.activeElement !== ref.current) {
      ref.current.focus();
    }
  }, [focusTick]);
  useEffect(() => {
    const el = ref.current;
    if (focusSuspect && el) {
      el.focus();
      el.setSelectionRange(focusSuspect.start, focusSuspect.end);
      el.scrollIntoView({ block: 'center' });
    }
  }, [focusSuspect]);

  const change = (text: string) => {
    setValue(text);
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      if (text === line.text) {
        if (line.origin === 'human') onRevert();
      } else if (text !== (line.corrected ?? line.text)) onSave(text);
    }, 500);
  };
  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    const el = e.currentTarget;
    if (e.key === 'ArrowUp' && !el.value.slice(0, el.selectionStart).includes('\n')) {
      e.preventDefault();
      onMove(-1);
    } else if (e.key === 'ArrowDown' && !el.value.slice(el.selectionEnd).includes('\n')) {
      e.preventDefault();
      onMove(1);
    }
  };

  // The textarea and a copy of its text share one grid cell, so the copy sizes the cell
  // and the textarea grows with every wrapped or added line - no measuring. The copy's text
  // is transparent; only its highlights of suspect words show through.
  const textClass = `px-1 py-0.5 leading-snug whitespace-pre-wrap break-words ${
    line.heading ? 'text-lg font-semibold' : ''
  }`;
  return (
    <li
      className={`rounded-md border px-2 py-1 ${selected ? 'border-blue-400 bg-blue-50' : 'border-transparent'} ${line.furniture ? 'opacity-60' : ''}`}
      onClick={onSelect}
    >
      <div className="flex items-start gap-2">
        <span className="w-6 shrink-0 pt-1 text-right text-xs text-slate-400">
          {line.index + 1}
        </span>
        <div className="grid min-w-0 flex-1">
          <span
            aria-hidden="true"
            className={`pointer-events-none col-start-1 row-start-1 text-transparent select-none ${textClass}`}
          >
            {marked(value, value === shown ? line.suspects : [])}
          </span>
          <textarea
            ref={ref}
            rows={1}
            spellCheck
            value={value}
            onChange={(e) => change(e.target.value)}
            onFocus={onSelect}
            onKeyDown={onKeyDown}
            aria-label={`Line ${line.index + 1}`}
            className={`col-start-1 row-start-1 min-w-0 resize-none overflow-hidden bg-transparent focus:outline-none focus:ring-1 focus:ring-blue-300 ${textClass}`}
          />
        </div>
        <div className="flex shrink-0 items-center gap-1 pt-0.5">
          {line.furniture && (
            <span
              className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600"
              title="A running header or footer: kept out of the text"
            >
              header/footer
            </span>
          )}
          {line.origin === 'human' && (
            <>
              <span
                className="rounded bg-blue-100 px-1.5 py-0.5 text-xs text-blue-800"
                title={`The engine read: ${line.text}`}
              >
                edited
              </span>
              <IconButton
                icon={RotateCcw}
                label="Revert to what the engine read"
                onClick={onRevert}
              />
            </>
          )}
        </div>
      </div>
      {line.suspects.length > 0 && value === shown && (
        <div className="mt-0.5 ml-8 flex flex-wrap items-center gap-2 text-xs text-slate-600">
          {[...new Set(line.suspects.map((s) => s.word))].map((word) => (
            <span key={word} className="inline-flex items-center gap-1">
              <span className="rounded bg-amber-100 px-1.5 py-0.5 text-amber-900">{word}</span>
              <button
                type="button"
                className="text-blue-700 hover:underline"
                title="Fine as it is — never flag this word again in this library"
                onClick={(e) => {
                  e.stopPropagation();
                  onIgnore(word);
                }}
              >
                ignore
              </button>
            </span>
          ))}
        </div>
      )}
    </li>
  );
}

/** The text with its suspects wrapped in <mark>, for the sizing copy behind the textarea. */
function marked(text: string, suspects: Suspect[]) {
  if (suspects.length === 0) return text + ' ';
  const parts = [];
  let at = 0;
  for (const s of [...suspects].sort((a, b) => a.start - b.start)) {
    if (s.start < at) continue;
    parts.push(text.slice(at, s.start));
    parts.push(
      <mark key={s.start} className="rounded-sm bg-amber-200 text-transparent">
        {text.slice(s.start, s.end)}
      </mark>
    );
    at = s.end;
  }
  parts.push(text.slice(at) + ' ');
  return parts;
}
