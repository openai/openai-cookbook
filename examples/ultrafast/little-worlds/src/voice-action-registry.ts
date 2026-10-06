import type { VoiceActionResult } from './live-voice';

type VoiceActionHandler = () => Promise<VoiceActionResult>;
const actions = new WeakMap<HTMLElement, VoiceActionHandler>();
const forms = new WeakMap<HTMLFormElement, VoiceActionHandler>();

/** Host controls can expose their real completion result to the voice surface. */
export function registerVoiceAction(element: HTMLElement, handler: VoiceActionHandler): () => void {
  actions.set(element, handler);
  return () => { if (actions.get(element) === handler) actions.delete(element); };
}

export function getVoiceAction(element: HTMLElement): VoiceActionHandler | undefined {
  return actions.get(element);
}

/** Native form submissions can report when the app accepts or rejects them. */
export function registerVoiceForm(form: HTMLFormElement, handler: VoiceActionHandler): () => void {
  forms.set(form, handler);
  return () => { if (forms.get(form) === handler) forms.delete(form); };
}

export function getVoiceForm(form: HTMLFormElement): VoiceActionHandler | undefined {
  return forms.get(form);
}
