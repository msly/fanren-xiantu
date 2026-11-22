"""Build an original, editable Han Li prototype in Blender 4.3+.

Run: blender -b --factory-startup --python tools/build_hanli.py
Units are metres. Blender forward is -Y; glTF forward is +Z.
The mesh, materials, armature and three authored actions are self-contained.
"""
import bpy
import math
import os
import random
import json
from pathlib import Path
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
ASSET = ROOT / 'assets' / '3d'
ART = ROOT / 'art'
QA = ROOT.parent / 'qa3d'
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
    'robe_light': material('Sage silk | lapels and cuffs', '#516d59', .73),
    'linen': material('Undyed silk | inner collar', '#c7c7ac', .86),
    'pants': material('Charcoal linen | trousers', '#263b3a', .92),
    'leather': material('Worn black leather', '#182523', .68),
    'sole': material('Boot soles', '#121b1b', .93),
    'gold': material('Antique bronze | engraved fittings', '#a68a50', .32, .78),
    'gold_dark': material('Patinated bronze', '#5c643e', .47, .58),
    'steel': material('Tempered steel | sword flats', '#9cbbbc', .23, .92),
    'edge': material('Polished cutting edge', '#d5e1dc', .15, 1),
    'skin': material('Warm skin', '#bd9478', .55),
    'skin_shadow': material('Warm recessed skin', '#9b705b', .65),
    'lips': material('Natural lip colour', '#9c7267', .53),
    'hair': material('Black hair', '#121c20', .39),
    'hair_light': material('Hair strands', '#293439', .42),
    'eye': material('Eye sclera', '#b6b6a2', .22),
    'iris': material('Brown iris', '#372e22', .3),
    'pupil': material('Pupil', '#080d0e', .12),
    'jade': material('Palm-heaven bottle | green jade', '#5d9271', .22, .08),
    'jade_dark': material('Jade engraving', '#214735', .44),
}
M['skin'].node_tree.nodes.get('Principled BSDF').inputs['Subsurface Weight'].default_value = .045
M['jade'].node_tree.nodes.get('Principled BSDF').inputs['Coat Weight'].default_value = .35


def cloth_texture():
    """Small embedded image maps, also understood by the standard glTF exporter."""
    n = 256
    base = bpy.data.images.new('Jade_weave_basecolor', n, n, alpha=True)
    normal = bpy.data.images.new('Jade_weave_normal', n, n, alpha=True)
    pixels, normals = [], []
    c = [int('28574b'[i:i + 2], 16) / 255 * .75 for i in (0, 2, 4)]
    for y in range(n):
        for x in range(n):
            a = math.sin(x * math.pi / 2)
            b = math.sin(y * math.pi / 2)
            variation = .97 + .025 * a * b + .018 * random.random()
            brocade = .008 * math.sin((x + math.sin(y / 18) * 5) / 9)
            pixels.extend([min(1, v * variation + brocade) for v in c] + [1])
            normals.extend([.5 + .065 * a, .5 + .065 * b, .992, 1])
    base.pixels.foreach_set(pixels)
    normal.pixels.foreach_set(normals)
    normal.colorspace_settings.name = 'Non-Color'
    for image in (base, normal):
        image.file_format = 'PNG'
        image.pack()
    m = M['robe']
    nodes = m.node_tree.nodes
    bsdf = nodes.get('Principled BSDF')
    tex = nodes.new('ShaderNodeTexImage')
    tex.image = base
    m.node_tree.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
    texn = nodes.new('ShaderNodeTexImage')
    texn.image = normal
    nm = nodes.new('ShaderNodeNormalMap')
    nm.inputs['Strength'].default_value = .28
    m.node_tree.links.new(texn.outputs['Color'], nm.inputs['Color'])
    m.node_tree.links.new(nm.outputs['Normal'], bsdf.inputs['Normal'])


cloth_texture()
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
    return mesh(name, verts, faces, mat, bone, skin_mode, uv)


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
    ring_mesh('High boot.' + suffix, [(.036, .048, .096, side * .089, -.04), (.06, .048, .094, side * .089, -.038), (.09, .044, .075, side * .089, -.02), (.12, .036, .041, side * .089, 0), (.22, .04, .041, side * .089, 0), (.31, .041, .043, side * .089, .003)], 'leather', 'foot.' + suffix, n=32)
    ring_mesh('Stitched sole.' + suffix, [(.008, .05, .099, side * .089, -.039), (.027, .051, .1, side * .089, -.039), (.036, .048, .096, side * .089, -.039)], 'sole', 'foot.' + suffix, n=32)
    for z in [.145, .17, .27, .292]:
        pts = [(side * .089 + math.sin(a) * .042, -math.cos(a) * .043, z + .002 * math.cos(a * 2)) for a in [i * math.tau / 16 for i in range(17)]]
        tube('Boot stitching.' + suffix, pts, .0011, 'gold_dark', 'foot.' + suffix)
    for z in [.105, .115, .126]:
        tube('Soft ankle crease.' + suffix, [(side * .089 - .032, -.031, z), (side * .089, -.041, z + .004), (side * .089 + .032, -.031, z)], .0012, 'robe_dark', 'foot.' + suffix)


ring_mesh('Inner body', [(.82, .13, .092, 0, 0), (.99, .126, .092, 0, 0), (1.17, .162, .095, 0, 0), (1.30, .18, .084, 0, 0), (1.35, .146, .074, 0, 0), (1.405, .052, .046, 0, 0)], 'robe_dark', skin_mode='torso')


def torso_warp(x, y, z, a, j):
    f = .0025 * math.sin(a * 11 + z * 23)
    return x + math.sin(a) * f, y - math.cos(a) * f, z


ring_mesh('Fitted outer robe', [(.87, .143, .102, 0, 0), (.96, .138, .100, 0, 0), (1.02, .136, .098, 0, 0), (1.10, .146, .102, 0, 0), (1.20, .17, .110, 0, 0), (1.29, .184, .098, 0, 0), (1.34, .151, .082, 0, 0), (1.37, .083, .057, 0, 0)], 'robe', skin_mode='torso', warp=torso_warp)

# Underskirt and three separated outer cloth panels, with curved hems and draping.
ring_mesh('Inner silk skirt', [(.13, .16, .13, 0, .015), (.31, .152, .122, 0, .008), (.60, .138, .11, 0, 0), (.88, .133, .096, 0, 0), (.98, .133, .096, 0, 0)], 'robe_dark', 'pelvis', skin_mode='inner_skirt')


def skirt(name, amin, amax, bone, mat, n=40):
    verts, faces, uv = [], [], []
    rows = 18
    def coord(u, f):
        a = amin + (amax - amin) * u
        z = .975 - f * .83
        rx = .142 + f ** .8 * .072
        ry = .109 + f ** 1.4 * .060
        folds = (.002 + .009 * f) * (math.sin(a * 9 + .2) + .32 * math.sin(a * 19))
        z += f ** 5 * (.013 * math.cos(a * 5) - .012 * math.sin(a))
        return (math.sin(a) * (rx + folds), -math.cos(a) * (ry + folds) + f ** 2 * .017, z)
    for j in range(rows + 1):
        for i in range(n + 1):
            verts.append(coord(i / n, j / rows))
            uv.append((i / n, 1 - j / rows))
            if i < n and j < rows:
                k = j * (n + 1) + i
                faces.append((k, k + 1, k + n + 2, k + n + 1))
    obj = mesh(name, verts, faces, mat, bone, 'skirt', uv)
    solid = obj.modifiers.new('Silk panel thickness', 'SOLIDIFY')
    solid.thickness = .0025
    for u in (0, 1):
        p = [coord(u, j / 20) for j in range(21)]
        tube(name + ' raised edge', p, .0021, 'gold_dark', bone)
    tube(name + ' stitched hem', [coord(i / n, .985) for i in range(n + 1)], .0017, 'gold', bone)
    return coord


left_panel = skirt('Left draped robe panel', .105, 1.10, 'robe.L', 'robe')
right_panel = skirt('Right draped robe panel', -1.10, -.105, 'robe.R', 'robe')
skirt('Back draped robe panel', 1.13, math.tau - 1.13, 'robe.back', 'robe_dark', n=56)
for side, panel in [('L', left_panel), ('R', right_panel)]:
    for band in [.76, .82]:
        pts = []
        for i in range(30):
            u = .18 + i / 29 * .61
            p = Vector(panel(u, band + math.sin(u * math.tau * 2) * .007))
            p.y -= .0015
            pts.append(tuple(p))
        tube('Cloud hem embroidery.' + side, pts, .0009, 'gold_dark', 'robe.' + side)

# Fine, body-conforming lapel ribbons, with a raised collar around the neck.
def front_surface(x, z, depth=.004):
    rows = [(1.04,.14,.102),(1.20,.17,.110),(1.29,.184,.098),(1.34,.151,.082),(1.37,.083,.057),(1.40,.052,.046),(1.445,.038,.036)]
    lo,hi=rows[0],rows[-1]
    for a,b in zip(rows, rows[1:]):
        if a[0] <= z <= b[0]: lo,hi=a,b;break
    f=max(0,min(1,(z-lo[0])/(hi[0]-lo[0])))
    rx=lo[1]*(1-f)+hi[1]*f;ry=lo[2]*(1-f)+hi[2]*f
    return -ry*math.sqrt(max(.03,1-(x/rx)**2))-depth

def tailored(name, xs1, xs2, zs, mat):
    left,right,centre=[],[],[]
    for i in range(len(zs)-1):
        for j in range(10):
            f=j/10;z=zs[i]*(1-f)+zs[i+1]*f
            x1=xs1[i]*(1-f)+xs1[i+1]*f;x2=xs2[i]*(1-f)+xs2[i+1]*f
            left.append((x1,front_surface(x1,z,.008),z))
            right.append((x2,front_surface(x2,z,.008),z))
            xc=(x1+x2)/2;centre.append((xc,front_surface(xc,z,.009),z))
    z=zs[-1];left.append((xs1[-1],front_surface(xs1[-1],z,.008),z));right.append((xs2[-1],front_surface(xs2[-1],z,.008),z))
    strip(name,left,right,mat)
    return centre

tailored('Ivory inner cross collar',[-.031,-.065,-.047,.009],[-.012,-.043,-.025,.031],[1.438,1.366,1.28,1.196],'linen')
tailored('Ivory underlap',[.012,.045,.025,-.057],[.032,.068,.046,-.035],[1.438,1.366,1.28,1.16],'linen')
lapel=tailored('Soft outer crossing lapel',[.065,.105,.035,-.092],[.086,.129,.058,-.069],[1.372,1.32,1.22,1.048],'robe_light')
tube('Collar bronze stitch',lapel,.00085,'gold')

# Sleeves are curved, tapered cloth volumes. Hands and fingers are modelled separately.
for side, suffix in [(-1, 'R'), (1, 'L')]:
    shoulder = (side * .167, 0, 1.305)
    elbow = (side * .271, -.006, 1.114)
    wrist = (side * .30, -.037, .946)
    # A flexible shoulder saddle overlaps the sleeve insertion and closes its seam.
    cap_v,cap_f,cap_uv=[],[],[]
    for j in range(9):
        f=j/8;x=side*(.104+.106*f);zz=1.35-.078*f;ry=.066+.017*math.sin(f*math.pi*.7)
        for i in range(17):
            a=-math.pi/2+i/16*math.pi
            cap_v.append((x,math.sin(a)*ry,zz+math.cos(a)*.037));cap_uv.append((i/16,f))
            if i<16 and j<8:
                k=j*17+i;cap_f.append((k,k+1,k+18,k+17) if side>0 else (k+17,k+18,k+1,k))
    cap=mesh('Soft shoulder saddle.'+suffix,cap_v,cap_f,'robe','upper_arm.'+suffix,'shoulder.'+suffix,cap_uv)
    mod=cap.modifiers.new('Shoulder silk thickness','SOLIDIFY');mod.thickness=.002
    # One continuous cloth envelope spans the shoulder and elbow; smooth skin weights bend it.
    path=[(side*.13,.005,1.326,.052,.060),(side*.17,0,1.30,.060,.062),
          (side*.205,-.004,1.255,.061,.060),(side*.244,-.006,1.19,.056,.054),
          (side*.268,-.007,1.123,.052,.049),(side*.282,-.017,1.065,.058,.051),
          (side*.294,-.029,1.002,.051,.046),(side*.30,-.037,.947,.038,.037)]
    sleeve_v,sleeve_f,sleeve_uv=[],[],[]
    n=32
    for j,(x,y,z,ru,rv) in enumerate(path):
        center=Vector((x,y,z))
        prev=Vector(path[max(0,j-1)][:3]);nxt=Vector(path[min(len(path)-1,j+1)][:3])
        axis=(nxt-prev).normalized();u=axis.cross(Vector((0,1,0))).normalized();v=axis.cross(u).normalized()
        for i in range(n+1):
            a=i/n*math.tau
            fold=.0025*math.sin(a*7+j*.7)+.0015*math.sin(a*13+j*.4)
            pt=center+u*math.cos(a)*(ru+fold)+v*math.sin(a)*(rv+fold)
            sleeve_v.append(tuple(pt));sleeve_uv.append((i/n,j/(len(path)-1)))
            if i<n and j<len(path)-1:
                k=j*(n+1)+i;sleeve_f.append((k,k+1,k+n+2,k+n+1))
    mesh('Continuous draped sleeve.'+suffix,sleeve_v,sleeve_f,'robe','upper_arm.'+suffix,'arm.'+suffix,sleeve_uv)
    cuff_start = Vector(wrist).lerp(Vector(elbow), .19)
    limb('Dark fitted cuff.' + suffix, cuff_start, wrist, [(0, .041, .039), (.17, .042, .039), (.83, .036, .035), (1, .036, .035)], 'robe_dark', 'forearm.' + suffix)
    for f in [.03, .86]:
        point = Vector(cuff_start).lerp(Vector(wrist), f)
        limb('Cuff bronze piping.' + suffix, point, point + (Vector(wrist) - Vector(cuff_start)).normalized() * .003, [(0, .042 if f < .5 else .037, .04 if f < .5 else .036), (1, .042 if f < .5 else .037, .04 if f < .5 else .036)], 'gold_dark', 'forearm.' + suffix)
    for offset in [-.016, .016]:
        tube('Sleeve soft fold.' + suffix, [(side * .205, -.062, 1.255 + offset), (side * .248, -.06, 1.185 + offset), (side * .27, -.054, 1.14 + offset)], .0011, 'robe_light', 'upper_arm.' + suffix)
    sphere('Hand palm.' + suffix, (side * .303, -.037, .914), (.026, .019, .042), 'skin', 'hand.' + suffix, segments=24)
    for i, length in enumerate([.048, .057, .055, .043]):
        x = side * (.286 + i * .012)
        z = .904
        pts = [(x, -.041, z), (x, -.047, z - length * .5), (x - side * .004, -.054 if suffix == 'R' else -.041, z - length)]
        tube('Finger %d.%s' % (i, suffix), pts, .0062 if i != 3 else .0055, 'skin', 'hand.' + suffix, radii=[1, .94, .58])
        sphere('Fingertip.%s.%d' % (suffix, i), pts[-1], (.0037, .0044, .0042), 'skin', 'hand.' + suffix, segments=12, rings=8)
    tube('Opposable thumb.' + suffix, [(side * .283, -.04, .931), (side * .275, -.062, .912), (side * .28, -.066, .897)], .008, 'skin', 'hand.' + suffix, radii=[1.2, 1, .65])

# Waist belt and carefully fitted bronze/jade buckle.
ring_mesh('Wide waist sash', [(.965, .143, .105, 0, 0), (.978, .144, .106, 0, 0), (1.025, .142, .104, 0, 0), (1.04, .138, .101, 0, 0)], 'leather', 'pelvis', n=64)
for z in [.976, 1.03]:
    tube('Belt edge stitching', [(math.sin(a) * .144, -math.cos(a) * .107, z) for a in [i * math.tau / 48 for i in range(49)]], .0018, 'gold', 'pelvis')
strip('Bronze waist clasp', [(-.032, -.111, 1.031), (-.035, -.115, 1.003), (-.032, -.112, .976)], [(.032, -.111, 1.031), (.035, -.115, 1.003), (.032, -.112, .976)], 'gold', 'pelvis')
sphere('Waist jade cabochon', (0, -.121, 1.003), (.019, .005, .018), 'jade', 'pelvis', segments=24)
strip('Long silk sash end', [(.075, -.108, .993), (.102, -.121, .88), (.075, -.142, .75), (.088, -.16, .62)], [(.108, -.093, .993), (.132, -.11, .88), (.104, -.13, .75), (.117, -.148, .62)], 'robe_light', 'robe.L')
tube('Sash edge', [(.104, -.108, .99), (.128, -.121, .88), (.1, -.142, .75), (.113, -.16, .62)], .0012, 'gold', 'robe.L')

# Palm-heaven bottle: bottle silhouette, neck cap and cut-like scrolling decoration.
bx, by, bz = .156, -.088, .907
tube('Bottle suspension cord', [(.125, -.07, 1.016), (.165, -.10, .975), (bx, by, .954)], .0019, 'gold_dark', 'pelvis')
ring_mesh('Palm-heaven jade bottle', [(bz - .038, .009, .009, bx, by), (bz - .031, .021, .019, bx, by), (bz - .006, .027, .023, bx, by), (bz + .017, .022, .02, bx, by), (bz + .028, .011, .01, bx, by), (bz + .046, .009, .008, bx, by)], 'jade', 'pelvis', n=32)
ring_mesh('Bottle bronze stopper', [(bz + .044, .010, .009, bx, by), (bz + .05, .012, .011, bx, by), (bz + .055, .008, .008, bx, by)], 'gold', 'pelvis', n=24)
for shift in [-.009, .009]:
    tube('Bottle cloud engraving', [(bx - .014, by - .018, bz + shift), (bx - .006, by - .024, bz + shift + .007), (bx + .006, by - .024, bz + shift), (bx + .013, by - .02, bz + shift + .004)], .0011, 'jade_dark', 'pelvis')

# Anatomical neck and a custom sculpted face surface, not a spherical head.
ring_mesh('Neck', [(1.363, .039, .037, 0, .002), (1.39, .039, .037, 0, .002), (1.445, .035, .034, 0, .001), (1.472, .04, .036, 0, 0)], 'skin', 'neck', n=40)
FACE_PROFILE = [(1.478, .009, .018), (1.488, .027, .032), (1.50, .039, .04), (1.52, .052, .048), (1.54, .064, .054), (1.56, .069, .058), (1.58, .073, .061), (1.60, .075, .064), (1.62, .073, .066), (1.64, .070, .066), (1.66, .066, .064), (1.68, .055, .057), (1.695, .035, .04), (1.705, .006, .008)]
face_rows = []
for k in range(len(FACE_PROFILE) - 1):
    a, b = FACE_PROFILE[k], FACE_PROFILE[k + 1]
    for j in range(3):
        f = j / 3
        face_rows.append(tuple(a[v] * (1 - f) + b[v] * f for v in range(3)) + (0, -.013))
face_rows.append(FACE_PROFILE[-1] + (0, -.013))


def face_shape(x, y, z, a, j):
    front = max(0, math.cos(a)) ** 3
    ridge = .014 * math.exp(-(x / .011) ** 2 - ((z - 1.599) / .039) ** 4)
    tip = .021 * math.exp(-(x / .014) ** 2 - ((z - 1.569) / .011) ** 2)
    sockets = .008 * math.exp(-((abs(x) - .031) / .018) ** 2 - ((z - 1.608) / .012) ** 2)
    cheek = .004 * math.exp(-((abs(x) - .043) / .025) ** 2 - ((z - 1.575) / .018) ** 2)
    muzzle = .0045 * math.exp(-(x / .03) ** 2 - ((z - 1.535) / .018) ** 2)
    y += front * (sockets - ridge - tip - cheek - muzzle)
    return x, y, z


mesh_head = ring_mesh('Sculpted face and cranium', face_rows, 'skin', 'head', n=80, warp=face_shape)
sub = mesh_head.modifiers.new('Fine facial surface', 'SUBSURF')
sub.levels = 1
sub.render_levels = 1

for side, suffix in [(-1, 'R'), (1, 'L')]:
    sphere('Ear.' + suffix, (side * .073, -.002, 1.589), (.014, .013, .026), 'skin', 'head', segments=24)
    sphere('Ear concha.' + suffix, (side * .082, -.009, 1.59), (.004, .006, .016), 'skin_shadow', 'head', segments=16)
    tube('Ear helix.' + suffix, [(side * .077, -.014, 1.608), (side * .084, -.01, 1.613), (side * .086, -.009, 1.59), (side * .079, -.009, 1.571)], .0033, 'skin', 'head')
    ex = side * .0305
    sphere('Visible eye.' + suffix, (ex, -.074, 1.609), (.0135, .0064, .0059), 'eye', 'head', segments=32)
    sphere('Iris.' + suffix, (ex, -.0800, 1.6087), (.0042, .001, .0042), 'iris', 'head', segments=24)
    sphere('Pupil.' + suffix, (ex, -.08105, 1.6087), (.0019, .00045, .0024), 'pupil', 'head', segments=20)
    lid = [(ex - .0138, -.072, 1.608), (ex - .006, -.08, 1.614), (ex + .004, -.081, 1.6145), (ex + .0138, -.0715, 1.609)]
    tube('Upper eyelid.' + suffix, lid, .00215, 'skin_shadow', 'head')
    tube('Lower eyelid.' + suffix, [(ex - .0138, -.072, 1.608), (ex, -.080, 1.6038), (ex + .0138, -.0715, 1.609)], .0019, 'skin', 'head')
    tube('Eyebrow.' + suffix, [(ex - .015, -.072, 1.624), (ex - .003, -.078, 1.627), (ex + .012, -.072, 1.624)], .0031, 'hair', 'head', radii=[.5, 1, .35])
    for i in range(5):
        x = ex - .011 + i * .0045
        tube('Brow hair.' + suffix, [(x, -.078, 1.625), (x + .002, -.0785, 1.628)], .00045, 'hair_light', 'head')
    sphere('Nostril.' + suffix, (side * .0082, -.0948, 1.56), (.0031, .0014, .0017), 'skin_shadow', 'head', segments=16)
    tube('Nasolabial form.' + suffix, [(side * .012, -.084, 1.555), (side * .019, -.078, 1.54)], .00055, 'skin_shadow', 'head')
tube('Upper lip contour', [(-.022, -.071, 1.535), (-.009, -.079, 1.537), (0, -.081, 1.5358), (.009, -.079, 1.537), (.022, -.071, 1.535)], .00225, 'lips', 'head', radii=[.18, .9, .75, .9, .18])
tube('Lower lip contour', [(-.022, -.071, 1.534), (0, -.0805, 1.5312), (.022, -.071, 1.534)], .0025, 'lips', 'head', radii=[.12, 1, .12])
tube('Mouth seam', [(-.020, -.074, 1.5348), (0, -.0824, 1.534), (.020, -.074, 1.5348)], .0007, 'skin_shadow', 'head', radii=[.2, 1, .2])

# A fitted scalp cap with individual swept strands, side locks and tied back hair.
verts, faces, uv = [], [], []
for j in range(18):
    f = j / 17
    for i in range(65):
        a = i / 64 * math.tau
        bottom = 1.545 + max(0, math.cos(a)) * .104 + .007 * math.sin(a * 2)
        z = bottom * (1 - f) + 1.713 * f
        rr = max(.001, math.sqrt(max(.001, 1 - ((z - 1.606) / .11) ** 2)))
        x = math.sin(a) * .078 * rr
        y = -.013 - math.cos(a) * .073 * rr
        verts.append((x, y, z)); uv.append((i / 64, f))
        if i < 64 and j < 17:
            k = j * 65 + i
            faces.append((k, k + 1, k + 66, k + 65))
mesh('Swept black scalp hair', verts, faces, 'hair', 'head', uv=uv)
for k in range(24):
    a = k / 24 * math.tau
    front = max(0, math.cos(a))
    bottom = 1.548 + front * .102 + .007 * math.sin(a * 2)
    pts = []
    for j in range(8):
        f = j / 7
        z = bottom * (1 - f) + 1.714 * f
        rr = math.sqrt(max(.001, 1 - ((z - 1.606) / .111) ** 2))
        aa = a * (1 - .18 * f)
        pts.append((math.sin(aa) * .079 * rr, -.013 - math.cos(aa) * .0745 * rr, z))
    tube('Swept scalp strand %02d' % k, pts, .0008, 'hair_light' if k % 3 == 0 else 'hair', 'head', radii=[.45, .8, 1, 1, 1, .8, .6, .1])
sphere('Tied hair knot', (0, .027, 1.733), (.03, .027, .039), 'hair', 'head', segments=32)
for i in range(9):
    a = i / 9 * math.tau
    tube('Hair knot winding', [(math.cos(a) * .029, .027 + math.sin(a) * .025, 1.712), (math.cos(a + .8) * .031, .027 + math.sin(a + .8) * .027, 1.737), (math.cos(a + 1.4) * .02, .027 + math.sin(a + 1.4) * .019, 1.763)], .0011, 'hair_light', 'head')
tube('Bronze hair pin', [(-.047, .026, 1.73), (.046, .026, 1.734)], .0028, 'gold', 'head')
sphere('Hairpin jade bead', (-.049, .026, 1.73), (.006, .004, .004), 'jade', 'head', segments=16)
for i in range(7):
    off = (i - 3) * .007
    tube('Long back hair %02d' % i, [(off, .044, 1.702), (off * 1.3, .061, 1.61), (off * 1.5 + .005, .074, 1.485), (off + .008, .091, 1.365)], .011 if i in [2, 3, 4] else .007, 'hair', 'head', radii=[1, 1.2, .85, .08])
for side, suffix in [(-1, 'R'), (1, 'L')]:
    tube('Temple lock.' + suffix, [(side * .058, -.043, 1.663), (side * .069, -.05, 1.61), (side * .065, -.043, 1.548)], .009, 'hair', 'head', radii=[1.15, .8, .1])
    tube('Temple strand.' + suffix, [(side * .063, -.048, 1.65), (side * .074, -.055, 1.60), (side * .066, -.048, 1.547)], .0012, 'hair_light', 'head', radii=[.5, 1, .05])
tube('Loose fringe', [(-.045, -.055, 1.685), (-.03, -.073, 1.657), (-.006, -.083, 1.64), (.006, -.082, 1.625)], .007, 'hair', 'head', radii=[1.2, 1, .7, .03])

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
    for poly in obj.data.polygons:
        poly.use_smooth = True
    mode = obj.get('skin_mode', 'rigid')
    bone = obj.get('bind_bone', 'chest')
    if bone == 'head':
        for vertex in obj.data.vertices: vertex.co.z -= .018
    def weight_vertex(v):
        z = v.co.z
        if mode.startswith('shoulder.'):
            suffix=mode.split('.')[1];f=max(0,min(1,(abs(v.co.x)-.12)/.075))
            return {'chest':1-f,'upper_arm.'+suffix:f}
        if mode.startswith('arm.'):
            suffix=mode.split('.')[1];f=max(0,min(1,(1.20-z)/.14))
            return {'upper_arm.'+suffix:1-f,'forearm.'+suffix:f}
        if bone.startswith('foot.'):
            suffix=bone.split('.')[1];f=max(0,min(1,(z-.12)/.13))
            return {bone:1-f,'shin.'+suffix:f}
        if mode == 'torso':
            if z < 1.08:
                f = min(1, max(0, (z - .91) / .17))
                return {'pelvis': 1 - f, 'spine': f}
            f = min(1, max(0, (z - 1.08) / .2))
            return {'spine': 1 - f, 'chest': f}
        if mode == 'skirt':
            f = min(1, max(0, (.98 - z) / .32))
            return {'pelvis': 1 - f, bone: f}
        if mode == 'inner_skirt':
            return {'pelvis': .7, 'robe.back': .3}
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
        ('upper_arm.' + suffix, (side * .167, 0, 1.305), (side * .271, -.006, 1.114), 'chest'),
        ('forearm.' + suffix, (side * .271, -.006, 1.114), (side * .30, -.037, .946), 'upper_arm.' + suffix),
        ('hand.' + suffix, (side * .30, -.037, .946), (side * .305, -.04, .885), 'forearm.' + suffix),
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
            for sign, side in [(1, 'L'), (-1, 'R')]:
                rig.pose.bones['thigh.' + side].rotation_euler.x = sign * stride * .32
                rig.pose.bones['shin.' + side].rotation_euler.x = max(0, -sign * stride) * -.42
                rig.pose.bones['foot.' + side].rotation_euler.x = sign * stride * -.10
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
walk = animate('Walk', 25, 2)
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
area('Fill | cloud light', (2.8, -1.4, 2.1), 260, (.68, .82, 1), 3)
area('Rim | jade edge', (1.3, 2.0, 3.1), 600, (.63, 1, .84), 2)
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
    'blender': bpy.app.version_string, 'forward': 'glTF +Z', 'height_m': round(max(v.co.z for v in body.data.vertices), 4),
    'vertices': len(body.data.vertices), 'triangles': sum(len(p.vertices) - 2 for p in body.data.polygons),
    'materials': len(body.data.materials), 'bones': len(rig.data.bones), 'clips': ['Idle', 'Walk', 'Attack'],
    'quality_scope': 'Original editable procedural prototype; not a AAA-ready production character.'}
(ASSET / 'hanli-info.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n')
print('HANLI_ASSET', json.dumps(metadata))
scene.render.filepath = str(QA / 'hero-preview.png')
bpy.ops.render.render(write_still=True)
camera.location = (0, -4.5, 1.75)
aim(camera, (0, -.015, .92))
scene.render.filepath = str(QA / 'hero-front.png')
bpy.ops.render.render(write_still=True)
print('HANLI_COMPLETE', str(ASSET / 'hanli.glb'))
