"""Layered, half-tied black hair with closed tapered locks and packed strand maps.

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
    crown = anatomy.get('crown_z', 1.705)
    cy = anatomy.get('center_y', -.013)
    height_offset = crown - 1.705

    M['hair_swept'] = material('Hair | blue-black longitudinal strands', '#13181d', .60)
    M['hair_under'] = material('Hair | soft dark underlayer', '#0e1318', .69)
    M['hair_fine'] = material('Hair | restrained fine strands', '#192129', .61)
    for key in ('hair_swept', 'hair_under', 'hair_fine'):
        bsdf = M[key].node_tree.nodes.get('Principled BSDF')
        bsdf.inputs['Specular IOR Level'].default_value = .18
        bsdf.inputs['Coat Weight'].default_value = 0
        bsdf.inputs['Coat Roughness'].default_value = .6

    # U crosses a lock; V follows its length. Fine lanes stay dark in the colour
    # map and contribute through low-relief normals and varied roughness.
    size = 512
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    phase = xx * math.tau / size
    drift = .085 * np.sin(yy * math.tau / size) + .035 * np.sin(yy * math.tau * 3 / size)
    lanes = (.48 * np.sin(phase * 53 + drift) + .28 * np.sin(phase * 89 - drift * .7)
             + .18 * np.sin(phase * 127 + drift * .3))
    broad = .5 + .5 * np.sin(phase * 7 + .2 * np.sin(yy * math.tau / size))
    normal = np.ones((size, size, 4), dtype=np.float32)
    normal[:, :, 0] = .5 + lanes * .035
    normal[:, :, 1] = .5 + .0015 * np.cos(yy * math.tau / size)
    normal[:, :, 2] = np.sqrt(np.maximum(0, 1 - (normal[:, :, 0] * 2 - 1) ** 2
                                         - (normal[:, :, 1] * 2 - 1) ** 2)) * .5 + .5
    rough = np.ones_like(normal)
    rough[:, :, :3] = (.64 + lanes * .045 + (broad - .5) * .065)[:, :, None]
    colour = np.ones_like(normal)
    for channel, base in enumerate((.052, .064, .080)):
        colour[:, :, channel] = base * (.88 + broad * .18 + lanes * .045)
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
                normal_node.inputs['Strength'].default_value = .52 if key == 'hair_swept' else .25
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
        front = max(0, math.cos(angle)); back = max(0, -math.cos(angle))
        bottom = 1.559 + .104 * front ** 1.2 - .017 * back
        # The asymmetric hairline is scalloped into the part and temples;
        # it does not form one smooth, horizontal helmet edge.
        bottom += (.0013 * math.sin(angle * 17) + .0006 * math.sin(angle * 31)
                   + .004 * front**3 * math.sin(angle * 2 + .45) + height_offset)
        fraction = max(0, min(1, fraction))
        skin_z = bottom + (crown - bottom) * fraction
        support_z=min(crown - .0001, skin_z)
        skin_rx, skin_ry = profile(support_z)
        lift = (.003 + .004 * math.sin(fraction * math.pi)) * (1 - fraction) ** .35
        rx = max(0, skin_rx) + clearance + lift
        ry = max(0, skin_ry) + clearance + lift
        z = skin_z + .006 * math.sin(fraction * math.pi / 2) ** 2
        y=cy-math.cos(angle)*ry
        if math.cos(angle)>0:
            y=face_surface(math.sin(angle)*skin_rx,support_z)-math.cos(angle)*(clearance+lift)
        return Vector((math.sin(angle) * rx,y,z))

    # A thin closed underlayer prevents see-through gaps between individual locks.
    columns, rows = 72, 16
    vertices, faces, uv = [], [], []
    for inside in (False, True):
        for row in range(rows):
            fraction = row / rows
            for col in range(columns + 1):
                angle = col / columns * math.tau
                p = scalp(angle, fraction, .0012 if inside else .0026)
                if inside:
                    p.z -= .0008
                vertices.append(tuple(p)); uv.append((col / columns, fraction))
    layer_size = rows * (columns + 1)
    for layer in range(2):
        for row in range(rows - 1):
            for col in range(columns):
                k = layer * layer_size + row * (columns + 1) + col
                face = (k, k + 1, k + columns + 2, k + columns + 1)
                faces.append(face if layer == 0 else tuple(reversed(face)))
        apex = len(vertices)
        vertices.append((0, cy, crown + .006 - layer * .001)); uv.append((.5, 1))
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
            if normal == 'scalp':
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

    def roof(x,y,lift=.015):
        hit,normal_hit,_,_=scalp_bvh.ray_cast(Vector((x,y,crown+.15)),Vector((0,0,-1)))
        if hit is not None:return hit+normal_hit*max(.0008,lift*.10)
        return scalp(math.atan2(x,cy-y),.65,.004)

    # Crown sections cross the dome, from a scalloped hairline to the low tie.
    # Covering the summit avoids a smooth exposed "helmet" between side locks.
    for index in range(64):
        x=(index-31.5)*.00195+.00022*math.sin(index*2.1)
        angle=math.asin(max(-.94,min(.94,x/.075)))
        root=scalp(angle,.015,.0017)
        wander=.0024*math.sin(index*.73)
        path=[root,roof(x+.003+wander,-.052,.010),roof(x+.006-wander,-.026,.015),
              roof(x+.005+wander,.006,.016),roof(x*.94,.035,.015),
              roof(x*.76,.058,.010),scalp(math.pi-x*.9,.44,.004)]
        width=.00175+.00038*math.sin(index*.7)
        lock('Hair | flowing crown section %02d'%index,path,
             [.00055,width,width*.99,width*.94,width*.91,width*.75,.00010],depth=.08,
             sides=6,steps=3)
        for offset in ((.19,) if index%4==0 else ()):
            fine=[p+Vector((offset*width,0,.00075)) for p in path]
            lock('Hair | crown fine strand %02d %.2f'%(index,offset),fine,
                 [.00004,.00018,.00021,.00020,.00019,.00016,.000035],depth=.45,
                 mat='hair_fine',sides=4,steps=3)
    # Short tapered locks feather the boundary against the forehead instead of
    # relying on the opaque undercap's single edge. They remain closed meshes.
    for index in range(24):
        angle=-1.31+index/23*2.62
        root=scalp(angle,.18,.0021)
        mid=scalp(angle+.025*math.sin(index),.055,.0022)
        tip=scalp(angle,.005,.0015)
        tip.z-=.0018+.0015*(.5+.5*math.sin(index*1.7))
        lock('Hair | feathered hairline %02d'%index,[root,mid,tip],
             [.0013,.0010,.000035],depth=.10,sides=5,steps=3)
    for side in (-1,1):
        for index in range(6):
            path=[scalp(side*(.94+index*.13),.02,.0022),
                  scalp(side*(1.12+index*.12),.30,.005),
                  scalp(side*(1.64+index*.09),.52,.005),
                  scalp(side*(2.32+index*.08),.48,.0045),
                  scalp(side*2.96,.29+index*.018,.004)]
            lock('Hair | low swept side section %s %02d'%(side,index),path,
                 [.001,.007,.0075,.006,.00015],depth=.11,sides=8,steps=4)

    # Main offset wave rises from the hairline and falls outside the eye socket.
    def point(x,y,z):
        return (x,y,z+height_offset)
    wave=[scalp(.62,.50,.004),point(.008,-.073,1.692),point(-.024,-.081,1.677),
          point(-.047,-.080,1.646),point(-.064,-.061,1.598),
          point(-.070,-.046,1.547),point(-.060,-.053,1.491)]
    lock('Hair | asymmetric S-shaped forelock',wave,[.0003,.0044,.0052,.0045,.0034,.0018,.00010],
         depth=.10,normal='front',sides=10,steps=5)
    for index in range(5):
        path=[Vector(p)+Vector((-.00135*(index+1),-.0006-index*.0003,-.0007*index)) for p in wave]
        path[0]=Vector(wave[0])
        path[-1].x-=.005*index;path[-1].z-=.006*index
        lock('Hair | separated fringe wisp %02d'%index,path,
             [.0002,.0010,.00115,.00085,.0006,.00035,.000035],depth=.14,normal='front',sides=6,steps=4)
    small_wave=[scalp(.65,.45,.004),point(.054,-.069,1.666),point(.070,-.054,1.625),
                point(.077,-.037,1.574),point(.073,-.040,1.527),point(.065,-.052,1.484)]
    lock('Hair | narrow opposite temple wave',small_wave,[.0003,.0045,.0045,.0035,.002,.0001],
         depth=.12,normal='front',sides=10,steps=5)

    # Loose under-hair broadens down the back, with staggered natural tips.
    back_paths=[]
    for index in range(13):
        x=(index-6)*.0118
        root_angle=math.pi - x/.078
        origin=scalp(root_angle,.43,.0025)
        end=1.045+.085*(abs(index-6)/6)**1.25+.035*math.sin(index*1.3)
        bend=.009*math.sin(index*.71)
        path=[origin,point(x*.93,.087,1.565),point(x*1.16+bend*.5,.107,1.470),
              point(x*1.24+bend,.120+.003*math.sin(index),1.355),
              point(x*1.18+.010+bend*.8,.136,1.235),point(x*1.04+.019+bend*.4,.152,end)]
        back_paths.append(path)
        lock('Hair | flowing back layer %02d'%index,path,
             [.003,.013,.017,.016,.011,.00010],depth=.045,normal='back',skin_mode='hair_back',
             sides=10,steps=5)
    # Raised secondary groups break up a uniform curtain without separate materials.
    for index in range(25):
        source=back_paths[min(12,round(index/24*12))]
        path=[Vector(p)+Vector((.0025*math.sin(index*.9+j*.58),
                               .0011+.0003*(index%3),.001*math.sin(j+index)))
              for j,p in enumerate(source)]
        path[-1].z+=.012+.021*(index%3);path[-1].x+=.005*math.sin(index)
        lock('Hair | back tapered strand group %02d'%index,path,
             [.0003,.0018,.0026,.0024,.0018,.00005],depth=.075,normal='back',
             skin_mode='hair_back',sides=6,steps=4)
        if index%4==0:
            path=[p+Vector((.001,.0014,0)) for p in path]
            lock('Hair | fine back filament %02d'%index,path,
                 [.00005,.00028,.00032,.00030,.00023,.00004],depth=.55,mat='hair_fine',
                 normal='back',skin_mode='hair_back',sides=4,steps=3)

    # Narrow locks pass beside the neck and rest in front of the high collar.
    for side in (-1,1):
        path=[scalp(side*1.71,.28,.002),point(side*.079,.012,1.548),
              point(side*.088,-.030,1.468),point(side*.096,-.092,1.398),
              point(side*.105,-.131,1.323),point(side*.114,-.132,1.244)]
        lock('Hair | long temple lock %s'%side,path,[.0015,.0045,.005,.0044,.003,.00010],
             depth=.13,normal='front',skin_mode='hair_front',sides=10,steps=5)
        thin=[Vector(p)+Vector((side*.003,-.002,0)) for p in path]
        thin[-1].x+=side*.005;thin[-1].z+=.035
        lock('Hair | loose temple fine lock %s'%side,thin,[.0004,.0018,.0020,.0017,.001,.00005],
             depth=.25,normal='front',skin_mode='hair_front',sides=6,steps=4)
        stray=[Vector(p)+Vector((-side*.002,-.0014,0)) for p in path]
        stray[-2].x-=side*.005;stray[-1].x-=side*.009;stray[-1].z+=.064
        lock('Hair | inner temple stray %s'%side,stray,
             [.0002,.0008,.0010,.0008,.00055,.000035],depth=.16,
             normal='front',skin_mode='hair_front',sides=5,steps=4)

    # The tie is a shallow gathered fold at the rear, not a spherical topknot.
    for index in range(4):
        z=1.625+index*.004
        path=[point(-.033,.071,z+.004),point(-.020,.089,z+.001),
              point(0,.096,z),point(.020,.089,z+.001),point(.033,.071,z+.004)]
        lock('Hair | low gathered tie %02d'%index,path,[.0005,.003,.0033,.003,.0005],
             depth=.5,normal='back',sides=6,steps=3)
    tube('Hair | slender antique hairpin',[point(-.071,.066,1.655),point(.065,.079,1.661)],
         .00145,'gold','head',radii=[.55,1])
    sphere('Hair | small hairpin end',point(.067,.079,1.661),(.0030,.0024,.0024),
           'gold_dark','head',segments=12,rings=8)

    created=parts[start:]
    tris=sum(sum(len(poly.vertices)-2 for poly in obj.data.polygons)
             for obj in created if obj.type=='MESH')
    assert tris<50000, ('Hair triangle budget exceeded',tris)
    return {'objects':len(created),'mesh_triangles':tris,'materials':3,
            'style':'asymmetric half-tied long hair, low occipital tie, no topknot',
            'coordinates':'unshifted face space; head offset is applied by the main pipeline',
            'long_hair_modes':['hair_back','hair_front'],'textures':[im.name for im in images]}
