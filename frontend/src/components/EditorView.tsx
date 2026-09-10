import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronLeft, ChevronRight, RotateCcw, SkipBack, SkipForward } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  correctLine,
  getPage,
  revertLine,
  type Document,
  type Line,
  type PageDetail,
} from '../api';
import { lineBox } from '../lib/boxes';
import { plural } from '../lib/format';
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
      <PageEditor key={pageId} docId={doc.id} pageId={pageId} />
    </div>
  );
}

function PageEditor({ docId, pageId }: { docId: string; pageId: string }) {
  const qc = useQueryClient();
  const page = useQuery({
    queryKey: ['page', docId, pageId],
    queryFn: () => getPage(docId, pageId),
  });
  const [selected, setSelected] = useState<number | null>(null);
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

  if (page.isError) return <ErrorText error={page.error} />;
  if (!page.data) return <p className="text-slate-500">Loading…</p>;
  const p = page.data;
  if (!p.read || p.read.status !== 'done')
    return <p className="text-slate-600">This page has not been read yet.</p>;

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
      <ErrorText error={save.error ?? revert.error} />
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
      <div className="grid gap-4 lg:grid-cols-2">
        <PagePreview page={p} selected={selected} onSelect={setSelected} />
        <LineList
          page={p}
          selected={selected}
          onSelect={setSelected}
          onSave={(index, text) => save.mutate({ index, text })}
          onRevert={(index) => revert.mutate(index)}
        />
      </div>
    </div>
  );
}

function PagePreview({
  page,
  selected,
  onSelect,
}: {
  page: PageDetail;
  selected: number | null;
  onSelect: (i: number) => void;
}) {
  const preview = page.read?.preview;
  const w = page.width ?? 1;
  const h = page.height ?? 1;
  const boxes = useMemo(
    () => page.lines.map((ln) => lineBox(ln, page.regions)),
    [page.lines, page.regions]
  );
  if (!preview) return <p className="text-slate-500">No preview for this page.</p>;
  return (
    <div className="relative self-start overflow-hidden rounded-xl bg-white shadow-sm">
      <img src={preview.url} alt={`Page ${page.position}`} className="block w-full" />
      {/* The boxes are in page pixels; the viewBox scales them with the image. */}
      <svg
        viewBox={`0 0 ${w} ${h}`}
        className="absolute inset-0 h-full w-full"
        preserveAspectRatio="none"
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
                selected === i
                  ? 'fill-blue-500/25 stroke-blue-600'
                  : page.lines[i].origin === 'human'
                    ? 'fill-transparent stroke-blue-400/70'
                    : 'fill-transparent stroke-amber-500/60'
              }`}
              strokeWidth={Math.max(2, w / 400)}
              onClick={() => onSelect(i)}
            />
          ) : null
        )}
      </svg>
    </div>
  );
}

function LineList({
  page,
  selected,
  onSelect,
  onSave,
  onRevert,
}: {
  page: PageDetail;
  selected: number | null;
  onSelect: (i: number) => void;
  onSave: (index: number, text: string) => void;
  onRevert: (index: number) => void;
}) {
  return (
    <ol className="space-y-1.5 self-start rounded-xl bg-white p-3 shadow-sm">
      {page.lines.map((ln) => (
        <LineRow
          key={ln.index}
          line={ln}
          selected={selected === ln.index}
          onSelect={() => onSelect(ln.index)}
          onSave={(t) => onSave(ln.index, t)}
          onRevert={() => onRevert(ln.index)}
        />
      ))}
    </ol>
  );
}

function LineRow({
  line,
  selected,
  onSelect,
  onSave,
  onRevert,
}: {
  line: Line;
  selected: boolean;
  onSelect: () => void;
  onSave: (text: string) => void;
  onRevert: () => void;
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

  const change = (text: string) => {
    setValue(text);
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      if (text === line.text) {
        if (line.origin === 'human') onRevert();
      } else if (text !== (line.corrected ?? line.text)) onSave(text);
    }, 500);
  };

  // The textarea and an invisible copy of its text share one grid cell, so the copy
  // sizes the cell and the textarea grows with every wrapped or added line - no measuring.
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
          <span aria-hidden="true" className={`invisible col-start-1 row-start-1 ${textClass}`}>
            {value + ' '}
          </span>
          <textarea
            ref={ref}
            rows={1}
            spellCheck
            value={value}
            onChange={(e) => change(e.target.value)}
            onFocus={onSelect}
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
    </li>
  );
}
