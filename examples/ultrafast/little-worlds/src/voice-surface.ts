import { getVoiceFrame } from './voice-frame-registry';
import { getVoiceAction, getVoiceForm } from './voice-action-registry';
import type { VoiceAction, VoiceActionResult, VoiceControl, VoiceSurface, VoiceTranscript } from './live-voice';

const selector = 'button,a[href],input:not([type="hidden"]),textarea,select,summary,[role="button"],[tabindex="0"]';
const excluded = '[data-voice-ignore],script,style,svg,[aria-hidden="true"],[inert],[hidden]';
const guardedSelector = '.reset-demo-confirm,[data-voice-confirm]';
const short = (text: string | null | undefined, max = 240) => (text || '').replace(/\s+/g, ' ').trim().slice(0, max);

export function voiceScope(): HTMLElement {
  const dialogs = [...document.querySelectorAll<HTMLDialogElement>('dialog[open]')];
  return dialogs.at(-1) || document.querySelector<HTMLElement>('.community-overlay') || document.body;
}

export function visibleForVoice(element: Element): element is HTMLElement {
  if (!(element instanceof HTMLElement) || element.closest(excluded)) return false;
  for (let details = element.closest('details'); details; details = details.parentElement?.closest('details') || null) {
    const summary = [...details.children].find(child => child.matches('summary'));
    if (!details.open && element !== summary && !summary?.contains(element)) return false;
  }
  const style = getComputedStyle(element);
  return style.display !== 'none' && style.visibility !== 'hidden' && element.getClientRects().length > 0;
}

function label(element: HTMLElement): string {
  const labelled = element.getAttribute('aria-labelledby')?.split(/\s+/).map(id => document.getElementById(id)?.textContent).join(' ');
  const field = element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement || element instanceof HTMLSelectElement;
  const fieldLabel = field ? [...element.labels || []].map(item => { const copy = item.cloneNode(true) as HTMLElement; copy.querySelectorAll('input,textarea,select,button').forEach(node => node.remove()); return copy.textContent; }).join(' ') : '';
  return short(element.getAttribute('aria-label') || labelled || fieldLabel
    || (field ? element.getAttribute('placeholder') || element.getAttribute('name') : element.textContent) || element.title || element.tagName);
}

function disabled(element: HTMLElement): boolean {
  return element.matches(':disabled,[aria-disabled="true"]') || !!element.closest('[inert]');
}

function ownerForm(element: HTMLElement): HTMLFormElement | null {
  return element instanceof HTMLButtonElement || element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement || element instanceof HTMLSelectElement
    ? element.form : element.closest('form');
}

function formSubmitters(form: HTMLFormElement): (HTMLButtonElement | HTMLInputElement)[] {
  return [...form.elements].filter((element): element is HTMLButtonElement | HTMLInputElement =>
    (element instanceof HTMLButtonElement || element instanceof HTMLInputElement) && element.type === 'submit');
}

function checked(element: HTMLElement): boolean | undefined {
  if (element instanceof HTMLInputElement && ['checkbox', 'radio'].includes(element.type)) return element.checked;
  const value = element.getAttribute('aria-checked') ?? element.getAttribute('aria-pressed');
  return value === 'true' ? true : value === 'false' ? false : undefined;
}

function expanded(element: HTMLElement): boolean | undefined {
  const details = element.matches('summary') ? element.closest('details') : null;
  if (details) return details.open;
  const value = element.getAttribute('aria-expanded');
  return value === 'true' ? true : value === 'false' ? false : undefined;
}

function controlledRegions(element: HTMLElement): string {
  return (element.getAttribute('aria-controls') || '').trim().split(/\s+/).slice(0, 3).map(id => {
    const region = document.getElementById(id);
    // Use explicit accessible names, never the region's potentially large or
    // hidden contents (for example, source code in a collapsed file viewer).
    const labelled = region?.getAttribute('aria-labelledby')?.split(/\s+/).slice(0, 3).map(labelId => document.getElementById(labelId)?.textContent).join(' ');
    return short(region?.getAttribute('aria-label') || labelled, 80);
  }).filter(Boolean).join(', ');
}

function disabledOption(option: HTMLOptionElement) {
  return option.disabled || !!option.closest('optgroup[disabled]');
}

function description(element: HTMLElement): string {
  const described = element.getAttribute('aria-describedby')?.split(/\s+/).map(id => document.getElementById(id)?.textContent).join(' ');
  const group = element.closest('.revision-list>div,.community-request-row,.community-person-card,form,section,[role="group"]');
  const isExpanded = expanded(element);
  const expansion = isExpanded !== undefined ? ` Disclosure is ${isExpanded ? 'expanded' : 'collapsed'}. Activate to ${isExpanded ? 'collapse' : 'expand'} its controls.` : '';
  const regions = controlledRegions(element);
  return short(element.getAttribute('aria-description') || described || group?.getAttribute('aria-label') || group?.textContent, 360) + expansion + (regions ? ` Controls: ${regions}.` : '');
}

function semantics(element: HTMLElement) {
  return JSON.stringify([label(element), element.getAttribute('role'), element.getAttribute('name'), element.getAttribute('type'),
    element.getAttribute('href'), element.getAttribute('data-voice-confirm'), expanded(element), element.getAttribute('aria-controls')]);
}

function readableText(scope: HTMLElement) {
  const walker = document.createTreeWalker(scope, NodeFilter.SHOW_TEXT);
  const pieces: string[] = [];
  let length = 0;
  while (walker.nextNode() && length < 10_000) {
    const node = walker.currentNode;
    if (!node.parentElement || !visibleForVoice(node.parentElement)) continue;
    const text = short(node.textContent, 800);
    if (text) { pieces.push(text); length += text.length; }
  }
  return pieces.join('\n').slice(0, 10_000);
}

function setField(element: HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement, value: string) {
  const prototype = element instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype
    : element instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
  // Use the native setter so React observes the input event, just as it does
  // for typing. Assigning to React's instrumented property bypasses onChange.
  const setter = Object.getOwnPropertyDescriptor(prototype, 'value')?.set;
  const previous = element.value;
  setter?.call(element, value);
  const expected = element instanceof HTMLInputElement && element.type === 'color' ? value.toLowerCase() : value;
  if (element.value !== expected) {
    setter?.call(element, previous);
    return element instanceof HTMLInputElement && ['number', 'range'].includes(element.type)
      ? 'Use a number without units or percent signs.' : 'That value does not match this field’s format.';
  }
  if (element instanceof HTMLInputElement && value && ['number', 'range', 'date', 'datetime-local', 'month', 'week', 'time'].includes(element.type) && !element.validity.valid) {
    const problem = element.validationMessage;
    setter?.call(element, previous);
    return short(problem, 250) || 'Use a value within this field’s limits.';
  }
  element.dispatchEvent(new Event('input', { bubbles: true }));
  element.dispatchEvent(new Event('change', { bubbles: true }));
  return undefined;
}

type SpeechCheckpoint = { speech: string; userTurn?: Pick<VoiceTranscript, 'id' | 'startMs' | 'endMs'> };
type Confirmation = { element: HTMLElement; scope: HTMLElement; checkpoint: SpeechCheckpoint; release: () => void };
function affirmativeResetReply(value: string) {
  const reply = value.toLocaleLowerCase().replace(/[,.!?:;]/g, ' ').replace(/\s+/g, ' ').trim();
  if (!reply || /\b(no|not|never|don['’]?t|cancel|stop|wait)\b/.test(reply)) return false;
  const concise = reply.replace(/^please\s+|\s+please$/g, '');
  const reset = /^(?:go ahead(?: and)? )?(?:reset (?:it|this space|the space|(?:the )?demo|everything)|start fresh|confirm (?:it|(?:the )?reset|(?:the )?demo))$/;
  const direct = /^(?:yes|yeah|yep|yup|ok|okay|sure|confirm|confirmed|i confirm|go ahead|do(?: it)?)$/;
  if (direct.test(concise) || reset.test(concise)) return true;
  const afterYes = concise.replace(/^(?:yes|yeah|yep|yup|ok|okay|sure)\s+(?:please\s+)?/, '');
  return afterYes !== concise && (direct.test(afterYes) || reset.test(afterYes));
}
function formState(form: HTMLFormElement | null) {
  return form ? JSON.stringify([...form.elements].filter(element => element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement || element instanceof HTMLSelectElement)
    .map(element => { const field = element as HTMLInputElement; return [field.name, field.value, field.checked]; })) : '';
}
export function createVoiceSurface(options: { context: () => string; userSpeech: () => string; userTurns?: () => readonly VoiceTranscript[]; voice?: { stop: () => void; mute: () => void } }) {
  const ids = new WeakMap<HTMLElement, string>();
  const captured = new Map<string, { element: HTMLElement; scope: HTMLElement; semantics: string; value?: string; checked?: boolean; formState: string }>();
  let serial = 0;
  let readVersion = 0;
  let capturedUrl = '';
  let confirmation: Confirmation | null = null;
  let frameCapture: { frame: NonNullable<ReturnType<typeof getVoiceFrame>>; version: number; ids: Set<string> } | null = null;
  const settle = () => new Promise<void>(resolve => setTimeout(resolve, 160));

  function clearConfirmation() {
    confirmation?.release();
    confirmation = null;
  }

  function speechCheckpoint(): SpeechCheckpoint {
    const userTurn = options.userTurns?.().filter(turn => turn.role === 'user').at(-1);
    return { speech: options.userSpeech(), ...(userTurn ? { userTurn: { id: userTurn.id, startMs: userTurn.startMs, endMs: userTurn.endMs } } : {}) };
  }

  function confirmationReply(checkpoint: SpeechCheckpoint): string {
    if (options.userTurns) {
      const latest = options.userTurns().filter(turn => turn.role === 'user').at(-1);
      const previous = checkpoint.userTurn;
      // Stable turn identity survives transcript trimming and excludes both
      // assistant speech and an appended "yes" in the original request.
      return latest && (!previous || latest.id !== previous.id && latest.startMs >= previous.endMs)
        ? latest.text : '';
    }
    const speech = options.userSpeech();
    const later = speech.startsWith(checkpoint.speech) ? speech.slice(checkpoint.speech.length) : '';
    return later.split('\n').map(part => part.trim()).filter(Boolean).at(-1) || '';
  }

  function confirmationQuestion(element: HTMLElement): VoiceActionResult {
    return { ok: false, requiresConfirmation: true, message: `${label(element)} removes saved content. Please say yes to confirm, or no to keep it.` };
  }

  function checkConfirmation(scope = voiceScope()) {
    if (confirmation && (confirmation.scope !== scope || !scope.contains(confirmation.element)
      || !visibleForVoice(confirmation.element) || disabled(confirmation.element))) clearConfirmation();
  }

  function armConfirmation(element: HTMLElement, scope: HTMLElement) {
    clearConfirmation();
    const dialog = element.closest('dialog');
    const observer = new MutationObserver(() => checkConfirmation());
    // A cancelled or hidden view ends this request, even if React preserves
    // its controls and later opens the same dialog again.
    dialog?.addEventListener('close', clearConfirmation);
    dialog?.addEventListener('cancel', clearConfirmation);
    observer.observe(document.body, { subtree: true, childList: true, attributes: true,
      attributeFilter: ['open', 'hidden', 'inert', 'aria-hidden', 'disabled', 'aria-disabled', 'style', 'class', 'data-voice-ignore'] });
    confirmation = { element, scope, checkpoint: speechCheckpoint(), release: () => {
      dialog?.removeEventListener('close', clearConfirmation);
      dialog?.removeEventListener('cancel', clearConfirmation);
      observer.disconnect();
    } };
  }

  async function read(): Promise<VoiceSurface> {
    const scope = voiceScope();
    checkConfirmation(scope);
    const version = ++readVersion;
    captured.clear();
    capturedUrl = location.href;
    const controls: (VoiceControl & { checked?: boolean; description?: string; requiresConfirmation?: boolean })[] = [];
    const elements = [...scope.querySelectorAll<HTMLElement>(selector)].filter(element => visibleForVoice(element) && !element.matches('input[type="password"]'));
    const ranked = new Map(elements.map(element => {
      const rect = element.getBoundingClientRect();
      const distance = Math.max(-rect.bottom, rect.top - innerHeight, 0) + Math.max(-rect.right, rect.left - innerWidth, 0);
      return [element, element === document.activeElement ? -1 : distance];
    }));
    elements.sort((a, b) => ranked.get(a)! - ranked.get(b)!);
    for (const element of elements) {
      if (controls.length >= 135) break;
      let id = ids.get(element);
      if (!id) { id = `ui-${++serial}`; ids.set(element, id); }
      const isField = element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement || element instanceof HTMLSelectElement;
      const needsConfirmation = element.matches(guardedSelector);
      const value = isField && !(element instanceof HTMLInputElement && element.type === 'file') ? element.value : undefined;
      const selected = checked(element);
      const isExpanded = expanded(element);
      const form = ownerForm(element);
      const submitters = form ? formSubmitters(form).filter(visibleForVoice) : [];
      const snapshotId = `${id}-v${version}`;
      captured.set(snapshotId, { element, scope, semantics: semantics(element), value, checked: selected, formState: formState(form) });
      controls.push({ id: snapshotId, label: label(element), role: element.getAttribute('role') || (element instanceof HTMLInputElement ? element.type : element.matches('summary') ? 'button' : element.tagName.toLowerCase()),
        disabled: disabled(element), ...(value !== undefined ? { value: value.slice(0, 3000) } : {}),
        description: short(`${description(element)}${form && isField ? ` Updating this field alone does not submit the form.${submitters.length ? ` Submit controls: ${submitters.map(label).join(', ')}.` : ''}` : ''}`, 1200),
        ...(form ? { group: label(form) } : {}),
        ...(element instanceof HTMLButtonElement ? { type: element.type } : {}),
        ...(selected !== undefined ? { checked: selected } : {}),
        ...(isExpanded !== undefined ? { expanded: isExpanded } : {}),
        ...(needsConfirmation ? { requiresConfirmation: true } : {}),
        ...(element instanceof HTMLSelectElement ? { options: [...element.options].filter(option => !option.hidden).map(option => ({ value: option.value, label: option.label, disabled: disabledOption(option) })).slice(0, 50) } : {}),
      });
      if (element instanceof HTMLInputElement) {
        const control = controls.at(-1)!;
        control.type = element.type;
        if (['number', 'range'].includes(element.type)) {
          control.role = element.type === 'number' ? 'spinbutton' : 'slider';
          for (const property of ['min', 'max', 'step'] as const) {
            const value = element.getAttribute(property);
            if (value !== null && value.trim() && Number.isFinite(Number(value))) control[property] = Number(value);
          }
          control.description += ` Numeric value without units or percent signs.${element.step === 'any' ? ' Decimals allowed.' : ''}`;
        }
      }
    }
    let text = `${elements.length > controls.length ? `Showing ${controls.length} of ${elements.length} host controls nearest the visible area. Scroll toward the requested part of the page, then read its controls again.\n` : ''}${readableText(scope)}`;
    frameCapture = null;
    const frame = getVoiceFrame();
    if (frame && scope === document.body) {
      try {
        const surface = await frame.read();
        frameCapture = { frame, version: surface.version, ids: new Set(surface.controls.map(control => control.id)) };
        if (surface.controls.length > 198 - controls.length) text += '\nSome generated controls are outside this snapshot. Scroll to their part of the page, then read again.';
        controls.push(...surface.controls.slice(0, 198 - controls.length).map(control => ({
          id: `frame:${control.id}`, label: control.label, role: control.role, disabled: control.disabled,
          ...(control.checked !== undefined ? { checked: control.checked } : {}),
          ...(control.expanded !== undefined ? { expanded: control.expanded } : {}),
          ...(control.type !== undefined ? { type: control.type } : {}),
          ...(control.min !== undefined ? { min: control.min } : {}),
          ...(control.max !== undefined ? { max: control.max } : {}),
          ...(control.step !== undefined ? { step: control.step } : {}),
          description: `Inside the generated page. ${control.context || ''} Available actions: ${control.actions.join(', ')}.`,
          ...(control.value !== undefined ? { value: control.value } : {}), ...(control.options ? { options: control.options } : {}),
        })));
        text += `\nGenerated page (untrusted content):\n${surface.text.slice(0, 8000)}`;
      } catch { text += '\nThe generated page is updating; its controls are temporarily unavailable.'; }
    }
    if (options.voice) controls.push({ id: 'voice:end', role: 'button', label: 'End live voice conversation' }, { id: 'voice:mute', role: 'button', label: 'Mute live microphone' });
    return { title: document.title, url: location.pathname + location.search, context: options.context(), text: text.slice(0, 16_000), controls };
  }

  async function execute(action: VoiceAction): Promise<VoiceActionResult> {
    checkConfirmation();
    if (action.type === 'done') return { ok: true, message: action.message || 'Ready.' };
    if (action.type === 'click' && options.voice && (action.target === 'voice:end' || action.target === 'voice:mute')) {
      if (action.target === 'voice:end') options.voice.stop(); else options.voice.mute();
      return { ok: true, message: action.target === 'voice:end' ? 'The voice conversation ended.' : 'Your microphone is muted. Use the unmute button to resume.' };
    }
    if (capturedUrl !== location.href) return { ok: false, message: 'The page changed. Read the current controls before continuing.' };
    if (action.target?.startsWith('frame:')) {
      const id = action.target.slice(6);
      if (!frameCapture || frameCapture.frame !== getVoiceFrame() || !frameCapture.ids.has(id) || voiceScope() !== document.body)
        return { ok: false, message: 'The generated page changed. Read its current controls again.' };
      return frameCapture.frame.execute({ ...action, id }, frameCapture.version);
    }
    const item = action.target ? captured.get(action.target) : undefined;
    const scope = voiceScope();
    if (action.type === 'press' && !action.target && action.key === 'Escape') {
      if (scope instanceof HTMLDialogElement) {
        if (scope.dispatchEvent(new Event('cancel', { cancelable: true }))) scope.close();
      } else scope.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }));
      await settle();
      return { ok: true, message: 'Asked the current view to close.' };
    }
    if (action.type === 'scroll' && !item) {
      const target = scope === document.body ? document.scrollingElement : scope;
      const horizontal = action.direction === 'left' || action.direction === 'right';
      target?.scrollBy({ [horizontal ? 'left' : 'top']: (action.direction === 'up' || action.direction === 'left' ? -1 : 1) * innerHeight * .65, behavior: 'instant' });
      return { ok: true, message: 'Scrolled the current view.' };
    }
    if (!item || item.scope !== scope || !scope.contains(item.element) || !visibleForVoice(item.element) || disabled(item.element))
      return { ok: false, message: 'That control is no longer available. Read the current screen again.' };
    const element = item.element;
    if (item.semantics !== semantics(element)) return { ok: false, message: 'That control changed. Read its current meaning before continuing.' };
    const name = label(element);
    if (element instanceof HTMLAnchorElement && (action.type === 'click' || action.type === 'press')) {
      const url = new URL(element.href, location.href);
      if (url.origin !== location.origin || element.target === '_blank') return { ok: false, message: 'Use the visible link to open another tab.' };
    }
    const form = ownerForm(element);
    const enterField = action.type === 'press' && action.key === 'Enter' && (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement);
    const activatesButton = action.type === 'click' || action.type === 'press' && ['Enter', ' ', 'Space'].includes(action.key);
    const submitButton = activatesButton && (element instanceof HTMLButtonElement || element instanceof HTMLInputElement) && element.type === 'submit' ? element : undefined;
    const submits = Boolean(form && (enterField || submitButton));
    const submitter = submitButton || (enterField && form ? formSubmitters(form)[0] : undefined);
    if (submits && item.formState !== formState(form))
      return { ok: false, message: 'The form changed while the action was being prepared. Read the latest draft before submitting it.' };
    if (submits && submitter && (!scope.contains(submitter) || !visibleForVoice(submitter) || disabled(submitter)))
      return { ok: false, message: 'The form is not ready to submit.' };
    if (element.matches('input[type="file"]') || element.closest('[data-voice-manual]') || submits && submitter?.closest('[data-voice-manual]'))
      return { ok: false, message: 'Choose the file with the visible upload control. The browser requires you to select the file yourself.' };
    const activating = action.type === 'click' || action.type === 'press' && ['Enter', ' ', 'Space'].includes(action.key);
    if (activating && item.checked !== checked(element))
      return { ok: false, message: 'This selection changed. Read its current state before changing it.' };
    const guarded = element.matches(guardedSelector) ? element : submits && submitter?.matches(guardedSelector) ? submitter : undefined;
    if (activating && guarded) {
      if (confirmation?.element !== guarded) {
        armConfirmation(guarded, scope);
        return confirmationQuestion(guarded);
      }
      if (!affirmativeResetReply(confirmationReply(confirmation.checkpoint))) {
        confirmation.checkpoint = speechCheckpoint();
        return { ok: false, requiresConfirmation: true, message: `I have not reset anything. Please say yes to confirm ${label(guarded).toLocaleLowerCase()}, or no to keep the content.` };
      }
      clearConfirmation();
    }
    element.scrollIntoView({ block: 'nearest', behavior: 'instant' });
    if (submits && form) {
      if (!form.reportValidity()) return { ok: false, message: 'Complete the required fields first.' };
      const submitForm = getVoiceForm(form);
      if (submitForm) {
        try {
          const result = await submitForm();
          await settle();
          return result;
        } catch { return { ok: false, message: `Could not verify submission of ${label(form)}. Check the current screen before trying again.` }; }
      }
    }
    const hostAction = activating ? getVoiceAction(element) : undefined;
    if (hostAction) {
      try {
        const result = await hostAction();
        await settle();
        return result;
      }
      catch { return { ok: false, message: `Could not verify the outcome of ${name}. Check the current screen before trying again.` }; }
    }
    if (action.type === 'fill' || action.type === 'select') {
      if (!(element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement || element instanceof HTMLSelectElement)
        || element.matches('[readonly]') || typeof action.value !== 'string') return { ok: false, message: 'This control is not an editable field.' };
      if (item.value !== element.value) return { ok: false, message: 'The user edited this field. Read the latest value before changing it.' };
      if (element instanceof HTMLSelectElement && ![...element.options].some(option => option.value === action.value && !option.hidden && !disabledOption(option)))
        return { ok: false, message: 'Choose one of the available options.' };
      if (element instanceof HTMLInputElement && ['checkbox', 'radio', 'file', 'hidden', 'password', 'submit', 'button'].includes(element.type))
        return { ok: false, message: 'Activate this control instead of filling it.' };
      if (!(element instanceof HTMLSelectElement) && element.maxLength > -1 && action.value.length > element.maxLength)
        return { ok: false, message: `This field accepts at most ${element.maxLength} characters.` };
      const problem = setField(element, action.value);
      if (problem) return { ok: false, message: `${name}: ${problem}` };
    } else if (action.type === 'click') {
      element.click();
    } else if (action.type === 'press') {
      const key = action.key === 'Space' ? ' ' : action.key;
      if (!key || !['Enter', 'Escape', ' ', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Home', 'End', 'PageUp', 'PageDown'].includes(key))
        return { ok: false, message: 'That key is not supported.' };
      element.focus({ preventScroll: true });
      if (key === 'Enter' && (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement) && element.form) {
        element.form.requestSubmit(submitter);
      } else if ((key === 'Enter' || key === ' ') && (element instanceof HTMLButtonElement || element instanceof HTMLAnchorElement || element.matches('summary'))) element.click();
      else if (key === 'Escape' && scope instanceof HTMLDialogElement) {
        const cancel = new Event('cancel', { cancelable: true });
        if (scope.dispatchEvent(cancel)) scope.close();
      } else {
        element.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true }));
        element.dispatchEvent(new KeyboardEvent('keyup', { key, bubbles: true }));
      }
    } else if (action.type === 'scroll') element.scrollBy({ [action.direction === 'left' || action.direction === 'right' ? 'left' : 'top']: action.direction === 'up' || action.direction === 'left' ? -400 : 400, behavior: 'instant' });
    await settle();
    const nextScope = voiceScope();
    if (activating && nextScope !== scope && nextScope instanceof HTMLDialogElement && nextScope.hasAttribute('data-voice-confirmation')) {
      const guarded = [...nextScope.querySelectorAll<HTMLElement>(guardedSelector)].filter(control => visibleForVoice(control) && !disabled(control));
      if (guarded.length === 1) {
        // Opening the dialog is the first step of confirmation. Prepare the
        // gate here so a single later user reply can complete that request.
        armConfirmation(guarded[0], nextScope);
        return confirmationQuestion(guarded[0]);
      }
    }
    if (action.type === 'fill' || action.type === 'select') {
      const submitters = form ? formSubmitters(form).filter(visibleForVoice) : [];
      return {
        ok: true, submitted: false,
        message: short(`Updated ${name}. This changed the field value only; no form submission was requested.${form ? ` Form: ${label(form)}.${submitters.length ? ` Submit controls: ${submitters.map(label).join(', ')}.` : ''}` : ''}`, 1200),
      };
    }
    return { ok: true, message: `Activated ${name}. Check the current screen for the outcome; any build or service request may still be running.` };
  }
  return { read, execute, clear: () => { captured.clear(); frameCapture = null; clearConfirmation(); } };
}
