export type GameJson = null | boolean | number | string | GameJson[] | { [key: string]: GameJson };

export type GameActor = { id: string; name: string };
export type GameConfig = { id: string; tickMs?: number; saveAction?: string; exportName?: string };
export type GameState = { [key: string]: GameJson; actorId: string };

type GameShapeBase = {
  id: string;
  x?: number;
  y?: number;
  rotation?: number;
  fill?: string;
  stroke?: string;
  lineWidth?: number;
};

export type GameShape = GameShapeBase & (
  | { type: 'rect'; width: number; height: number; radius?: number }
  | { type: 'circle'; radius: number }
  | { type: 'path'; d: string }
  | { type: 'text'; text: string; fontSize?: number; align?: 'left' | 'center' | 'right' }
);

export type GameView = {
  width: number;
  height: number;
  background?: string;
  objects: GameShape[];
  values?: Record<string, string | number>;
  finished?: boolean;
};

export type GamePayload = {
  revisionId: number;
  config: GameConfig;
  bundle: string;
  actor: GameActor;
  saved: GameState | null;
};

export function validateGameConfig(config: unknown): GameConfig;
export function gameConfigs(meta: { game?: GameConfig; games?: GameConfig[] } | null | undefined): GameConfig[];
export function validateGameState(state: unknown, actor: GameActor): GameState;
export function validateGameView(view: unknown): GameView;
export const gameValidationCode: string;
