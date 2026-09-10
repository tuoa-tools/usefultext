import type { LucideIcon } from 'lucide-react';

const TONES = {
  default: 'border-slate-200 text-slate-700 hover:bg-slate-100',
  primary: 'border-blue-600 bg-blue-600 text-white hover:bg-blue-700',
  danger: 'border-red-200 text-red-700 hover:bg-red-50',
};

/** A small button with an icon *and* a word - icons alone are a gamble for a non-technical user. */
export default function ActionButton({
  icon: Icon,
  label,
  onClick,
  disabled = false,
  tone = 'default',
  large = false,
}: {
  icon: LucideIcon;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  tone?: keyof typeof TONES;
  large?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex items-center gap-1.5 rounded-md border font-medium disabled:cursor-not-allowed disabled:opacity-50 ${
        large ? 'px-4 py-2.5 text-base' : 'px-2.5 py-1.5 text-sm'
      } ${tone === 'primary' ? '' : 'bg-white'} ${TONES[tone]}`}
    >
      <Icon className={large ? 'h-5 w-5' : 'h-4 w-4'} aria-hidden="true" />
      {label}
    </button>
  );
}
