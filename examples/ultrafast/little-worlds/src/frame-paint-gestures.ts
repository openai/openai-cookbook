import type { PaintConfig } from '../shared/paint-schema.mjs';

/** Trusted, declarative painting only; this function is serialized into the frame. */
export function installPaintGestures(options: {
  isActive: () => boolean;
  dispatch: (action: Record<string, unknown>) => Promise<boolean>;
}, validateConfig: (value: unknown, raster?: boolean) => PaintConfig, validatePixels: (pixels: unknown, config: PaintConfig) => string) {
  type Config = PaintConfig;
  type Mark = { grid: Grid; action: string; cell: number; color: number; colorValue: string; sequence: number; columns: number; rows: number };
  type Overlay = Mark & { base: string };
  type Grid = { root: Element; identity: string; index: number; overlays: Map<number, Overlay>; geometry: string; config: Config; raster: boolean; pixels: string; cursor: number; cursorVisible: boolean; label: string };
  type Stroke = { pointerId: number; grid: Grid; config: Config; previous: number | null; visited: Set<number> };
  const grids: Grid[] = [];
  let queue: Mark[] = [];
  let stroke: Stroke | undefined;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let processing = false;
  let sequence = 0;
  let generation = 0;
  let suppressClick: { root: Element; until: number } | undefined;
  const alphabet = '0123456789abcdefghijklmnopqrstuv';
  const isRaster = (root: Element): root is HTMLCanvasElement => typeof HTMLCanvasElement !== 'undefined' && root instanceof HTMLCanvasElement;

  function configFor(root: Element): Config | undefined {
    try {
      const raw = root.getAttribute('data-paint-grid') || '';
      if (raw.length > 4000 || root.closest('[data-service]') || root.parentElement?.closest('[data-paint-grid]')) return;
      const raster = isRaster(root);
      if (!raster && root.getAttribute('data-paint-pixels') !== null) return;
      if (raster && (root.closest('svg,math,template,[data-game],[data-game-canvas]')
        || root.parentElement?.closest('canvas,select,option,optgroup'))) return;
      const config = validateConfig(JSON.parse(raw), raster);
      if (raster) validatePixels(root.getAttribute('data-paint-pixels'), config);
      return config;
    } catch { return; }
  }
  const identityFor = (root: Element) => root.getAttribute('data-key') || root.id || '';
  const geometryFor = (root: Element, config: Config) => JSON.stringify([isRaster(root), config.action, config.columns, config.rows, config.palette, config.background]);
  function gridFor(root: Element, config: Config): Grid {
    let grid = grids.find(item => item.root === root);
    const geometry = geometryFor(root, config);
    if (!grid) {
      grid = { root, identity: identityFor(root), index: [...document.querySelectorAll('[data-paint-grid]')].indexOf(root), overlays: new Map(), geometry, config, raster: isRaster(root), pixels: '', cursor: 0, cursorVisible: false, label: root.getAttribute('aria-label') || 'Painting canvas' };
      grids.push(grid);
    } else if (grid.geometry !== geometry) {
      // Row-major indices belong to one geometry. Never send buffered marks to
      // a resized surface, or reinterpret pending palette indices after edits.
      cancel();
      grid.geometry = geometry;
      grid.cursor = Math.min(grid.cursor, config.columns * config.rows - 1);
    }
    grid.config = config;
    grid.raster = isRaster(root);
    if (grid.raster) grid.pixels = root.getAttribute('data-paint-pixels') || '';
    return grid;
  }
  function resolveRoot(grid: Grid) {
    if (grid.root.isConnected) return grid.root;
    const candidates = [...document.querySelectorAll('[data-paint-grid]')];
    const replacement = grid.identity ? candidates.find(root => identityFor(root) === grid.identity) : candidates[grid.index];
    if (replacement) grid.root = replacement;
    return replacement;
  }
  function cellNode(grid: Grid, cell: number): HTMLElement | SVGElement | undefined {
    const root = resolveRoot(grid);
    const node = root?.querySelector(`[data-paint-cell="${cell}"]`);
    return node && node.closest('[data-paint-grid]') === root && (node instanceof HTMLElement || node instanceof SVGElement) ? node : undefined;
  }
  const colorProperty = (node: HTMLElement | SVGElement) => node instanceof SVGElement ? 'fill' : 'backgroundColor';
  const pixelColor = (grid: Grid, cell: number) => grid.config.palette?.[alphabet.indexOf(grid.pixels[cell])] || grid.config.background || '#ffffff';
  function drawPixel(grid: Grid, cell: number, color: string) {
    if (!isRaster(grid.root)) return;
    const context = grid.root.getContext('2d');
    if (!context) return;
    context.fillStyle = color;
    context.fillRect(cell % grid.config.columns, Math.floor(cell / grid.config.columns), 1, 1);
  }
  function drawCursor(grid: Grid) {
    if (!isRaster(grid.root)) return;
    const root = grid.root;
    root.setAttribute('aria-label', `${grid.label}. Column ${grid.cursor % grid.config.columns + 1} of ${grid.config.columns}, row ${Math.floor(grid.cursor / grid.config.columns) + 1} of ${grid.config.rows}.`);
    root.setAttribute('aria-description', 'Use arrow keys to move, Home and End for row edges, and Space or Enter to paint.');
    if (!grid.cursorVisible || document.activeElement !== root) return;
    const context = root.getContext('2d');
    if (!context) return;
    const x = grid.cursor % grid.config.columns, y = Math.floor(grid.cursor / grid.config.columns);
    context.save();
    context.lineWidth = .25;
    context.strokeStyle = '#000000';
    context.strokeRect(x - .125, y - .125, 1.25, 1.25);
    context.lineWidth = .125;
    context.strokeStyle = '#ffffff';
    context.strokeRect(x + .0625, y + .0625, .875, .875);
    context.restore();
  }
  function drawRaster(grid: Grid) {
    if (!isRaster(grid.root)) return;
    const root = grid.root, config = grid.config;
    if (root.width !== config.columns) root.width = config.columns;
    if (root.height !== config.rows) root.height = config.rows;
    root.style.width = '100%';
    root.style.height = 'auto';
    root.style.aspectRatio = `${config.columns} / ${config.rows}`;
    root.style.imageRendering = 'pixelated';
    if (!root.hasAttribute('tabindex')) root.tabIndex = 0;
    const context = root.getContext('2d');
    if (!context) return;
    context.imageSmoothingEnabled = false;
    // One bitmap upload, independent of the number of painted cells or DOM
    // nodes. Optimistic overlays stay separate from authoritative pixels.
    const image = context.createImageData(config.columns, config.rows);
    const colors = [...(config.palette || []), config.background || '#ffffff'].map(color => {
      const full = color.length === 4 ? [...color.slice(1)].map(char => char + char).join('') : color.slice(1);
      return [parseInt(full.slice(0, 2), 16), parseInt(full.slice(2, 4), 16), parseInt(full.slice(4, 6), 16)];
    });
    for (let cell = 0; cell < config.columns * config.rows; cell++) {
      const color = colors[alphabet.indexOf(grid.pixels[cell])] || colors[colors.length - 1];
      const offset = cell * 4;
      image.data[offset] = color[0]; image.data[offset + 1] = color[1]; image.data[offset + 2] = color[2]; image.data[offset + 3] = 255;
    }
    context.putImageData(image, 0, 0);
    for (const overlay of grid.overlays.values()) drawPixel(grid, overlay.cell, overlay.colorValue);
    drawCursor(grid);
  }
  function restore(grid: Grid, overlay: Overlay) {
    if (grid.raster) { drawPixel(grid, overlay.cell, pixelColor(grid, overlay.cell)); return; }
    const node = cellNode(grid, overlay.cell);
    if (node) node.style[colorProperty(node)] = overlay.base;
  }
  function releaseStroke() {
    const previous = stroke;
    stroke = undefined;
    if (!previous) return;
    suppressClick = { root: previous.grid.root, until: Date.now() + 700 };
    try {
      if (previous.grid.root.hasPointerCapture?.(previous.pointerId)) previous.grid.root.releasePointerCapture(previous.pointerId);
    } catch { /* A removed node or browser cancellation may already release it. */ }
  }
  function cancel() {
    generation++;
    if (timer !== undefined) clearTimeout(timer);
    timer = undefined;
    queue = [];
    releaseStroke();
    for (const grid of grids) {
      for (const overlay of grid.overlays.values()) restore(grid, overlay);
      grid.overlays.clear();
      if (grid.raster) drawRaster(grid);
    }
  }
  function flush() {
    if (timer !== undefined) clearTimeout(timer);
    timer = undefined;
    if (processing || !queue.length) return;
    if (!options.isActive()) { cancel(); return; }
    const first = queue[0];
    const batch: Mark[] = [];
    while (queue.length && batch.length < 120 && queue[0].grid === first.grid && queue[0].action === first.action && queue[0].columns === first.columns && queue[0].rows === first.rows) batch.push(queue.shift()!);
    const epoch = generation;
    processing = true;
    void Promise.resolve().then(() => epoch === generation && options.isActive()
      ? options.dispatch({ type: first.action, ...(first.grid.raster ? { columns: first.columns, rows: first.rows } : {}), cells: batch.map(mark => ({ cell: mark.cell, color: mark.color })) }) : false)
      .catch(() => false)
      .then(saved => {
        if (epoch !== generation) return;
        if (!saved) { cancel(); return; }
        // A newer stroke may cover the same cell while this batch is saving.
        for (const mark of batch) {
          const overlay = mark.grid.overlays.get(mark.cell);
          if (overlay?.sequence === mark.sequence) {
            restore(mark.grid, overlay);
            mark.grid.overlays.delete(mark.cell);
          }
        }
        if (first.grid.raster) drawCursor(first.grid);
      }).finally(() => { processing = false; if (queue.length) flush(); });
  }
  function schedule() {
    if (timer === undefined && !processing) timer = setTimeout(flush, 40);
  }
  function markCell(current: Stroke, cell: number) {
    if (current.visited.has(cell) || queue.length >= 8192) return;
    const node = current.grid.raster ? undefined : cellNode(current.grid, cell);
    if (!current.grid.raster && !node) return;
    current.visited.add(cell);
    const property = node ? colorProperty(node) : undefined;
    const existing = current.grid.overlays.get(cell);
    const mark = { grid: current.grid, action: current.config.action, cell, color: current.config.color, colorValue: current.config.colorValue, sequence: ++sequence, columns: current.config.columns, rows: current.config.rows };
    current.grid.overlays.set(cell, { ...mark, base: existing?.base ?? (node && property ? node.style[property] : pixelColor(current.grid, cell)) });
    if (node && property) node.style[property] = mark.colorValue;
    else drawPixel(current.grid, cell, mark.colorValue);
    queue.push(mark);
    schedule();
  }
  function cellAt(current: Stroke, x: number, y: number): number | null {
    const root = resolveRoot(current.grid);
    if (!root || !Number.isFinite(x) || !Number.isFinite(y)) return null;
    const box = root.getBoundingClientRect();
    if (!box.width || !box.height || x < box.left || y < box.top || x >= box.right || y >= box.bottom) return null;
    const target = current.grid.raster ? undefined : document.elementFromPoint(x, y)?.closest('[data-paint-cell]');
    if (target?.closest('[data-paint-grid]') === root) {
      const index = Number(target.getAttribute('data-paint-cell'));
      if (Number.isInteger(index) && index >= 0 && index < current.config.columns * current.config.rows) return index;
    }
    return Math.floor((y - box.top) / box.height * current.config.rows) * current.config.columns
      + Math.floor((x - box.left) / box.width * current.config.columns);
  }
  function sample(current: Stroke, x: number, y: number) {
    const cell = cellAt(current, x, y);
    if (cell === null) { current.previous = null; return; }
    const previous = current.previous ?? cell;
    const columns = current.config.columns;
    let x0 = previous % columns;
    let y0 = Math.floor(previous / columns);
    const x1 = cell % columns;
    const y1 = Math.floor(cell / columns);
    const dx = Math.abs(x1 - x0), dy = -Math.abs(y1 - y0);
    const sx = x0 < x1 ? 1 : -1, sy = y0 < y1 ? 1 : -1;
    let error = dx + dy;
    // Fill skipped cells in fast pointer moves rather than leaving dotted lines.
    for (;;) {
      markCell(current, y0 * columns + x0);
      if (x0 === x1 && y0 === y1) break;
      const twice = 2 * error;
      if (twice >= dy) { error += dy; x0 += sx; }
      if (twice <= dx) { error += dx; y0 += sy; }
    }
    current.previous = cell;
  }
  function reapply() {
    for (const grid of grids) {
      const root = resolveRoot(grid);
      if (!root || !configFor(root)) {
        if (grid.overlays.size || stroke?.grid === grid) cancel();
      }
    }
    for (const root of document.querySelectorAll<HTMLElement | SVGElement>('[data-paint-grid]')) {
      const config = configFor(root);
      if (config) {
        root.style.touchAction = 'none'; root.style.userSelect = 'none';
        const grid = gridFor(root, config);
        if (grid.raster) drawRaster(grid);
      }
    }
    for (const grid of grids) for (const overlay of grid.overlays.values()) {
      if (grid.raster) continue;
      const node = cellNode(grid, overlay.cell);
      if (!node) continue;
      const property = colorProperty(node);
      // Called after the host's authoritative DOM update, before drawing any
      // unsaved local marks back over it.
      overlay.base = node.style[property];
      node.style[property] = overlay.colorValue;
    }
  }
  document.addEventListener('pointerdown', event => {
    if (!options.isActive() || stroke || event.button !== 0 || event.isPrimary === false || !(event.target instanceof Element)) return;
    const root = event.target.closest('[data-paint-grid]');
    const config = root && configFor(root);
    if (!root || !config) return;
    const grid = gridFor(root, config);
    const current: Stroke = { pointerId: event.pointerId, grid, config, previous: null, visited: new Set() };
    if (cellAt(current, event.clientX, event.clientY) === null) return;
    if (grid.raster && isRaster(root)) {
      grid.cursor = cellAt(current, event.clientX, event.clientY)!;
      root.focus({ preventScroll: true });
      grid.cursorVisible = false;
      drawRaster(grid);
    }
    stroke = current;
    event.preventDefault();
    try { root.setPointerCapture(event.pointerId); } catch { /* Document listeners still handle the gesture. */ }
    sample(current, event.clientX, event.clientY);
  }, true);
  document.addEventListener('pointermove', event => {
    if (!stroke || stroke.pointerId !== event.pointerId) return;
    if (!options.isActive()) { cancel(); return; }
    if (event.buttons === 0 && event.pointerType !== 'touch') { releaseStroke(); flush(); return; }
    event.preventDefault();
    sample(stroke, event.clientX, event.clientY);
  }, true);
  document.addEventListener('pointerup', event => {
    if (!stroke || stroke.pointerId !== event.pointerId) return;
    if (options.isActive()) sample(stroke, event.clientX, event.clientY);
    event.preventDefault();
    releaseStroke();
    flush();
  }, true);
  for (const name of ['pointercancel', 'lostpointercapture']) document.addEventListener(name, event => {
    if (!stroke || stroke.pointerId !== (event as PointerEvent).pointerId) return;
    releaseStroke();
    flush();
  }, true);
  document.addEventListener('click', event => {
    if (!(event.target instanceof Element)) return;
    if (event.detail === 0 && options.isActive()) {
      const node = event.target.closest('[data-paint-cell]');
      const root = node?.closest('[data-paint-grid]');
      const config = root && configFor(root);
      const cell = Number(node?.getAttribute('data-paint-cell'));
      if (root && config && Number.isInteger(cell) && cell >= 0 && cell < config.columns * config.rows) {
        event.preventDefault();
        event.stopImmediatePropagation();
        markCell({ pointerId: -1, grid: gridFor(root, config), config, previous: null, visited: new Set() }, cell);
        flush();
      }
      return;
    }
    if (!suppressClick || Date.now() > suppressClick.until) return;
    if (suppressClick.root.contains(event.target)) { event.preventDefault(); event.stopImmediatePropagation(); suppressClick = undefined; }
  }, true);
  document.addEventListener('keydown', event => {
    if (!options.isActive() || !isRaster(event.target as Element) || event.altKey || event.metaKey) return;
    const root = event.target as HTMLCanvasElement;
    const config = configFor(root);
    if (!config) return;
    const grid = gridFor(root, config);
    const column = grid.cursor % config.columns, row = Math.floor(grid.cursor / config.columns);
    let next = grid.cursor;
    switch (event.key) {
      case 'ArrowLeft': next -= column > 0 ? 1 : 0; break;
      case 'ArrowRight': next += column < config.columns - 1 ? 1 : 0; break;
      case 'ArrowUp': next -= row > 0 ? config.columns : 0; break;
      case 'ArrowDown': next += row < config.rows - 1 ? config.columns : 0; break;
      case 'Home': next = event.ctrlKey ? 0 : grid.cursor - column; break;
      case 'End': next = event.ctrlKey ? config.columns * config.rows - 1 : grid.cursor - column + config.columns - 1; break;
      case ' ': case 'Enter':
        markCell({ pointerId: -1, grid, config, previous: null, visited: new Set() }, grid.cursor);
        flush(); break;
      default: return;
    }
    event.preventDefault();
    event.stopImmediatePropagation();
    grid.cursor = next;
    grid.cursorVisible = true;
    drawRaster(grid);
  }, true);
  document.addEventListener('focusin', event => {
    if (!isRaster(event.target as Element)) return;
    const root = event.target as HTMLCanvasElement, config = configFor(root);
    if (!config) return;
    const grid = gridFor(root, config);
    grid.cursorVisible = true;
    drawRaster(grid);
  });
  document.addEventListener('focusout', event => {
    const grid = grids.find(item => item.root === event.target && item.raster);
    if (grid) { grid.cursorVisible = false; drawRaster(grid); }
  });
  reapply();
  return { reapply, cancel };
}
