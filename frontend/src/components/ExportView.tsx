import { useMutation } from '@tanstack/react-query';
import { ClipboardCopy, Download, FolderOpen } from 'lucide-react';
import { exportUrl, getPlainText, revealDocument, type Document, type ExportKind } from '../api';
import { plural } from '../lib/format';
import ActionButton from './ActionButton';
import ErrorText from './ErrorText';

const DOWNLOADS: { kind: ExportKind; label: string; note: string }[] = [
  {
    kind: 'md',
    label: 'Markdown (.md)',
    note: 'All pages with headings, page markers and notes on pages that read poorly.',
  },
  {
    kind: 'txt',
    label: 'Plain text (.txt)',
    note: 'All pages with a simple separator between them.',
  },
  {
    kind: 'pages.zip',
    label: 'One file per page (.zip)',
    note: 'Named by position and photo; the first line says where each came from.',
  },
  {
    kind: 'jsonl',
    label: 'Every line as data (.jsonl)',
    note: 'For programs: text, position on the page, read quality, corrections.',
  },
  {
    kind: 'csv',
    label: 'Page report (.csv)',
    note: 'One row per page: read quality, blur, rotation, printed page number.',
  },
  {
    kind: 'docx',
    label: 'Word (.docx)',
    note: 'Headings, paragraphs and a page break between pages; notes on pages that read poorly.',
  },
];

export default function ExportView({ doc }: { doc: Document }) {
  const copy = useMutation({
    mutationFn: async () => {
      const text = await getPlainText(doc.id);
      await navigator.clipboard.writeText(text);
      return text.length;
    },
  });
  const reveal = useMutation({ mutationFn: () => revealDocument(doc.id) });
  const unread = doc.included - doc.read;
  return (
    <div className="space-y-4">
      {unread > 0 && (
        <p className="rounded-md bg-amber-50 px-4 py-2 text-sm text-amber-900">
          {plural(unread, 'page')} {unread === 1 ? 'has' : 'have'} not been read yet; the exports
          cover the {plural(doc.read, 'page')} that {doc.read === 1 ? 'has' : 'have'}.
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2 rounded-xl bg-white p-4 shadow-sm">
        <ActionButton
          icon={ClipboardCopy}
          label={copy.isPending ? 'Copying…' : 'Copy all the text'}
          tone="primary"
          onClick={() => copy.mutate()}
          disabled={copy.isPending}
          large
        />
        <ActionButton
          icon={FolderOpen}
          label="Open the document’s folder"
          onClick={() => reveal.mutate()}
        />
        {copy.isSuccess && (
          <span className="text-sm text-green-700">
            Copied {copy.data.toLocaleString()} characters.
          </span>
        )}
        <ErrorText error={copy.error ?? reveal.error} />
      </div>
      <ul className="space-y-2">
        {DOWNLOADS.map((d) => (
          <li key={d.kind} className="flex items-center gap-3 rounded-xl bg-white p-3 shadow-sm">
            <a
              href={exportUrl(doc.id, d.kind)}
              download
              className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-sm font-medium hover:bg-slate-100"
            >
              <Download className="h-4 w-4" aria-hidden="true" /> {d.label}
            </a>
            <span className="text-sm text-slate-600">{d.note}</span>
          </li>
        ))}
      </ul>
      <p className="text-xs text-slate-500">
        Every export uses your corrections. Read quality is the engine’s own certainty, never a
        measure of accuracy.
      </p>
    </div>
  );
}
