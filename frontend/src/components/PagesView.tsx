import { useMutation, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, Eye, EyeOff, FolderInput, GripVertical, Upload, X } from 'lucide-react';
import { useRef, useState, type DragEvent } from 'react';
import {
  addFiles,
  addPath,
  adoptFiles,
  setPages,
  sortPages,
  type Document,
  type JobWarning,
  type Page,
} from '../api';
import { ACCEPT, filesFromDataTransfer, filesFromInput } from '../lib/files';
import { useNativeDialogs } from '../lib/native';
import { plural, quality } from '../lib/format';
import { moveItem } from '../lib/pages';
import type { Route } from '../lib/route';
import { compactInputClass } from '../lib/ui';
import ActionButton from './ActionButton';
import ErrorText from './ErrorText';
import IconButton from './IconButton';

export default function PagesView({
  doc,
  navigate,
}: {
  doc: Document;
  navigate: (r: Route) => void;
}) {
  const qc = useQueryClient();
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['document', doc.id] });
    qc.invalidateQueries({ queryKey: ['library'] });
  };
  const active = doc.status === 'running' || doc.status === 'queued';
  const [replaceTarget, setReplaceTarget] = useState<string | null>(null);
  const replaceInput = useRef<HTMLInputElement>(null);

  const add = useMutation({
    mutationFn: ({ files, replace }: { files: File[]; replace?: string }) =>
      addFiles(doc.id, files, replace),
    onSuccess: invalidate,
  });
  const addFolder = useMutation({
    mutationFn: ({ path, move }: { path: string; move: boolean | null }) =>
      addPath(doc.id, path, move),
    onSuccess: invalidate,
  });
  /** Paths from the window's dialogs, one at a time; copied or moved as Settings says. */
  const addPaths = useMutation({
    mutationFn: async (paths: string[]) => {
      for (const p of paths) await addPath(doc.id, p, null);
    },
    onSuccess: invalidate,
  });
  const adopt = useMutation({
    mutationFn: (files: string[]) => adoptFiles(doc.id, files),
    onSuccess: invalidate,
  });
  const order = useMutation({
    mutationFn: (pages: { id: string; excluded: boolean }[]) => setPages(doc.id, pages),
    onSuccess: invalidate,
  });
  const sort = useMutation({
    mutationFn: (by: 'name' | 'time' | 'printed') => sortPages(doc.id, by),
    onSuccess: invalidate,
  });

  const pages = doc.pages;
  const update = (next: Page[]) =>
    order.mutate(next.map((p) => ({ id: p.id, excluded: p.excluded })));
  const toggle = (id: string) =>
    update(pages.map((p) => (p.id === id ? { ...p, excluded: !p.excluded } : p)));
  const remove = (page: Page) => {
    if (window.confirm(`Remove ${page.label} from the document? The photo stays in the folder.`))
      update(pages.filter((p) => p.id !== page.id));
  };
  const error =
    add.error ?? addFolder.error ?? addPaths.error ?? adopt.error ?? order.error ?? sort.error;

  return (
    <div className="space-y-4">
      {active ? (
        <p className="rounded-md bg-slate-100 px-4 py-2 text-sm text-slate-600">
          Pause the document to add, reorder or remove pages.
        </p>
      ) : (
        <AddArea
          onPaths={(paths) => addPaths.mutate(paths)}
          pending={add.isPending || addFolder.isPending}
          onFiles={(files) => add.mutate({ files })}
          onFolder={(path, move) => addFolder.mutate({ path, move })}
          defaultMove={false}
        />
      )}
      <ErrorText error={error} />
      {sort.data?.notes?.length ? (
        <ul className="rounded-md bg-slate-100 px-4 py-2 text-sm text-slate-700">
          {sort.data.notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      ) : null}
      <Warnings warnings={doc.warnings} />
      {doc.stray_files.length > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-md bg-amber-50 px-4 py-2 text-sm text-amber-900">
          <span>
            {plural(doc.stray_files.length, 'photo')} in this folder{' '}
            {doc.stray_files.length === 1 ? 'is' : 'are'} not part of the document:{' '}
            {doc.stray_files.map((f) => f.replace(/^photos\//, '')).join(', ')}
          </span>
          {!active && (
            <ActionButton
              icon={FolderInput}
              label="Add them"
              onClick={() => adopt.mutate(doc.stray_files)}
              disabled={adopt.isPending}
            />
          )}
        </div>
      )}

      {pages.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-slate-600">Sort by</span>
          <button
            type="button"
            className="rounded-md border border-slate-200 bg-white px-2.5 py-1 hover:bg-slate-50 disabled:opacity-50"
            disabled={active}
            onClick={() => sort.mutate('name')}
          >
            file name
          </button>
          <button
            type="button"
            className="rounded-md border border-slate-200 bg-white px-2.5 py-1 hover:bg-slate-50 disabled:opacity-50"
            disabled={active}
            onClick={() => sort.mutate('time')}
          >
            time taken
          </button>
          <button
            type="button"
            className="rounded-md border border-slate-200 bg-white px-2.5 py-1 hover:bg-slate-50 disabled:opacity-50"
            disabled={active || doc.read === 0}
            title={
              doc.read === 0
                ? 'Available once the pages have been read'
                : 'The page numbers printed on the pages'
            }
            onClick={() => sort.mutate('printed')}
          >
            printed page number
          </button>
          <span className="ml-auto text-slate-500">Drag a page to move it.</span>
        </div>
      )}

      <PageList
        pages={pages}
        disabled={active || order.isPending}
        onReorder={(from, to) => update(moveItem(pages, from, to))}
        onToggle={toggle}
        onRemove={remove}
        onReplace={(id) => {
          setReplaceTarget(id);
          replaceInput.current?.click();
        }}
        onOpen={(id) => navigate({ view: 'document', id: doc.id, tab: 'editor', pageId: id })}
      />
      <input
        ref={replaceInput}
        type="file"
        accept={ACCEPT}
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f && replaceTarget) add.mutate({ files: [f], replace: replaceTarget });
          e.target.value = '';
          setReplaceTarget(null);
        }}
      />
    </div>
  );
}

function AddArea({
  pending,
  onFiles,
  onFolder,
  onPaths,
  defaultMove,
}: {
  pending: boolean;
  onFiles: (files: File[]) => void;
  onFolder: (path: string, move: boolean | null) => void;
  onPaths: (paths: string[]) => void;
  defaultMove: boolean;
}) {
  const native = useNativeDialogs();
  const input = useRef<HTMLInputElement>(null);
  const folderInput = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [showFolder, setShowFolder] = useState(false);
  const [path, setPath] = useState('');
  const [move, setMove] = useState(defaultMove);
  const onDrop = async (e: DragEvent) => {
    e.preventDefault();
    setOver(false);
    const { files } = await filesFromDataTransfer(e.dataTransfer);
    if (files.length) onFiles(files);
  };
  const pick = (list: FileList | null) => {
    const { files } = filesFromInput(list);
    if (files.length) onFiles(files);
  };
  return (
    <div className="space-y-2">
      <div
        role="button"
        tabIndex={0}
        onClick={() => input.current?.click()}
        onKeyDown={(e) => e.key === 'Enter' && input.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={onDrop}
        className={`cursor-pointer rounded-xl border-2 border-dashed p-6 text-center transition ${
          over ? 'border-blue-500 bg-blue-50' : 'border-slate-300 bg-white hover:bg-slate-50'
        }`}
      >
        <Upload className="mx-auto h-6 w-6 text-slate-500" aria-hidden="true" />
        <p className="mt-2 font-medium">
          {pending ? 'Adding to your library…' : 'Drop page photos here, or click to choose them'}
        </p>
        <p className="text-sm text-slate-500">
          JPEG, PNG, HEIC, TIFF, WebP or PDF — or a whole folder.{' '}
          {native
            ? `Files chosen below are ${defaultMove ? 'moved' : 'copied'} into this document’s folder (Settings decides which); dropped ones are copied.`
            : 'They are copied into this document’s folder.'}
        </p>
        <input
          ref={input}
          type="file"
          multiple
          accept={ACCEPT}
          className="hidden"
          onChange={(e) => {
            pick(e.target.files);
            e.target.value = '';
          }}
        />
        <input
          ref={folderInput}
          type="file"
          // @ts-expect-error webkitdirectory is a real attribute browsers honour
          webkitdirectory=""
          className="hidden"
          onChange={(e) => {
            pick(e.target.files);
            e.target.value = '';
          }}
        />
      </div>
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <button
          type="button"
          className="text-blue-700 hover:underline"
          onClick={async () => {
            if (!native) return folderInput.current?.click();
            const chosen = await native.pick_folder();
            if (chosen) onPaths([chosen]);
          }}
        >
          Choose a folder…
        </button>
        {native ? (
          <button
            type="button"
            className="text-blue-700 hover:underline"
            onClick={async () => {
              const chosen = await native.pick_files();
              if (chosen.length) onPaths(chosen);
            }}
          >
            Choose photos or PDFs…
          </button>
        ) : (
          <button
            type="button"
            className="text-blue-700 hover:underline"
            onClick={() => setShowFolder((v) => !v)}
          >
            {showFolder
              ? 'Hide the path box'
              : 'Or type a folder’s path (the only way to move rather than copy)…'}
          </button>
        )}
      </div>
      {showFolder && !native && (
        <form
          className="flex flex-wrap items-center gap-2 rounded-md bg-white p-3 shadow-sm"
          onSubmit={(e) => {
            e.preventDefault();
            if (path.trim()) onFolder(path.trim(), move);
          }}
        >
          <input
            className={`${compactInputClass} flex-1`}
            placeholder="/Users/you/Pictures/scans"
            value={path}
            onChange={(e) => setPath(e.target.value)}
          />
          <label className="inline-flex items-center gap-1.5">
            <input type="checkbox" checked={move} onChange={(e) => setMove(e.target.checked)} />{' '}
            move instead of copy
          </label>
          <button
            type="submit"
            disabled={!path.trim() || pending}
            className="rounded-md bg-blue-600 px-3 py-1.5 font-semibold text-white disabled:opacity-50"
          >
            Add
          </button>
        </form>
      )}
    </div>
  );
}

const KIND_LABEL: Record<JobWarning['kind'], string> = {
  retake: 'Consider retaking',
  duplicate: 'Possible repeat',
  printed_duplicate: 'Page number twice',
  printed_gap: 'Page number missing',
};

function Warnings({ warnings }: { warnings: JobWarning[] }) {
  if (warnings.length === 0) return null;
  return (
    <div className="rounded-xl border border-amber-200 bg-amber-50 p-3">
      <h3 className="mb-1 flex items-center gap-1.5 text-sm font-semibold text-amber-900">
        <AlertTriangle className="h-4 w-4" aria-hidden="true" /> {plural(warnings.length, 'thing')}{' '}
        to look at
      </h3>
      <ul className="space-y-1 text-sm text-amber-900">
        {warnings.map((w, i) => (
          <li key={i}>
            <span className="mr-1 rounded bg-amber-100 px-1.5 py-0.5 text-xs font-medium">
              {KIND_LABEL[w.kind]}
            </span>
            {w.message}
          </li>
        ))}
      </ul>
    </div>
  );
}

function PageList({
  pages,
  disabled,
  onReorder,
  onToggle,
  onRemove,
  onReplace,
  onOpen,
}: {
  pages: Page[];
  disabled: boolean;
  onReorder: (from: number, to: number) => void;
  onToggle: (id: string) => void;
  onRemove: (page: Page) => void;
  onReplace: (id: string) => void;
  onOpen: (id: string) => void;
}) {
  const [dragging, setDragging] = useState<number | null>(null);
  const [overIndex, setOverIndex] = useState<number | null>(null);
  if (pages.length === 0) return null;
  return (
    <ol className="space-y-1.5" aria-label="Pages">
      {pages.map((page, i) => (
        <li
          key={page.id}
          draggable={!disabled}
          onDragStart={() => setDragging(i)}
          onDragOver={(e) => {
            e.preventDefault();
            setOverIndex(i);
          }}
          onDragLeave={() => setOverIndex(null)}
          onDrop={(e) => {
            e.preventDefault();
            if (dragging !== null && dragging !== i) onReorder(dragging, i);
            setDragging(null);
            setOverIndex(null);
          }}
          onDragEnd={() => {
            setDragging(null);
            setOverIndex(null);
          }}
          className={`flex items-center gap-3 rounded-xl bg-white p-2 shadow-sm ${page.excluded ? 'opacity-60' : ''} ${
            overIndex === i && dragging !== i ? 'ring-2 ring-blue-400' : ''
          }`}
        >
          <GripVertical
            className={`h-5 w-5 shrink-0 ${disabled ? 'text-slate-200' : 'cursor-grab text-slate-400'}`}
            aria-hidden="true"
          />
          <span className="w-8 shrink-0 text-center text-sm font-semibold text-slate-500">
            {page.position ?? '–'}
          </span>
          <button
            type="button"
            onClick={() => page.read && onOpen(page.id)}
            className="shrink-0"
            title={page.read ? 'Open in the editor' : 'Not read yet'}
          >
            <img
              src={page.thumb}
              alt=""
              className="h-16 w-12 rounded object-cover"
              loading="lazy"
            />
          </button>
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-medium">{page.label}</div>
            <PageChips page={page} />
          </div>
          <IconButton
            icon={Upload}
            label="Replace with a retake"
            onClick={() => onReplace(page.id)}
            disabled={disabled}
          />
          <IconButton
            icon={page.excluded ? EyeOff : Eye}
            label={page.excluded ? 'Include this page' : 'Leave this page out'}
            onClick={() => onToggle(page.id)}
            disabled={disabled}
          />
          <IconButton
            icon={X}
            label="Remove from the document"
            tone="danger"
            onClick={() => onRemove(page)}
            disabled={disabled}
          />
        </li>
      ))}
    </ol>
  );
}

function Chip({
  tone,
  children,
}: {
  tone: 'grey' | 'amber' | 'red' | 'green' | 'blue';
  children: React.ReactNode;
}) {
  const tones = {
    grey: 'bg-slate-100 text-slate-700',
    amber: 'bg-amber-100 text-amber-900',
    red: 'bg-red-100 text-red-800',
    green: 'bg-green-100 text-green-800',
    blue: 'bg-blue-100 text-blue-800',
  };
  return <span className={`rounded px-1.5 py-0.5 text-xs ${tones[tone]}`}>{children}</span>;
}

export function PageChips({ page }: { page: Page }) {
  const r = page.read;
  return (
    <div className="mt-0.5 flex flex-wrap gap-1">
      {page.excluded && <Chip tone="grey">left out</Chip>}
      {page.replaced_from && <Chip tone="blue">retake</Chip>}
      {!r && page.blurry && <Chip tone="amber">looks blurry</Chip>}
      {r?.status === 'error' && <Chip tone="red">could not be read</Chip>}
      {r?.status === 'done' && (
        <>
          <Chip tone={r.low_conf ? 'red' : 'green'}>read quality {quality(r.mean_conf)}</Chip>
          {r.blurry && <Chip tone="amber">looks blurry</Chip>}
          {r.rotation ? <Chip tone="grey">rotated {r.rotation}°</Chip> : null}
          {r.columns > 1 && <Chip tone="grey">{r.columns} columns</Chip>}
          {r.printed_page !== null && <Chip tone="grey">printed p. {r.printed_page}</Chip>}
          {r.corrected > 0 && <Chip tone="blue">{plural(r.corrected, 'line')} corrected</Chip>}
          {r.stale > 0 && <Chip tone="amber">{plural(r.stale, 'correction')} to check</Chip>}
          {r.suspects > 0 && <Chip tone="amber">{plural(r.suspects, 'suspect word')}</Chip>}
        </>
      )}
    </div>
  );
}
