import type { Line, Region } from '../api';

export type Box = [number, number, number, number];

/** The box round all of a line's regions, in page pixels; null for a line with no regions. */
export function lineBox(line: Line, regions: readonly Region[]): Box | null {
  const boxes = line.regions.map((i) => regions[i]?.bbox).filter((b): b is Box => !!b);
  if (boxes.length === 0) return null;
  return [
    Math.min(...boxes.map((b) => b[0])),
    Math.min(...boxes.map((b) => b[1])),
    Math.max(...boxes.map((b) => b[2])),
    Math.max(...boxes.map((b) => b[3])),
  ];
}
