export type ConstellationCamera = { yaw: number; pitch: number; zoom: number; x: number; y: number };
export type ConstellationSize = { width: number; height: number };
export type GalaxyPoint = { x: number; y: number; z: number };
export type GalaxyProjection = { x: number; y: number; depth: number; scale: number };
export const initialCamera: ConstellationCamera = { yaw: 0, pitch: 0, zoom: 1, x: 0, y: 0 };
export const clamp = (value: number, low: number, high: number) => Math.max(low, Math.min(high, value));

// A loose arrangement in a shallow disk, rather than points on a sphere. The
// opening composition leaves room for all eight portrait hit areas on a phone.
const anchors: Record<string, GalaxyPoint> = {
  mira: { x: -.86, y: -.84, z: .12 },
  james: { x: .86, y: -.84, z: -.10 },
  jake: { x: .86, y: 0, z: .08 },
  erica: { x: .86, y: .84, z: .16 },
  leo: { x: -.86, y: .84, z: -.16 },
  iris: { x: -.86, y: 0, z: -.10 },
  luca: { x: 0, y: .84, z: .04 },
  karen: { x: 0, y: -.84, z: .06 },
};
const irisId = 'person_8d44ad87-657a-4df8-8739-c9251f897834';

function hash(id: string, seed = 2166136261) {
  let value = seed;
  for (let i = 0; i < id.length; i++) value = Math.imul(value ^ id.charCodeAt(i), 16777619);
  return (value >>> 0) / 0xffffffff;
}

/** A person's position depends on identity, never directory order or count. */
export function positionForPerson(id: string): GalaxyPoint {
  const key = id === irisId ? 'iris' : id;
  if (anchors[key]) return { ...anchors[key] };
  const alongArm = hash(key);
  const arm = Math.floor(hash(key, 374761393) * 3);
  const phase = alongArm * Math.PI * 2.4 + arm * Math.PI * 2 / 3;
  const radius = .28 + .76 * Math.sqrt(alongArm);
  return {
    x: Math.cos(phase) * radius,
    y: Math.sin(phase) * radius * .9,
    z: (hash(key, 668265263) - .5) * .30,
  };
}

/** Bounded ambient movement in world space; time is in seconds. */
export function galaxyDrift(id: string, time: number): GalaxyPoint {
  const phase = hash(id === irisId ? 'iris' : id) * Math.PI * 2;
  return {
    x: .018 * (Math.sin(time * .12 + phase) - Math.sin(phase)),
    y: .014 * (Math.sin(time * .10 + phase * 1.7) - Math.sin(phase * 1.7)),
    z: .008 * (Math.sin(time * .08 + phase * .7) - Math.sin(phase * .7)),
  };
}

function viewport(size: ConstellationSize, camera: ConstellationCamera) {
  const width = Math.max(1, size.width);
  const height = Math.max(1, size.height);
  const zoom = Math.max(.0001, camera.zoom);
  return {
    radiusX: Math.min(width * .36, height * .50) * zoom,
    radiusY: Math.min(height * .29, width * .48) * zoom,
    centerX: width / 2 + camera.x,
    centerY: height / 2 - 12 + camera.y,
  };
}

/**
 * Orthographic projection makes depth crossings continuous. A depth cue changes
 * portrait size gently; no collision response pushes neighboring people around.
 */
export function projectGalaxyPoint(world: GalaxyPoint, camera: ConstellationCamera, size: ConstellationSize): GalaxyProjection {
  const cosYaw = Math.cos(camera.yaw), sinYaw = Math.sin(camera.yaw);
  const cosPitch = Math.cos(camera.pitch), sinPitch = Math.sin(camera.pitch);
  // Horizontal dragging spins the galaxy in its own plane. Vertical dragging
  // tilts that plane; yaw can never turn the whole composition edge-on.
  const turnX = world.x * cosYaw - world.y * sinYaw;
  const planeY = world.x * sinYaw + world.y * cosYaw;
  const turnY = planeY * cosPitch - world.z * sinPitch;
  const depth = planeY * sinPitch + world.z * cosPitch;
  const view = viewport(size, camera);
  return {
    x: view.centerX + turnX * view.radiusX,
    y: view.centerY + turnY * view.radiusY,
    depth,
    scale: clamp((.94 + depth * .10) * Math.sqrt(Math.max(.0001, camera.zoom)), .7, 1.25),
  };
}

/**
 * Inverse projection at a fixed camera-space depth. Holding the depth from
 * pointer-down lets a person follow the pointer exactly at any camera angle.
 */
export function unprojectGalaxyPoint(screen: { x: number; y: number }, depth: number, camera: ConstellationCamera, size: ConstellationSize): GalaxyPoint {
  const view = viewport(size, camera);
  const turnX = (screen.x - view.centerX) / view.radiusX;
  const turnY = (screen.y - view.centerY) / view.radiusY;
  const cosYaw = Math.cos(camera.yaw), sinYaw = Math.sin(camera.yaw);
  const cosPitch = Math.cos(camera.pitch), sinPitch = Math.sin(camera.pitch);
  const planeY = turnY * cosPitch + depth * sinPitch;
  const worldZ = -turnY * sinPitch + depth * cosPitch;
  return {
    x: turnX * cosYaw + planeY * sinYaw,
    y: -turnX * sinYaw + planeY * cosYaw,
    z: worldZ,
  };
}

/** Explicit world positions pin dragged people; everybody else drifts gently. */
export function projectConstellation<T extends { id: string }>(people: T[], camera: ConstellationCamera, time: number, size: ConstellationSize, positions?: ReadonlyMap<string, GalaxyPoint>) {
  return [...people].sort((a, b) => a.id.localeCompare(b.id)).map(person => {
    const pinned = positions?.get(person.id);
    let world = pinned;
    if (!world) {
      const base = positionForPerson(person.id);
      const drift = galaxyDrift(person.id, time);
      world = { x: base.x + drift.x, y: base.y + drift.y, z: base.z + drift.z };
    }
    return { ...person, ...projectGalaxyPoint(world, camera, size) };
  });
}
