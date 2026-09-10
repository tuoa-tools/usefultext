import { useMutation, useQuery } from '@tanstack/react-query';
import { getHealth, quitApp } from '../api';
import { ghostButton } from '../lib/ui';

/** Engine and library notices, and the "has quit" screen. */
export default function StatusBar() {
  const health = useQuery({
    queryKey: ['health'],
    queryFn: getHealth,
    refetchInterval: (query) => (query.state.data?.engine.state === 'loading' ? 2000 : 60_000),
  });
  const h = health.data;

  if (h?.quit_requested) {
    return (
      <div className="rounded-xl bg-white p-8 text-center shadow-md">
        <h2 className="text-xl font-semibold">UsefulText has quit</h2>
        <p className="mt-2 text-slate-600">
          You can close this tab. Open the app again from its icon.
        </p>
      </div>
    );
  }
  return (
    <>
      {h?.engine.state === 'loading' && (
        <p className="rounded-md bg-slate-100 px-4 py-2 text-sm text-slate-600">
          Loading the reading engine… reading starts once it’s ready.
        </p>
      )}
      {h?.engine.state === 'failed' && (
        <p role="alert" className="rounded-md bg-red-100 px-4 py-2 text-sm text-red-800">
          The reading engine isn’t working: {h.engine.error}. Try reinstalling the app.
        </p>
      )}
      {h?.library_error && (
        <p role="alert" className="rounded-md bg-amber-50 px-4 py-2 text-sm text-amber-900">
          {h.library_error} Choose another folder in Settings.
        </p>
      )}
      {h && !h.heif && (
        <p className="rounded-md bg-amber-50 px-4 py-2 text-sm text-amber-900">
          HEIC photos (iPhone) can’t be opened on this machine: {h.heif_error}
        </p>
      )}
    </>
  );
}

export function QuitButton() {
  const health = useQuery({ queryKey: ['health'], queryFn: getHealth });
  const quit = useMutation({ mutationFn: quitApp });
  if (!health.data?.desktop) return null;
  return (
    <button
      type="button"
      onClick={() => {
        if (window.confirm('Quit UsefulText? Reading in progress will pause; resume it next time.'))
          quit.mutate();
      }}
      className={ghostButton}
    >
      Quit
    </button>
  );
}
