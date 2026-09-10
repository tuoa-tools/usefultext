import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { FolderOpen, Plus, Trash2, Upload } from 'lucide-react';
import { useRef, useState, type DragEvent } from 'react';
import {
  addFiles,
  createDocument,
  getLibrary,
  removeDocument,
  revealDocument,
  type DocumentSummary,
} from '../api';
import {
  ACCEPT,
  filesFromDataTransfer,
  filesFromInput,
  suggestTitle,
  type Dropped,
} from '../lib/files';
import { plural, shortDate, statusLabel, statusTone } from '../lib/format';
import { compactInputClass } from '../lib/ui';
import ActionButton from './ActionButton';
import ErrorText from './ErrorText';
import IconButton from './IconButton';

export default function LibraryView({ onOpen }: { onOpen: (id: string) => void }) {
  const qc = useQueryClient();
  const library = useQuery({
    queryKey: ['library'],
    queryFn: getLibrary,
    refetchInterval: (q) =>
      q.state.data?.documents.some((d) => d.status === 'running' || d.status === 'queued')
        ? 2000
        : 15_000,
  });
  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState('');
  const create = useMutation({
    mutationFn: () => createDocument(title.trim()),
    onSuccess: (doc) => {
      qc.invalidateQueries({ queryKey: ['library'] });
      setCreating(false);
      setTitle('');
      onOpen(doc.id);
    },
  });
  /** Photos first, name later: the document is named after them and can be renamed any time. */
  const fromFiles = useMutation({
    mutationFn: async (dropped: Dropped) => {
      const doc = await createDocument(suggestTitle(dropped));
      await addFiles(doc.id, dropped.files);
      return doc;
    },
    onSuccess: (doc) => {
      qc.invalidateQueries({ queryKey: ['library'] });
      onOpen(doc.id);
    },
  });
  const remove = useMutation({
    mutationFn: removeDocument,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['library'] }),
  });
  const reveal = useMutation({ mutationFn: revealDocument });

  const docs = library.data?.documents ?? [];
  return (
    <section className="space-y-4">
      <DropToCreate pending={fromFiles.isPending} onDropped={(d) => fromFiles.mutate(d)} />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-xl font-semibold">Your library</h2>
        <ActionButton
          icon={Plus}
          label="New document (name first)"
          onClick={() => setCreating(true)}
        />
      </div>
      {creating && (
        <form
          className="flex flex-wrap gap-2 rounded-xl bg-white p-4 shadow-sm"
          onSubmit={(e) => {
            e.preventDefault();
            if (title.trim()) create.mutate();
          }}
        >
          <input
            autoFocus
            className={`${compactInputClass} flex-1`}
            placeholder="What is this document? (e.g. Our Iceberg Is Melting)"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <button
            type="submit"
            disabled={!title.trim() || create.isPending}
            className="rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
          >
            Create
          </button>
          <button
            type="button"
            onClick={() => setCreating(false)}
            className="rounded-md px-3 py-2 text-sm text-slate-600 hover:bg-slate-100"
          >
            Cancel
          </button>
          <ErrorText error={create.error} />
        </form>
      )}
      <ErrorText error={library.error ?? remove.error ?? fromFiles.error} />
      {library.isSuccess && docs.length === 0 && !creating && (
        <p className="text-center text-sm text-slate-500">
          Nothing here yet. Drop a document’s photos above to start.
        </p>
      )}
      <ul className="space-y-2">
        {docs.map((d) => (
          <DocumentRow
            key={d.id}
            doc={d}
            onOpen={() => onOpen(d.id)}
            onReveal={() => reveal.mutate(d.id)}
            onRemove={() => {
              if (
                window.confirm(
                  `Remove “${d.title}” from your library?\n\nIts folder (${d.folder}) goes to the trash, photos and text included, and can be recovered from there.`
                )
              )
                remove.mutate(d.id);
            }}
          />
        ))}
      </ul>
    </section>
  );
}

function DropToCreate({
  pending,
  onDropped,
}: {
  pending: boolean;
  onDropped: (d: Dropped) => void;
}) {
  const [over, setOver] = useState(false);
  const files = useRef<HTMLInputElement>(null);
  const folder = useRef<HTMLInputElement>(null);
  const onDrop = async (e: DragEvent) => {
    e.preventDefault();
    setOver(false);
    const dropped = await filesFromDataTransfer(e.dataTransfer);
    if (dropped.files.length) onDropped(dropped);
  };
  const pick = (list: FileList | null) => {
    const dropped = filesFromInput(list);
    if (dropped.files.length) onDropped(dropped);
  };
  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={onDrop}
      className={`rounded-xl border-2 border-dashed p-5 text-center transition ${
        over ? 'border-blue-500 bg-blue-50' : 'border-slate-300 bg-white'
      }`}
    >
      <Upload className="mx-auto h-6 w-6 text-slate-500" aria-hidden="true" />
      <p className="mt-2 font-medium">
        {pending ? 'Adding to your library…' : 'Drop the photos of a document here to start one'}
      </p>
      <p className="text-sm text-slate-500">
        A folder, or the page photos themselves. It is named after them; rename it any time.
      </p>
      <div className="mt-2 flex flex-wrap justify-center gap-3 text-sm">
        <button
          type="button"
          className="text-blue-700 hover:underline"
          onClick={() => files.current?.click()}
        >
          Choose photos…
        </button>
        <button
          type="button"
          className="text-blue-700 hover:underline"
          onClick={() => folder.current?.click()}
        >
          Choose a folder…
        </button>
      </div>
      <input
        ref={files}
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
        ref={folder}
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
  );
}

function DocumentRow({
  doc,
  onOpen,
  onReveal,
  onRemove,
}: {
  doc: DocumentSummary;
  onOpen: () => void;
  onReveal: () => void;
  onRemove: () => void;
}) {
  const attention = doc.low_conf + doc.blurry + doc.errors;
  return (
    <li className="flex items-center gap-3 rounded-xl bg-white p-3 shadow-sm">
      <button type="button" onClick={onOpen} className="min-w-0 flex-1 text-left">
        <div className="flex flex-wrap items-center gap-2">
          <span className="truncate text-base font-semibold hover:underline">{doc.title}</span>
          <span
            className={`rounded-full px-2 py-0.5 text-xs font-medium ${statusTone(doc.status)}`}
          >
            {statusLabel(doc.status)}
          </span>
        </div>
        <div className="mt-0.5 text-sm text-slate-600">
          {doc.included === 0
            ? 'No pages yet'
            : `${doc.read} of ${plural(doc.included, 'page')} read`}
          {attention > 0 && (
            <span className="text-amber-800"> · {plural(attention, 'page')} to look at</span>
          )}
          {doc.corrected_lines > 0 && (
            <span> · {plural(doc.corrected_lines, 'line')} corrected</span>
          )}
          {doc.updated_at && <span className="text-slate-400"> · {shortDate(doc.updated_at)}</span>}
        </div>
      </button>
      <IconButton icon={FolderOpen} label="Open folder" onClick={onReveal} />
      <IconButton icon={Trash2} label="Remove from library" tone="danger" onClick={onRemove} />
    </li>
  );
}
