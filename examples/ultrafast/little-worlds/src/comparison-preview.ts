/** Fit the full canvas into each lane without changing its responsive viewport.
 * The outer footprint owns scrolling; the inner world keeps its logical size.
 * ResizeObserver follows published frame heights without inspecting frame DOM.
 */
export function fitComparisonPreviews(root: HTMLElement): () => void {
  if (typeof ResizeObserver === 'undefined') return () => {};
  const reference = root.querySelector<HTMLElement>('.build-comparison-size-reference');
  if (!reference) return () => {};
  const previews = [...root.querySelectorAll<HTMLElement>('.build-comparison-preview')].map(preview => ({
    preview,
    world: preview.querySelector<HTMLElement>('.build-comparison-world')!,
  }));
  const write = (element: HTMLElement, name: string, value: string) => {
    if (element.style.getPropertyValue(name) !== value) element.style.setProperty(name, value);
  };
  let active = true;
  const update = () => {
    if (!active) return;
    const width = reference.getBoundingClientRect().width;
    if (width <= 0) return;
    // Set both logical widths before measuring either height. Sidebar changes
    // then affect only the scale, not iframe breakpoints or content geometry.
    for (const { preview } of previews) {
      const available = preview.clientWidth;
      if (!available) continue;
      write(preview, '--comparison-world-width', `${width}px`);
      write(preview, '--comparison-world-scale', `${Math.min(1, available / width)}`);
      preview.setAttribute('data-scaled-world', '');
    }
    const heights = previews.map(({ preview, world }) =>
      Math.ceil(world.offsetHeight * Number(preview.style.getPropertyValue('--comparison-world-scale') || 1)));
    previews.forEach(({ preview }, index) => write(preview, '--comparison-world-height', `${heights[index]}px`));
  };
  const observer = new ResizeObserver(update);
  observer.observe(reference);
  for (const { preview, world } of previews) { observer.observe(preview); observer.observe(world); }
  update();
  return () => {
    active = false;
    observer.disconnect();
    for (const { preview } of previews) {
      preview.removeAttribute('data-scaled-world');
      for (const name of ['--comparison-world-width', '--comparison-world-scale', '--comparison-world-height']) preview.style.removeProperty(name);
    }
  };
}
