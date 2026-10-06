// Runs only inside the opaque generated frame. Preserve document identity,
// pointer capture, native input state and service conversations between saves.
export function installFrameRenderer() {
  const root = document.getElementById('living-space-content');
  const key = (node: Node) => node instanceof Element
    ? node.getAttribute('data-key') || node.id || (node.hasAttribute('data-paint-cell') ? `paint:${node.getAttribute('data-paint-cell')}` : '') : '';
  const compatible = (a: Node, b: Node) => a.nodeType === b.nodeType && (!(a instanceof Element) || b instanceof Element && a.tagName === b.tagName && a.namespaceURI === b.namespaceURI && key(a) === key(b));
  function patch(current: Node, next: Node) {
    if (current instanceof Element && next instanceof Element) {
      // Preserve only host-populated service data. Authored headings/layout
      // outside these bindings can still respond to public state changes.
      if (current.closest('[data-service]') && current.matches('[data-service-messages],[data-service-items],[data-service-sources],[data-service-text],[data-service-error],[data-service-note]')) return;
      const input = current instanceof HTMLInputElement || current instanceof HTMLTextAreaElement;
      const keepValue = input && (current === document.activeElement || current.value !== current.defaultValue);
      const value = input ? current.value : undefined;
      const checked = current instanceof HTMLInputElement ? current.checked : undefined;
      const keepChecked = current instanceof HTMLInputElement && current.checked !== current.defaultChecked;
      for (const attr of [...current.attributes]) if (!next.hasAttribute(attr.name)) current.removeAttribute(attr.name);
      for (const attr of [...next.attributes]) if (current.getAttribute(attr.name) !== attr.value) current.setAttribute(attr.name, attr.value);
      if (current instanceof HTMLTextAreaElement && next instanceof HTMLTextAreaElement) current.defaultValue = next.defaultValue;
      else children(current, next);
      if (input && keepValue) current.value = value!;
      if (current instanceof HTMLInputElement && keepChecked) current.checked = checked!;
    } else if (current.nodeValue !== next.nodeValue) current.nodeValue = next.nodeValue;
  }
  function children(current: Node, next: Node) {
    const keyed = new Map([...current.childNodes].filter(node => key(node)).map(node => [key(node), node]));
    let cursor = current.firstChild;
    for (const incoming of [...next.childNodes]) {
      let match = key(incoming) ? keyed.get(key(incoming)) : cursor;
      if (!match || !compatible(match, incoming)) {
        const inserted = incoming.cloneNode(true);
        current.insertBefore(inserted, cursor);
        continue;
      }
      if (match !== cursor) current.insertBefore(match, cursor);
      patch(match, incoming);
      cursor = match.nextSibling;
    }
    while (cursor) { const nextSibling = cursor.nextSibling; current.removeChild(cursor); cursor = nextSibling; }
  }
  return (html: string) => {
    if (!root || typeof html !== 'string' || html.length > 180_000) return;
    const template = document.createElement('template');
    template.innerHTML = html;
    // Server verification is authoritative; keep a browser-side backstop too.
    template.content.querySelectorAll('script,iframe,object,embed,base,meta,link').forEach(node => node.remove());
    for (const node of template.content.querySelectorAll('*')) for (const attr of [...node.attributes]) {
      if (/^on/i.test(attr.name)) node.removeAttribute(attr.name);
    }
    children(root, template.content);
  };
}
