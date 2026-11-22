"""Render the actual game GLB using the editable source file's studio.

Run with Blender 4.3+:
  blender -b --factory-startup --python tools/render_glb_review.py -- \
    --studio art/hanli.blend --asset assets/3d/hanli.glb \
    --output-dir ../qa3d/glb-review --name hanli --views full head

This is offline asset review, not a Three.js/WebGL screenshot or FPS test.
It does not save or change the .blend source or the GLB.
"""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--studio', type=Path, required=True)
    parser.add_argument('--asset', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--name', choices=('hanli', 'mojiao'), required=True)
    parser.add_argument('--views', nargs='+', choices=('full', 'portrait', 'head', 'back', 'reference', 'face-front', 'face-profile'), default=['full', 'head'])
    parser.add_argument('--samples', type=int, default=48)
    parser.add_argument('--resolution-scale', type=float, default=1.0,
                        help='Scale output dimensions for quick shape reviews')
    parser.add_argument('--clip', choices=('Idle', 'Walk', 'Attack'),
                        help='Pose the imported Han Li rig using this exported clip')
    parser.add_argument('--frame', type=float, default=1)
    return parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])


args = parse_args()
if not 0 < args.resolution_scale <= 2:
    raise ValueError('resolution-scale must be greater than zero and at most two')
source_path = args.studio.resolve()
asset_path = args.asset.resolve()
output_dir = args.output_dir.resolve()
output_dir.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(source_path))
scene = bpy.context.scene
camera = scene.camera
if camera is None:
    raise RuntimeError('Source studio has no camera')

studio = {
    'camera': {
        'location': list(camera.location),
        'rotation_euler': list(camera.rotation_euler),
        'type': camera.data.type,
        'ortho_scale': camera.data.ortho_scale,
    },
    'color': {
        'view_transform': scene.view_settings.view_transform,
        'look': scene.view_settings.look,
        'exposure': scene.view_settings.exposure,
        'gamma': scene.view_settings.gamma,
    },
    'lights': [
        {'name': ob.name, 'type': ob.data.type, 'location': list(ob.location),
         'rotation_euler': list(ob.rotation_euler), 'color': list(ob.data.color),
         'energy': ob.data.energy, 'size': getattr(ob.data, 'size', None)}
        for ob in scene.objects if ob.type == 'LIGHT'
    ],
}

# Keep only the source studio; all rendered character geometry comes from GLB.
keep_ground = {'Studio ground', 'Studio floor'}
for ob in list(bpy.data.objects):
    if ob.type not in ('CAMERA', 'LIGHT') and ob.name not in keep_ground:
        bpy.data.objects.remove(ob, do_unlink=True)

before_import = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=str(asset_path))
imported = [ob for ob in bpy.data.objects if ob not in before_import]
if args.clip:
    rigs = [ob for ob in imported if ob.type == 'ARMATURE']
    if len(rigs) != 1:
        raise RuntimeError('Explicit clip review requires one imported character rig')
    rig = rigs[0]
    tracks = [track for track in rig.animation_data.nla_tracks if track.name == args.clip]
    if len(tracks) != 1 or len(tracks[0].strips) != 1:
        raise RuntimeError('Imported clip not found: ' + args.clip)
    rig.animation_data.action = tracks[0].strips[0].action
    for track in rig.animation_data.nla_tracks:
        track.mute = True
scene.frame_set(int(args.frame), subframe=args.frame % 1)
bpy.context.view_layer.update()
mesh_objects = [ob for ob in imported if ob.type == 'MESH']
if not mesh_objects:
    raise RuntimeError('GLB imported no mesh objects')
for ob in mesh_objects:
    if not all(math.isfinite(v) for row in ob.matrix_world for v in row):
        raise RuntimeError('Non-finite imported transform: ' + ob.name)

scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.cycles.samples = args.samples
scene.cycles.use_denoising = False
scene.render.image_settings.file_format = 'PNG'
scene.render.resolution_percentage = 100
scene.render.film_transparent = False
original = (camera.location.copy(), camera.rotation_euler.copy(), camera.data.ortho_scale,
            scene.render.resolution_x, scene.render.resolution_y)
renders = []
for view in args.views:
    camera.location = original[0]
    camera.rotation_euler = original[1]
    camera.data.ortho_scale = original[2]
    scene.render.resolution_x, scene.render.resolution_y = original[3:]
    if view == 'head':
        if args.name == 'hanli':
            camera.location = (-1.3, -3.0, 1.72)
            target = Vector((0, -.015, 1.565))
            camera.data.ortho_scale = .53
        else:
            camera.location = (3.2, -5.5, 2.45)
            target = Vector((0, -1.4, 1.3))
            camera.data.ortho_scale = 2.7
        camera.rotation_euler = (target - camera.location).to_track_quat('-Z', 'Y').to_euler()
        scene.render.resolution_x = 900
        scene.render.resolution_y = 900
    elif view == 'portrait':
        if args.name == 'hanli':
            camera.location = (-.95, -4.0, 1.48)
            target = Vector((0, -.025, 1.16))
            camera.data.ortho_scale = 1.20
        else:
            camera.location = (3.2, -5.5, 2.45)
            target = Vector((0, -1.0, 1.24))
            camera.data.ortho_scale = 3.5
        camera.rotation_euler = (target - camera.location).to_track_quat('-Z', 'Y').to_euler()
        scene.render.resolution_x = 900
        scene.render.resolution_y = 1200
    elif view in ('reference', 'face-front', 'face-profile'):
        if args.name != 'hanli':
            raise ValueError('Reference and facial review views are defined for Han Li')
        if view == 'reference':
            # Match the reference's visible side, including its long forelock.
            camera.location = (-1.45, -4.0, 1.53)
            target = Vector((0, -.015, 1.235))
            camera.data.ortho_scale = 1.04
            scene.render.resolution_x, scene.render.resolution_y = 900, 1200
        else:
            camera.location = (0, -4.0, 1.60) if view == 'face-front' else (4.0, -.035, 1.60)
            target = Vector((0, -.015, 1.565))
            camera.data.ortho_scale = .38
            scene.render.resolution_x = scene.render.resolution_y = 900
        camera.rotation_euler = (target - camera.location).to_track_quat('-Z', 'Y').to_euler()
    elif view == 'back':
        camera.location.x *= -1
        camera.location.y *= -1
        target = Vector((0, 0, .92 if args.name == 'hanli' else 1.1))
        camera.rotation_euler = (target - camera.location).to_track_quat('-Z', 'Y').to_euler()
    scene.render.resolution_x = max(64, round(scene.render.resolution_x * args.resolution_scale))
    scene.render.resolution_y = max(64, round(scene.render.resolution_y * args.resolution_scale))
    path = output_dir / (args.name + '-glb-' + view + '.png')
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    renders.append({'view': view, 'file': str(path), 'camera_location': list(camera.location),
                    'camera_rotation': list(camera.rotation_euler),
                    'ortho_scale': camera.data.ortho_scale,
                    'resolution': [scene.render.resolution_x, scene.render.resolution_y]})

manifest = {
    'asset': str(asset_path), 'asset_sha256': hashlib.sha256(asset_path.read_bytes()).hexdigest(),
    'studio_source': str(source_path), 'blender': bpy.app.version_string,
    'method': 'Import runtime GLB and render using source studio, CPU Cycles',
    'webgl_tested': False, 'mesh_objects': len(mesh_objects), 'samples': args.samples,
    'denoised': False, 'resolution_scale': args.resolution_scale,
    'clip': args.clip, 'frame': args.frame,
    'studio': studio, 'renders': renders,
}
(output_dir / (args.name + '-glb-review.json')).write_text(json.dumps(manifest, indent=2) + '\n')
print('GLB_REVIEW', json.dumps({'asset': args.name, 'hash': manifest['asset_sha256'],
                              'renders': [r['file'] for r in renders]}))
