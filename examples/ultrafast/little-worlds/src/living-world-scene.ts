/**
 * A small, physical world. Every feature is anchored to the same spherical
 * surface, so rotation, lighting and occlusion remain coherent.
 *
 * The module deliberately creates no renderer or animation loop. The host owns
 * those, and can dispose the complete scene with the returned callback.
 */
import * as THREE from 'three'
type V3 = import('three').Vector3
type Geometry = import('three').BufferGeometry
type Material = import('three').Material

export function createLivingWorldScene() {
  const world = new THREE.Group()
  world.name = 'little-worlds-devday-globe'
  const geometries = new Set<Geometry>()
  const materials = new Set<Material>()
  const textures = new Set<import('three').Texture>()
  const trackGeometry = <T extends Geometry>(geometry: T): T => { geometries.add(geometry); return geometry }
  const trackMaterial = <T extends Material>(material: T): T => { materials.add(material); return material }
  const clamp = (value: number) => Math.max(0, Math.min(1, value))
  const smooth = (a: number, b: number, value: number) => {
    const t = clamp((value - a) / (b - a))
    return t * t * (3 - 2 * t)
  }
  const direction = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z).normalize()
  function surfaceNormals(geometry: Geometry) {
    geometry.computeVertexNormals()
    const position = geometry.getAttribute('position')
    const normals = geometry.getAttribute('normal')
    const fallback = new THREE.Vector3()
    for (let i = 0; i < normals.count; i++) {
      // SphereGeometry includes unused pole vertices with no adjacent faces.
      if (Math.hypot(normals.getX(i), normals.getY(i), normals.getZ(i)) < 0.01) {
        fallback.fromBufferAttribute(position, i).normalize()
        normals.setXYZ(i, fallback.x, fallback.y, fallback.z)
      }
    }
  }

  // Smooth, deterministic three-dimensional variation is continuous at the
  // longitude seam and stays attached to the world as it turns.
  function noise(p: V3, scale = 1) {
    const x = p.x * scale, y = p.y * scale, z = p.z * scale
    return (Math.sin(x * 1.91 + y * 2.13 + z * 0.87)
      + Math.sin(-x * 2.43 + y * 0.71 + z * 1.73 + 2.1)
      + Math.sin(x * 0.83 - y * 1.97 + z * 2.37 + 4.7)) / 3
  }
  const regions = [
    { normal: direction(-0.58, -0.24, 0.79), width: 0.62, strength: 1.0 },
    { normal: direction(0.15, -0.70, 0.69), width: 0.41, strength: 0.86 },
    { normal: direction(0.66, 0.65, 0.38), width: 0.43, strength: 0.95 },
    { normal: direction(-0.30, 0.83, 0.46), width: 0.23, strength: 0.92 },
    { normal: direction(0.91, -0.10, 0.26), width: 0.25, strength: 0.77 },
    { normal: direction(-0.64, 0.23, -0.73), width: 0.56, strength: 1.0 },
    { normal: direction(0.41, -0.32, -0.85), width: 0.52, strength: 0.95 },
  ]
  const hills = [
    { normal: direction(-0.52, 0.02, 0.85), width: 0.27, height: 0.145 },
    { normal: direction(-0.52, -0.44, 0.72), width: 0.32, height: 0.112 },
    { normal: direction(0.64, 0.69, 0.33), width: 0.27, height: 0.140 },
    { normal: direction(-0.75, 0.35, -0.56), width: 0.29, height: 0.115 },
    { normal: direction(0.35, -0.40, -0.85), width: 0.30, height: 0.130 },
  ]
  const ridges = [
    { normal: direction(-0.48, -0.16, 0.86), length: 0.34, width: 0.068, height: 0.036, angle: -0.55 },
    { normal: direction(0.10, -0.68, 0.72), length: 0.23, width: 0.064, height: 0.038, angle: 0.6 },
    { normal: direction(0.67, 0.65, 0.32), length: 0.25, width: 0.060, height: 0.034, angle: 0.45 },
    { normal: direction(-0.63, 0.27, -0.72), length: 0.28, width: 0.075, height: 0.038, angle: -0.35 },
  ].map(ridge => {
    const east = new THREE.Vector3().crossVectors(new THREE.Vector3(0, 1, 0), ridge.normal).normalize()
    const north = new THREE.Vector3().crossVectors(ridge.normal, east).normalize()
    return {
      ...ridge,
      along: east.clone().multiplyScalar(Math.cos(ridge.angle)).addScaledVector(north, Math.sin(ridge.angle)),
      across: east.clone().multiplyScalar(-Math.sin(ridge.angle)).addScaledVector(north, Math.cos(ridge.angle)),
    }
  })
  const lakeNormal = direction(0.38, 0.35, 0.86)
  const lakeU = new THREE.Vector3().crossVectors(new THREE.Vector3(0, 1, 0), lakeNormal).normalize()
  const lakeV = new THREE.Vector3().crossVectors(lakeNormal, lakeU).normalize()
  const lakeWidth = 0.285
  const lakeHeight = 0.205
  const waterRadius = 1.006
  const lakeBoundary = (angle: number) => 1 + 0.13 * Math.cos(angle * 3 + 0.6) + 0.07 * Math.sin(angle * 2 - 0.3)
  function lakeDistance(p: V3) {
    const facing = p.dot(lakeNormal)
    if (facing < 0.55) return 10
    const u = p.dot(lakeU) / facing / lakeWidth
    const v = p.dot(lakeV) / facing / lakeHeight
    return Math.hypot(u, v) / lakeBoundary(Math.atan2(v, u))
  }
  function lakeDirection(angle: number, radial: number) {
    const boundary = lakeBoundary(angle) * radial
    return lakeNormal.clone()
      .addScaledVector(lakeU, Math.cos(angle) * lakeWidth * boundary)
      .addScaledVector(lakeV, Math.sin(angle) * lakeHeight * boundary)
      .normalize()
  }
  function terrain(p: V3) {
    let field = 0
    for (const region of regions) {
      const d2 = 2 * (1 - p.dot(region.normal))
      field = Math.max(field, region.strength * Math.exp(-d2 / (region.width * region.width)))
    }
    field += noise(p, 5.0) * 0.095 + noise(p, 10.8) * 0.022
    const moss = smooth(0.36, 0.43, field)
    let elevation = 0
    for (const hill of hills) {
      elevation += hill.height * Math.exp(-2 * (1 - p.dot(hill.normal)) / (hill.width * hill.width))
    }
    // Wide hills continue under the charcoal soil. Lower curving ridges add readable
    // topography inside the moss without changing the globe into a spiky shape.
    for (const ridge of ridges) {
      const facing = p.dot(ridge.normal)
      if (facing < 0.7) continue
      const along = p.dot(ridge.along) / facing
      const across = p.dot(ridge.across) / facing + Math.sin(along * 9) * 0.018
      const distance = (along / ridge.length) ** 2 + (across / ridge.width) ** 2
      elevation += ridge.height * Math.exp(-distance) * moss
    }
    let radius = 1 + noise(p, 2.2) * 0.0045 + elevation + moss * (0.009 + noise(p, 8.2) * 0.006 + noise(p, 21) * 0.0012)
    const lake = lakeDistance(p)
    if (lake < 1.24) radius = 0.982 + (radius - 0.982) * smooth(1.01, 1.24, lake)
    return { radius, moss: moss * smooth(1.15, 1.40, lake), elevation }
  }

  // One small texture supplies material grain, rather than thousands of loose
  // particles. Mipmaps keep its fine detail stable at smaller screen sizes.
  const textureWidth = 512, textureHeight = 256
  const textureData = new Uint8Array(textureWidth * textureHeight * 4)
  const hash = (x: number, y: number) => {
    let value = Math.imul(x + 374761393, 668265263) ^ Math.imul(y + 1442695041, 2246822519)
    value = Math.imul(value ^ (value >>> 13), 1274126177)
    return ((value ^ (value >>> 16)) >>> 0) / 4294967295
  }
  for (let y = 0; y < textureHeight; y++) {
    for (let x = 0; x < textureWidth; x++) {
      const fine = hash(x, y)
      const broad = hash(Math.floor(x / 3), Math.floor(y / 3))
      const value = Math.round(208 + fine * 37 + broad * 10)
      const index = (y * textureWidth + x) * 4
      textureData[index] = textureData[index + 1] = textureData[index + 2] = value
      textureData[index + 3] = 255
    }
  }
  const grain = new THREE.DataTexture(textureData, textureWidth, textureHeight, THREE.RGBAFormat)
  grain.wrapS = grain.wrapT = THREE.RepeatWrapping
  grain.magFilter = THREE.LinearFilter
  grain.minFilter = THREE.LinearMipmapLinearFilter
  grain.generateMipmaps = true
  grain.needsUpdate = true
  textures.add(grain)

  const sandColor = new THREE.Color('#42454b')
  const mossColor = new THREE.Color('#168b52')
  const mossLight = new THREE.Color('#04b84c')
  const surfaceColor = new THREE.Color()
  const landGeometry = trackGeometry(new THREE.SphereGeometry(1, 160, 112))
  const landPosition = landGeometry.getAttribute('position')
  const colors = new Float32Array(landPosition.count * 3)
  const p = new THREE.Vector3()
  for (let index = 0; index < landPosition.count; index++) {
    p.fromBufferAttribute(landPosition, index).normalize()
    const sample = terrain(p)
    surfaceColor.copy(mossColor).lerp(mossLight, clamp(0.4 + noise(p, 4.1) * 0.35 + sample.elevation * 2))
    surfaceColor.lerp(sandColor, 1 - sample.moss)
    const variation = 1 + noise(p, 22) * 0.014
    colors[index * 3] = surfaceColor.r * variation
    colors[index * 3 + 1] = surfaceColor.g * variation
    colors[index * 3 + 2] = surfaceColor.b * variation
    landPosition.setXYZ(index, p.x * sample.radius, p.y * sample.radius, p.z * sample.radius)
  }
  landGeometry.setAttribute('color', new THREE.BufferAttribute(colors, 3))
  surfaceNormals(landGeometry)
  landGeometry.computeBoundingSphere()
  const landMaterial = trackMaterial(new THREE.MeshStandardMaterial({
    vertexColors: true, roughness: 0.96, map: grain, bumpMap: grain, bumpScale: 0.023,
  }))
  const land = new THREE.Mesh(landGeometry, landMaterial)
  land.name = 'continuous-terrain'
  land.castShadow = land.receiveShadow = true
  world.add(land)

  // The water follows the planet's equipotential surface. Its recessed bed and
  // matching bank keep it embedded in the terrain, including at grazing angles.
  const segments = 96, waterRings = 12
  const waterPositions: number[] = [], waterColors: number[] = [], waterIndices: number[] = []
  const deepWater = new THREE.Color('#6d40af'), shallowWater = new THREE.Color('#924ff7')
  for (let ring = 0; ring <= waterRings; ring++) {
    const radial = ring / waterRings
    for (let segment = 0; segment <= segments; segment++) {
      const point = lakeDirection(segment / segments * Math.PI * 2, radial).multiplyScalar(waterRadius)
      waterPositions.push(point.x, point.y, point.z)
      surfaceColor.copy(deepWater).lerp(shallowWater, Math.pow(radial, 4) * 0.8)
      waterColors.push(surfaceColor.r, surfaceColor.g, surfaceColor.b)
      if (ring < waterRings && segment < segments) {
        const a = ring * (segments + 1) + segment, b = a + segments + 1
        waterIndices.push(a, b, a + 1, b, b + 1, a + 1)
      }
    }
  }
  const waterGeometry = trackGeometry(new THREE.BufferGeometry())
  waterGeometry.setAttribute('position', new THREE.Float32BufferAttribute(waterPositions, 3))
  waterGeometry.setAttribute('color', new THREE.Float32BufferAttribute(waterColors, 3))
  waterGeometry.setIndex(waterIndices)
  // The exact sphere normals avoid radial fan highlights in the water.
  const waterNormals = Float32Array.from(waterPositions, value => value / waterRadius)
  waterGeometry.setAttribute('normal', new THREE.BufferAttribute(waterNormals, 3))
  const waterMaterial = trackMaterial(new THREE.MeshPhysicalMaterial({
    vertexColors: true, roughness: 0.29, metalness: 0.02, clearcoat: 0.3, clearcoatRoughness: 0.22,
  }))
  const water = new THREE.Mesh(waterGeometry, waterMaterial)
  water.name = 'quiet-lake'
  water.receiveShadow = true
  world.add(water)

  const bankPositions: number[] = [], bankIndices: number[] = []
  const bankRings = 5
  for (let ring = 0; ring <= bankRings; ring++) {
    const radial = 1 + ring / bankRings * 0.23
    for (let segment = 0; segment <= segments; segment++) {
      const point = lakeDirection(segment / segments * Math.PI * 2, radial)
      // The inner lip meets the water exactly; the outer lip sinks very slightly
      // into the original surface, avoiding either a floating rim or a crack.
      const lip = waterRadius + Math.sin(ring / bankRings * Math.PI) * 0.006
      const radius = Math.max(lip, terrain(point).radius + 0.0004)
      point.multiplyScalar(radius)
      bankPositions.push(point.x, point.y, point.z)
      if (ring < bankRings && segment < segments) {
        const a = ring * (segments + 1) + segment, b = a + segments + 1
        bankIndices.push(a, b, a + 1, b, b + 1, a + 1)
      }
    }
  }
  const bankGeometry = trackGeometry(new THREE.BufferGeometry())
  bankGeometry.setAttribute('position', new THREE.Float32BufferAttribute(bankPositions, 3))
  bankGeometry.setIndex(bankIndices)
  bankGeometry.computeVertexNormals()
  const bankMaterial = trackMaterial(new THREE.MeshStandardMaterial({ color: '#77727f', roughness: 1 }))
  const bank = new THREE.Mesh(bankGeometry, bankMaterial)
  bank.name = 'lake-shore'
  bank.castShadow = bank.receiveShadow = true
  world.add(bank)

  const trunkMaterial = trackMaterial(new THREE.MeshStandardMaterial({ color: '#828087', roughness: 1 }))
  const foliageMaterials = ['#20a964', '#04b84c', '#58dc8a'].map(color => trackMaterial(new THREE.MeshStandardMaterial({
    color, roughness: 1, map: grain, bumpMap: grain, bumpScale: 0.026,
  })))
  const up = new THREE.Vector3(0, 1, 0)
  function addTree(normal: V3, height: number, crownRadius: number, variant: number) {
    const tree = new THREE.Group()
    tree.name = `grove-tree-${variant + 1}`
    tree.position.copy(normal).multiplyScalar(terrain(normal).radius - 0.005)
    tree.quaternion.setFromUnitVectors(up, normal)
    const trunkGeometry = trackGeometry(new THREE.CylinderGeometry(0.007, 0.011, height, 9))
    const trunk = new THREE.Mesh(trunkGeometry, trunkMaterial)
    trunk.position.y = height / 2
    trunk.castShadow = trunk.receiveShadow = true
    tree.add(trunk)
    const crownGeometry = trackGeometry(new THREE.SphereGeometry(1, 48, 32))
    const vertices = crownGeometry.getAttribute('position')
    const vertex = new THREE.Vector3()
    for (let i = 0; i < vertices.count; i++) {
      vertex.fromBufferAttribute(vertices, i)
      const lump = 1 + noise(vertex, 3.6 + variant * 0.3) * 0.12 + noise(vertex, 8) * 0.045 + noise(vertex, 18) * 0.02
      vertices.setXYZ(i, vertex.x * crownRadius * lump, vertex.y * crownRadius * 1.12 * lump, vertex.z * crownRadius * lump)
    }
    surfaceNormals(crownGeometry)
    const crown = new THREE.Mesh(crownGeometry, foliageMaterials[variant])
    crown.position.y = height + crownRadius * 0.52
    crown.castShadow = crown.receiveShadow = true
    tree.add(crown)
    world.add(tree)
  }
  addTree(direction(-0.38, 0.82, 0.43), 0.105, 0.068, 0)
  addTree(direction(-0.265, 0.875, 0.405), 0.145, 0.077, 1)
  addTree(direction(-0.175, 0.815, 0.552), 0.105, 0.060, 2)

  const rockMaterial = trackMaterial(new THREE.MeshStandardMaterial({ color: '#a8a8ae', roughness: 1, bumpMap: grain, bumpScale: 0.008 }))
  function addStone(normal: V3, size: number, turn: number) {
    const rockGeometry = trackGeometry(new THREE.SphereGeometry(1, 14, 10))
    const vertices = rockGeometry.getAttribute('position')
    const vertex = new THREE.Vector3()
    for (let i = 0; i < vertices.count; i++) {
      vertex.fromBufferAttribute(vertices, i)
      const lump = 1 + noise(vertex, 2.3) * 0.16
      vertices.setXYZ(i, vertex.x * size * lump, vertex.y * size * 0.42 * lump, vertex.z * size * 0.67 * lump)
    }
    surfaceNormals(rockGeometry)
    const stone = new THREE.Mesh(rockGeometry, rockMaterial)
    stone.position.copy(normal).multiplyScalar(terrain(normal).radius + size * 0.11)
    stone.quaternion.setFromUnitVectors(up, normal)
    stone.rotateY(turn)
    stone.castShadow = stone.receiveShadow = true
    world.add(stone)
  }
  addStone(direction(-0.44, -0.08, 0.895), 0.048, 0.5)
  addStone(direction(-0.49, -0.11, 0.86), 0.030, 0.2)
  addStone(direction(0.68, 0.69, 0.25), 0.053, -0.7)
  addStone(direction(-0.29, 0.79, 0.54), 0.026, -0.5)

  // The event's point-and-line language follows the terrain, so the grid rotates
  // with the physical world and does not compete with pointer interaction.
  const gridPositions: number[] = []
  const surfacePoint = (latitude: number, longitude: number) => {
    const normal = new THREE.Vector3(Math.cos(latitude) * Math.cos(longitude), Math.sin(latitude), Math.cos(latitude) * Math.sin(longitude))
    return normal.multiplyScalar(Math.max(terrain(normal).radius, lakeDistance(normal) < 1.02 ? waterRadius : 0) + 0.006)
  }
  const addGridSegment = (a: V3, b: V3) => gridPositions.push(a.x, a.y, a.z, b.x, b.y, b.z)
  for (let latitude = -2; latitude <= 2; latitude++) {
    for (let segment = 0; segment < 120; segment++) {
      addGridSegment(surfacePoint(latitude * Math.PI / 6, segment / 120 * Math.PI * 2), surfacePoint(latitude * Math.PI / 6, (segment + 1) / 120 * Math.PI * 2))
    }
  }
  for (let longitude = 0; longitude < 12; longitude++) {
    for (let segment = 0; segment < 60; segment++) {
      addGridSegment(surfacePoint(-Math.PI / 2 + segment / 60 * Math.PI, longitude * Math.PI / 6), surfacePoint(-Math.PI / 2 + (segment + 1) / 60 * Math.PI, longitude * Math.PI / 6))
    }
  }
  const gridGeometry = trackGeometry(new THREE.BufferGeometry())
  gridGeometry.setAttribute('position', new THREE.Float32BufferAttribute(gridPositions, 3))
  const gridMaterial = trackMaterial(new THREE.LineBasicMaterial({ color: '#d5e6dd', transparent: true, opacity: .13, depthWrite: false }))
  const grid = new THREE.LineSegments(gridGeometry, gridMaterial)
  grid.name = 'devday-coordinate-grid'
  world.add(grid)

  return {
    world,
    dispose() {
      geometries.forEach(geometry => geometry.dispose())
      materials.forEach(material => material.dispose())
      textures.forEach(texture => texture.dispose())
      world.clear()
    },
  }
}
