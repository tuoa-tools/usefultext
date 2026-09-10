/** The desktop window (pywebview) puts native dialogs on window.pywebview.api; a browser
 *  tab has none, and the UI falls back to the browser's own pickers and a typed path. */
import { useEffect, useState } from 'react';

export interface NativeDialogs {
  /** A folder chosen in the OS dialog, or null if the person cancelled. */
  pick_folder(): Promise<string | null>;
  /** Photo and PDF paths chosen in the OS dialog; empty if cancelled. */
  pick_files(): Promise<string[]>;
  /** The launch secret, to send as a header (see api.ts setNativeToken). */
  token(): Promise<string>;
}

declare global {
  interface Window {
    pywebview?: { api: NativeDialogs };
  }
}

export function nativeDialogs(): NativeDialogs | null {
  return typeof window === 'undefined' ? null : (window.pywebview?.api ?? null);
}

/** The window's dialogs once the bridge is ready (pywebview announces it after load). */
export function useNativeDialogs(): NativeDialogs | null {
  const [api, setApi] = useState(nativeDialogs);
  useEffect(() => {
    if (api) return;
    const ready = () => setApi(nativeDialogs());
    window.addEventListener('pywebviewready', ready);
    return () => window.removeEventListener('pywebviewready', ready);
  }, [api]);
  return api;
}

/** The last path segment, for naming a document after the folder or file chosen. */
export function baseName(path: string): string {
  const parts = path.replace(/[\\/]+$/, '').split(/[\\/]/);
  return parts[parts.length - 1] || path;
}

/** A document title for paths from the dialog: the folder's or file's name, or a count. */
export function titleForPaths(paths: string[], now: Date = new Date()): string {
  if (paths.length === 1) return baseName(paths[0]).replace(/\.[A-Za-z0-9]{2,5}$/, '');
  const day = now.toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
  return `${paths.length} pages, ${day}`;
}
