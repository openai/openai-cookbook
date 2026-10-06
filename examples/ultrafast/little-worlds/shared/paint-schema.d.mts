export type PaintConfig = {
  action: string;
  columns: number;
  rows: number;
  color: number;
  colorValue: string;
  palette?: string[];
  background?: string;
};
export function validatePaintConfig(value: unknown, raster?: boolean): PaintConfig;
export function validatePaintPixels(pixels: unknown, config: PaintConfig): string;
export const paintValidationCode: string;
