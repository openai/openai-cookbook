import type { FrameVoiceAction, FrameVoiceControl, FrameVoiceResult, FrameVoiceSurface, FrameVoiceViewport } from './voice-frame-registry';

/** Serialized into the trusted, opaque frame: keep all runtime helpers inside. */
export function installFrameVoice() {
  const identities = new WeakMap<Element, string>();
  let nextIdentity = 0;
  let generation = 0;
  let snapshotVersion = -1;
  let controls = new Map<string, { element: HTMLElement; actions: FrameVoiceAction['type'][]; semantics: string; value?: string; checked?: boolean; formState: string; serviceState: string }>();
  const text = (value: unknown, limit = 160) => typeof value === 'string' ? value.replace(/\s+/g, ' ').trim().slice(0, limit) : '';
  const visible = (element: HTMLElement) => {
    if (!element.isConnected || element.closest('[hidden],[inert],[aria-hidden="true"],template')) return false;
    for (let details = element.closest('details'); details; details = details.parentElement?.closest('details') || null) {
      const summary = [...details.children].find(child => child.matches('summary'));
      if (!details.hasAttribute('open') && element !== summary && !summary?.contains?.(element)) return false;
    }
    const style = getComputedStyle(element);
    return style.display !== 'none' && style.visibility !== 'hidden' && style.visibility !== 'collapse' && element.getClientRects().length > 0;
  };
  const disabled = (element: HTMLElement) => element.matches(':disabled') || !!element.closest('[aria-disabled="true"]');
  const checkedState = (element: HTMLElement) => {
    if (element instanceof HTMLInputElement && ['checkbox', 'radio'].includes(element.type)) return element.checked;
    if (!(element instanceof HTMLButtonElement || element instanceof HTMLAnchorElement || element instanceof HTMLInputElement)) return undefined;
    const value = element.getAttribute('aria-checked') ?? element.getAttribute('aria-pressed');
    return value === 'true' ? true : value === 'false' ? false : undefined;
  };
  const disclosure = (element: HTMLElement) => element.matches('summary') ? element.closest('details') : null;
  const expandedState = (element: HTMLElement): boolean | undefined => {
    const details = disclosure(element);
    if (details) return details.hasAttribute('open');
    const value = element.getAttribute('aria-expanded');
    return value === 'true' ? true : value === 'false' ? false : undefined;
  };
  const controlledRegions = (element: HTMLElement) => (element.getAttribute('aria-controls') || '').trim().split(/\s+/).slice(0, 3).map(id => {
    const region = document.getElementById(id);
    const labelled = region?.getAttribute('aria-labelledby')?.split(/\s+/).slice(0, 3).map(labelId => document.getElementById(labelId)?.textContent || '').join(' ');
    return text(region?.getAttribute('aria-label') || labelled, 80);
  }).filter(Boolean).join(', ');
  const editable = (element: HTMLElement): element is HTMLInputElement | HTMLTextAreaElement => element instanceof HTMLTextAreaElement || element instanceof HTMLInputElement && ['text', 'search', 'email', 'url', 'tel', 'number', 'date', 'datetime-local', 'month', 'week', 'time', 'range', 'color'].includes(element.type);
  const formFor = (element: HTMLElement) => element instanceof HTMLFormElement ? element
    : element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement || element instanceof HTMLSelectElement || element instanceof HTMLButtonElement ? element.form : element.closest<HTMLFormElement>('form');
  const fieldsState = (root: HTMLElement | null) => root ? JSON.stringify([...(root instanceof HTMLFormElement ? root.elements : root.querySelectorAll('input,textarea,select'))]
    .filter((element): element is HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement => element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement || element instanceof HTMLSelectElement)
    .map(element => [element.name, element.value, element instanceof HTMLInputElement ? element.checked : undefined, element instanceof HTMLSelectElement ? [...element.options].filter(option => option.selected).map(option => option.value) : undefined])) : '';
  const label = (element: HTMLElement) => {
    if (element.id === 'living-space-content') return 'Scroll generated page';
    const labelledBy = element.getAttribute('aria-labelledby');
    const labelled = labelledBy?.split(/\s+/).map(id => document.getElementById(id)?.textContent || '').join(' ');
    const nativeLabel = (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement || element instanceof HTMLSelectElement || element instanceof HTMLButtonElement) ? [...element.labels || []].map(item => {
      const copy = item.cloneNode(true) as HTMLElement;
      copy.querySelectorAll('input,textarea,select,button').forEach(node => node.remove());
      return copy.textContent || '';
    }).join(' ') : '';
    return text(labelled || element.getAttribute('aria-label') || nativeLabel || element.getAttribute('placeholder') || element.getAttribute('title') || (element instanceof HTMLInputElement ? element.value || element.name : element.textContent), 200) || (element instanceof HTMLFormElement ? 'Form' : element.tagName.toLowerCase());
  };
  const context = (element: HTMLElement) => {
    const form = formFor(element);
    const group = element.closest<HTMLElement>('[data-game],[data-service],section,article,fieldset,[role="group"],details') || form;
    const heading = group?.querySelector('h1,h2,h3,h4,legend');
    const labelled = group?.getAttribute('aria-labelledby')?.split(/\s+/).map(id => document.getElementById(id)?.textContent || '').join(' ');
    const submitter = form && [...form.querySelectorAll<HTMLButtonElement | HTMLInputElement>('button,input')].find(node => node.type === 'submit' && visible(node));
    const format = element instanceof HTMLInputElement && ['number', 'range'].includes(element.type)
      ? `Numeric value without units or percent signs.${element.getAttribute('step') === 'any' ? ' Decimals allowed.' : ''}` : '';
    const expanded = expandedState(element);
    const expansion = expanded !== undefined ? `Disclosure is ${expanded ? 'expanded' : 'collapsed'}. Activate to ${expanded ? 'collapse' : 'expand'} its controls.` : '';
    const regions = controlledRegions(element);
    const described = element.getAttribute('aria-describedby')?.split(/\s+/).map(id => document.getElementById(id)?.textContent || '').join(' ');
    return text([group?.dataset.service, group?.getAttribute('aria-label') || labelled || heading?.textContent,
      form ? `Form${submitter ? `: ${label(submitter)}` : ''}. Field edits are drafts until this form is submitted.` : '',
      element.getAttribute('aria-description') || described, format, expansion, regions ? `Controls: ${regions}.` : ''].filter(Boolean).join(' · '), 700);
  };
  const actionsFor = (element: HTMLElement): FrameVoiceAction['type'][] => {
    if (element.hasAttribute('data-paint-cell')) return [];
    if (element.id === 'living-space-content') return ['scroll'];
    if (disclosure(element)) return ['click', 'press', 'scroll'];
    if (element instanceof HTMLAnchorElement) return element.matches('a[data-service-link][href],a[data-action]') ? ['click', 'press', 'scroll'] : [];
    if (element instanceof HTMLButtonElement) return ['click', 'press', 'scroll'];
    if (element instanceof HTMLInputElement && ['checkbox', 'radio', 'button', 'submit', 'reset'].includes(element.type)) return ['click', 'press', 'scroll'];
    if (editable(element)) return element.readOnly ? ['scroll'] : ['fill', 'press', 'scroll'];
    if (element instanceof HTMLSelectElement) return ['select', 'press', 'scroll'];
    if (element instanceof HTMLFormElement) return ['press', 'scroll'];
    return element.scrollHeight > element.clientHeight || element.scrollWidth > element.clientWidth ? ['scroll'] : [];
  };
  const semantics = (element: HTMLElement) => JSON.stringify([label(element), element.getAttribute('name'), element.getAttribute('type'), element.getAttribute('href'), element.getAttribute('data-action'), element.getAttribute('data-service-operation'), element.getAttribute('data-game-command'), element.getAttribute('data-game-action'), element.getAttribute('data-game-release'), element.getAttribute('data-game-keys'), formFor(element)?.getAttribute('data-action'), expandedState(element), element.getAttribute('aria-controls')]);
  function read(version: number, viewport?: FrameVoiceViewport): FrameVoiceSurface {
    snapshotVersion = version;
    generation++;
    controls = new Map();
    const result: FrameVoiceControl[] = [];
    const root = document.getElementById('living-space-content');
    const elements = [...root?.querySelectorAll<HTMLElement>('button,input,textarea,select,summary,a[data-service-link],a[data-action],form,[data-service-messages],[data-service-items],[data-service-sources]') || []]
      .filter(element => visible(element) && actionsFor(element).length);
    if (root && document.scrollingElement && document.scrollingElement.scrollHeight > window.innerHeight + 1) elements.unshift(root);
    const area = viewport && [viewport.top, viewport.left, viewport.width, viewport.height].every(value => typeof value === 'number' && Number.isFinite(value) && Math.abs(value) <= 100000)
      && viewport.width >= 0 && viewport.height >= 0 ? viewport : null;
    if (area) {
      const rank = (element: HTMLElement) => {
        if (element === document.activeElement) return -1;
        const rect = element.getBoundingClientRect();
        const dx = Math.max(area.left - rect.right, rect.left - area.left - area.width, 0);
        const dy = Math.max(area.top - rect.bottom, rect.top - area.top - area.height, 0);
        return dx + dy;
      };
      const ranked = new Map(elements.map(element => [element, rank(element)]));
      // Stable sort keeps DOM order within the viewport. Offscreen controls
      // remain available when there is room and move into scope after a scroll.
      elements.sort((a, b) => ranked.get(a)! - ranked.get(b)!);
    }
    for (const element of elements) {
      if (result.length >= 160) break;
      const actions = actionsFor(element);
      let identity = identities.get(element);
      if (!identity) { identity = String(++nextIdentity); identities.set(element, identity); }
      // A context refresh must never silently update the baseline used by an
      // older model response. Each read issues fresh, single-snapshot targets.
      const id = `${generation}:${identity}`;
      const checked = checkedState(element);
      controls.set(id, { element, actions, semantics: semantics(element), value: editable(element) || element instanceof HTMLSelectElement ? element.value : undefined,
        checked,
        formState: fieldsState(formFor(element)), serviceState: fieldsState(element.closest<HTMLElement>('[data-service]')) });
      const control: FrameVoiceControl = { id, label: label(element), role: element instanceof HTMLFormElement ? 'form' : element instanceof HTMLTextAreaElement || editable(element) ? 'textbox' : element instanceof HTMLSelectElement ? 'combobox' : element instanceof HTMLAnchorElement ? 'link' : element instanceof HTMLInputElement ? element.type : element instanceof HTMLButtonElement || disclosure(element) ? 'button' : 'region', context: context(element), disabled: disabled(element), actions };
      if (element instanceof HTMLInputElement) {
        control.type = element.type;
        if (['number', 'range'].includes(element.type)) {
          control.role = element.type === 'number' ? 'spinbutton' : 'slider';
          for (const property of ['min', 'max', 'step'] as const) {
            const value = element.getAttribute(property);
            if (value !== null && value.trim() && Number.isFinite(Number(value))) control[property] = Number(value);
          }
        }
      }
      if (editable(element) || element instanceof HTMLSelectElement) control.value = element.value.slice(0, 4000);
      if (checked !== undefined) control.checked = checked;
      const expanded = expandedState(element);
      if (expanded !== undefined) control.expanded = expanded;
      if (element instanceof HTMLSelectElement) control.options = [...element.options].filter(option => !option.disabled && !option.hidden && !option.closest('optgroup[disabled]')).slice(0, 80).map(option => ({ value: option.value.slice(0, 400), label: text(option.label, 160) }));
      result.push(control);
    }
    // SVG charts and game boards often expose their useful state only through
    // an accessible name. Include it without exposing source or hidden content.
    const descriptions = [...root?.querySelectorAll<HTMLElement>('[role="img"][aria-label],[role="img"][aria-labelledby],svg[aria-label],svg[aria-labelledby]') || []]
      .filter(visible).map(element => label(element)).filter(Boolean).slice(0, 30);
    const truncated = elements.length > result.length ? `Showing ${result.length} of ${elements.length} controls nearest the visible area. Scroll toward the requested part of the page, then read its controls again.` : '';
    return { version, controls: result, text: text([truncated, root?.innerText || '', ...descriptions].filter(Boolean).join('\n'), 14000) };
  }
  function execute(action: FrameVoiceAction, version: number): FrameVoiceResult {
    const fail = (message: string): FrameVoiceResult => ({ ok: false, message });
    if (!action || typeof action !== 'object' || !Number.isSafeInteger(version) || version !== snapshotVersion) return fail('The space changed. Read its controls again.');
    const entry = controls.get(action.id);
    if (!entry || !entry.actions.includes(action.type)) return fail('That control is not in the current space. Read its controls again.');
    const element = entry.element;
    if (!visible(element) || disabled(element) || !actionsFor(element).includes(action.type)) return fail('That control is no longer available.');
    if (entry.semantics !== semantics(element)) return fail('That control changed while the action was being prepared. Read its current meaning before continuing.');
    if (action.value !== undefined && (typeof action.value !== 'string' || action.value.length > 4000 || action.value.includes('\0'))) return fail('Use a shorter plain-text value.');
    const name = label(element);
    const submit = (form: HTMLFormElement, submitter?: HTMLButtonElement | HTMLInputElement): FrameVoiceResult => {
      if (entry.formState !== fieldsState(form)) return fail('The form changed while this action was being prepared. Read the latest draft before submitting.');
      if (!form.checkValidity()) { form.reportValidity(); return fail('Complete the required fields with valid values before submitting.'); }
      const available = submitter || [...form.querySelectorAll<HTMLButtonElement | HTMLInputElement>('button,input')].find(node => node.type === 'submit' && visible(node) && !disabled(node));
      // A disabled authored submit button must not be bypassed by form submission.
      if (!available && [...form.querySelectorAll<HTMLButtonElement | HTMLInputElement>('button,input')].some(node => node.type === 'submit')) return fail('This form cannot be submitted right now.');
      form.requestSubmit(available);
      return { ok: true, message: `Submitted ${name}.` };
    };
    try {
      if (action.type === 'fill') {
        if (!editable(element) || element.readOnly || action.value === undefined) return fail('This control does not accept text.');
        if (element.value !== entry.value) return fail('This field changed while the action was being prepared. Read its latest value before editing.');
        if (element.maxLength >= 0 && action.value.length > element.maxLength) return fail(`This field allows up to ${element.maxLength} characters.`);
        const prototype = element instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
        const setValue = Object.getOwnPropertyDescriptor(prototype, 'value')?.set;
        const previousValue = element.value;
        setValue?.call(element, action.value);
        const expected = element instanceof HTMLInputElement && element.type === 'color' ? action.value.toLowerCase() : action.value;
        if (element.value !== expected) {
          setValue?.call(element, previousValue);
          return fail(`${name}: ${element instanceof HTMLInputElement && ['number', 'range'].includes(element.type) ? 'Use a number without units or percent signs.' : 'That value does not match this field’s format.'}`);
        }
        if (element instanceof HTMLInputElement && action.value && ['number', 'range', 'date', 'datetime-local', 'month', 'week', 'time'].includes(element.type) && element.validity && !element.validity.valid) {
          const problem = text(element.validationMessage, 250);
          setValue?.call(element, previousValue);
          return fail(`${name}: ${problem || 'Use a value within this field’s limits.'}`);
        }
        element.dispatchEvent(new Event('input', { bubbles: true }));
        element.dispatchEvent(new Event('change', { bubbles: true }));
        return { ok: true, message: `Updated ${name} to ${text(element.value, 200)}.${formFor(element) ? ' This is a draft; submit its form to apply or save it.' : ''}` };
      }
      if (action.type === 'select') {
        if (!(element instanceof HTMLSelectElement) || action.value === undefined) return fail('Choose an available option.');
        if (element.value !== entry.value) return fail('This field changed while the action was being prepared. Read its latest value before editing.');
        const option = [...element.options].find(item => item.value === action.value && !item.disabled && !item.hidden && !item.closest('optgroup[disabled]'));
        if (!option) return fail('That option is not available.');
        Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value')?.set?.call(element, option.value);
        element.dispatchEvent(new Event('input', { bubbles: true }));
        element.dispatchEvent(new Event('change', { bubbles: true }));
        return { ok: true, message: `Selected ${text(option.label)} in ${name}.` };
      }
      if (action.type === 'scroll') {
        const amount = typeof action.amount === 'number' && Number.isFinite(action.amount) ? Math.min(1200, Math.max(50, action.amount)) : 400;
        if (action.direction !== undefined && !['up', 'down', 'left', 'right'].includes(action.direction)) return fail('Use a valid scroll direction.');
        if (element.id !== 'living-space-content') element.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'instant' });
        const direction = action.direction || 'down';
        const target = element.id === 'living-space-content' ? document.scrollingElement : element;
        target?.scrollBy({ left: direction === 'left' ? -amount : direction === 'right' ? amount : 0, top: direction === 'up' ? -amount : direction === 'down' ? amount : 0, behavior: 'instant' });
        return { ok: true, message: `Scrolled ${name}.` };
      }
      if (action.type === 'press' && !['Enter', ' ', 'Space'].includes(action.key || '')) return fail('This control supports Enter or Space.');
      if (checkedState(element) !== entry.checked) return fail('This selection changed. Read its current state before changing it.');
      if (entry.serviceState !== fieldsState(element.closest<HTMLElement>('[data-service]'))) return fail('The conversation draft changed. Read its latest value before continuing.');
      if ((element instanceof HTMLButtonElement || element instanceof HTMLInputElement) && element.type === 'reset' && entry.formState !== fieldsState(formFor(element))) return fail('The form changed. Read its latest draft before clearing it.');
      if (element instanceof HTMLFormElement) return action.key === 'Enter' ? submit(element) : fail('Use Enter to submit this form.');
      if (editable(element) || element instanceof HTMLSelectElement) return action.key === 'Enter' && element.form ? submit(element.form) : fail('Use Enter to submit this field’s form.');
      if ((element instanceof HTMLButtonElement || element instanceof HTMLInputElement) && element.type === 'submit' && element.form) return submit(element.form, element);
      if (element instanceof HTMLAnchorElement && !element.matches('a[data-service-link][href],a[data-action]')) return fail('That link is not available.');
      element.click();
      return { ok: true, message: `Activated ${name}.` };
    } catch { return fail('That control could not be used. Read the current space and try again.'); }
  }
  return { read, execute, invalidate: () => { snapshotVersion = -1; controls.clear(); } };
}
