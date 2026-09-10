import type { LucideIcon } from 'lucide-react';

const TONES = {
  default: 'border-slate-200 text-slate-600 hover:bg-slate-100 hover:text-slate-900',
  primary: 'border-blue-200 text-blue-700 hover:bg-blue-50',
  danger: 'border-red-200 text-red-600 hover:bg-red-50',
};

/** A square icon button; the label is its tooltip and its accessible name. */
export default function IconButton({
  icon: Icon,
  label,
  onClick,
  disabled = false,
  tone = 'default',
}: {
  icon: LucideIcon;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  tone?: keyof typeof TONES;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      title={label}
      className={`inline-flex h-9 w-9 items-center justify-center rounded-md border bg-white disabled:cursor-not-allowed disabled:opacity-50 ${TONES[tone]}`}
    >
      <Icon className="h-5 w-5" aria-hidden="true" />
    </button>
  );
}
