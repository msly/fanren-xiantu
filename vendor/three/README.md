# Three.js runtime

Pinned to Three.js **0.180.0 (r180)**, MIT license; see `LICENSE`.

Files are the official npm distribution, retrieved from `https://unpkg.com/three@0.180.0/`:

- `build/three.module.min.js` is stored as `build/three.module.js`.
- `build/three.core.min.js` retains its original name.
- `examples/jsm/loaders/GLTFLoader.js`, `controls/OrbitControls.js`, `utils/BufferGeometryUtils.js`, and `environments/RoomEnvironment.js` are stored under `addons/` with the same internal layout.

`package.json` is a minimal local module/export manifest for optional Node-based checks. Browser loading uses the import map in `game3d.html`. Runtime scripts are served from this repository; no CDN request is needed by the game.
