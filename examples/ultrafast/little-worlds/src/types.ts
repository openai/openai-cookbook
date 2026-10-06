export interface PersonaProfile { role: string; tagline: string; theme: string }
export interface Actor { id: string; name: string; profile?: PersonaProfile }
export interface SignedIn { user: Actor; ownSpaceId: string; simulated?: boolean }
export interface SpaceIcon { status: 'empty' | 'generating' | 'ready' | 'error'; source?: 'generated' | 'upload'; version?: string; dataUrl?: string; lightDataUrl?: string; error?: string }
export interface SpaceAppearance { lightCss: string; presentationCss?: string }
export interface AccountPerson extends Actor { ownSpaceId: string; icon?: SpaceIcon }
export interface SpaceSummary { id: string; owner: Actor; kind: 'studio' | 'blank'; revisionId: number; hasBuilt: boolean; profile?: PersonaProfile; icon?: SpaceIcon; appearance?: SpaceAppearance }
export interface SavedTurn { id: string; message: string; status: string; startedAt: string; revisionId?: number }
export interface Project { id: string; title: string; description: string; color: string }
export interface Contribution { id: string; actorId: string; projectId: string; points: number }
export interface SpaceState { projects: Project[]; contributions: Contribution[]; extras: Record<string, unknown> }
export interface Check { name: string; ok: boolean; message?: string }
export interface Revision { id: number; title: string; createdAt: string; source: string; tests: string; checks: Check[]; meta?: {title?: string; layout?: string; persona?: string; capabilities?: string[]; game?: import('../shared/game-schema.mjs').GameConfig; games?: import('../shared/game-schema.mjs').GameConfig[]; suggestions?: Array<{label: string; prompt: string}>} }
export type Stage = 'inspect' | 'build' | 'verify' | 'publish';
export interface RuntimeEvent {
  id: string; type: string; time: string; turnId?: string; stage?: Stage;
  title: string; detail?: string; durationMs?: number; data?: Record<string, unknown>;
}
export interface Snapshot {
  state: SpaceState; revision: Revision; html: string; actor: Actor;
  session: { id?: string; status: string; turnCount?: number; lastMessage?: string; turns?: SavedTurn[] };
  config: { model: string; requestedTier: string; reasoningEffort: string; keyAvailable: boolean; adapter: string };
  events: RuntimeEvent[];
  space: SpaceSummary;
  permissions: { canEdit: boolean; canViewRuntime: boolean };
}
