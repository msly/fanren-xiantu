"""Build an original, editable Han Li prototype in Blender 4.3+.

Run: blender -b --factory-startup --python tools/build_hanli.py
Units are metres. Blender forward is -Y; glTF forward is +Z.
The mesh, materials, armature and three authored actions are self-contained.
"""
import bpy
import bmesh
import numpy as np
import math
import os
import random
import json
import hashlib
import sys
from pathlib import Path
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
ASSET = ROOT / 'assets' / '3d'
ART = ROOT / 'art'
QA = Path(os.environ.get('FANREN_QA_DIR', str(ROOT.parent / 'qa3d' / 'character-v5')))
for directory in (ASSET, ART, QA):
    directory.mkdir(parents=True, exist_ok=True)
random.seed(19)
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
for dat in list(bpy.data.materials):
    bpy.data.materials.remove(dat)


def rgba(h):
    rgb = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return tuple(v / 12.92 if v < .04045 else ((v + .055) / 1.055) ** 2.4 for v in rgb) + (1,)


def material(name, color, roughness=.6, metal=0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = m.node_tree.nodes.get('Principled BSDF')
    p.inputs['Base Color'].default_value = rgba(color)
    p.inputs['Roughness'].default_value = roughness
    p.inputs['Metallic'].default_value = metal
    m.diffuse_color = rgba(color)
    return m


M = {
    'robe': material('Jade silk | woven outer robe', '#28574b', .78),
    'robe_dark': material('Ink green | layered lining', '#132f2b', .82),
    'robe_light': material('Sage silk | lapels and cuffs', '#375249', .8),
    'linen': material('Undyed silk | inner collar', '#aaa88e', .88),
    'pants': material('Charcoal linen | trousers', '#263b3a', .92),
    'leather': material('Worn black leather', '#182523', .68),
    'sole': material('Boot soles', '#121b1b', .93),
    'gold': material('Antique bronze | engraved fittings', '#a68a50', .32, .78),
    'gold_dark': material('Patinated bronze', '#5c643e', .47, .58),
    'steel': material('Tempered steel | sword flats', '#9cbbbc', .23, .92),
    'edge': material('Polished cutting edge', '#d5e1dc', .15, 1),
    'skin': material('Warm skin', '#b78c70', .62),
    'skin_shadow': material('Warm recessed skin', '#825a48', .7),
    'lips': material('Natural lip colour', '#8f6557', .62),
    'hair': material('Black hair', '#101718', .58),
    'hair_light': material('Hair strands', '#182123', .61),
    'eye': material('Eye sclera', '#96978c', .31),
    'iris': material('Brown iris', '#3f3426', .31),
    'iris_rim': material('Dark limbal ring', '#282820', .28),
    'pupil': material('Pupil', '#090d0c', .16),
    'jade': material('Palm-heaven bottle | green jade', '#5d9271', .22, .08),
    'jade_dark': material('Jade engraving', '#214735', .44),
}
M['skin'].node_tree.nodes.get('Principled BSDF').inputs['Subsurface Weight'].default_value = .045
M['jade'].node_tree.nodes.get('Principled BSDF').inputs['Coat Weight'].default_value = .35
for key in ('hair','hair_light'):
    M[key].node_tree.nodes['Principled BSDF'].inputs['Specular IOR Level'].default_value=.28


# Clothing and hair modules own their packed PBR maps.
PARTS = []


def tag(obj, mat, bone='chest', skin_mode='rigid'):
    obj.data.materials.append(M[mat])
    obj['bind_bone'] = bone
    obj['skin_mode'] = skin_mode
    PARTS.append(obj)
    if obj.type == 'MESH':
        for p in obj.data.polygons:
            p.use_smooth = True
    return obj


def mesh(name, verts, faces, mat, bone='chest', skin_mode='rigid', uv=None):
    data = bpy.data.meshes.new(name)
    data.from_pydata(verts, [], faces)
    data.update()
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    tag(obj, mat, bone, skin_mode)
    if uv:
        layer = data.uv_layers.new(name='UVMap')
        for poly in data.polygons:
            for loop in poly.loop_indices:
                layer.data[loop].uv = uv[data.loops[loop].vertex_index]
    return obj


def sphere(name, loc, scale, mat, bone='head', segments=32, rings=16):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=rings, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    return tag(obj, mat, bone)


def tube(name, points, radius, mat, bone='chest', radii=None):
    data = bpy.data.curves.new(name, 'CURVE')
    data.dimensions = '3D'
    data.resolution_u = 3
    data.bevel_depth = radius
    data.bevel_resolution = 1
    sp = data.splines.new('BEZIER')
    sp.bezier_points.add(len(points) - 1)
    for i, (bp, point) in enumerate(zip(sp.bezier_points, points)):
        bp.co = point
        bp.handle_left_type = 'AUTO'
        bp.handle_right_type = 'AUTO'
        if radii:
            bp.radius = radii[i]
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    return tag(obj, mat, bone)


def ring_mesh(name, rows, mat, bone='chest', n=48, skin_mode='rigid', warp=None):
    verts, uv, faces = [], [], []
    for j, (z, rx, ry, cx, cy) in enumerate(rows):
        for i in range(n + 1):
            a = i / n * math.tau
            x, y = cx + math.sin(a) * rx, cy - math.cos(a) * ry
            if warp:
                x, y, z1 = warp(x, y, z, a, j)
            else:
                z1 = z
            verts.append((x, y, z1))
            uv.append((i / n, j / (len(rows) - 1)))
            if i < n and j < len(rows) - 1:
                k = j * (n + 1) + i
                faces.append((k, k + 1, k + n + 2, k + n + 1))
    faces.extend([tuple(range(n, -1, -1)), tuple((len(rows) - 1) * (n + 1) + i for i in range(n + 1))])
    obj=mesh(name, verts, faces, mat, bone, skin_mode, uv)
    # End caps use a planar chart; a single lathe V coordinate has no tangent basis.
    layer=obj.data.uv_layers.active
    for poly,row in zip(list(obj.data.polygons)[-2:],(rows[0],rows[-1])):
        _,rx,ry,cx,cy=row
        for loop_index in poly.loop_indices:
            co=obj.data.vertices[obj.data.loops[loop_index].vertex_index].co
            layer.data[loop_index].uv=(.5+(co.x-cx)/(2*rx),.5+(co.y-cy)/(2*ry))
    bm=bmesh.new();bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=1e-6)
    bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(obj.data);bm.free()
    return obj


def strip(name, left, right, mat, bone='chest'):
    verts = []
    uv = []
    for i, (a, b) in enumerate(zip(left, right)):
        verts.extend((a, b))
        uv.extend(((0, i / (len(left) - 1)), (1, i / (len(left) - 1))))
    faces = [(i * 2, i * 2 + 1, i * 2 + 3, i * 2 + 2) for i in range(len(left) - 1)]
    obj = mesh(name, verts, faces, mat, bone, uv=uv)
    mod = obj.modifiers.new('Tailored thickness', 'SOLIDIFY')
    mod.thickness = .003
    mod = obj.modifiers.new('Soft woven edges', 'BEVEL')
    mod.width = .001
    mod.segments = 2
    return obj


def limb(name, a, b, profile, mat, bone, n=24):
    a, b = Vector(a), Vector(b)
    axis = (b - a).normalized()
    u = axis.cross(Vector((0, 1, 0))).normalized()
    v = axis.cross(u).normalized()
    verts, uv, faces = [], [], []
    for j, (f, ru, rv) in enumerate(profile):
        center = a.lerp(b, f)
        for i in range(n + 1):
            angle = i * math.tau / n
            point = center + u * (math.cos(angle) * ru) + v * (math.sin(angle) * rv)
            verts.append(tuple(point))
            uv.append((i / n, f))
            if i < n and j < len(profile) - 1:
                k = j * (n + 1) + i
                faces.append((k, k + 1, k + n + 2, k + n + 1))
    faces.extend([tuple(range(n, -1, -1)), tuple((len(profile) - 1) * (n + 1) + i for i in range(n + 1))])
    return mesh(name, verts, faces, mat, bone, uv=uv)


# Trousers and fitted, slightly creased boots.
for side, suffix in [(-1, 'R'), (1, 'L')]:
    thigh = (side * .083, .018, .85)
    knee = (side * .086, -.004, .46)
    ankle = (side * .089, -.001, .095)
    limb('Trouser thigh.' + suffix, thigh, knee, [(0, .065, .068), (.2, .068, .066), (.65, .056, .054), (1, .045, .048)], 'pants', 'thigh.' + suffix)
    limb('Trouser shin.' + suffix, knee, ankle, [(0, .045, .045), (.2, .048, .044), (.75, .033, .034), (1, .03, .03)], 'pants', 'shin.' + suffix)
    boot_v,boot_f=[],[]
    profile=[(-.145,.023,.018),(-.135,.038,.022),(-.105,.043,.035),(-.065,.044,.053),(-.02,.038,.076),(.025,.034,.068),(.048,.028,.027)]
    for j,(yy,ww,hh) in enumerate(profile):
        for i in range(17):
            aa=i/16*math.pi
            boot_v.append((side*.089+math.cos(aa)*ww,yy,.028+math.sin(aa)*hh))
            if i<16 and j<len(profile)-1:
                k=j*17+i;boot_f.append((k,k+17,k+18,k+1))
    boot_f += [tuple(range(17)),tuple((len(profile)-1)*17+i for i in range(16,-1,-1))]
    for j in range(len(profile)-1):
        k=j*17;boot_f.append((k,k+16,k+33,k+17))
    boot=mesh('Soft leather boot vamp.'+suffix,boot_v,boot_f,'leather','foot.'+suffix)
    bm=bmesh.new();bm.from_mesh(boot.data);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(boot.data);bm.free()
    mod=boot.modifiers.new('Soft boot surface','SUBSURF');mod.levels=1
    ring_mesh('High boot.'+suffix,[(.085,.031,.038,side*.089,.001),(.115,.033,.037,side*.089,.002),(.22,.038,.040,side*.089,.002),(.29,.040,.041,side*.089,.003)],'leather','foot.'+suffix,n=32)
    ring_mesh('Stitched sole.'+suffix,[(.008,.046,.097,side*.089,-.042),(.019,.046,.097,side*.089,-.042),(.028,.044,.094,side*.089,-.042)],'sole','foot.'+suffix,n=40)
    for z in [.145, .17, .27, .292]:
        pts = [(side * .089 + math.sin(a) * .042, -math.cos(a) * .043, z + .002 * math.cos(a * 2)) for a in [i * math.tau / 16 for i in range(17)]]
        tube('Boot stitching.' + suffix, pts, .0011, 'gold_dark', 'foot.' + suffix)
    for z in [.105, .115, .126]:
        tube('Soft ankle crease.' + suffix, [(side * .089 - .032, -.031, z), (side * .089, -.041, z + .004), (side * .089 + .032, -.031, z)], .0012, 'robe_dark', 'foot.' + suffix)


# Separate reusable asset components keep the reference-driven modeling editable.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from hanli_costume import build_costume
from hanli_face import build_face
from hanli_hair import build_hair

build_costume(globals())

anatomy = build_face(globals())
build_hair(globals(), anatomy)

# Sword: diamond cross-section blade, separate polished edges and bronze guard.
grip = Vector((-.307, -.055, .916))
axis = Vector((-.17, -.10, -.95)).normalized()
across = Vector((1, 0, -.17)).normalized()
normal = axis.cross(across).normalized()


def sword_point(z, x=0, y=0):
    return tuple(grip + axis * z + across * x + normal * y)


verts, faces = [], []
sections = [(.055, .023), (.12, .022), (.62, .017), (.735, .010), (.795, .0004)]
for dist, width in sections:
    for a, b in [(-width, 0), (0, .004), (width, 0), (0, -.004)]:
        verts.append(sword_point(dist, a, b))
for j in range(len(sections) - 1):
    for k in range(4):
        faces.append((j * 4 + k, j * 4 + (k + 1) % 4, (j + 1) * 4 + (k + 1) % 4, (j + 1) * 4 + k))
blade = mesh('Qingzhu sword | forged diamond blade', verts, faces, 'steel', 'hand.R')
for side in [-1, 1]:
    tube('Sword polished edge', [sword_point(d, side * w) for d, w in sections], .0008, 'edge', 'hand.R', radii=[1, 1, 1, .7, .05])
    tube('Sword engraved flute', [sword_point(.12, side * .008, .0032), sword_point(.32, side * .007, .0032), sword_point(.58, side * .005, .0032)], .0005, 'gold_dark', 'hand.R')
tube('Wrapped sword grip', [sword_point(-.06), sword_point(.05)], .012, 'leather', 'hand.R')
for i in range(9):
    d = -.055 + i * .012
    p = [sword_point(d + j / 15 * .008, math.cos(j / 15 * math.tau) * .0122, math.sin(j / 15 * math.tau) * .0122) for j in range(16)]
    tube('Sword grip weave', p, .0012, 'gold_dark', 'hand.R')
tube('Swept bronze sword guard', [sword_point(.052, -.062, .003), sword_point(.037, -.031, .004), sword_point(.047, 0, .004), sword_point(.037, .031, .004), sword_point(.052, .062, .003)], .007, 'gold', 'hand.R', radii=[.55, 1, 1.3, 1, .55])
sphere('Sword pommel', sword_point(-.068), (.016, .014, .014), 'gold', 'hand.R', segments=24)
sphere('Sword guard jade', sword_point(.049, 0, -.009), (.009, .005, .009), 'jade', 'hand.R', segments=20)
for i in range(6):
    start = Vector(sword_point(-.073))
    tube('Sword tassel', [tuple(start), tuple(start + Vector((.018 + i * .001, .015, -.07))), tuple(start + Vector((.013 + i * .002, .03, -.13)))], .00125, 'robe_light', 'hand.R', radii=[1, 1, .1])

# Convert all detail to editable mesh; keep weights and materials when joining.
for obj in PARTS:
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    if obj.type != 'MESH':
        bpy.ops.object.convert(target='MESH')
    for mod in list(obj.modifiers):
        bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    # Solidify creates rim polygons with collapsed UVs. Give those small faces
    # their own tangent charts after all modifiers, preserving every valid chart.
    layer=obj.data.uv_layers.active
    if layer and any(m.use_nodes and m.node_tree.nodes.get('Principled BSDF') and
                     m.node_tree.nodes['Principled BSDF'].inputs['Normal'].is_linked
                     for m in obj.data.materials):
        for poly in obj.data.polygons:
            loops=list(poly.loop_indices)
            coords=[layer.data[i].uv.copy() for i in loops]
            area=sum(abs((coords[k].x-coords[0].x)*(coords[k+1].y-coords[0].y)-
                         (coords[k].y-coords[0].y)*(coords[k+1].x-coords[0].x))
                     for k in range(1,len(coords)-1))
            if area < 1e-12 and poly.area > 1e-12:
                u=poly.normal.orthogonal().normalized();v=poly.normal.cross(u).normalized()
                for index in loops:
                    co=obj.data.vertices[obj.data.loops[index].vertex_index].co
                    layer.data[index].uv=(co.dot(u)/.2,co.dot(v)/.2)
    for poly in obj.data.polygons:
        poly.use_smooth = True
    mode = obj.get('skin_mode', 'rigid')
    bone = obj.get('bind_bone', 'chest')
    if bone == 'head':
        for vertex in obj.data.vertices: vertex.co.z -= .036
    if bone.startswith(('upper_arm.','forearm.','hand.')):
        side=-1 if bone.endswith('.R') else 1
        for vertex in obj.data.vertices:
            z=vertex.co.z
            if bone.startswith('hand.'):offset=.065
            else:offset=.055*max(0,min(1,(1.305-z)/.191))+.010*max(0,min(1,(1.114-z)/.168))
            vertex.co.x-=side*offset
    def weight_vertex(v):
        z = v.co.z
        if mode in ('hair_back','hair_front'):
            f=max(0,min(1,(z-1.26)/.26));f=f*f*(3-2*f)
            return {'head':f,'chest':1-f}
        if mode.startswith('shoulder.'):
            suffix=mode.split('.')[1];f=max(0,min(1,(abs(v.co.x)-.12)/.075))
            return {'chest':1-f,'upper_arm.'+suffix:f}
        if mode.startswith('arm.'):
            suffix=mode.split('.')[1];f=max(0,min(1,(1.20-z)/.14))
            shoulder=max(0,min(1,(abs(v.co.x)-.095)/.083))
            shoulder=shoulder*shoulder*(3-2*shoulder)
            return {'chest':1-shoulder,'upper_arm.'+suffix:(1-f)*shoulder,'forearm.'+suffix:f*shoulder}
        if bone.startswith('foot.'):
            suffix=bone.split('.')[1];f=max(0,min(1,(z-.12)/.13))
            return {bone:1-f,'shin.'+suffix:f}
        if mode == 'torso':
            if z < 1.08:
                f = min(1, max(0, (z - .91) / .17))
                return {'pelvis': 1 - f, 'spine': f}
            f = min(1, max(0, (z - 1.08) / .2))
            return {'spine': 1 - f, 'chest': f}
        if mode in ('skirt', 'inner_skirt'):
            # The calf must not overtake a pelvis-bound robe during a stride.
            # Fade out the waist binding before introducing shin movement;
            # this keeps each vertex within glTF's four-weight skin budget.
            follow = max(0, min(1, (1.01-z)/.42))
            follow = follow*follow*(3-2*follow)
            shin = max(0, min(1, (.52-z)/.28))
            shin = shin*shin*(3-2*shin)
            if mode == 'skirt' and bone in ('robe.L', 'robe.R'):
                side = bone.rsplit('.', 1)[1]
                return {'pelvis':1-follow, bone:.12*follow,
                        'thigh.'+side:.88*follow*(1-shin),
                        'shin.'+side:.88*follow*shin}
            left = max(0, min(1, .5+v.co.x/.13))
            left = left*left*(3-2*left)
            return {'pelvis':1-follow,
                    'thigh.L':follow*(1-shin)*left,
                    'thigh.R':follow*(1-shin)*(1-left),
                    'shin.L':follow*shin*left,
                    'shin.R':follow*shin*(1-left)}
        return {bone: 1}
    for v in obj.data.vertices:
        for b, weight in weight_vertex(v).items():
            if weight > .00001:
                group = obj.vertex_groups.get(b) or obj.vertex_groups.new(name=b)
                group.add([v.index], weight, 'REPLACE')

bpy.ops.object.select_all(action='DESELECT')
for obj in PARTS:
    obj.select_set(True)
bpy.context.view_layer.objects.active = PARTS[0]
bpy.ops.object.join()
body = bpy.context.object
body.name = 'Hanli_Surface'
body.data.name = 'Hanli editable character mesh'

root = bpy.data.objects.new('Hanli', None)
bpy.context.collection.objects.link(root)
root['asset_role'] = 'Original procedural character prototype; not a scanned or AAA production asset'
root['forward'] = 'Blender -Y, glTF +Z'
root['units'] = 'metres'
root['source'] = 'tools/build_hanli.py'
arm_data = bpy.data.armatures.new('Hanli Skeleton')
rig = bpy.data.objects.new('Hanli_Rig', arm_data)
bpy.context.collection.objects.link(rig)
rig.parent = root
bpy.context.view_layer.objects.active = rig
bpy.ops.object.select_all(action='DESELECT')
rig.select_set(True)
bpy.ops.object.mode_set(mode='EDIT')
bones = [
    ('root', (0, 0, 0), (0, 0, .2), None),
    ('pelvis', (0, 0, .86), (0, 0, 1.01), 'root'),
    ('spine', (0, 0, 1.01), (0, 0, 1.20), 'pelvis'),
    ('chest', (0, 0, 1.20), (0, 0, 1.37), 'spine'),
    ('neck', (0, 0, 1.37), (0, 0, 1.472), 'chest'),
    ('head', (0, 0, 1.472), (0, 0, 1.682), 'neck'),
    ('robe.L', (.06, 0, .97), (.13, -.04, .25), 'pelvis'),
    ('robe.R', (-.06, 0, .97), (-.13, -.04, .25), 'pelvis'),
    ('robe.back', (0, .05, .97), (0, .13, .2), 'pelvis'),
]
for side, suffix in [(-1, 'R'), (1, 'L')]:
    bones += [
        ('upper_arm.' + suffix, (side * .167, 0, 1.305), (side * .216, -.006, 1.114), 'chest'),
        ('forearm.' + suffix, (side * .216, -.006, 1.114), (side * .235, -.037, .946), 'upper_arm.' + suffix),
        ('hand.' + suffix, (side * .235, -.037, .946), (side * .240, -.04, .885), 'forearm.' + suffix),
        ('thigh.' + suffix, (side * .083, .018, .85), (side * .086, -.004, .46), 'pelvis'),
        ('shin.' + suffix, (side * .086, -.004, .46), (side * .089, -.001, .095), 'thigh.' + suffix),
        ('foot.' + suffix, (side * .089, -.001, .095), (side * .089, -.09, .035), 'shin.' + suffix),
    ]
for name, head, tail, parent in bones:
    b = arm_data.edit_bones.new(name)
    b.head, b.tail = head, tail
    if parent:
        b.parent = arm_data.edit_bones[parent]
bpy.ops.object.mode_set(mode='OBJECT')
body.parent = rig
mod = body.modifiers.new('Hanli skin deformation', 'ARMATURE')
mod.object = rig
rig.show_in_front = True

# Ground the exported animation using the actual weighted boot soles.  This
# compensates the vertical lift of the authored stride without moving the
# scene root or adding runtime-only offsets.  It does not implement foot IK.
sole_material = list(body.data.materials).index(M['sole'])
sole_indices = sorted({index for poly in body.data.polygons
                       if poly.material_index == sole_material
                       for index in poly.vertices})
group_names = {group.index: group.name for group in body.vertex_groups}
sole_vertices = [(body.data.vertices[index].co.copy(),
                  [(group_names[g.group], g.weight)
                   for g in body.data.vertices[index].groups])
                 for index in sole_indices]
rest_inverse = {bone.name: bone.matrix_local.inverted()
                for bone in arm_data.bones}


def ground_pose():
    posed = {}
    for bone in arm_data.bones:
        basis = rig.pose.bones[bone.name].matrix_basis
        if bone.parent:
            posed[bone.name] = (posed[bone.parent.name]
                               @ rest_inverse[bone.parent.name]
                               @ bone.matrix_local @ basis)
        else:
            posed[bone.name] = bone.matrix_local @ basis
    skin = {name: transform @ rest_inverse[name]
            for name, transform in posed.items()}
    lowest = min(sum((skin[name] @ point).z * weight
                     for name, weight in weights)
                 for point, weights in sole_vertices)
    # Rotation interpolation during Walk/Idle blends can lower the soles by
    # about 10 mm relative to either grounded endpoint.  Retain that measured
    # clearance in the baked clips; the 60 Hz transition check enforces it.
    rig.pose.bones['pelvis'].location.y += .010 - lowest


def animate(name, frame_count, samples):
    action = bpy.data.actions.new(name)
    rig.animation_data_create()
    rig.animation_data.action = action
    for frame in range(1, frame_count + 1, samples):
        phase = (frame - 1) / (frame_count - 1)
        for pb in rig.pose.bones:
            pb.rotation_mode = 'XYZ'
            pb.rotation_euler = (0, 0, 0)
            pb.location = (0, 0, 0)
        if name == 'Idle':
            breath = math.sin(phase * math.tau)
            rig.pose.bones['chest'].rotation_euler.x = .014 * breath
            rig.pose.bones['head'].rotation_euler.y = .018 * breath
            rig.pose.bones['upper_arm.L'].rotation_euler.x = .014 * breath
            rig.pose.bones['upper_arm.R'].rotation_euler.x = -.012 * breath
            rig.pose.bones['robe.back'].rotation_euler.x = .01 * breath
        elif name == 'Walk':
            stride = math.sin(phase * math.tau)
            rig.pose.bones['pelvis'].location.y = .012 * abs(stride)
            rig.pose.bones['pelvis'].location.x = .006 * stride
            for sign, side in [(1, 'L'), (-1, 'R')]:
                rig.pose.bones['thigh.' + side].rotation_euler.x = sign * stride * .32
                rig.pose.bones['shin.' + side].rotation_euler.x = max(0, -sign * stride) * -.42
                # Keep the boot's sole level while the thigh and knee flex.
                # The old additive foot pitch made the support foot tiptoe.
                rig.pose.bones['foot.' + side].rotation_euler.x = (
                    -rig.pose.bones['thigh.' + side].rotation_euler.x
                    -rig.pose.bones['shin.' + side].rotation_euler.x)
                rig.pose.bones['upper_arm.' + side].rotation_euler.x = -sign * stride * .2
                rig.pose.bones['forearm.' + side].rotation_euler.x = -.06 - abs(stride) * .04
                rig.pose.bones['robe.' + side].rotation_euler.x = sign * stride * .06
            rig.pose.bones['chest'].rotation_euler.y = .035 * stride
            rig.pose.bones['robe.back'].rotation_euler.x = .055 + .025 * math.cos(phase * math.tau * 2)
        else:
            # Measured anticipation, a diagonal cut, then recovery. Authored keys.
            if phase < .32:
                wind = phase / .32
                sweep = 0
            elif phase < .55:
                wind = 1
                sweep = (phase - .32) / .23
            else:
                wind = max(0, 1 - (phase - .55) / .45)
                sweep = wind
            rig.pose.bones['upper_arm.R'].rotation_euler.x = (-1.15 + 1.5 * sweep) * wind
            rig.pose.bones['upper_arm.R'].rotation_euler.z = (-.72 + 1.12 * sweep) * wind
            rig.pose.bones['forearm.R'].rotation_euler.x = -.42 * wind
            rig.pose.bones['hand.R'].rotation_euler.y = -.5 * wind
            rig.pose.bones['chest'].rotation_euler.y = (-.22 + .44 * sweep) * wind
            rig.pose.bones['head'].rotation_euler.y = .11 * wind
            rig.pose.bones['upper_arm.L'].rotation_euler.x = -.35 * wind
            rig.pose.bones['thigh.L'].rotation_euler.x = -.1 * wind
            rig.pose.bones['robe.L'].rotation_euler.x = .08 * wind
        ground_pose()
        for pb in rig.pose.bones:
            pb.keyframe_insert('rotation_euler', frame=frame, group=pb.name)
            pb.keyframe_insert('location', frame=frame, group=pb.name)
    action.use_fake_user = True
    track = rig.animation_data.nla_tracks.new()
    track.name = name
    st = track.strips.new(name, 1, action)
    st.action_frame_start, st.action_frame_end = 1, frame_count
    track.mute = True
    return action


idle = animate('Idle', 73, 3)
walk = animate('Walk', 25, 1)
attack = animate('Attack', 31, 1)
rig.animation_data.action = idle
bpy.context.scene.frame_set(1)
scene = bpy.context.scene
scene.render.fps = 24
scene.frame_start, scene.frame_end = 1, 73

# Lighting/camera remain in the editable source, excluded from the game export.
studio = bpy.data.collections.new('Studio | source only')
scene.collection.children.link(studio)


def move_to_studio(obj):
    for collection in list(obj.users_collection):
        collection.objects.unlink(obj)
    studio.objects.link(obj)


def aim(obj, point):
    obj.rotation_euler = (Vector(point) - obj.location).to_track_quat('-Z', 'Y').to_euler()


def area(name, loc, energy, color, size):
    data = bpy.data.lights.new(name, 'AREA')
    obj = bpy.data.objects.new(name, data)
    studio.objects.link(obj)
    obj.location = loc
    data.energy, data.color, data.shape, data.size = energy, color, 'DISK', size
    aim(obj, (0, 0, 1.05))


area('Key | warm silk', (-2.2, -3.2, 4.2), 430, (1, .89, .74), 3)
area('Fill | cloud light', (2.8, -1.4, 2.1), 110, (.75, .84, 1), 3)
area('Rim | jade edge', (1.3, 2.0, 3.1), 360, (.72, .88, 1), 2)
bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 0, -.004))
floor = bpy.context.object
floor.name = 'Studio ground'
floor.data.materials.append(material('Studio slate', '#1d2e31', .83))
move_to_studio(floor)
camdata = bpy.data.cameras.new('Portrait camera')
camera = bpy.data.objects.new('Portrait camera', camdata)
studio.objects.link(camera)
camera.location = (2.5, -4.5, 2.05)
aim(camera, (0, -.015, .92))
camera.data.type = 'ORTHO'
camera.data.ortho_scale = 2.18
scene.camera = camera
scene.world.color = (.045, .055, .065)
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.cycles.samples = 48
scene.cycles.use_denoising = False
scene.render.resolution_x = 720
scene.render.resolution_y = 900
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
scene.view_settings.view_transform = 'AgX'
scene.view_settings.look = 'AgX - Medium High Contrast'
scene.view_settings.exposure = -.1
scene.render.film_transparent = False

# Save the source with packed textures and export only character/rig/root.
bpy.ops.object.select_all(action='DESELECT')
for obj in (root, rig, body):
    obj.select_set(True)
bpy.context.view_layer.objects.active = rig
bpy.ops.wm.save_as_mainfile(filepath=str(ART / 'hanli.blend'), compress=True)
bpy.ops.export_scene.gltf(filepath=str(ASSET / 'hanli.glb'), export_format='GLB', use_selection=True,
    export_animations=True, export_animation_mode='ACTIONS', export_force_sampling=True,
    export_skins=True, export_yup=True, export_apply=False, export_extras=True,
    export_materials='EXPORT', export_cameras=False, export_lights=False)
metadata = {'asset': 'hanli.glb', 'source': 'art/hanli.blend', 'generator': 'tools/build_hanli.py',
    'revision': 5, 'uv_revision': 2,
    'generator_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'component_sha256': {name: hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest()
                         for name in ['hanli_face.py', 'hanli_hair.py', 'hanli_costume.py']},
    'art_direction': 'User-provided Han Li reference: youthful face, half-tied long black hair, teal and pale-blue layered robes, pale-gold filigree and crimson tassels.',
    'glb_bytes': (ASSET / 'hanli.glb').stat().st_size,
    'glb_sha256': hashlib.sha256((ASSET / 'hanli.glb').read_bytes()).hexdigest(),
    'blend_sha256': hashlib.sha256((ART / 'hanli.blend').read_bytes()).hexdigest(),
    'blender': bpy.app.version_string, 'forward': 'glTF +Z', 'height_m': round(max(v.co.z for v in body.data.vertices), 4),
    'vertices': len(body.data.vertices), 'triangles': sum(len(p.vertices) - 2 for p in body.data.polygons),
    'materials': len(body.data.materials), 'bones': len(rig.data.bones), 'clips': ['Idle', 'Walk', 'Attack'],
    'quality_scope': 'Original editable procedural prototype; not a AAA-ready production character.'}
(ASSET / 'hanli-info.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n')
print('HANLI_ASSET', json.dumps(metadata))
scene.render.filepath = str(QA / 'hero-preview.png')
if not os.environ.get('FANREN_SKIP_RENDER'):
    bpy.ops.render.render(write_still=True)
camera.location=(.38,-1.6,1.66)
aim(camera,(0,-.02,1.58));camera.data.ortho_scale=.42
scene.render.resolution_x=800;scene.render.resolution_y=900
scene.render.filepath=str(QA/'hero-face.png')
if not os.environ.get('FANREN_SKIP_RENDER'):
    bpy.ops.render.render(write_still=True)
camera.location=(0,-4.5,1.75);aim(camera,(0,-.015,.92));camera.data.ortho_scale=2.18
scene.render.resolution_x=720;scene.render.resolution_y=900
scene.render.filepath=str(QA/'hero-front.png')
if not os.environ.get('FANREN_SKIP_RENDER'):
    bpy.ops.render.render(write_still=True)
print('HANLI_COMPLETE', str(ASSET / 'hanli.glb'))
