import type { DocStatus } from '../api';

export function formatEta(seconds: number | null | undefined): string {
  if (seconds == null) return '';
  if (seconds < 45) return 'under a minute left';
  const minutes = Math.round(seconds / 60);
  return minutes <= 1 ? 'about a minute left' : `about ${minutes} minutes left`;
}

export function statusLabel(status: DocStatus): string {
  switch (status) {
    case 'new':
      return 'Not read yet';
    case 'queued':
      return 'Waiting';
    case 'running':
      return 'Reading';
    case 'paused':
      return 'Partly read';
    case 'done':
      return 'Read';
    case 'error':
      return 'Something went wrong';
  }
}

export function statusTone(status: DocStatus): string {
  switch (status) {
    case 'running':
    case 'queued':
      return 'bg-blue-100 text-blue-800';
    case 'done':
      return 'bg-green-100 text-green-800';
    case 'paused':
      return 'bg-amber-100 text-amber-900';
    case 'error':
      return 'bg-red-100 text-red-800';
    default:
      return 'bg-slate-200 text-slate-700';
  }
}

/** Read quality is the engine's own certainty - shown as it is, never as "accuracy". */
export function quality(conf: number): string {
  return conf.toFixed(2);
}

export function plural(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}

export function shortDate(iso: string): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
}
