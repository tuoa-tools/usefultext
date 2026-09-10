import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useState } from 'react';
import { getHealth, getSettings, saveSettings } from './api';
import DocumentView from './components/DocumentView';
import ErrorText from './components/ErrorText';
import HelpPanel from './components/HelpPanel';
import LibraryView from './components/LibraryView';
import Modal from './components/Modal';
import SettingsPanel from './components/SettingsPanel';
import StatusBar, { QuitButton } from './components/StatusBar';
import { useRoute } from './lib/route';
import { compactInputClass, headerButton } from './lib/ui';

type Panel = 'settings' | 'help' | null;

export default function App() {
  const [route, navigate] = useRoute();
  const [panel, setPanel] = useState<Panel>(null);
  const closePanel = useCallback(() => setPanel(null), []);
  const health = useQuery({ queryKey: ['health'], queryFn: getHealth });

  return (
    <main className="mx-auto w-full max-w-5xl space-y-5 p-4 sm:p-6">
      <header className="flex items-center justify-between">
        <button
          type="button"
          onClick={() => navigate({ view: 'library' })}
          className="text-3xl font-bold"
        >
          UsefulText
        </button>
        <div className="flex gap-2">
          <button type="button" onClick={() => setPanel('settings')} className={headerButton}>
            Settings
          </button>
          <button type="button" onClick={() => setPanel('help')} className={headerButton}>
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
  if (!settings.data) return <p className="text-slate-500">Loading…</p>;
  return <FirstRunForm suggested={settings.data.default_library_dir} />;
}

function FirstRunForm({ suggested }: { suggested: string }) {
  const qc = useQueryClient();
  const [dir, setDir] = useState(suggested);
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
      <input
        className={compactInputClass}
        value={dir}
        onChange={(e) => setDir(e.target.value)}
        aria-label="Library folder"
      />
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
