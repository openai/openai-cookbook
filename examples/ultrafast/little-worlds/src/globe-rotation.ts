import { Quaternion, Vector3 } from 'three';

const IDLE_SPEED = Math.PI * 2 / 60;
// One time constant lets a throw settle directly into the ordinary spin,
// retaining its weight instead of braking to a stop and starting over.
const MOTION_TIME_CONSTANT = 1.4;
const FRICTION = 1 / MOTION_TIME_CONSTANT;
const MAX_SPEED = 5.5;
const STOP_SPEED = 0.007;
const VELOCITY_WINDOW_MS = 120;
const RELEASE_GRACE_MS = 150;
const STALE_RELEASE_MS = 700;
const UP = new Vector3(0, 1, 0);
const RIGHT = new Vector3(1, 0, 0);

type MotionSample = { start: number; end: number; rotation: Vector3 };

/** Screen-space virtual trackball. Coordinates are measured in globe radii, with y pointing up. */
export function createGlobeRotation() {
  const quaternion = new Quaternion();
  const previousPoint = new Vector3();
  const currentPoint = new Vector3();
  const cameraBasis = new Quaternion();
  const cameraInverse = new Quaternion();
  const delta = new Quaternion();
  const pitchRotation = new Quaternion();
  const angularVelocity = new Vector3();
  const pendingMotion = new Vector3();
  const axis = new Vector3();
  let samples: MotionSample[] = [];
  let isDragging = false;
  let cruiseSpeed = IDLE_SPEED;
  let autonomousMotion = true;
  let previousTime = 0;
  let lastMotionTime = -Infinity;

  function project(x: number, y: number, target: Vector3) {
    if (!Number.isFinite(x) || !Number.isFinite(y)) return false;
    // The hyperbolic skirt stays continuous at the silhouette and avoids a hard rim.
    const safeX = Math.max(-1e6, Math.min(1e6, x));
    const safeY = Math.max(-1e6, Math.min(1e6, y));
    const radiusSquared = safeX * safeX + safeY * safeY;
    const z = radiusSquared <= 0.5 ? Math.sqrt(1 - radiusSquared) : 0.5 / Math.sqrt(radiusSquared);
    target.set(safeX, safeY, z).normalize();
    return true;
  }

  function clearMomentum() {
    angularVelocity.set(0, 0, 0);
    pendingMotion.set(0, 0, 0);
    cruiseSpeed = 0;
    samples = [];
    lastMotionTime = -Infinity;
  }

  function applyRotation(rotation: Quaternion) {
    quaternion.premultiply(rotation).normalize();
  }

  function estimateVelocity(time: number) {
    const earliest = time - VELOCITY_WINDOW_MS;
    samples = samples.filter(sample => sample.end > earliest);
    angularVelocity.set(0, 0, 0);
    if (!samples.length) return;
    for (const sample of samples) {
      const fraction = (sample.end - Math.max(sample.start, earliest)) / (sample.end - sample.start);
      angularVelocity.addScaledVector(sample.rotation, fraction);
    }
    const duration = (time - Math.max(samples[0].start, earliest)) / 1000;
    if (duration > 0) angularVelocity.divideScalar(duration).clampLength(0, MAX_SPEED);
  }

  return {
    quaternion,
    get dragging() { return isDragging; },
    get moving() { return !isDragging && angularVelocity.lengthSq() > STOP_SPEED * STOP_SPEED; },

    begin(x: number, y: number, timeMs: number, cameraQuaternion: Quaternion) {
      if (!Number.isFinite(timeMs) || !project(x, y, previousPoint)) return;
      isDragging = true;
      clearMomentum();
      previousTime = timeMs;
      cameraBasis.copy(cameraQuaternion).normalize();
      cameraInverse.copy(cameraBasis).invert();
    },

    drag(x: number, y: number, timeMs: number) {
      if (!isDragging || !Number.isFinite(timeMs) || timeMs < previousTime || !project(x, y, currentPoint)) return;
      delta.setFromUnitVectors(previousPoint, currentPoint);
      delta.premultiply(cameraBasis).multiply(cameraInverse).normalize();
      applyRotation(delta);
      previousPoint.copy(currentPoint);

      // Quaternion logarithm gives an angular displacement in the frozen camera basis.
      if (delta.w < 0) delta.set(-delta.x, -delta.y, -delta.z, -delta.w);
      const sine = Math.hypot(delta.x, delta.y, delta.z);
      const angle = 2 * Math.atan2(sine, delta.w);
      // Stationary pointer events (including pointerup at the same position)
      // must not overwrite the last measured movement with zero velocity.
      // end() handles a deliberate pause separately from the movement sample.
      if (angle <= 1e-8) return;
      lastMotionTime = timeMs;
      if (autonomousMotion) {
        axis.set(delta.x, delta.y, delta.z);
        if (sine > 1e-8) axis.multiplyScalar(angle / sine);
        else axis.set(0, 0, 0);
        pendingMotion.add(axis);
        if (timeMs > previousTime) {
          // A hold before dragging is not part of the movement's duration.
          // Bound sparse event intervals to the recent sampling window.
          samples.push({ start: Math.max(previousTime, timeMs - VELOCITY_WINDOW_MS), end: timeMs, rotation: pendingMotion.clone() });
          pendingMotion.set(0, 0, 0);
          estimateVelocity(timeMs);
        } else if (samples.length) {
          // Browsers can deliver several moves with one rounded timestamp.
          // Add their displacement to that sample without losing the throw.
          samples[samples.length - 1].rotation.add(pendingMotion);
          pendingMotion.set(0, 0, 0);
          estimateVelocity(timeMs);
        }
      } else {
        angularVelocity.set(0, 0, 0);
        pendingMotion.set(0, 0, 0);
        samples = [];
      }
      previousTime = timeMs;
    },

    end(timeMs: number) {
      if (!isDragging) return;
      isDragging = false;
      const age = Math.max(0, timeMs - lastMotionTime);
      if (!autonomousMotion || !Number.isFinite(age) || age >= STALE_RELEASE_MS) clearMomentum();
      else {
        // Allow ordinary pointerup latency, then smoothly fade a deliberate hold.
        const hold = Math.max(0, (age - RELEASE_GRACE_MS) / (STALE_RELEASE_MS - RELEASE_GRACE_MS));
        angularVelocity.multiplyScalar(1 - hold * hold * (3 - 2 * hold));
        pendingMotion.set(0, 0, 0);
        samples = [];
      }
    },

    cancel() {
      isDragging = false;
      clearMomentum();
    },

    step(deltaSeconds: number, allowMotion = true) {
      autonomousMotion = allowMotion;
      if (!allowMotion) {
        clearMomentum();
        return;
      }
      if (isDragging || !Number.isFinite(deltaSeconds) || deltaSeconds <= 0) return;
      const speed = angularVelocity.length();
      if (speed > Number.EPSILON) {
        // Integrate exponential drag analytically so 30, 60 and 120 Hz coast identically.
        const decay = Math.exp(-FRICTION * deltaSeconds);
        axis.copy(angularVelocity).divideScalar(speed);
        applyRotation(delta.setFromAxisAngle(axis, speed * (1 - decay) / FRICTION));
        angularVelocity.multiplyScalar(decay);
      } else {
        angularVelocity.set(0, 0, 0);
      }

      // Ease back to cruising after a grab, integrating the acceleration across the frame.
      const recovery = -Math.expm1(-deltaSeconds / MOTION_TIME_CONSTANT);
      const cruiseAngle = IDLE_SPEED * deltaSeconds
        + (cruiseSpeed - IDLE_SPEED) * MOTION_TIME_CONSTANT * recovery;
      cruiseSpeed += (IDLE_SPEED - cruiseSpeed) * recovery;
      applyRotation(delta.setFromAxisAngle(UP, cruiseAngle));
      // Carry the coast axis with the cruising world so composition is frame-rate independent.
      angularVelocity.applyQuaternion(delta);
    },

    /** Positive yaw moves the visible surface right; positive pitch moves it up. */
    nudge(yaw: number, pitch: number, cameraQuaternion = new Quaternion()) {
      if (!Number.isFinite(yaw) || !Number.isFinite(pitch)) return;
      isDragging = false;
      clearMomentum();
      cameraBasis.copy(cameraQuaternion).normalize();
      cameraInverse.copy(cameraBasis).invert();
      delta.setFromAxisAngle(UP, yaw).multiply(pitchRotation.setFromAxisAngle(RIGHT, -pitch));
      delta.premultiply(cameraBasis).multiply(cameraInverse);
      applyRotation(delta);
    },
  };
}
