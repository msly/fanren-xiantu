// Original procedural environment for the Xiantu 3D preview. No external assets.
export function createEnvironment(THREE, scene, renderer) {
  const root = new THREE.Group();
  root.name = 'Xiantu_StoneCourt';
  scene.add(root);
  const animated = [];
  let seed = 173189;
  const random = () => { seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; return seed / 4294967296; };
  const range = (a, b) => a + (b - a) * random();
  const TAU = Math.PI * 2;
  const v3 = (x, y, z) => new THREE.Vector3(x, y, z);
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const axisY = v3(0, 1, 0);
  const maxAnisotropy = Math.min(8, renderer?.capabilities?.getMaxAnisotropy?.() || 1);
  const canvas = (size) => { const c = document.createElement('canvas'); c.width = c.height = size; return c; };
  const texture = (c, color = false, repeat = 1) => {
    const t = new THREE.CanvasTexture(c);
    if (color) t.colorSpace = THREE.SRGBColorSpace;
    t.wrapS = t.wrapT = THREE.RepeatWrapping;
    t.repeat.set(repeat, repeat);
    t.anisotropy = maxAnisotropy;
    return t;
  };
  const material = (color, extra = {}) => new THREE.MeshStandardMaterial({ color, roughness: .88, metalness: .02, ...extra });
  const stoneMaps = (size = 1024) => {
    const col = canvas(size), hei = canvas(size), rough = canvas(size), norm = canvas(size);
    const c = col.getContext('2d'), h = hei.getContext('2d'), r = rough.getContext('2d'), n = norm.getContext('2d');
    const ci = c.createImageData(size, size), hi = h.createImageData(size, size), ri = r.createImageData(size, size);
    const hash = (x, y) => { let k = Math.imul(x + 491, 374761393) ^ Math.imul(y + 891, 668265263); k = Math.imul(k ^ k >>> 13, 1274126177); return ((k ^ k >>> 16) >>> 0) / 4294967295; };
    const noise = (x, y, scale) => {
      x /= scale; y /= scale; const ix = Math.floor(x), iy = Math.floor(y), ax = x - ix, ay = y - iy;
      const sx = ax * ax * (3 - 2 * ax), sy = ay * ay * (3 - 2 * ay);
      return (hash(ix, iy) * (1 - sx) + hash(ix + 1, iy) * sx) * (1 - sy) + (hash(ix, iy + 1) * (1 - sx) + hash(ix + 1, iy + 1) * sx) * sy;
    };
    for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
      const i = (y * size + x) * 4;
      const a = noise(x, y, 126), b = noise(x, y, 23), grain = hash(x, y);
      const p = 63 + a * 33 + b * 13 + grain * 10;
      const moss = Math.max(0, noise(x + 180, y + 56, 87) - .63) * 110;
      ci.data[i] = p * .87 - moss * .35; ci.data[i + 1] = p * .99 + moss * .12; ci.data[i + 2] = p * .94 - moss * .25; ci.data[i + 3] = 255;
      const level = 115 + b * 15 + grain * 7;
      hi.data[i] = hi.data[i + 1] = hi.data[i + 2] = level; hi.data[i + 3] = 255;
      ri.data[i] = ri.data[i + 1] = ri.data[i + 2] = 171 + a * 52 + grain * 15; ri.data[i + 3] = 255;
    }
    c.putImageData(ci, 0, 0); h.putImageData(hi, 0, 0); r.putImageData(ri, 0, 0);
    const center = size / 2;
    const seam = (ctx, pts, color, width) => { ctx.strokeStyle = color; ctx.lineWidth = width; ctx.lineCap = 'round'; ctx.beginPath(); ctx.moveTo(pts[0][0], pts[0][1]); for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]); ctx.stroke(); };
    // Unequal radial slabs form an old stone dais; their joints are cut into the normal map.
    const rings = [0, .23, .45, .66, .84, 1.02];
    for (let j = 1; j < rings.length; j++) {
      const rr = rings[j] * center;
      for (const [ctx, color, width] of [[c, 'rgba(12,21,19,.62)', 3.8], [h, '#383838', 4.4], [r, '#f1f1f1', 5]]) {
        ctx.beginPath(); ctx.strokeStyle = color; ctx.lineWidth = width; ctx.arc(center, center, rr, 0, TAU); ctx.stroke();
      }
      const count = 6 + j * 6, offset = j * .213;
      for (let k = 0; k < count; k++) {
        const a = k * TAU / count + offset + range(-.018, .018), r0 = rings[j - 1] * center + 1;
        const pts = [[center + Math.cos(a) * r0, center + Math.sin(a) * r0], [center + Math.cos(a + range(-.006, .006)) * (r0 + rr) / 2, center + Math.sin(a) * (r0 + rr) / 2], [center + Math.cos(a) * rr, center + Math.sin(a) * rr]];
        seam(c, pts, 'rgba(10,20,19,.68)', 3.6); seam(h, pts, '#343434', 4.2); seam(r, pts, '#eeeeee', 4.8);
        seam(c, pts.map(([x, y]) => [x + 2, y - 1]), 'rgba(168,177,158,.13)', 1.2);
      }
    }
    for (let k = 0; k < 42; k++) {
      let x = range(70, size - 70), y = range(70, size - 70), a = range(0, TAU);
      const pts = [[x, y]];
      for (let i = 0; i < 5; i++) { a += range(-.55, .55); x += Math.cos(a) * range(8, 24); y += Math.sin(a) * range(8, 24); pts.push([x, y]); }
      seam(c, pts, 'rgba(9,19,17,.58)', 1.2); seam(h, pts, '#565656', 1.6);
      if (k % 3 === 0) seam(c, pts.map(([x, y]) => [x - 1, y]), 'rgba(100,123,72,.38)', 3.2);
    }
    const height = h.getImageData(0, 0, size, size).data, ni = n.createImageData(size, size);
    for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
      const at = (xx, yy) => height[((yy + size) % size * size + (xx + size) % size) * 4] / 255;
      const dx = (at(x - 1, y) - at(x + 1, y)) * 2.8, dy = (at(x, y - 1) - at(x, y + 1)) * 2.8, len = Math.hypot(dx, dy, 1), i = (y * size + x) * 4;
      ni.data[i] = (dx / len * .5 + .5) * 255; ni.data[i + 1] = (dy / len * .5 + .5) * 255; ni.data[i + 2] = (1 / len * .5 + .5) * 255; ni.data[i + 3] = 255;
    }
    n.putImageData(ni, 0, 0);
    return { map: texture(col, true), roughnessMap: texture(rough), normalMap: texture(norm) };
  };
  const maps = stoneMaps();
  const floorMat = material(0xc0c7b4, { ...maps, normalScale: new THREE.Vector2(.58, .58), roughness: .94 });
  const stone = material(0x485853, { map: maps.map, normalMap: maps.normalMap, normalScale: new THREE.Vector2(.35, .35) });
  const darkStone = material(0x263b3a, { map: maps.map, normalMap: maps.normalMap });
  const moss = material(0x344634, { roughness: 1 });
  const bronze = material(0x75806a, { roughness: .54, metalness: .55 });
  const wood = material(0x332e25, { roughness: .94 });
  const roofMat = material(0x173638, { roughness: .77, metalness: .06, side: THREE.DoubleSide });
  const gold = material(0xad9255, { roughness: .45, metalness: .68 });
  const addMesh = (geo, mat, pos = [0, 0, 0], scale = null, rotation = null, cast = true) => {
    const m = new THREE.Mesh(geo, mat); m.position.set(...pos); if (scale) m.scale.set(...scale); if (rotation) m.rotation.set(...rotation);
    m.castShadow = cast; m.receiveShadow = true; root.add(m); return m;
  };
  const unitBox = new THREE.BoxGeometry(1, 1, 1);
  const box = (sx, sy, sz, mat, x, y, z) => addMesh(unitBox, mat, [x, y, z], [sx, sy, sz]);
  const cylinder = (rt, rb, height, mat, x, y, z, sides = 16) => addMesh(new THREE.CylinderGeometry(rt, rb, height, sides), mat, [x, y, z]);
  const ring = (inner, outer, mat, y, segments = 128) => addMesh(new THREE.RingGeometry(inner, outer, segments), mat, [0, y, 0], null, [-Math.PI / 2, 0, 0], false);
  // The traversable court is flat at y=0. Outer earth is only 6cm lower.
  addMesh(new THREE.PlaneGeometry(260, 260), material(0x1f332b, { roughness: 1 }), [0, -.065, 0], null, [-Math.PI / 2, 0, 0], false);
  const court = cylinder(12, 12.3, .5, [darkStone, floorMat, darkStone], 0, -.25, 0, 128);
  court.name = 'WalkableCourt';
  ring(11.72, 11.9, bronze, .014); ring(10.85, 10.89, bronze, .012); ring(3.15, 3.18, bronze, .013);
  ring(3.32, 3.36, darkStone, .014); ring(.93, .97, bronze, .014);
  // An incised compass motif sits below the actors rather than becoming a glowing UI disc.
  const rune = canvas(512), rc = rune.getContext('2d'); rc.translate(256, 256);
  rc.strokeStyle = 'rgba(176,176,129,.50)'; rc.lineWidth = 3;
  for (let i = 0; i < 8; i++) { rc.save(); rc.rotate(i * TAU / 8); for (let k = 0; k < 3; k++) { rc.beginPath(); const y = -165 - k * 16; if ((i + k) % 3) { rc.moveTo(-22, y); rc.lineTo(22, y); } else { rc.moveTo(-22, y); rc.lineTo(-6, y); rc.moveTo(6, y); rc.lineTo(22, y); } rc.stroke(); } rc.restore(); }
  rc.lineWidth = 1.5; rc.beginPath(); rc.arc(0, 0, 217, 0, TAU); rc.stroke();
  const runeMat = new THREE.MeshStandardMaterial({ map: texture(rune, true), transparent: true, roughness: .8, opacity: .46, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -1 });
  addMesh(new THREE.PlaneGeometry(7.9, 7.9), runeMat, [0, .018, 0], null, [-Math.PI / 2, 0, 0], false);
  // Small chips around the rim and irregular grass/moss patches hide perfect geometry.
  const rockGeo = new THREE.IcosahedronGeometry(1, 1), rp = rockGeo.attributes.position;
  for (let i = 0; i < rp.count; i++) { const x = rp.getX(i), y = rp.getY(i), z = rp.getZ(i); const r = .86 + .16 * Math.sin(x * 18 + z * 11 + y * 7); rp.setXYZ(i, x * r, y * r, z * r); } rockGeo.computeVertexNormals();
  const rockInstances = [], patchInstances = [], stemInstances = [], canopyInstances = [];
  for (let i = 0; i < 108; i++) { const a = range(0, TAU), radius = i < 68 ? range(12.2, 21) : range(21, 36); const s = i < 68 ? range(.14, .62) : range(.8, 2.4); rockInstances.push({ p: [Math.cos(a) * radius, s * .3 - .04, Math.sin(a) * radius], s: [s * range(1, 1.7), s * range(.6, 1.1), s], r: [range(0, .4), a, range(0, .3)], c: new THREE.Color().setHSL(.40, .1, range(.16, .27)) }); }
  for (let i = 0; i < 34; i++) { const a = range(0, TAU), rad = range(9.8, 12.05); patchInstances.push({ p: [Math.cos(a) * rad, .016, Math.sin(a) * rad], s: [range(.3, .9), .014, range(.2, .7)], r: [0, a, 0], c: new THREE.Color().setHSL(.24, .25, range(.12, .19)) }); }
  const instances = (geo, mat, records, name, cast = true) => {
    const m = new THREE.InstancedMesh(geo, mat, records.length), obj = new THREE.Object3D(); m.name = name;
    records.forEach((v, i) => { obj.position.set(...v.p); obj.scale.set(...v.s); obj.rotation.set(...(v.r || [0, 0, 0])); if (v.q) obj.quaternion.copy(v.q); obj.updateMatrix(); m.setMatrixAt(i, obj.matrix); if (v.c) m.setColorAt(i, v.c); });
    m.castShadow = cast; m.receiveShadow = true; m.instanceMatrix.needsUpdate = true; root.add(m); return m;
  };
  instances(rockGeo, material(0xa0aaa0, { roughness: .95 }), rockInstances, 'RimAndSlopeRocks');
  instances(rockGeo, moss, patchInstances, 'MossInStoneJoints', false);
  const beamRecord = (a, b, radius, color) => { const va = v3(...a), vb = v3(...b), d = vb.clone().sub(va); return { p: va.add(vb).multiplyScalar(.5).toArray(), s: [radius, d.length(), radius], q: new THREE.Quaternion().setFromUnitVectors(axisY, d.normalize()), c: color }; };
  // Wind-shaped pines: bent trunks, ascending boughs, layered horizontal needle masses.
  for (let i = 0; i < 17; i++) {
    const side = i % 2 ? 1 : -1, x = side * range(14.3, 28), z = range(-24, 17), ht = range(4.5, 8), lean = range(-1.2, 1.2), bark = new THREE.Color(0x3b3b2d);
    const joints = [[x, 0, z], [x + lean * .25, ht * .36, z + .15], [x + lean * .65, ht * .68, z - .25], [x + lean, ht, z - .4]];
    for (let k = 0; k < 3; k++) stemInstances.push(beamRecord(joints[k], joints[k + 1], .19 - k * .045, bark));
    for (let k = 0; k < 8; k++) {
      const y = ht * (.35 + k * .074), a = k * 2.32 + i, len = (1 - k / 12) * range(1.4, 2.5), ox = x + lean * y / ht, oz = z - .4 * y / ht;
      const end = [ox + Math.cos(a) * len, y + range(.25, .65), oz + Math.sin(a) * len];
      stemInstances.push(beamRecord([ox, y, oz], end, .065, bark));
      for (let j = 0; j < 2; j++) canopyInstances.push({ p: [end[0] + range(-.45, .45), end[1] + .12 + j * .28, end[2] + range(-.45, .45)], s: [range(.85, 1.45), range(.3, .55), range(.8, 1.3)], r: [0, range(0, TAU), 0], c: new THREE.Color().setHSL(.37, .25, range(.13, .22)) });
    }
  }
  instances(new THREE.CylinderGeometry(.65, 1, 1, 7), material(0x9e9b7a, { roughness: 1 }), stemInstances, 'PineTrunksAndBoughs');
  instances(rockGeo, material(0x809e84, { roughness: 1 }), canopyInstances, 'LayeredPineNeedles');
  // Bamboo groves use one draw each for stems, nodes and pointed leaf clusters.
  const bambooStems = [], bambooNodes = [], bambooLeaves = [];
  const leafShape = new THREE.Shape(); leafShape.moveTo(0, 0); leafShape.quadraticCurveTo(.11, .35, .02, .77); leafShape.quadraticCurveTo(-.12, .36, 0, 0);
  const leafGeo = new THREE.ShapeGeometry(leafShape, 4);
  for (let grove = 0; grove < 2; grove++) for (let j = 0; j < 19; j++) {
    const x = (grove ? 1 : -1) * range(13.3, 17.8), z = (grove ? -7 : 4) + range(-3, 3), height = range(3.2, 6.1), tilt = range(-.06, .06), color = new THREE.Color().setHSL(.30, .23, range(.20, .29));
    bambooStems.push({ p: [x, height * .5, z], s: [.045, height, .045], r: [tilt, 0, tilt], c: color });
    for (let k = 1; k < height / .46; k++) {
      const yy = k * .46; bambooNodes.push({ p: [x - tilt * (yy - height / 2), yy, z + tilt * (yy - height / 2)], s: [.05, .025, .05], c: color.clone().multiplyScalar(1.35) });
      if (k > 4 && k % 2 === 0) for (let l = 0; l < 4; l++) bambooLeaves.push({ p: [x + range(-.15, .15), yy, z + range(-.15, .15)], s: [range(.8, 1.3), range(.8, 1.5), 1], r: [range(-.5, .5), range(0, TAU), range(-1.4, 1.4)], c: new THREE.Color().setHSL(.30, .34, range(.15, .26)) });
    }
  }
  instances(new THREE.CylinderGeometry(1, 1, 1, 7), material(0xadc29d, { roughness: .83 }), bambooStems, 'BambooCulms');
  instances(new THREE.CylinderGeometry(1, 1, 1, 7), material(0xbac8a7, { roughness: .9 }), bambooNodes, 'BambooNodes', false);
  instances(leafGeo, material(0x9db58c, { roughness: .95, side: THREE.DoubleSide }), bambooLeaves, 'BambooLeaves', false);
  // Curved roof geometry for a weathered paifang at the northern edge of the court.
  const roofGeometry = (halfWidth, halfDepth, baseY) => {
    const vertices = [], uv = [], indices = [], nx = 32, nz = 12;
    for (let j = 0; j <= nz; j++) for (let i = 0; i <= nx; i++) {
      const x = (i / nx * 2 - 1) * halfWidth, z = (j / nz * 2 - 1) * halfDepth;
      const y = baseY + .9 * Math.pow(1 - Math.abs(z / halfDepth), 1.65) + .6 * Math.pow(Math.abs(x / halfWidth), 4) + .12 * Math.pow(Math.abs(z / halfDepth), 7);
      vertices.push(x, y, z); uv.push(i / nx, j / nz);
      if (i < nx && j < nz) { const a = j * (nx + 1) + i; indices.push(a, a + nx + 1, a + 1, a + 1, a + nx + 1, a + nx + 2); }
    }
    const geo = new THREE.BufferGeometry(); geo.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3)); geo.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2)); geo.setIndex(indices); geo.computeVertexNormals(); return geo;
  };
  const gz = -13.7;
  for (const side of [-1, 1]) {
    const x = side * 3.65;
    box(1.18, .28, 1.15, darkStone, x, .14, gz);
    cylinder(.49, .58, .56, stone, x, .45, gz, 8);
    cylinder(.28, .38, 4.7, stone, x, 2.85, gz, 8);
    box(.83, .22, .78, darkStone, x, 5.17, gz);
    for (let k = 0; k < 3; k++) box(.82 + k * .25, .13, .60 + k * .2, wood, x, 5.37 + k * .15, gz);
    const brace = box(.18, 1.4, .2, wood, x - side * .53, 4.72, gz); brace.rotation.z = -side * .65;
    // A stone guardian-like base made from faceted architectural blocks, not another creature.
    cylinder(.29, .42, .3, darkStone, x + side * .8, .15, gz + .5, 6);
    addMesh(rockGeo, stone, [x + side * .8, .45, gz + .5], [.35, .36, .29]);
  }
  box(8.1, .38, .43, wood, 0, 4.48, gz);
  box(8.9, .32, .5, wood, 0, 5.5, gz);
  box(3.05, .92, .2, darkStone, 0, 4.92, gz + .2);
  box(3.2, .08, .25, bronze, 0, 5.42, gz + .2); box(3.2, .08, .25, bronze, 0, 4.43, gz + .2);
  const crest = new THREE.TorusGeometry(.29, .022, 7, 40);
  addMesh(crest, gold, [0, 4.92, gz + .33]);
  for (const side of [-1, 1]) { const bar = box(.92, .025, .03, gold, side * .91, 4.92, gz + .33); bar.rotation.z = side * .05; }
  addMesh(roofGeometry(5.3, 1.25, 5.67), roofMat, [0, 0, gz]);
  const roofLines = [], roofLineMaterial = material(0x34504b, { roughness: .82 });
  for (const zsign of [-1, 1]) {
    const points = [];
    for (let i = 0; i <= 28; i++) { const x = (i / 28 * 2 - 1) * 5.3; points.push(v3(x, 5.79 + .6 * Math.pow(Math.abs(x / 5.3), 4), gz + zsign * 1.25)); }
    addMesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(points), 48, .07, 6, false), darkStone);
  }
  for (let i = 0; i < 43; i++) {
    const x = (i / 42 * 2 - 1) * 5.3;
    for (const sign of [-1, 1]) { const pts = [];
      for (let k = 0; k < 8; k++) { const z = sign * k / 7 * 1.25; pts.push(v3(x, 5.69 + .9 * Math.pow(1 - Math.abs(z / 1.25), 1.65) + .6 * Math.pow(Math.abs(x / 5.3), 4) + .12 * Math.pow(Math.abs(z / 1.25), 7), gz + z)); }
      for (let k = 0; k < pts.length - 1; k++) roofLines.push(beamRecord(pts[k].toArray(), pts[k + 1].toArray(), .017, new THREE.Color(0x597269)));
    }
  }
  instances(new THREE.CylinderGeometry(1, 1, 1, 5), roofLineMaterial, roofLines, 'OldRoofTileRidges', false);
  const ridge = cylinder(.09, .09, 9.7, darkStone, 0, 6.6, gz, 8); ridge.rotation.z = Math.PI / 2;
  for (const side of [-1, 1]) {
    const p = [v3(side * 4.6, 6.63, gz), v3(side * 5.0, 6.85, gz), v3(side * 5.17, 7.13, gz)];
    addMesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(p), 12, .10, 6, false), darkStone);
  }
  // A pair of frayed silk streamers lends movement to the otherwise quiet ruin.
  const clothCanvas = canvas(256), cc = clothCanvas.getContext('2d');
  cc.fillStyle = '#563d31'; cc.fillRect(0, 0, 256, 256);
  for (let i = 0; i < 256; i += 3) { cc.strokeStyle = `rgba(150,120,73,${i % 2 ? .12 : .08})`; cc.beginPath(); cc.moveTo(i, 0); cc.lineTo(i, 256); cc.stroke(); }
  cc.strokeStyle = '#af9460'; cc.lineWidth = 4; cc.strokeRect(25, 12, 206, 232);
  cc.lineWidth = 8; cc.beginPath(); cc.moveTo(128, 38); cc.lineTo(88, 94); cc.lineTo(146, 117); cc.lineTo(103, 161); cc.lineTo(128, 217); cc.moveTo(81, 179); cc.lineTo(173, 179); cc.stroke();
  const clothMat = material(0xc9bfa6, { map: texture(clothCanvas, true), roughness: .95, side: THREE.DoubleSide });
  for (const side of [-1, 1]) {
    const geo = new THREE.PlaneGeometry(.64, 2.2, 5, 17), pos = geo.attributes.position;
    for (let i = 0; i < pos.count; i++) if (pos.getY(i) < -1) pos.setY(i, pos.getY(i) + .10 * Math.sin(i * 3.2));
    const mesh = addMesh(geo, clothMat, [side * 2.64, 3.3, gz + .32], null, null, false); const base = Float32Array.from(pos.array);
    animated.push((t) => { for (let i = 0; i < pos.count; i++) { const amount = (1.1 - base[i * 3 + 1]) / 2.2; pos.setZ(i, Math.sin(t * 1.8 + amount * 5 + side) * .11 * amount + Math.sin(t * 2.3 + i) * .012); } pos.needsUpdate = true; geo.computeVertexNormals(); });
    const rod = cylinder(.025, .025, .9, bronze, side * 2.64, 4.43, gz + .32, 6); rod.rotation.z = Math.PI / 2;
  }
  // Ornamental stairs and broken balustrades sit beyond the usable combat space.
  for (let i = 0; i < 5; i++) box(6.2 + i * .4, .14, .55, stone, 0, -.07 - i * .018, 12.1 + i * .54);
  for (const side of [-1, 1]) for (let i = 0; i < 5; i++) {
    const z = -8.8 + i * 3.4, x = side * 12.0;
    cylinder(.17, .25, 1.05, darkStone, x, .5, z, 8); cylinder(.26, .20, .16, stone, x, 1.06, z, 8);
    if (i < 4 && i !== 1) box(.15, .14, 3.1, stone, x, .77, z + 1.7);
  }
  // Warm stone lanterns: four emissive fixtures, two actual lights.
  const lampCore = material(0xe5b779, { emissive: 0xffb454, emissiveIntensity: 2.8, roughness: .5 });
  const lamps = [[-9.2, -6.4], [9.2, -6.4], [-10.5, 7.5], [10.5, 7.5]];
  for (let i = 0; i < lamps.length; i++) {
    const [x, z] = lamps[i];
    cylinder(.38, .48, .22, darkStone, x, .11, z, 8); cylinder(.18, .25, .62, stone, x, .51, z, 8);
    cylinder(.42, .36, .14, darkStone, x, .9, z, 8); cylinder(.30, .30, .60, lampCore, x, 1.26, z, 8);
    for (let k = 0; k < 4; k++) { const a = k * TAU / 4 + Math.PI / 4; box(.075, .69, .075, darkStone, x + Math.cos(a) * .28, 1.26, z + Math.sin(a) * .28); }
    cylinder(.48, .38, .15, darkStone, x, 1.64, z, 8); cylinder(.13, .5, .32, darkStone, x, 1.86, z, 8); cylinder(.035, .13, .18, bronze, x, 2.08, z, 8);
    if (i < 2) { const light = new THREE.PointLight(0xffb36a, 10, 11, 2); light.position.set(x, 1.5, z); light.castShadow = false; root.add(light); animated.push((t) => { light.intensity = 10 + Math.sin(t * 3.1 + i) * .4 + Math.sin(t * 7.6 + i * 3) * .2; }); }
  }
  // Distant steep karst stacks, built as actual meshes with uneven ledges.
  const mountainGeo = () => {
    const verts = [], ids = [], levels = 13, sides = 18;
    for (let j = 0; j <= levels; j++) for (let i = 0; i < sides; i++) {
      const f = j / levels, a = i / sides * TAU, taper = Math.pow(1 - f, .34) * (.86 + .15 * Math.sin(f * 19)) + .03;
      const ridge = 1 + .12 * Math.sin(a * 5 + f * 13) + .07 * Math.sin(a * 11 - f * 3);
      verts.push(Math.cos(a) * taper * ridge + f * .20, f * (1 + .045 * Math.sin(a * 3)), Math.sin(a) * taper * ridge);
      if (j < levels) { const b = j * sides + i, c = j * sides + (i + 1) % sides; ids.push(b, c, b + sides, c, c + sides, b + sides); }
    }
    const geo = new THREE.BufferGeometry(); geo.setAttribute('position', new THREE.Float32BufferAttribute(verts, 3)); geo.setIndex(ids); geo.computeVertexNormals(); return geo;
  };
  const mountainRecords = [];
  for (let i = 0; i < 38; i++) { const a = i * TAU / 38 + range(-.08, .08), radius = range(48, 95), h = range(12, 36), w = range(3.5, 8.5); mountainRecords.push({ p: [Math.cos(a) * radius, -.8, Math.sin(a) * radius], s: [w, h, w * range(.65, 1.15)], r: [0, range(0, TAU), 0], c: new THREE.Color().setHSL(.48, .16, range(.15, .25)) }); }
  instances(mountainGeo(), material(0x728c83, { roughness: 1 }), mountainRecords, 'MistKarstRange', false);
  // Drifting motes mark depth without large transparent fog planes or expensive post effects.
  const count = 90, positions = new Float32Array(count * 3), colors = new Float32Array(count * 3), bases = [];
  for (let i = 0; i < count; i++) { const p = [range(-16, 16), range(.15, 5.5), range(-17, 17)]; bases.push(p); positions.set(p, i * 3); colors.set(i % 4 ? [.34, .59, .49] : [.85, .62, .29], i * 3); }
  const particles = new THREE.BufferGeometry(); particles.setAttribute('position', new THREE.BufferAttribute(positions, 3)); particles.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  const moteCanvas = canvas(32), mc = moteCanvas.getContext('2d'), mg = mc.createRadialGradient(16, 16, 0, 16, 16, 16); mg.addColorStop(0, 'rgba(255,255,255,1)'); mg.addColorStop(.23, 'rgba(255,255,255,.6)'); mg.addColorStop(1, 'rgba(255,255,255,0)'); mc.fillStyle = mg; mc.fillRect(0, 0, 32, 32);
  const motes = new THREE.Points(particles, new THREE.PointsMaterial({ map: texture(moteCanvas, true), size: .055, transparent: true, opacity: .45, vertexColors: true, depthWrite: false, blending: THREE.AdditiveBlending })); root.add(motes);
  animated.push((t) => { for (let i = 0; i < count; i++) { positions[i * 3] = bases[i][0] + Math.sin(t * .11 + i) * .45; positions[i * 3 + 1] = bases[i][1] + Math.sin(t * .21 + i * 2) * .3; } particles.attributes.position.needsUpdate = true; });
  // Batch repeated masonry/woodwork after their final transforms have been authored.
  const architecture = new Map();
  for (const mesh of root.children) if (mesh.isMesh && !mesh.isInstancedMesh && mesh.geometry === unitBox) {
    let group = architecture.get(mesh.material); if (!group) architecture.set(mesh.material, group = []); group.push(mesh);
  }
  for (const [mat, meshes] of architecture) if (meshes.length > 1) {
    const records = meshes.map((m) => ({ p: m.position.toArray(), s: m.scale.toArray(), q: m.quaternion.clone() }));
    instances(unitBox, mat, records, 'BatchedArchitecture'); for (const m of meshes) root.remove(m);
  }
  return {
    root,
    bounds: 16,
    spawn: [0, 0, 3],
    bossSpawn: [0, 0, -5],
    update(dt, time) { for (const fn of animated) fn(time); },
    dispose() {
      root.traverse((o) => { if (o.geometry) o.geometry.dispose(); if (o.material) for (const m of (Array.isArray(o.material) ? o.material : [o.material])) m.dispose(); });
      for (const t of Object.values(maps)) t.dispose(); root.removeFromParent();
    }
  };
}
