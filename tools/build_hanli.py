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
from pathlib import Path
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
ASSET = ROOT / 'assets' / '3d'
ART = ROOT / 'art'
QA = Path(os.environ.get('FANREN_QA_DIR', str(ROOT.parent / 'qa3d' / 'polish-v3')))
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


def cloth_texture():
    """Packed woven albedo, tangent normal and roughness, saved before packing."""
    n=512
    yy,xx=np.mgrid[0:n,0:n].astype(np.float32)
    weave=np.sin(xx*math.pi/2)*np.cos(yy*math.pi/2)
    grain=np.random.default_rng(19).random((n,n),dtype=np.float32)-.5
    # Quiet diagonal brocade within the jade cloth, not broad glossy ridges.
    motif=np.sin(xx*.085+np.sin(yy*.043)*2)*np.sin(yy*.055)
    c=np.array([.105,.211,.176],dtype=np.float32)
    albedo=np.ones((n,n,4),dtype=np.float32)
    albedo[:,:,:3]=c[None,None,:]*(.97+.024*weave[:,:,None]+.018*motif[:,:,None])+grain[:,:,None]*.004
    normal=np.ones((n,n,4),dtype=np.float32)
    normal[:,:,0]=.5+.028*np.sin(xx*math.pi/2)
    normal[:,:,1]=.5+.028*np.sin(yy*math.pi/2)
    normal[:,:,2]=.998
    rough=np.ones((n,n,4),dtype=np.float32)
    rough[:,:,:3]=(.8+.035*weave+.025*grain)[:,:,None]
    m=M['robe'];nodes=m.node_tree.nodes;bsdf=nodes.get('Principled BSDF')
    for name,data,space,socket in [('Jade_weave_basecolor',albedo,'sRGB','Base Color'),('Jade_weave_normal',normal,'Non-Color','Normal'),('Jade_weave_roughness',rough,'Non-Color','Roughness')]:
        im=bpy.data.images.new(name,n,n,alpha=True);im.colorspace_settings.name=space
        im.pixels.foreach_set(data.ravel());im.update();im.file_format='PNG';im.filepath_raw=str(QA/(name+'.png'));im.save();im.pack()
        tex=nodes.new('ShaderNodeTexImage');tex.image=im
        if socket=='Normal':
            nm=nodes.new('ShaderNodeNormalMap');nm.inputs['Strength'].default_value=.26
            m.node_tree.links.new(tex.outputs['Color'],nm.inputs['Color']);m.node_tree.links.new(nm.outputs['Normal'],bsdf.inputs['Normal'])
        else:m.node_tree.links.new(tex.outputs['Color'],bsdf.inputs[socket])


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


# The outer robe is a closed garment shell; no overlapping inner torso is needed.


def torso_warp(x, y, z, a, j):
    f = .0018 * math.sin(a * 9 + z * 19)
    f += .0023 * math.exp(-((z - 1.06) / .09) ** 2) * math.sin(a * 11 + z * 27)
    f += .0012 * math.sin(a * 3 + z * 12)
    return x + math.sin(a) * f, y - math.cos(a) * f, z


TORSO_ROWS = [(.87, .143, .102, 0, 0), (.96, .138, .100, 0, 0),
              (1.02, .136, .098, 0, 0), (1.10, .146, .102, 0, 0),
              (1.20, .17, .110, 0, 0), (1.29, .184, .098, 0, 0),
              (1.34, .151, .082, 0, 0), (1.37, .083, .057, 0, 0),
              (1.39, .054, .045, 0, 0), (1.407, .040, .036, 0, .002)]
torso_rows = []
for low, high in zip(TORSO_ROWS, TORSO_ROWS[1:]):
    for t in np.linspace(0, 1, 5, endpoint=False):
        torso_rows.append(tuple(a * (1-t) + b * t for a, b in zip(low, high)))
torso_rows.append(TORSO_ROWS[-1])
ring_mesh('Fitted outer robe', torso_rows, 'robe', skin_mode='torso', warp=torso_warp, n=64)

# Underskirt and three separated outer cloth panels, with curved hems and draping.
ring_mesh('Inner silk skirt', [(.13, .16, .13, 0, .015), (.31, .152, .122, 0, .008), (.60, .138, .11, 0, 0), (.88, .133, .096, 0, 0), (.98, .133, .096, 0, 0)], 'robe_dark', 'pelvis', skin_mode='inner_skirt')


def skirt(name, amin, amax, bone, mat, n=40):
    verts, faces, uv = [], [], []
    rows = 18
    def coord(u, f):
        a = amin + (amax - amin) * u
        length=.79 if 'Left' in name else (.835 if 'Right' in name else .805)
        z = .975 - f * length
        rx = .142 + f ** .8 * .072
        ry = .109 + f ** 1.4 * .060
        a += (.11 if 'Left' in name else -.045)*(1-f)**2
        folds=.003*math.sin(a*3.4+.6*f)+(.002+.007*f)*(math.sin(a*6.5+1.1*math.sin(f*2.4))+.27*math.sin(a*15-.7*f))
        z += f ** 5 * (.009 * math.cos(a * 3) - .008 * math.sin(a))
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
        tube(name + ' raised edge', p, .0012, 'gold_dark', bone)
    tube(name + ' stitched hem', [coord(i / n, .985) for i in range(n + 1)], .0009, 'gold_dark', bone)
    return coord


left_panel = skirt('Left draped robe panel', -.14, 1.10, 'robe.L', 'robe')
right_panel = skirt('Right draped robe panel', -1.10, .025, 'robe.R', 'robe')
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
    rows = [row[:3] for row in TORSO_ROWS]
    lo,hi=rows[0],rows[-1]
    for a,b in zip(rows, rows[1:]):
        if a[0] <= z <= b[0]: lo,hi=a,b;break
    f=max(0,min(1,(z-lo[0])/(hi[0]-lo[0])))
    rx=lo[1]*(1-f)+hi[1]*f;ry=lo[2]*(1-f)+hi[2]*f
    angle=math.asin(max(-.999,min(.999,x/rx)))
    return torso_warp(x,-ry*math.cos(angle),z,angle,0)[1]-depth

def tailored(name, xs1, xs2, zs, mat):
    edges,centre=[],[]
    for i in range(len(zs)-1):
        for j in range(10):
            f=j/10;z=zs[i]*(1-f)+zs[i+1]*f
            x1=xs1[i]*(1-f)+xs1[i+1]*f;x2=xs2[i]*(1-f)+xs2[i+1]*f
            edges.append((x1,x2,z))
            xc=(x1+x2)/2;centre.append((xc,front_surface(xc,z,.005),z))
    edges.append((xs1[-1],xs2[-1],zs[-1]))
    vv,ff,uv=[],[],[]
    for j,(x1,x2,z) in enumerate(edges):
        for k in range(9):
            u=k/8;x=x1*(1-u)+x2*u
            vv.append((x,front_surface(x,z,.0035)-.0006*math.sin(u*math.pi),z))
            uv.append((u,j/(len(edges)-1)))
            if k<8 and j<len(edges)-1:
                q=j*9+k;ff.append((q,q+9,q+10,q+1))
    obj=mesh(name,vv,ff,mat,'chest',uv=uv)
    solid=obj.modifiers.new('Woven lapel thickness','SOLIDIFY');solid.thickness=.0018
    return centre

# A solid linen bib follows the torso, with its margins hidden under the outer lapels.
lining_v,lining_f=[],[]
for j in range(25):
    f=j/24;zz=1.405-f*.113;half=.032*(1-f)+.001
    for i in range(9):
        xx=(-half+2*half*i/8)-.008*f
        lining_v.append((xx,front_surface(xx,zz,.003),zz))
        if i<8 and j<24:
            k=j*9+i;lining_f.append((k,k+9,k+10,k+1))
lining=mesh('Solid inner linen overlap',lining_v,lining_f,'linen','chest')
mod=lining.modifiers.new('Inner fabric thickness','SOLIDIFY');mod.thickness=.0013
tailored('Left underlap collar',[-.035,-.065,-.027],[-.021,-.047,-.012],[1.405,1.348,1.285],'robe_light')
outer=tailored('Wide crossing outer lapel',[.020,.061,.016,-.116],[.050,.109,.053,-.080],[1.405,1.338,1.207,1.038],'robe_light')
tube('Crossing lapel seam',outer,.0007,'gold_dark')
# Raised rear collar settles around the neck and joins the front fabric.
collar_v,collar_f=[],[]
for j in range(3):
    zz=1.375+j*.016
    for i in range(33):
        aa=.72+i/32*(math.tau-1.44)
        collar_v.append((math.sin(aa)*(.047-j*.001),-math.cos(aa)*(.043-j*.001),zz))
        if i<32 and j<2:
            k=j*33+i;collar_f.append((k,k+1,k+34,k+33))
collar=mesh('Standing cloth collar',collar_v,collar_f,'robe_light','chest')
mod=collar.modifiers.new('Collar cloth thickness','SOLIDIFY');mod.thickness=.002

# Sleeves are curved, tapered cloth volumes. Hands and fingers are modelled separately.
for side, suffix in [(-1, 'R'), (1, 'L')]:
    shoulder = (side * .167, 0, 1.305)
    elbow = (side * .271, -.006, 1.114)
    wrist = (side * .30, -.037, .946)
    # One continuous cloth envelope spans the shoulder and elbow; smooth skin weights bend it.
    path=[(side*.076,.002,1.294,.046,.060),(side*.127,0,1.310,.052,.064),
          (side*.171,-.002,1.292,.056,.060),(side*.208,-.004,1.246,.050,.056),
          (side*.241,-.006,1.19,.051,.055),(side*.268,-.007,1.123,.049,.050),
          (side*.282,-.017,1.065,.053,.052),(side*.294,-.029,1.002,.045,.046),
          (side*.30,-.037,.947,.037,.036)]
    smooth_path=[]
    for j in range(len(path)-1):
        p0,p1,p2,p3=[np.array(path[k],dtype=float) for k in [max(0,j-1),j,j+1,min(len(path)-1,j+2)]]
        for q in range(3):
            f=q/3
            smooth_path.append(tuple(.5*((2*p1)+(-p0+p2)*f+(2*p0-5*p1+4*p2-p3)*f*f+(-p0+3*p1-3*p2+p3)*f*f*f)))
    path=smooth_path+[path[-1]]
    sleeve_v,sleeve_f,sleeve_uv=[],[],[]
    n=32
    for j,(x,y,z,ru,rv) in enumerate(path):
        center=Vector((x,y,z))
        prev=Vector(path[max(0,j-1)][:3]);nxt=Vector(path[min(len(path)-1,j+1)][:3])
        axis=(nxt-prev).normalized();u=axis.cross(Vector((0,1,0))).normalized();v=axis.cross(u).normalized()
        for i in range(n+1):
            a=i/n*math.tau
            fold=.0022*math.sin(a*5+j*.19)+.0013*math.sin(a*11-j*.34)
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
    if suffix=='R':
        grip_center=Vector((-.307,-.055,.916));handle_axis=Vector((-.17,-.10,-.95)).normalized()
        h_across=Vector((1,0,-.17)).normalized();h_front=handle_axis.cross(h_across).normalized()
        sphere('Gripping palm.R',(-.304,-.031,.917),(.027,.018,.045),'skin','hand.R',segments=28)
        for i in range(4):
            d=-.027+i*.017
            pts=[]
            for degree in [230,185,140,95,52]:
                aa=math.radians(degree)
                pp=grip_center+handle_axis*d+h_across*math.cos(aa)*.018+h_front*math.sin(aa)*.018
                pts.append(tuple(pp))
            tube('Closed sword finger.%d'%i,pts,.0068 if i<3 else .0059,'skin','hand.R',radii=[1,1.05,1,.92,.68])
        tube('Opposing sword thumb',[(-.282,-.035,.943),(-.282,-.060,.936),(-.294,-.075,.927),(-.310,-.072,.928)],.009,'skin','hand.R',radii=[1.1,1,.85,.65])
    else:
        sphere('Relaxed palm.L',(side*.303,-.037,.913),(.027,.019,.044),'skin','hand.L',segments=28)
        for i,length in enumerate([.061,.072,.068,.054]):
            x=side*(.284+i*.013)
            pts=[(x,-.038,.894),(x+.002,-.049,.894-length*.5),(x,-.047,.894-length)]
            tube('Relaxed finger.%d'%i,pts,.0066 if i<3 else .0058,'skin','hand.L',radii=[1.05,.91,.58])
        tube('Relaxed thumb.L',[(.281,-.035,.931),(.272,-.056,.910),(.276,-.065,.892)],.008,'skin','hand.L',radii=[1.2,1,.65])

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
ring_mesh('Neck', [(1.363,.039,.037,0,.004),(1.39,.037,.035,0,.006),(1.445,.032,.031,0,.012),(1.478,.027,.027,0,.019)], 'skin', 'neck', n=40)
FACE_PROFILE = [(1.478, .009, .023), (1.488, .026, .036),
                (1.50, .043, .047), (1.52, .057, .049),
                (1.54, .062, .052), (1.56, .068, .058),
                (1.58, .073, .063), (1.60, .074, .064),
                (1.62, .071, .066), (1.64, .070, .066),
                (1.66, .066, .064), (1.68, .055, .057),
                (1.695, .035, .040), (1.705, .006, .008)]


def face_profile(z):
    """Smooth anatomical sections shared by skin, eyelids and the fitted scalp."""
    z=max(FACE_PROFILE[0][0],min(FACE_PROFILE[-1][0],z))
    for k,(a,b) in enumerate(zip(FACE_PROFILE,FACE_PROFILE[1:])):
        if a[0] <= z <= b[0]:
            t=(z-a[0])/(b[0]-a[0]);p=FACE_PROFILE[max(0,k-1)];q=FACE_PROFILE[min(len(FACE_PROFILE)-1,k+2)]
            result=[]
            for axis in (1,2):
                m1=(b[axis]-p[axis])/(b[0]-p[0])*(b[0]-a[0])
                m2=(q[axis]-a[axis])/(q[0]-a[0])*(b[0]-a[0])
                result.append((2*t**3-3*t*t+1)*a[axis]+(t**3-2*t*t+t)*m1+(-2*t**3+3*t*t)*b[axis]+(t**3-t*t)*m2)
            return tuple(result)
    return FACE_PROFILE[-1][1:]


face_rows=[(float(z),*face_profile(float(z)),0,-.013) for z in np.linspace(1.478,1.705,101)]


def face_shape(x, y, z, a, j):
    front = max(0, math.cos(a)) ** 3
    ridge = .015 * math.exp(-(x / .0105) ** 2 - ((z - 1.589) / .034) ** 4)
    tip = .022 * math.exp(-(x / .0125) ** 2 - ((z - 1.567) / .009) ** 2)
    sockets = .009 * math.exp(-((abs(x) - .031) / .018) ** 2 - ((z - 1.608) / .010) ** 2)
    cheek = .009 * math.exp(-((abs(x) - .045) / .021) ** 2 - ((z - 1.584) / .014) ** 2)
    hollow = .0035 * math.exp(-((abs(x) - .048) / .020) ** 2 - ((z - 1.550) / .017) ** 2)
    muzzle = .005 * math.exp(-(x / .030) ** 2 - ((z - 1.535) / .013) ** 2)
    brow=.0045*math.exp(-((abs(x)-.030)/.021)**2-((z-1.622)/.0065)**2)
    chin=.007*math.exp(-(x/.027)**2-((z-1.503)/.010)**2)
    chin_fold=.002*math.exp(-(x/.024)**2-((z-1.520)/.0045)**2)
    wings=.0065*math.exp(-((abs(x)-.012)/.006)**2-((z-1.560)/.0055)**2)
    nostril_recess=.0030*math.exp(-((abs(x)-.010)/.0033)**2-((z-1.5565)/.0023)**2)
    philtrum=.0014*math.exp(-(x/.004)**2-((z-1.547)/.007)**2)
    y += front * (sockets+hollow+chin_fold+philtrum-ridge-tip-cheek-muzzle-brow-chin-wings+nostril_recess)
    return x, y, z


# Low-contrast facial colour and roughness variation, packed as real textures.
M['skin_face']=material('Skin | subtle complexion', '#b78c70',.65)
n=512
yy,xx=np.mgrid[0:n,0:n].astype(np.float32)
frow=yy/(n-1)*(len(face_rows)-1);lo=np.floor(frow).astype(int);hi=np.minimum(lo+1,len(face_rows)-1);ff=frow-lo
rows=np.array(face_rows);zz=rows[lo,0]*(1-ff)+rows[hi,0]*ff;rr=rows[lo,1]*(1-ff)+rows[hi,1]*ff
aa=xx/(n-1)*math.tau;fx=np.sin(aa)*rr;front=np.maximum(0,np.cos(aa))**4
noise=np.random.default_rng(47).random((n,n),dtype=np.float32)-.5
cheek=np.exp(-((np.abs(fx)-.045)/.025)**2-((zz-1.574)/.022)**2)*front
under_eye=np.exp(-((np.abs(fx)-.031)/.020)**2-((zz-1.592)/.009)**2)*front
nose_warm=np.exp(-(fx/.017)**2-((zz-1.568)/.022)**2)*front
skin=np.ones((n,n,4),dtype=np.float32)
base=np.array([177,137,112],dtype=np.float32)/255
skin[:,:,:3]=base[None,None,:]+noise[:,:,None]*.010
skin[:,:,0]+=.026*cheek+.016*nose_warm
skin[:,:,1]-=.008*cheek+.008*nose_warm+.017*under_eye
skin[:,:,2]-=.010*cheek+.006*nose_warm+.012*under_eye
rough=np.ones((n,n,4),dtype=np.float32)
rough[:,:,:3]=(.59+noise*.04-.05*nose_warm)[:,:,None]
for name,data,space,socket in [('Hanli_skin_complexion',skin,'sRGB','Base Color'),('Hanli_skin_roughness',rough,'Non-Color','Roughness')]:
    im=bpy.data.images.new(name,n,n,alpha=True);im.colorspace_settings.name=space
    im.pixels.foreach_set(np.clip(data,0,1).ravel());im.update();im.file_format='PNG';im.filepath_raw=str(QA/(name+'.png'));im.save();im.pack()
    m=M['skin_face'];tex=m.node_tree.nodes.new('ShaderNodeTexImage');tex.image=im
    m.node_tree.links.new(tex.outputs['Color'],m.node_tree.nodes.get('Principled BSDF').inputs[socket])

mesh_head = ring_mesh('Sculpted face and cranium', face_rows, 'skin_face', 'head', n=160, warp=face_shape)

def skin_front(x,z):
    rx,ry=face_profile(z)
    angle=math.asin(max(-.999,min(.999,x/rx)))
    return face_shape(x,-.013-ry*math.cos(angle),z,angle,0)[1]

M['nostril']=material('Nostril recess', '#49312b',.9)
# Eye whites occupy only the almond-shaped opening; skin lids cover their margins.
for side,suffix in [(-1,'R'),(1,'L')]:
    sphere('Ear.'+suffix,(side*.073,-.002,1.589),(.012,.011,.024),'skin','head',segments=28)
    sphere('Ear concha.'+suffix,(side*.080,-.008,1.59),(.0028,.0035,.014),'skin_shadow','head',segments=20)
    tube('Ear helix.'+suffix,[(side*.076,-.011,1.607),(side*.082,-.009,1.610),(side*.084,-.008,1.59),(side*.078,-.008,1.573)],.0022,'skin','head')
    ex=side*.0305;ez=1.6075
    ev,ef,euv=[],[],[]
    for j in range(9):
        v=-1+j/4
        for i in range(25):
            u=-1+i/12;x=ex+u*.0130
            h=(.0042 if v>=0 else .0033)*math.sqrt(max(0,1-u*u))
            z=ez+side*(x-ex)*.07+v*h
            y=skin_front(x,z)-.0007-.0024*(1-u*u)*(1-v*v)
            ev.append((x,y,z));euv.append((i/24,j/8))
            if i<24 and j<8:
                k=j*25+i;ef.append((k,k+1,k+26,k+25))
    mesh('Recessed almond eye.'+suffix,ev,ef,'eye','head',uv=euv)
    for name,radius,mat,depth in [('Limbal ring',.00465,'iris_rim',.00338),('Iris',.00405,'iris',.00350),('Pupil',.0020,'pupil',.00362)]:
        zv=ez-.00035
        iv=[(ex,skin_front(ex,zv)-depth,zv)];iff=[]
        for i in range(33):
            aa=i/32*math.tau;dx=math.cos(aa)*radius;dz=math.sin(aa)*radius
            x=ex+dx;z=zv+dz
            # Clip the lower circumference into the opening, below the lower lid.
            lower=ez+side*(x-ex)*.07-.0033*math.sqrt(max(0,1-(dx/.013)**2))
            upper=ez+side*(x-ex)*.07+.0042*math.sqrt(max(0,1-(dx/.013)**2))
            z=max(lower+.00015,min(upper-.00015,z))
            y=skin_front(x,z)-depth+.00035*(dx/radius)**2
            iv.append((x,y,z))
            if i<32:iff.append((0,i+1,i+2))
        mesh(name+' shallow surface.'+suffix,iv,iff,mat,'head')
    for upper in [True,False]:
        lv,lf=[],[]
        for j in range(4):
            v=j/3
            for i in range(25):
                u=-1+i/12;x=ex+u*.013
                h=(.0042 if upper else -.0033)*math.sqrt(max(0,1-u*u))
                z=ez+side*(x-ex)*.07+h+(1 if upper else -1)*v*.0033*math.sqrt(max(0,1-u*u))
                y=skin_front(x,z)-.0005-.0011*(1-v)*math.sqrt(max(0,1-u*u))
                lv.append((x,y,z))
                if i<24 and j<3:
                    k=j*25+i;lf.append((k,k+1,k+26,k+25))
        mesh(('Upper' if upper else 'Lower')+' skin lid.'+suffix,lv,lf,'skin','head')
    # A thin, dark lash line sits on the upper edge rather than a thick brown tube.
    lash=[]
    for i in range(17):
        u=-1+i/8;x=ex+u*.0127;z=ez+side*(x-ex)*.07+.00415*math.sqrt(max(0,1-u*u))
        lash.append((x,skin_front(x,z)-.0016,z))
    tube('Upper lash.'+suffix,lash,.00032,'hair','head',radii=[.25]+[1]*15+[.25])
    # Flattened natural brow, with a lower inner end and tapered outer end.
    bl,br=[],[]
    for i in range(17):
        u=i/16;x=side*(.015+u*.029)
        z=1.6215+.0032*math.sin(u*math.pi*.8)-.001*u
        thick=.0016*math.sin(math.pi*(.04+.92*u))
        bl.append((x,skin_front(x,z-thick)-.0009,z-thick))
        br.append((x,skin_front(x,z+thick)-.0009,z+thick))
    strip('Natural brow.'+suffix,bl,br,'hair','head')
    # Small planar dark recess in the integrated nose wing; no external nostril bead.
    vv=[(side*.009,skin_front(side*.009,1.5574)-.0003,1.5574)];ff=[]
    for i in range(17):
        aa=i/16*math.tau;x=side*.009+math.cos(aa)*.0023;z=1.5574+math.sin(aa)*.0009
        vv.append((x,skin_front(x,z)-.00035,z))
        if i<16:ff.append((0,i+1,i+2))
    mesh('Nostril opening.'+suffix,vv,ff,'nostril','head')
# Lip surfaces grow continuously from the skin and meet at a fine mouth line.
for upper in [True,False]:
    vv,ff=[],[]
    for j in range(5):
        v=j/4
        for i in range(33):
            u=-1+i/16;x=u*.021
            seam=1.5350-.0006*(1-u*u)
            if upper:
                edge=.0024*(1-u*u)+.0008*math.exp(-((abs(u)-.3)/.2)**2)
            else:edge=-.0030*(1-u*u)
            z=seam+v*edge
            depth=.0004+.0017*(1-u*u)*math.sin(v*math.pi)
            vv.append((x,skin_front(x,z)-depth,z))
            if i<32 and j<4:
                k=j*33+i;ff.append((k,k+1,k+34,k+33))
    mesh(('Upper' if upper else 'Lower')+' fitted lip',vv,ff,'lips','head')
seam=[]
for i in range(25):
    u=-1+i/12;x=u*.0208;z=1.5350-.0006*(1-u*u)
    seam.append((x,skin_front(x,z)-.00065,z))
tube('Fine mouth seam',seam,.00025,'skin_shadow','head',radii=[.1]+[.7]*23+[.1])

# Fitted hair shell uses the same skull profile, plus a measured clearance.
def skull_profile(z):
    return face_profile(z)

def hair_point(a,f,clear=.003):
    front=max(0,math.cos(a))
    bottom=1.545+front**.8*.109+.005*front*math.sin(a*2)**2
    z=bottom*(1-f)+1.710*f
    rx,ry=skull_profile(min(z,1.704))
    return (math.sin(a)*(rx+clear),-.013-math.cos(a)*(ry+clear),z)
verts,faces,uv=[],[],[]
for j in range(25):
    for i in range(81):
        a=i/80*math.tau;verts.append(hair_point(a,j/24));uv.append((i/80,j/24))
        if i<80 and j<24:
            k=j*81+i;faces.append((k,k+1,k+82,k+81))
cap=mesh('Swept fitted hair shell',verts,faces,'hair','head',uv=uv)
bm=bmesh.new();bm.from_mesh(cap.data);bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=1e-6);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(cap.data);bm.free()
for k in range(42):
    a=(k+.2)/42*math.tau
    pts=[hair_point(a+.11*math.sin(f*math.pi),f,.0038) for f in [j/12 for j in range(13)]]
    tube('Swept fine hair groove %02d'%k,pts,.00020,'hair_light','head',radii=[.3,.7,1,1,1,1,1,1,.8,.5,.3,.2,.05])
knot=sphere('Bound hair knot',(-.002,.027,1.728),(.031,.027,.028),'hair','head',segments=36)
for v in knot.data.vertices:
    az=math.atan2(v.co.y,v.co.x)
    v.co.x*=1+.065*math.sin(az*3+v.co.z*2)
    v.co.z+=.07*math.sin(az*2)*(1-v.co.z*v.co.z)
knot.rotation_euler.y=.14
for k in range(14):
    a=k/14*math.tau
    tube('Knot fine ridge',[(math.cos(a)*.028,.026+math.sin(a)*.026,1.711),(math.cos(a+.6)*.031,.026+math.sin(a+.6)*.029,1.728),(math.cos(a+1.1)*.018,.026+math.sin(a+1.1)*.018,1.752)],.00022,'hair_light','head')
tube('Bronze hair pin',[(-.047,.026,1.729),(.044,.026,1.733)],.0024,'gold','head')
sphere('Hairpin jade bead',(-.049,.026,1.729),(.005,.004,.004),'jade','head',segments=16)
# Broad tapered locks replace cylindrical strands.
def lock(name,centres,widths):
    v,f,uv=[],[],[]
    keys=[np.array((*point,width),dtype=float) for point,width in zip(centres,widths)]
    samples=[]
    for j in range(len(keys)-1):
        p0,p1,p2,p3=[keys[k] for k in [max(0,j-1),j,j+1,min(len(keys)-1,j+2)]]
        for q in range(8):
            t=q/8
            samples.append(.5*((2*p1)+(-p0+p2)*t+(2*p0-5*p1+4*p2-p3)*t*t+(-p0+3*p1-3*p2+p3)*t*t*t))
    samples.append(keys[-1])
    for j,sample in enumerate(samples):
        point=sample[:3];w=max(.0002,sample[3])
        for i in range(9):
            u=i/8;xx=(u-.5)*2*w
            ridge=.0025*math.sin(u*math.pi)+.00020*math.sin(u*math.pi*8)
            v.append((point[0]+xx,point[1]-ridge,point[2]+.001*math.sin(u*math.pi)))
            uv.append((u,j/(len(samples)-1)))
            if i<8 and j<len(samples)-1:
                k=j*9+i;f.append((k,k+9,k+10,k+1))
    o=mesh(name,v,f,'hair','head',uv=uv);mod=o.modifiers.new('Hair lock thickness','SOLIDIFY');mod.thickness=.0011
    return o
for k in range(7):
    off=(k-3)*.011
    lock('Back hair lock.%02d'%k,[(off*.65,.032,1.69),(off,.073,1.58),(off*1.15,.082,1.47),(off+.010,.096,1.354+.018*math.sin(k))],[.001,.011,.010,.0003])
for side in [-1,1]:
    # Side locks are narrow and lie against the temples, with distinct tapered ends.
    lock('Temple lock',[(side*.056,-.043,1.660),(side*.069,-.048,1.615),(side*.069,-.047,1.575),(side*.063,-.043,1.543)],[.0005,.008,.006,.0002])
lock('Swept fringe',[(-.043,-.056,1.681),(-.040,-.078,1.655),(-.020,-.082,1.636),(-.008,-.083,1.622)],[.0005,.010,.006,.0002])
lock('Fine fringe',[(-.036,-.059,1.678),(-.030,-.078,1.652),(-.010,-.082,1.635),(-.003,-.082,1.628)],[.0003,.0022,.0014,.0001])

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
        for vertex in obj.data.vertices: vertex.co.z -= .018
    if bone.startswith(('upper_arm.','forearm.','hand.')):
        side=-1 if bone.endswith('.R') else 1
        for vertex in obj.data.vertices:
            z=vertex.co.z
            if bone.startswith('hand.'):offset=.065
            else:offset=.055*max(0,min(1,(1.305-z)/.191))+.010*max(0,min(1,(1.114-z)/.168))
            vertex.co.x-=side*offset
    def weight_vertex(v):
        z = v.co.z
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
    'revision': 3, 'uv_revision': 2,
    'generator_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
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
