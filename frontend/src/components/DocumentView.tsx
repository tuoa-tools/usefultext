import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronLeft, Pause, Pencil, Play, RotateCcw } from 'lucide-react';
import { getDocument, pauseDocument, startDocument, updateDocument, type Document } from '../api';
import { formatEta, plural, quality, statusLabel, statusTone } from '../lib/format';
import type { Route, Tab } from '../lib/route';
import { tabClass } from '../lib/ui';
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
        <IconButton
          icon={ChevronLeft}
          label="Back to the library"
          onClick={() => navigate({ view: 'library' })}
          small
        />
        <ErrorText error={doc.error} />
      </section>
    );
  }
  if (!doc.data) return <p className="text-slate-500">Loading…</p>;
  const d = doc.data;
  const active = d.status === 'running' || d.status === 'queued';
  const setTab = (tab: Tab) => navigate({ view: 'document', id: route.id, tab });

  return (
    <section className="space-y-3">
      {/* One row: the way back, the name, where it stands, and what to do next. */}
      <div className="flex flex-wrap items-center gap-2">
        <IconButton
          icon={ChevronLeft}
          label="Back to the library"
          onClick={() => navigate({ view: 'library' })}
          small
        />
        <h2 className="min-w-0 truncate text-xl font-semibold">{d.title}</h2>
        <IconButton
          icon={Pencil}
          label="Rename"
          small
          onClick={() => {
            const title = window.prompt('Document name', d.title);
            if (title && title.trim() && title.trim() !== d.title) rename.mutate(title.trim());
          }}
        />
        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${statusTone(d.status)}`}>
          {statusLabel(d.status)}
        </span>
        <span className="text-sm text-slate-500">
          {d.included === 0 ? 'No pages yet' : `${d.read} of ${plural(d.included, 'page')} read`}
          {d.total_pages > d.included && ` · ${d.total_pages - d.included} excluded`}
          {d.low_conf + d.blurry + d.errors > 0 && (
            <span className="text-amber-800">
              {' '}
              · {plural(d.low_conf + d.blurry + d.errors, 'page')} to look at
            </span>
          )}
          {d.corrected_lines > 0 && ` · ${plural(d.corrected_lines, 'line')} corrected`}
        </span>
        <div className="ml-auto">
          <ReadControls
            doc={d}
            onStart={(force) => start.mutate(force)}
            onPause={() => pause.mutate()}
            busy={start.isPending || pause.isPending}
          />
        </div>
      </div>
      <ErrorText error={start.error ?? pause.error ?? rename.error} />
      {d.last_run?.error && (
        <p role="alert" className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-800">
          The last read stopped with an error: {d.last_run.error}
        </p>
      )}
      {active && d.progress && <ProgressBar doc={d} />}

      <nav className="flex gap-5 border-b border-slate-200" aria-label="View">
        <button
          type="button"
          className={tabClass(route.tab === 'pages')}
          onClick={() => setTab('pages')}
        >
          Pages
        </button>
        <button
          type="button"
          className={tabClass(route.tab === 'editor')}
          onClick={() => setTab('editor')}
          disabled={d.read === 0}
        >
          Editor
        </button>
        <button
          type="button"
          className={tabClass(route.tab === 'export')}
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
        />
      )}
      {s === 'new' && (
        <ActionButton
          icon={Play}
          label="Start reading"
          tone="primary"
          onClick={() => onStart(false)}
          disabled={busy || !canStart}
        />
      )}
      {(s === 'paused' || s === 'error') && (
        <ActionButton
          icon={Play}
          label={s === 'error' ? 'Try again' : 'Resume'}
          tone="primary"
          onClick={() => onStart(false)}
          disabled={busy || !canStart}
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
    <div className="space-y-1" aria-live="polite">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 text-xs text-slate-600">
        <span>
          <span className="font-medium text-slate-800">
            {p.status === 'queued'
              ? 'Waiting for the engine…'
              : `Reading page ${Math.min(p.done + 1, p.total)} of ${p.total}`}
          </span>
          {p.current && p.status === 'running' && ` · ${p.current}`}
          {last && (
            <>
              {' '}
              · last: {last.label},{' '}
              {last.status === 'error'
                ? `could not be read (${last.error})`
                : `read quality ${quality(last.mean_conf)}`}
              {last.rotation ? `, rotated ${last.rotation}°` : ''}
              {last.blurry ? ', looks blurry' : ''}
              {last.low_conf ? ', low read quality' : ''}
            </>
          )}
        </span>
        <span>{formatEta(p.eta_seconds)}</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-slate-200">
        <div className="h-full bg-blue-600 transition-all" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
