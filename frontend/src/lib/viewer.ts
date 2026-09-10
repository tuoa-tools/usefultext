/** Geometry for the editor's picture panel: what scale fits the page or a line into the
 *  panel, and where the panel's window onto the page sits for a given centre. */
import type { Box } from './boxes';

export type Preset = 'page' | 'line';

export const ZOOM_STEP = 1.25;
export const ZOOM_MIN = 0.5;
export const ZOOM_MAX = 8;

export function clamp(v: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, v));
}

/** Panel pixels per page pixel that show the whole page. */
export function pageFit(pageW: number, pageH: number, panelW: number, panelH: number): number {
  return Math.min(panelW / pageW, panelH / pageH);
}

/** Panel pixels per page pixel that show the line's full width plus a margin, but never
 *  magnify past about three times the page-width fit — a two-word heading would otherwise
 *  fill the panel with a few letters. */
export function lineFit(box: Box, pageW: number, panelW: number): number {
  const boxW = box[2] - box[0];
  const viewW = Math.min(pageW, Math.max(boxW * 1.1 + pageW * 0.02, pageW * 0.35));
  return panelW / viewW;
}

export interface Viewport {
  scale: number;
  /** Page coordinates at the panel's top-left corner; negative when the page is smaller
   *  than the panel on that axis and sits centred with a margin. */
  left: number;
  top: number;
}

/** The panel's window onto the page at `scale`, centred on `centre` where the page is
 *  larger than the panel and clamped to the page's edges. */
export function viewport(
  scale: number,
  pageW: number,
  pageH: number,
  panelW: number,
  panelH: number,
  centre: [number, number]
): Viewport {
  const viewW = panelW / scale;
  const viewH = panelH / scale;
  const left =
    viewW >= pageW ? -(viewW - pageW) / 2 : clamp(centre[0] - viewW / 2, 0, pageW - viewW);
  const top =
    viewH >= pageH ? -(viewH - pageH) / 2 : clamp(centre[1] - viewH / 2, 0, pageH - viewH);
  return { scale, left, top };
}
