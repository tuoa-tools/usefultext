/** Files dropped or chosen in the browser: folders unpacked, unsupported ones left out. */

export const SUPPORTED = [
  'jpg',
  'jpeg',
  'png',
  'heic',
  'heif',
  'tif',
  'tiff',
  'bmp',
  'webp',
  'pdf',
];
export const ACCEPT = SUPPORTED.map((e) => `.${e}`).join(',');

export function isSupported(name: string): boolean {
  const ext = name.split('.').pop()?.toLowerCase() ?? '';
  return !name.startsWith('.') && SUPPORTED.includes(ext);
}

export function stem(name: string): string {
  return name.replace(/\.[^.]+$/, '');
}

function byName(a: File, b: File): number {
  return a.name.localeCompare(b.name, undefined, { numeric: true });
}

async function readEntry(entry: FileSystemEntry): Promise<File[]> {
  if (entry.isFile) {
    const file = await new Promise<File>((resolve, reject) =>
      (entry as FileSystemFileEntry).file(resolve, reject)
    );
    return [file];
  }
  if (entry.isDirectory) {
    const reader = (entry as FileSystemDirectoryEntry).createReader();
    const out: File[] = [];
    for (;;) {
      const batch = await new Promise<FileSystemEntry[]>((resolve, reject) =>
        reader.readEntries(resolve, reject)
      );
      if (batch.length === 0) break;
      for (const e of batch) out.push(...(await readEntry(e)));
    }
    return out;
  }
  return [];
}

export interface Dropped {
  files: File[];
  /** The folder's name when a whole folder was dropped or chosen. */
  folder: string | null;
}

/** What a drop contained. A dropped folder is walked (its name is kept for the title). */
export async function filesFromDataTransfer(dt: DataTransfer): Promise<Dropped> {
  const entries = Array.from(dt.items ?? [])
    .map((item) => (item.webkitGetAsEntry ? item.webkitGetAsEntry() : null))
    .filter((e): e is FileSystemEntry => e !== null);
  const folders = entries.filter((e) => e.isDirectory);
  if (folders.length === 0) return { files: keep(Array.from(dt.files)), folder: null };
  const files: File[] = [];
  for (const e of entries) files.push(...(await readEntry(e)));
  return { files: keep(files), folder: folders.length === 1 ? folders[0].name : null };
}

/** What a file input gave, with the folder's name when it was a folder picker. */
export function filesFromInput(list: FileList | null): Dropped {
  const files = Array.from(list ?? []);
  const rel = files[0]?.webkitRelativePath;
  const folder = rel && rel.includes('/') ? rel.split('/')[0] : null;
  return { files: keep(files), folder };
}

function keep(files: File[]): File[] {
  return files.filter((f) => isSupported(f.name)).sort(byName);
}

/** A name for a document made from dropped photos; a person can rename it any time. */
export function suggestTitle(dropped: Dropped, now: Date = new Date()): string {
  if (dropped.folder) return dropped.folder;
  if (dropped.files.length === 1) return stem(dropped.files[0].name);
  const day = now.toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
  return `${dropped.files.length} pages, ${day}`;
}
