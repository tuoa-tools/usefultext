import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { getSettings, saveSettings, type AddMode, type AppSettings } from '../api';
import { compactInputClass } from '../lib/ui';
import ErrorText from './ErrorText';

export default function SettingsPanel({ onSaved }: { onSaved?: () => void }) {
  const settings = useQuery({ queryKey: ['settings'], queryFn: getSettings });
  if (settings.isError) return <ErrorText error={settings.error} />;
  if (!settings.data) return <p className="text-slate-500">Loading…</p>;
  return <SettingsForm initial={settings.data} onSaved={onSaved} />;
}

function SettingsForm({ initial, onSaved }: { initial: AppSettings; onSaved?: () => void }) {
  const qc = useQueryClient();
  const [libraryDir, setLibraryDir] = useState(initial.library_dir ?? initial.default_library_dir);
  const [addMode, setAddMode] = useState<AddMode>(initial.add_mode);
  const [pdfDpi, setPdfDpi] = useState(String(initial.pdf_dpi));
  const [minConf, setMinConf] = useState(String(initial.min_page_conf));
  const [blur, setBlur] = useState(String(initial.blur_threshold));

  const save = useMutation({
    mutationFn: () =>
      saveSettings({
        library_dir: libraryDir,
        add_mode: addMode,
        pdf_dpi: Number(pdfDpi),
        min_page_conf: Number(minConf),
        blur_threshold: Number(blur),
      }),
    onSuccess: () => {
      qc.invalidateQueries();
      onSaved?.();
    },
  });

  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      <label className="block">
        <span className="text-sm font-medium">Library folder</span>
        <input
          className={compactInputClass}
          value={libraryDir}
          onChange={(e) => setLibraryDir(e.target.value)}
        />
        <span className="text-xs text-slate-500">
          One sub-folder per document. Move it later and everything comes along.
        </span>
      </label>
      <fieldset>
        <legend className="text-sm font-medium">When adding files from a folder</legend>
        {(['copy', 'move'] as AddMode[]).map((mode) => (
          <label key={mode} className="mr-4 inline-flex items-center gap-1.5 text-sm">
            <input
              type="radio"
              name="add_mode"
              checked={addMode === mode}
              onChange={() => setAddMode(mode)}
            />
            {mode === 'copy' ? 'Copy them into the library' : 'Move them into the library'}
          </label>
        ))}
      </fieldset>
      <div className="grid gap-3 sm:grid-cols-3">
        <label className="block">
          <span className="text-sm font-medium">PDF resolution (dpi)</span>
          <input
            className={compactInputClass}
            type="number"
            min={72}
            max={600}
            value={pdfDpi}
            onChange={(e) => setPdfDpi(e.target.value)}
          />
        </label>
        <label className="block">
          <span className="text-sm font-medium">Read-quality gate</span>
          <input
            className={compactInputClass}
            type="number"
            min={0}
            max={1}
            step={0.05}
            value={minConf}
            onChange={(e) => setMinConf(e.target.value)}
          />
          <span className="text-xs text-slate-500">Pages below this are flagged.</span>
        </label>
        <label className="block">
          <span className="text-sm font-medium">Blur threshold</span>
          <input
            className={compactInputClass}
            type="number"
            min={0}
            step={5}
            value={blur}
            onChange={(e) => setBlur(e.target.value)}
          />
          <span className="text-xs text-slate-500">Sharpness below this looks blurry.</span>
        </label>
      </div>
      <ErrorText error={save.error} />
      <div className="flex items-center gap-3">
        <button
          type="submit"
          disabled={save.isPending}
          className="rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
        >
          Save
        </button>
        {save.isSuccess && <span className="text-sm text-green-700">Saved.</span>}
      </div>
    </form>
  );
}
