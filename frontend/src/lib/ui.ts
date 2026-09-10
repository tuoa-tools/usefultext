export const inputClass =
  'w-full rounded-md border border-slate-300 bg-white p-3 text-base focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200';

/** The same field, a little shorter - for dialogs where several sit side by side. */
export const compactInputClass =
  'w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-base focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200';

/** An underline tab: quiet when inactive, a blue rule when active. */
export function tabClass(active: boolean): string {
  return `-mb-px border-b-2 px-1 pb-1.5 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-40 ${
    active
      ? 'border-blue-600 text-blue-700'
      : 'border-transparent text-slate-600 hover:border-slate-300 hover:text-slate-900'
  }`;
}

/** A bordered button beside an input ("Choose…"). */
export const headerButton =
  'rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium hover:bg-slate-50';

/** The app bar's quiet text buttons. */
export const ghostButton =
  'rounded-md px-2.5 py-1 text-sm font-medium text-slate-600 hover:bg-slate-200/70 hover:text-slate-900';
