"""Side-parted half-tied hair with sculpted flow masses and feathered alpha cards.

Geometry uses the face module's unshifted coordinates; the main pipeline applies
the shared head offset and blends long locks into the upper-body rig.
"""
import math
import struct
import zlib
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree


def build_hair(ctx, anatomy):
    get = ctx.__getitem__ if isinstance(ctx, dict) else lambda key: getattr(ctx, key)
    M, material, mesh = get('M'), get('material'), get('mesh')
    tube, sphere, parts = get('tube'), get('sphere'), get('PARTS')
    qa = Path(get('QA'))
    start = len(parts)
    profile = anatomy['profile']
    face_surface = anatomy['surface']
    skull_bvh = anatomy.get('scalp_bvh') or anatomy.get('head_bvh')
    crown = anatomy.get('crown_z', 1.705)
    cy = anatomy.get('center_y', -.013)
    height_offset = crown - 1.705

    M['hair_swept'] = material('Hair | soft black-brown silk bundles', '#151719', .42)
    M['hair_under'] = material('Hair | close dark underlayer', '#101214', .50)
    M['hair_fine'] = material('Hair | fine black-brown flyaways', '#1b1c20', .48)
    for key in ('hair_swept', 'hair_under', 'hair_fine'):
        bsdf = M[key].node_tree.nodes.get('Principled BSDF')
        bsdf.inputs['Specular IOR Level'].default_value = .16
        bsdf.inputs['Coat Weight'].default_value = 0
        bsdf.inputs['Coat Roughness'].default_value = .6
        if 'Anisotropic' in bsdf.inputs:
            bsdf.inputs['Anisotropic'].default_value = .72
            bsdf.inputs['Anisotropic Rotation'].default_value = .25

    # U crosses a lock; V follows its length. Fine lanes stay dark in the colour
    # map and contribute through low-relief normals and varied roughness.
    size = 1024
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    phase = xx * math.tau / size
    drift = .085 * np.sin(yy * math.tau / size) + .035 * np.sin(yy * math.tau * 3 / size)
    lanes = (.48 * np.sin(phase * 137 + drift) + .28 * np.sin(phase * 211 - drift * .7)
             + .18 * np.sin(phase * 307 + drift * .3))
    broad = .5 + .5 * np.sin(phase * 7 + .2 * np.sin(yy * math.tau / size))
    normal = np.ones((size, size, 4), dtype=np.float32)
    normal[:, :, 0] = .5 + lanes * .012
    normal[:, :, 1] = .5 + .0015 * np.cos(yy * math.tau / size)
    normal[:, :, 2] = np.sqrt(np.maximum(0, 1 - (normal[:, :, 0] * 2 - 1) ** 2
                                         - (normal[:, :, 1] * 2 - 1) ** 2)) * .5 + .5
    rough = np.ones_like(normal)
    rough[:, :, :3] = (.52 + lanes * .035 + (broad - .5) * .050)[:, :, None]
    colour = np.ones_like(normal)
    for channel, base in enumerate((.068, .073, .083)):
        colour[:, :, channel] = base * (.90 + broad * .20 + lanes * .18)
    images = []
    for name, values, space in [('Hanli_hair_strand_colour', colour, 'sRGB'),
                                 ('Hanli_hair_strand_normal', normal, 'Non-Color'),
                                 ('Hanli_hair_strand_roughness', rough, 'Non-Color')]:
        # These arrays are already encoded sRGB (colour) or linear data (others).
        # Write literal 8-bit PNG samples, then reload, avoiding Generated-image
        # colour conversion differences between the source scene and GLB.
        pixels=np.clip(values*255+.5,0,255).astype(np.uint8)
        def chunk(kind,data):
            return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
        raw=b''.join(b'\0'+row.tobytes() for row in pixels)
        png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',size,size,8,6,0,0,0))
        png+=chunk(b'IDAT',zlib.compress(raw,6))+chunk(b'IEND',b'')
        image_path=qa/(name+'.png');image_path.write_bytes(png)
        image=bpy.data.images.load(str(image_path),check_existing=False);image.name=name
        image.colorspace_settings.name=space;image.pack();images.append(image)
    for key in ('hair_swept', 'hair_under'):
        mat = M[key]; nodes = mat.node_tree.nodes; links = mat.node_tree.links
        bsdf = nodes.get('Principled BSDF')
        for index, image in enumerate(images):
            tex = nodes.new('ShaderNodeTexImage'); tex.image = image
            tex.extension = 'REPEAT'
            if index == 0:
                links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
            elif index == 1:
                normal_node = nodes.new('ShaderNodeNormalMap')
                normal_node.inputs['Strength'].default_value = .16 if key == 'hair_swept' else .20
                links.new(tex.outputs['Color'], normal_node.inputs['Color'])
                links.new(normal_node.outputs['Normal'], bsdf.inputs['Normal'])
            else:
                links.new(tex.outputs['Color'], bsdf.inputs['Roughness'])

    def finish(obj):
        bm = bmesh.new(); bm.from_mesh(obj.data)
        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1e-7)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.to_mesh(obj.data); bm.free()
        obj.data.update()
        layer=obj.data.uv_layers.active
        if layer:
            for face in obj.data.polygons:
                loops=list(face.loop_indices)
                values=[layer.data[loop].uv.copy() for loop in loops]
                area=sum(a.x*b.y-b.x*a.y for a,b in zip(values,values[1:]+values[:1]))
                if abs(area)<1e-12 and face.area>1e-12:
                    u=face.normal.orthogonal().normalized();v=face.normal.cross(u).normalized()
                    for loop in loops:
                        p=obj.data.vertices[obj.data.loops[loop].vertex_index].co
                        layer.data[loop].uv=(p.dot(u)/.05,p.dot(v)/.05)
        for face in obj.data.polygons:
            face.use_smooth = True
        return obj

    def scalp(angle, fraction, clearance=.003):
        front = max(0, math.cos(angle))
        # The side hairline climbs over the ear. A low, level cap edge makes a
        # rectangular black sideburn across the cheek on an anatomical head.
        a = abs((angle + math.pi) % math.tau - math.pi)
        line = [(0,1.663),(.50,1.657),(.95,1.638),(1.35,1.629),
                (1.65,1.623),(1.95,1.600),(2.35,1.565),(math.pi,1.543)]
        bottom = line[-1][1]
        for left,right in zip(line,line[1:]):
            if left[0] <= a <= right[0]:
                t=(a-left[0])/(right[0]-left[0]);t=t*t*(3-2*t)
                bottom=left[1]*(1-t)+right[1]*t
                break
        bottom += .0025*math.sin(angle+.30)*front**2 + .0005*math.sin(angle*11+.4) + height_offset
        fraction = max(0, min(1, fraction))
        skin_z = bottom + (crown - bottom) * fraction
        support_z = min(crown - .0001, skin_z)
        skin_rx, skin_ry = profile(support_z)
        puff = (.0035 + .008 * math.sin(fraction * math.pi))
        puff *= 1 + .38 * max(0, -math.sin(angle)) * front
        puff *= (1 - fraction) ** .36
        puff += .0010 * math.sin(angle*11 + fraction*2) * math.sin(math.pi*fraction) ** 1.5
        rx = max(0, skin_rx) + clearance + puff
        ry = max(0, skin_ry) + clearance + puff
        z = skin_z + .011 * math.sin(fraction * math.pi / 2) ** 2
        y = cy - math.cos(angle) * ry
        if math.cos(angle) > 0:
            y = face_surface(math.sin(angle)*skin_rx, support_z) - math.cos(angle)*(clearance+puff)
        x = math.sin(angle) * rx + .003 * fraction**2
        if skull_bvh is not None and support_z >= 1.638:
            radial = Vector((math.sin(angle), -math.cos(angle), 0))
            origin = Vector((0, cy, support_z)) + radial * .35
            hit, normal_hit, _, _ = skull_bvh.ray_cast(origin, -radial, .70)
            expected_radius = math.sqrt((math.sin(angle)*skin_rx)**2 + (math.cos(angle)*skin_ry)**2)
            valid_hit = (hit is not None and normal_hit.dot(radial) > .22
                         and (hit-Vector((0,cy,support_z))).dot(radial) > max(.006, expected_radius*.60))
            if valid_hit:
                p = hit + normal_hit * (clearance + puff)
                p.z += .011 * math.sin(fraction*math.pi/2)**2
                return p
        return Vector((x, y, z))

    # A thin closed underlayer prevents see-through gaps between individual locks.
    columns, rows = 72, 16
    vertices, faces, uv = [], [], []
    for inside in (False, True):
        for row in range(rows):
            fraction = .075 + row / rows * .925
            for col in range(columns + 1):
                angle = col / columns * math.tau
                p = scalp(angle, fraction, .0012 if inside else .0026)
                if inside:
                    p.z -= .0008
                vertices.append(tuple(p)); uv.append((fraction + .14*math.sin(angle), col / columns))
    layer_size = rows * (columns + 1)
    for layer in range(2):
        for row in range(rows - 1):
            for col in range(columns):
                k = layer * layer_size + row * (columns + 1) + col
                face = (k, k + 1, k + columns + 2, k + columns + 1)
                faces.append(face if layer == 0 else tuple(reversed(face)))
        apex = len(vertices)
        vertices.append((.003, cy, crown + .011 - layer * .001)); uv.append((.5, 1))
        for col in range(columns):
            k = layer * layer_size + (rows - 1) * (columns + 1) + col
            face = (k, k + 1, apex)
            faces.append(face if layer == 0 else tuple(reversed(face)))
    for col in range(columns):
        faces.append((col, layer_size + col, layer_size + col + 1, col + 1))
    scalp_bvh=BVHTree.FromPolygons(vertices,faces[:rows*columns],all_triangles=False)
    finish(mesh('Hair | close scalp underlayer', vertices, faces, 'hair_under', 'head', uv=uv))

    def catmull(a, b, c, d, t):
        return .5 * ((2 * b) + (-a + c) * t + (2*a - 5*b + 4*c - d) * t*t
                     + (-a + 3*b - 3*c + d) * t*t*t)

    def lock(name, points, widths, depth=.18, mat='hair_swept', skin_mode='rigid',
             normal='scalp', sides=8, steps=4):
        points = [Vector(p) for p in points]
        keys = [Vector((*p, w)) for p, w in zip(points, widths)]
        samples = []
        for index in range(len(keys) - 1):
            for j in range(steps):
                samples.append(catmull(keys[max(0,index-1)], keys[index], keys[index+1],
                                       keys[min(len(keys)-1,index+2)], j/steps))
        samples.append(keys[-1])
        positions = [Vector(p[:3]) for p in samples]
        if normal=='scalp':
            for index,center in enumerate(positions):
                point,normal_hit,_,_=scalp_bvh.find_nearest(center)
                if point is not None:
                    positions[index]=point+normal_hit*(.0008+max(.000035,samples[index][3])*depth*.8)
        distances = [0.]
        for index in range(1, len(samples)):
            distances.append(distances[-1] + (positions[index] - positions[index-1]).length)
        v, f, texcoords, frames = [], [], [], []
        for index, sample in enumerate(samples):
            center = positions[index]
            tangent = (positions[min(index+1,len(samples)-1)] - positions[max(0,index-1)]).normalized()
            if normal in ('scalp', 'volume'):
                hint = Vector((center.x/.08, (center.y-cy)/.09, (center.z-(1.602+height_offset))/.105))
            else:
                hint = Vector((0, -1 if normal == 'front' else 1, .025))
            outward = hint - tangent * hint.dot(tangent)
            if outward.length < .001:
                outward = tangent.orthogonal()
            outward.normalize()
            across = tangent.cross(outward).normalized()
            outward = across.cross(tangent).normalized()
            width = max(.000035, sample[3])
            thickness = max(.000025, width * depth)
            frames.append((across, outward, width, thickness))
            for side in range(sides + 1):
                angle = side / sides * math.tau
                # Lenticular sections keep volume without cylindrical rope forms.
                p = center + across * (math.cos(angle)*width) + outward * (math.sin(angle)*thickness)
                v.append(tuple(p)); texcoords.append((side/sides, distances[index]/max(.001,distances[-1])))
                if index < len(samples)-1 and side < sides:
                    k=index*(sides+1)+side; f.append((k,k+1,k+sides+2,k+sides+1))
        caps = []
        for index in (0, len(samples)-1):
            center_index=len(v);v.append(tuple(positions[index]));texcoords.append((.5,.5))
            for side in range(sides):
                a=index*(sides+1)+side;b=a+1
                face=(center_index,b,a) if index==0 else (center_index,a,b)
                caps.append((len(f),index));f.append(face)
        obj=mesh(name,v,f,mat,'head',skin_mode=skin_mode,uv=texcoords)
        layer=obj.data.uv_layers.active
        for polygon_index,index in caps:
            across,outward,width,thickness=frames[index]
            for loop in obj.data.polygons[polygon_index].loop_indices:
                p=obj.data.vertices[obj.data.loops[loop].vertex_index].co-positions[index]
                layer.data[loop].uv=(.5+p.dot(across)/(2*width),.5+p.dot(outward)/(2*thickness))
        return finish(obj)

    # One packed mask is shared by all feather cards. Individual strands have
    # different roots, drift and tip lengths; no opaque rectangular silhouette.
    size = 1024
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    u, v = xx / (size-1), yy / (size-1)
    alpha = np.zeros_like(u)
    rng = np.random.default_rng(607)
    for index in range(88):
        center = (.04 + index / 87 * .92) + rng.uniform(-.004, .004)
        drift = rng.uniform(-.008, .008) * np.sin(v * math.pi * rng.uniform(.7, 1.5))
        finish_v = rng.uniform(.72, 1.04)
        start_v = rng.uniform(-.04, .075)
        width = rng.uniform(.00065, .00145)
        strand = np.exp(-((u-center-drift)/width)**2)
        root_fade = np.clip((v-start_v)/.06, 0, 1)
        tip_fade = np.clip((finish_v-v)/.095, 0, 1)
        alpha = np.maximum(alpha, strand * root_fade * tip_fade * rng.uniform(.70, 1.0))
    rgba = np.empty((size, size, 4), dtype=np.float32)
    rgba[:, :, :3] = (.067, .072, .080)
    rgba[:, :, :3] *= (1 + .07*np.sin(xx*.063))[:, :, None]
    rgba[:, :, 3] = np.clip(alpha * 1.55, 0, 1)
    pixels = np.clip(rgba*255+.5, 0, 255).astype(np.uint8)
    def chunk(kind, data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    raw = b''.join(b'\0'+row.tobytes() for row in pixels[::-1])
    data = b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',size,size,8,6,0,0,0))
    data += chunk(b'IDAT', zlib.compress(raw,6)) + chunk(b'IEND',b'')
    mask_path = qa/'Hanli_hair_feather_rgba.png'; mask_path.write_bytes(data)
    mask = bpy.data.images.load(str(mask_path),check_existing=False)
    mask.name='Hanli_hair_feather_rgba';mask.colorspace_settings.name='sRGB';mask.pack()
    images.append(mask)
    M['hair_feather'] = material('Hair | feathered fine strand cards', '#17191c', .46)
    cardmat=M['hair_feather'];cardmat.use_backface_culling=False
    cardmat.blend_method='CLIP';cardmat.alpha_threshold=.32
    bsdf=cardmat.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Specular IOR Level'].default_value=.13
    bsdf.inputs['Anisotropic'].default_value=.70
    bsdf.inputs['Anisotropic Rotation'].default_value=.25
    tex=cardmat.node_tree.nodes.new('ShaderNodeTexImage');tex.image=mask;tex.extension='CLIP'
    cardmat.node_tree.links.new(tex.outputs['Color'],bsdf.inputs['Base Color'])
    clip=cardmat.node_tree.nodes.new('ShaderNodeMath');clip.operation='GREATER_THAN';clip.inputs[1].default_value=.32
    cardmat.node_tree.links.new(tex.outputs['Alpha'],clip.inputs[0])
    cardmat.node_tree.links.new(clip.outputs[0],bsdf.inputs['Alpha'])

    def card(name, points, widths, normal='front', skin_mode='rigid', steps=5):
        keys=[Vector((*Vector(p),w)) for p,w in zip(points,widths)]
        samples=[]
        for i in range(len(keys)-1):
            for j in range(steps):
                samples.append(catmull(keys[max(0,i-1)],keys[i],keys[i+1],keys[min(len(keys)-1,i+2)],j/steps))
        samples.append(keys[-1])
        positions=[Vector(p[:3]) for p in samples]
        vv,ff,uv=[],[],[]
        for i, row in enumerate(samples):
            center=positions[i]
            tangent=(positions[min(i+1,len(positions)-1)]-positions[max(0,i-1)]).normalized()
            hint=Vector((center.x/.08,(center.y-cy)/.09,(center.z-1.60)/.11)) if normal=='volume' else Vector((0,-1 if normal=='front' else 1,0))
            outward=hint-tangent*hint.dot(tangent)
            if outward.length<.001:outward=tangent.orthogonal()
            outward.normalize(); across=tangent.cross(outward).normalized()
            for j in range(5):
                f=j/4; signed=f*2-1
                p=center+across*(max(.0001,row[3])*signed)+outward*(.0006*(1-signed*signed))
                vv.append(tuple(p));uv.append((f,i/(len(samples)-1)))
                if i<len(samples)-1 and j<4:
                    k=i*5+j;ff.append((k,k+1,k+6,k+5))
        obj=mesh(name,vv,ff,'hair_feather','head',skin_mode=skin_mode,uv=uv)
        # Single-sided sheets deliberately keep their authored outward normals;
        # backfaces are visible through glTF doubleSided.
        for p in obj.data.polygons:p.use_smooth=True
        return obj

    def point(x,y,z):
        return Vector((x,y,z+height_offset))

    # The crown is one continuous surface with shallow flow undulations.
    # Separate opaque strips here produced hard, armor-like steps in three-quarter
    # lighting; their strand detail belongs in the normal/roughness maps instead.

    # Fine roots soften the cap edge with actual transparent strand silhouettes.
    for index in range(38):
        angle=-1.42+index/37*2.84
        root=scalp(angle,.20,.003)
        mid=scalp(angle-.028,.055,.0032)
        tip=scalp(angle-.046,.0,.0027)
        tip.z-=.003+(.5+.5*math.sin(index*1.7))*.004
        card('Hair | individual feathered hairline %02d'%index,[root,mid,tip],
             [.0032,.0048,.0026],normal='volume',steps=4)

    # A wide, flat S-wave hangs from the side part. Its large section changes the
    # forehead silhouette, while the alpha-card edge splits into fine strands.
    wave=[scalp(.66,.43,.004),point(.025,-.066,1.687),point(-.004,-.086,1.665),
          point(-.030,-.094,1.642),point(-.052,-.080,1.610),
          point(-.061,-.066,1.563),point(-.056,-.060,1.512)]
    # The anatomical head is deeper than the old analytic face. Keep the hero
    # fringe in front of the actual face AND hair-cap surface, instead of burying
    # its old absolute Y coordinates in the forehead after a head replacement.
    for index, (p, width) in enumerate(zip(wave, [.001,.010,.015,.014,.010,.005,.00012])):
        front_y = face_surface(p.x, min(crown-.0001, p.z))
        cap_hit, _, _, _ = scalp_bvh.ray_cast(Vector((p.x, -.45, p.z)), Vector((0,1,0)), .8)
        if cap_hit is not None:
            front_y = min(front_y, cap_hit.y)
        p.y = min(p.y, front_y - .0025 - width*.12)
        wave[index] = p
    lock('Hair | broad asymmetric S forelock',wave,
         [.001,.010,.015,.014,.010,.005,.00012],depth=.11,normal='front',sides=10,steps=6)
    card('Hair | feathered S forelock edge',[p+Vector((-.002,-.0015,0)) for p in wave],
         [.002,.013,.018,.017,.014,.008,.002],steps=6)
    for index in range(3):
        path=[p+Vector((-.0017*(index+1),-.002-index*.0005,-.001*index)) for p in wave]
        path[-1].x-=.005*(index+1);path[-1].z-=.009*(index+1)
        card('Hair | separate long fringe wisp %02d'%index,path,
             [.0006,.0020,.0030,.0026,.0022,.0016,.0002],steps=5)
    opposite=[scalp(.89,.30,.004),point(.067,-.058,1.649),point(.078,-.044,1.608),
              point(.078,-.036,1.559),point(.067,-.047,1.520)]
    card('Hair | wispy ear-side edge',[p+Vector((.0015,-.0013,0)) for p in opposite],
         [.001,.007,.007,.006,.001],steps=5)

    # Separated long rear groups grow from the low half-tie, not a straight sheet.
    back_paths=[]
    for index in range(15):
        x=(index-7)*.0105
        root_angle=math.pi-x/.08
        radial=Vector((math.sin(root_angle),-math.cos(root_angle),0))
        origin=scalp(root_angle,.54,.001)-radial*.016
        nape=scalp(root_angle,.075,.001)-radial*.012
        end=1.035+.105*(abs(index-7)/7)**1.3+.025*math.sin(index*1.5)
        sway=.012*math.sin(index*.68)
        path=[origin,nape,point(x*1.12+sway*.4,.111,1.483),
              point(x*1.35+sway,.139+.005*math.sin(index),1.365),
              point(x*1.37+sway*.8+.010,.157,1.225),point(x*1.18+.029+sway*.7,.178,end)]
        back_paths.append(path)
        lock('Hair | tapered loose back mass %02d'%index,path,
             [.004,.010,.014,.015,.011,.00012],depth=.055,
             normal='back',skin_mode='hair_back',sides=8,steps=5)
        card('Hair | feathered long back layer %02d'%index,
             [p+Vector((.001*math.sin(index),.0013,0)) for p in path],
             [.004,.011,.017,.018,.014,.003],normal='back',skin_mode='hair_back',steps=6)
    for index in (0,3,6,9,12,14):
        source=back_paths[index]
        stray=[p+Vector(((-.006 if index<7 else .006)*(j/5),.002,-.004*j)) for j,p in enumerate(source)]
        card('Hair | back silhouette loose wisp %02d'%index,stray,
             [.0008,.0025,.004,.0045,.004,.0007],normal='back',skin_mode='hair_back',steps=5)

    # Shoulder locks are broad, curved, asymmetric and split into fine ends.
    # The path stays forward of the neck and garment throughout the rest pose.
    for side in (-1,1):
        length_shift=.027 if side>0 else 0
        path=[scalp(side*1.65,.26,.004),point(side*.081,.005,1.553),
              point(side*.087,-.035,1.477),point(side*.099,-.102,1.405),
              point(side*.117,-.137,1.323),point(side*.126,-.146,1.237+length_shift)]
        lock('Hair | broad flowing shoulder lock %s'%side,path,
             [.001,.014,.018,.017,.012,.00012],depth=.10,
             normal='front',skin_mode='hair_front',sides=8,steps=6)
        card('Hair | transparent shoulder lock edges %s'%side,
             [p+Vector((side*.0015,-.0012,0)) for p in path],
             [.002,.016,.020,.021,.017,.004],skin_mode='hair_front',steps=6)
        for index in range(2):
            stray=[p+Vector((side*(.003+index*.002),-.002-index*.0007,-.002*j)) for j,p in enumerate(path)]
            stray[-1].x+=side*(.007+index*.006);stray[-1].z+=.022*(index+1)
            card('Hair | fine shoulder tail %s %s'%(side,index),stray,
                 [.0004,.002,.0026,.0025,.002,.0006],skin_mode='hair_front',steps=5)

    # Shallow gathered half-tie follows the occipital curve. Antique pin is kept.
    for index in range(4):
        z=1.625+index*.0035
        path=[point(-.033,.049,z+.004),point(-.020,.059,z+.001),
              point(0,.064,z),point(.020,.059,z+.001),point(.033,.049,z+.004)]
        lock('Hair | low gathered tie %02d'%index,path,[.0005,.003,.0033,.003,.0005],
             depth=.4,normal='back',sides=6,steps=3)
    tube('Hair | slender antique hairpin',[point(-.074,.038,1.658),point(.068,.050,1.664)],
         .00145,'gold','head',radii=[.55,1])
    sphere('Hair | small hairpin end',point(.070,.050,1.664),(.0030,.0024,.0024),
           'gold_dark','head',segments=12,rings=8)

    created=parts[start:]
    tris=sum(sum(len(poly.vertices)-2 for poly in obj.data.polygons)
             for obj in created if obj.type=='MESH')
    assert tris<50000, ('Hair triangle budget exceeded',tris)
    return {'objects':len(created),'mesh_triangles':tris,'materials':len({m.name for ob in created for m in ob.data.materials}),
            'style':'sculpted side part, broad S forelock, feathered alpha cards, low half-tie',
            'coordinates':'unshifted face space; head offset is applied by the main pipeline',
            'long_hair_modes':['hair_back','hair_front'],'textures':[im.name for im in images]}
