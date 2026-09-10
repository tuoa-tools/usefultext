import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useState } from 'react';
import { getHealth, getSettings, saveSettings, setNativeToken } from './api';
import DocumentView from './components/DocumentView';
import ErrorText from './components/ErrorText';
import HelpPanel from './components/HelpPanel';
import LibraryView from './components/LibraryView';
import Modal from './components/Modal';
import SettingsPanel from './components/SettingsPanel';
import StatusBar, { QuitButton } from './components/StatusBar';
import { useNativeDialogs } from './lib/native';
import { useRoute } from './lib/route';
import { compactInputClass, ghostButton, headerButton } from './lib/ui';

type Panel = 'settings' | 'help' | null;

export default function App() {
  const [route, navigate] = useRoute();
  const [panel, setPanel] = useState<Panel>(null);
  const closePanel = useCallback(() => setPanel(null), []);
  const qc = useQueryClient();
  const native = useNativeDialogs();
  // Inside the desktop window, take the launch secret from the bridge and send it as a
  // header from now on; anything that failed for want of the cookie is asked again.
  useEffect(() => {
    if (!native) return;
    let cancelled = false;
    native
      .token()
      .then((token) => {
        if (cancelled || !token) return;
        setNativeToken(token);
        qc.invalidateQueries();
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [native, qc]);
  // Also the keep-alive: in desktop mode with a browser tab, two minutes without this
  // ping (and nothing being read) tells the server the tab is gone and it exits.
  const health = useQuery({
    queryKey: ['health'],
    queryFn: getHealth,
    refetchInterval: 60_000,
    refetchIntervalInBackground: true,
  });

  return (
    <main
      className={`mx-auto w-full space-y-3 px-4 py-3 sm:px-6 ${
        route.view === 'document' && route.tab === 'editor' ? 'max-w-[1500px]' : 'max-w-5xl'
      }`}
    >
      {/* One quiet bar: the wordmark is the way home, the rest stays out of the way. */}
      <header className="flex items-center justify-between gap-3">
        <button
          type="button"
          onClick={() => navigate({ view: 'library' })}
          className="text-lg font-semibold tracking-tight"
        >
          UsefulText
        </button>
        <div className="flex gap-1">
          <button type="button" onClick={() => setPanel('settings')} className={ghostButton}>
            Settings
          </button>
          <button type="button" onClick={() => setPanel('help')} className={ghostButton}>
            Help
          </button>
          <QuitButton />
        </div>
      </header>

      <StatusBar />
      {panel === 'settings' && (
        <Modal title="Settings" onClose={closePanel} wide>
          <SettingsPanel onSaved={closePanel} />
        </Modal>
      )}
      {panel === 'help' && (
        <Modal title="Help" onClose={closePanel}>
          <HelpPanel />
        </Modal>
      )}

      {health.isPending ? (
        <p className="text-slate-500">Loading…</p>
      ) : health.data?.first_run ? (
        <FirstRun />
      ) : route.view === 'library' ? (
        <LibraryView onOpen={(id) => navigate({ view: 'document', id, tab: 'pages' })} />
      ) : (
        <DocumentView route={route} navigate={navigate} />
      )}
    </main>
  );
}

/** The one-time choice of a library folder; nothing else works until it is made. */
function FirstRun() {
  const settings = useQuery({ queryKey: ['settings'], queryFn: getSettings });
  if (settings.isError) return <ErrorText error={settings.error} />;
  if (!settings.data) return <p className="text-slate-500">Loading…</p>;
  return <FirstRunForm suggested={settings.data.default_library_dir} />;
}

function FirstRunForm({ suggested }: { suggested: string }) {
  const qc = useQueryClient();
  const [dir, setDir] = useState(suggested);
  const native = useNativeDialogs();
  const save = useMutation({
    mutationFn: () => saveSettings({ library_dir: dir }),
    onSuccess: () => qc.invalidateQueries(),
  });
  return (
    <form
      className="space-y-4 rounded-xl bg-white p-6 shadow-md"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      <h2 className="text-xl font-semibold">Welcome. Where should your library live?</h2>
      <p className="text-slate-600">
        Every document you read becomes a folder here, with its photos, its text and your
        corrections. You can move the folder later.
      </p>
      <div className="flex gap-2">
        <input
          className={`${compactInputClass} flex-1`}
          value={dir}
          onChange={(e) => setDir(e.target.value)}
          aria-label="Library folder"
        />
        {native && (
          <button
            type="button"
            className={headerButton}
            onClick={async () => {
              const chosen = await native.pick_folder();
              if (chosen) setDir(chosen);
            }}
          >
            Choose…
          </button>
        )}
      </div>
      <ErrorText error={save.error} />
      <button
        type="submit"
        disabled={!dir.trim() || save.isPending}
        className="rounded-md bg-blue-600 px-4 py-2 font-semibold text-white disabled:opacity-50"
      >
        Use this folder
      </button>
    </form>
  );
}
