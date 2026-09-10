import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronLeft, Pause, Pencil, Play, RotateCcw } from 'lucide-react';
import { getDocument, pauseDocument, startDocument, updateDocument, type Document } from '../api';
import { formatEta, plural, quality, statusLabel, statusTone } from '../lib/format';
import type { Route, Tab } from '../lib/route';
import { segmentClass } from '../lib/ui';
import ActionButton from './ActionButton';
import EditorView from './EditorView';
import ErrorText from './ErrorText';
import ExportView from './ExportView';
import IconButton from './IconButton';
import PagesView from './PagesView';

type DocRoute = Extract<Route, { view: 'document' }>;

function useDocument(id: string) {
  return useQuery({
    queryKey: ['document', id],
    queryFn: () => getDocument(id),
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s === 'running' || s === 'queued' ? 1000 : 10_000;
    },
  });
}

export default function DocumentView({
  route,
  navigate,
}: {
  route: DocRoute;
  navigate: (r: Route) => void;
}) {
  const qc = useQueryClient();
  const doc = useDocument(route.id);
  const invalidate = () => qc.invalidateQueries({ queryKey: ['document', route.id] });
  const start = useMutation({
    mutationFn: (force: boolean) => startDocument(route.id, force),
    onSuccess: invalidate,
  });
  const pause = useMutation({ mutationFn: () => pauseDocument(route.id), onSuccess: invalidate });
  const rename = useMutation({
    mutationFn: (title: string) => updateDocument(route.id, { title }),
    onSuccess: () => {
      invalidate();
      qc.invalidateQueries({ queryKey: ['library'] });
    },
  });

  if (doc.isError) {
    return (
      <section className="space-y-3">
        <BackLink navigate={navigate} />
        <ErrorText error={doc.error} />
      </section>
    );
  }
  if (!doc.data) return <p className="text-slate-500">Loading…</p>;
  const d = doc.data;
  const active = d.status === 'running' || d.status === 'queued';
  const setTab = (tab: Tab) => navigate({ view: 'document', id: route.id, tab });

  return (
    <section className="space-y-4">
      <BackLink navigate={navigate} />
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h2 className="truncate text-2xl font-semibold">{d.title}</h2>
            <IconButton
              icon={Pencil}
              label="Rename"
              onClick={() => {
                const title = window.prompt('Document name', d.title);
                if (title && title.trim() && title.trim() !== d.title) rename.mutate(title.trim());
              }}
            />
            <span
              className={`rounded-full px-2 py-0.5 text-xs font-medium ${statusTone(d.status)}`}
            >
              {statusLabel(d.status)}
            </span>
          </div>
          <p className="text-sm text-slate-600">
            {d.included === 0 ? 'No pages yet' : `${d.read} of ${plural(d.included, 'page')} read`}
            {d.total_pages > d.included && ` · ${d.total_pages - d.included} excluded`}
            {d.low_conf + d.blurry + d.errors > 0 && (
              <span className="text-amber-800">
                {' '}
                · {plural(d.low_conf + d.blurry + d.errors, 'page')} to look at
              </span>
            )}
            {d.corrected_lines > 0 && ` · ${plural(d.corrected_lines, 'line')} corrected`}
          </p>
        </div>
        <ReadControls
          doc={d}
          onStart={(force) => start.mutate(force)}
          onPause={() => pause.mutate()}
          busy={start.isPending || pause.isPending}
        />
      </div>
      <ErrorText error={start.error ?? pause.error ?? rename.error} />
      {d.last_run?.error && (
        <p role="alert" className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-800">
          The last read stopped with an error: {d.last_run.error}
        </p>
      )}
      {active && d.progress && <ProgressBar doc={d} />}

      <nav className="flex gap-2 rounded-lg bg-slate-200 p-1" aria-label="View">
        <button
          type="button"
          className={segmentClass(route.tab === 'pages')}
          onClick={() => setTab('pages')}
        >
          Pages
        </button>
        <button
          type="button"
          className={segmentClass(route.tab === 'editor')}
          onClick={() => setTab('editor')}
          disabled={d.read === 0}
        >
          Editor
        </button>
        <button
          type="button"
          className={segmentClass(route.tab === 'export')}
          onClick={() => setTab('export')}
          disabled={d.read === 0}
        >
          Export
        </button>
      </nav>

      {route.tab === 'pages' && <PagesView doc={d} navigate={navigate} />}
      {route.tab === 'editor' && <EditorView doc={d} route={route} navigate={navigate} />}
      {route.tab === 'export' && <ExportView doc={d} />}
    </section>
  );
}

function BackLink({ navigate }: { navigate: (r: Route) => void }) {
  return (
    <button
      type="button"
      onClick={() => navigate({ view: 'library' })}
      className="inline-flex items-center gap-1 text-sm text-slate-600 hover:text-slate-900"
    >
      <ChevronLeft className="h-4 w-4" aria-hidden="true" /> Library
    </button>
  );
}

/** One play/pause-style button whose label follows the state, plus "Read again". */
function ReadControls({
  doc,
  onStart,
  onPause,
  busy,
}: {
  doc: Document;
  onStart: (force: boolean) => void;
  onPause: () => void;
  busy: boolean;
}) {
  const s = doc.status;
  const canStart = doc.included > 0;
  return (
    <div className="flex flex-wrap items-center gap-2">
      {(s === 'running' || s === 'queued') && (
        <ActionButton
          icon={Pause}
          label={s === 'queued' ? 'Waiting… Pause' : 'Pause'}
          onClick={onPause}
          disabled={busy}
          large
        />
      )}
      {s === 'new' && (
        <ActionButton
          icon={Play}
          label="Start reading"
          tone="primary"
          onClick={() => onStart(false)}
          disabled={busy || !canStart}
          large
        />
      )}
      {(s === 'paused' || s === 'error') && (
        <ActionButton
          icon={Play}
          label={s === 'error' ? 'Try again' : 'Resume'}
          tone="primary"
          onClick={() => onStart(false)}
          disabled={busy || !canStart}
          large
        />
      )}
      {doc.read > 0 && s !== 'running' && s !== 'queued' && (
        <ActionButton
          icon={RotateCcw}
          label="Read again"
          onClick={() => {
            const kept =
              doc.corrected_lines > 0
                ? `\n\nYour ${plural(doc.corrected_lines, 'corrected line')} will be kept wherever the text reads the same, and listed as needing a look where it doesn’t.`
                : '';
            if (
              window.confirm(
                `Read all ${plural(doc.included, 'page')} again from the photos?${kept}`
              )
            )
              onStart(true);
          }}
          disabled={busy}
        />
      )}
    </div>
  );
}

function ProgressBar({ doc }: { doc: Document }) {
  const p = doc.progress!;
  const pct = p.total ? Math.round((p.done / p.total) * 100) : 0;
  const last = p.last_page;
  return (
    <div className="space-y-2 rounded-xl bg-white p-4 shadow-sm" aria-live="polite">
      <div className="flex flex-wrap items-baseline justify-between gap-2 text-sm">
        <span className="font-medium">
          {p.status === 'queued'
            ? 'Waiting for the engine…'
            : `Reading page ${Math.min(p.done + 1, p.total)} of ${p.total}`}
          {p.current && p.status === 'running' && (
            <span className="text-slate-500"> · {p.current}</span>
          )}
        </span>
        <span className="text-slate-600">{formatEta(p.eta_seconds)}</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-slate-200">
        <div className="h-full bg-blue-600 transition-all" style={{ width: `${pct}%` }} />
      </div>
      {last && (
        <p className="text-xs text-slate-600">
          Last page: {last.label} ·{' '}
          {last.status === 'error'
            ? `could not be read (${last.error})`
            : `read quality ${quality(last.mean_conf)}`}
          {last.rotation ? ` · rotated ${last.rotation}°` : ''}
          {last.blurry ? ' · looks blurry' : ''}
          {last.low_conf ? ' · low read quality' : ''}
        </p>
      )}
    </div>
  );
}
