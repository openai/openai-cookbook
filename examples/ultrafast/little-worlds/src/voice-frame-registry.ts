export type FrameVoiceAction = {
  type: 'click' | 'fill' | 'select' | 'press' | 'scroll';
  id: string;
  value?: string;
  key?: string;
  direction?: 'up' | 'down' | 'left' | 'right';
  amount?: number;
};

export type FrameVoiceControl = {
  id: string;
  label: string;
  role: string;
  context?: string;
  value?: string;
  checked?: boolean;
  expanded?: boolean;
  type?: string;
  min?: number;
  max?: number;
  step?: number;
  disabled: boolean;
  options?: { value: string; label: string }[];
  actions: FrameVoiceAction['type'][];
};

export type FrameVoiceSurface = { version: number; controls: FrameVoiceControl[]; text: string };
export type FrameVoiceViewport = { top: number; left: number; width: number; height: number };
export type FrameVoiceResult = { ok: boolean; message: string };
export type VoiceFrame = {
  read(): Promise<FrameVoiceSurface>;
  execute(action: FrameVoiceAction, version: number): Promise<FrameVoiceResult>;
};

let current: VoiceFrame | undefined;

/** Only the currently mounted published frame can receive voice requests. */
export function registerVoiceFrame(frame: VoiceFrame): () => void {
  current = frame;
  return () => { if (current === frame) current = undefined; };
}

export function getVoiceFrame(): VoiceFrame | undefined { return current; }
