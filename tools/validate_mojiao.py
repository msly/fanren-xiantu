"""Check the saved Mojiao source and exported motion without modifying either.

Run: blender -b --python tools/validate_mojiao.py
Optional after --: --report path/to/report.json
"""
from pathlib import Path
import argparse
import hashlib
import json
import math
import struct
import sys

import bpy
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
args = argparse.ArgumentParser()
args.add_argument('--report', default=str(ROOT / 'docs/mojiao-verification.json'))
options = args.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
source = ROOT / 'art/mojiao.blend'
runtime = ROOT / 'assets/3d/mojiao.glb'
bpy.ops.wm.open_mainfile(filepath=str(source))
root = bpy.data.objects['Mojiao']
objects = [root] + list(root.children_recursive)
meshes = [ob for ob in objects if ob.type == 'MESH']
animated = [ob for ob in objects if ob.animation_data]
feet = {ob.name: {child.name for child in ob.children_recursive if child.type == 'MESH'}
        for ob in objects if ob.name.endswith('_foot')}
assert len(feet) == 4, 'Missing independently counter-rotated foot nodes'
vertices = {}
for ob in meshes:
    co = np.empty(len(ob.data.vertices) * 3, dtype=np.float64)
    ob.data.vertices.foreach_get('co', co)
    vertices[ob.name] = co.reshape((-1, 3))
    assert np.isfinite(co).all(), ob.name + ' contains non-finite vertices'

clips = []
for name, end in [('Idle', 120), ('Walk', 36), ('Attack', 42)]:
    for ob in animated:
        for track in ob.animation_data.nla_tracks:
            track.mute = track.name != name
    bounds = np.array([[np.inf] * 3, [-np.inf] * 3])
    contact = {name: [np.inf, -np.inf] for name in feet}
    first = None
    samples = np.arange(1, end + .1, .5)
    for frame in samples:
        bpy.context.scene.frame_set(math.floor(frame), subframe=frame % 1)
        bpy.context.view_layer.update()
        if first is None:
            first = {ob.name: np.array(ob.matrix_world) for ob in animated}
        foot_min = {name: np.inf for name in feet}
        for ob in meshes:
            matrix = np.array(ob.matrix_world)
            assert np.isfinite(matrix).all(), (name, frame, ob.name)
            points = vertices[ob.name] @ matrix[:3, :3].T + matrix[:3, 3]
            assert np.isfinite(points).all(), (name, frame, ob.name)
            bounds[0] = np.minimum(bounds[0], points.min(0))
            bounds[1] = np.maximum(bounds[1], points.max(0))
            for foot, children in feet.items():
                if ob.name in children:
                    foot_min[foot] = min(foot_min[foot], float(points[:, 2].min()))
        for foot, value in foot_min.items():
            contact[foot][0] = min(contact[foot][0], value)
            contact[foot][1] = max(contact[foot][1], value)
    endpoint_error = max(float(np.abs(np.array(ob.matrix_world) - first[ob.name]).max())
                         for ob in animated)
    assert bounds[0, 2] >= -.005, (name, 'ground penetration', bounds[0, 2])
    assert endpoint_error < 1e-6, (name, 'animation loop seam', endpoint_error)
    for foot, (low, high) in contact.items():
        assert low >= -.005, (name, foot, 'ground penetration', low)
        assert high < (.10 if name == 'Walk' else .02), (name, foot, 'unintended hovering', high)
    clips.append({'clip': name, 'samples': len(samples), 'bounds_blender_xyz': bounds.tolist(),
                  'min_ground_z_m': float(bounds[0, 2]), 'loop_matrix_max_error': endpoint_error,
                  'foot_tip_z_range_m': contact})

# Read the runtime asset too: a source-only check misses stale or incorrectly
# exported animation endpoints. GLB accessors retain the actual baked keyframes.
raw = runtime.read_bytes()
assert raw[:4] == b'glTF' and struct.unpack_from('<I', raw, 4)[0] == 2
cursor = 12
document = None
binary = None
while cursor < len(raw):
    length, kind = struct.unpack_from('<II', raw, cursor)
    payload = raw[cursor + 8:cursor + 8 + length]
    if kind == 0x4E4F534A:
        document = json.loads(payload)
    elif kind == 0x004E4942:
        binary = payload
    cursor += 8 + length
assert document and binary

def accessor(index):
    data = document['accessors'][index]
    view = document['bufferViews'][data['bufferView']]
    assert data['componentType'] == 5126 and 'sparse' not in data
    width = {'SCALAR': 1, 'VEC3': 3, 'VEC4': 4}[data['type']]
    offset = view.get('byteOffset', 0) + data.get('byteOffset', 0)
    stride = view.get('byteStride', width * 4)
    result = np.ndarray((data['count'], width), dtype='<f4', buffer=binary,
                        offset=offset, strides=(stride, 4))
    assert np.isfinite(result).all()
    return result

export_checks = []
assert sorted(a['name'] for a in document['animations']) == ['Attack', 'Idle', 'Walk']
for animation in document['animations']:
    errors = []
    for channel in animation['channels']:
        sampler = animation['samplers'][channel['sampler']]
        times = accessor(sampler['input']).ravel()
        values = accessor(sampler['output'])
        assert sampler.get('interpolation', 'LINEAR') == 'LINEAR'
        assert len(times) == len(values) and np.all(np.diff(times) > 0)
        error = float(np.max(np.abs(values[0] - values[-1])))
        if channel['target']['path'] == 'rotation':
            error = min(error, float(np.max(np.abs(values[0] + values[-1]))))
        assert error < 1e-6, (animation['name'], channel['target'], error)
        errors.append(error)
    export_checks.append({'clip': animation['name'], 'channels': len(errors),
                          'endpoint_max_error': max(errors)})

packed = [im.name for im in bpy.data.images if im.name.startswith('mojiao-v2-hide') and im.packed_file]
assert len(packed) == 3
manifest = json.loads((ROOT / 'assets/3d/mojiao-info.json').read_text())
assert manifest['glb_bytes'] == len(raw)
for key, path in [('glb_sha256', runtime), ('blend_sha256', source),
                  ('generator_sha256', ROOT / 'tools/build_mojiao.py')]:
    assert manifest[key] == hashlib.sha256(path.read_bytes()).hexdigest(), key + ' is stale'
report = {'result': 'PASS', 'blender': bpy.app.version_string,
          'scope': 'Reopened source, half-frame grounded animation samples and actual GLB loop endpoints; no WebGL rendering',
          'source': 'art/mojiao.blend', 'runtime': 'assets/3d/mojiao.glb',
          'glb_sha256': manifest['glb_sha256'], 'blend_sha256': manifest['blend_sha256'],
          'generator_sha256': manifest['generator_sha256'], 'glb_bytes': len(raw),
          'mesh_objects': len(meshes), 'triangles': manifest['triangles'],
          'packed_textures': packed, 'animation_sampling': clips,
          'runtime_animation_endpoints': export_checks}
destination = Path(options.report)
destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print('MOJIAO_VERIFY', json.dumps({'result': 'PASS', 'samples': sum(c['samples'] for c in clips),
                                 'runtime_endpoints': export_checks, 'report': str(destination)}))
