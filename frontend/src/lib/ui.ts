export const inputClass =
  'w-full rounded-md border border-slate-300 bg-white p-3 text-base focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200';

/** The same field, a little shorter - for dialogs where several sit side by side. */
export const compactInputClass =
  'w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-base focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200';

export function segmentClass(active: boolean): string {
  return `flex-1 rounded-md px-4 py-3 text-base font-medium transition ${
    active ? 'bg-blue-600 text-white shadow' : 'bg-white text-slate-700 hover:bg-slate-50'
  }`;
}

export const headerButton =
  'rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium hover:bg-slate-50';
