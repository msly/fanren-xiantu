"""Reference-directed young Han Li head; imported by build_hanli.py.

All dimensions are metres in Blender's -Y-forward frame.  Head parts retain
their authored height here; the shared character assembly applies its -36 mm
head offset.  The neck stays on the neck bone.  No scene, source or export is
saved by this module.
"""
import math
from pathlib import Path

import bpy
import bmesh
import numpy as np
from mathutils import Vector


def build_face(ctx):
    M, material = ctx['M'], ctx['material']
    mesh, sphere, tube = ctx['mesh'], ctx['sphere'], ctx['tube']
    ring_mesh, parts = ctx['ring_mesh'], ctx['PARTS']
    qa = Path(ctx['QA'])
    qa.mkdir(parents=True, exist_ok=True)
    start = len(parts)
    chin_z, crown_z, cy, eye_z = 1.496, 1.705, -.013, 1.607

    def rgba(hex_value):
        values = [int(hex_value[i:i+2], 16) / 255 for i in (1, 3, 5)]
        return tuple(v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4
                     for v in values) + (1,)

    def update_material(key, label, colour, roughness, coat=0):
        # Hands have already been constructed: preserve the shared skin object.
        mat = M.get(key)
        if mat is None:
            mat = material(label, colour, roughness)
            M[key] = mat
        mat.name = label
        bsdf = mat.node_tree.nodes.get('Principled BSDF')
        bsdf.inputs['Base Color'].default_value = rgba(colour)
        bsdf.inputs['Roughness'].default_value = roughness
        bsdf.inputs['Metallic'].default_value = 0
        bsdf.inputs['Coat Weight'].default_value = coat
        mat.diffuse_color = rgba(colour)
        return mat

    skin_colour = '#b8947d'
    update_material('skin', 'Skin | warm natural complexion', skin_colour, .56)
    skin_shader = M['skin'].node_tree.nodes.get('Principled BSDF')
    skin_shader.inputs['Subsurface Weight'].default_value = .035
    skin_shader.inputs['Specular IOR Level'].default_value = .25
    update_material('skin_face', 'Skin | sculpted young complexion', skin_colour, .55)
    face_shader = M['skin_face'].node_tree.nodes.get('Principled BSDF')
    face_shader.inputs['Subsurface Weight'].default_value = .035
    face_shader.inputs['Specular IOR Level'].default_value = .25
    update_material('skin_shadow', 'Skin | soft warm fold', '#916d59', .66)
    update_material('eye', 'Eye | shaded ivory sclera', '#92968c', .20, .20)
    update_material('iris', 'Eye | dark chestnut iris and pupil', '#302218', .17, .38)
    update_material('brow', 'Eyebrows | natural dark brown', '#211a16', .78)
    update_material('lash', 'Lash line | warm black', '#211a17', .70)
    update_material('nostril', 'Nostril | recessed opening', '#483029', .90)
    update_material('lips', 'Lips | natural muted rose', '#93675d', .49)
    update_material('mouth_seam', 'Mouth | relaxed closed seam', '#50332c', .72)

    # A tapered mandibular contour with an unbroken, gently rounded cheek.
    sections = [
        (1.496, .0175, .025), (1.502, .0270, .037),
        (1.511, .0370, .046), (1.521, .0465, .051),
        (1.534, .0525, .055), (1.548, .0590, .059),
        (1.570, .0650, .062), (1.590, .0685, .064),
        (1.610, .0685, .065), (1.632, .0670, .066),
        (1.652, .0635, .064), (1.672, .0560, .058),
        (1.690, .0390, .045), (1.705, .0035, .006),
    ]

    def profile(z):
        z = max(chin_z, min(crown_z, float(z)))
        for k, (a, b) in enumerate(zip(sections, sections[1:])):
            if a[0] <= z <= b[0]:
                t = (z-a[0])/(b[0]-a[0])
                p, q = sections[max(0, k-1)], sections[min(len(sections)-1, k+2)]
                result = []
                for axis in (1, 2):
                    m0 = (b[axis]-p[axis])/(b[0]-p[0])*(b[0]-a[0])
                    m1 = (q[axis]-a[axis])/(q[0]-a[0])*(b[0]-a[0])
                    value = ((2*t**3-3*t*t+1)*a[axis] + (t**3-2*t*t+t)*m0
                             + (-2*t**3+3*t*t)*b[axis] + (t**3-t*t)*m1)
                    result.append(max(.001, value))
                return tuple(result)
        return sections[-1][1:]

    nose_sections = [(1.548, 0), (1.555, .007), (1.563, .0195),
                     (1.572, .0220), (1.586, .0170), (1.602, .010),
                     (1.617, .0035), (1.628, 0)]

    def bridge(z):
        for k,(a,b) in enumerate(zip(nose_sections,nose_sections[1:])):
            if a[0] <= z <= b[0]:
                t = (z-a[0])/(b[0]-a[0])
                p=nose_sections[max(0,k-1)];q=nose_sections[min(len(nose_sections)-1,k+2)]
                m0=0 if k==0 else (b[1]-p[1])/(b[0]-p[0])*(b[0]-a[0])
                m1=0 if k==len(nose_sections)-2 else (q[1]-a[1])/(q[0]-a[0])*(b[0]-a[0])
                return max(0,(2*t**3-3*t*t+1)*a[1]+(t**3-2*t*t+t)*m0
                           +(-2*t**3+3*t*t)*b[1]+(t**3-t*t)*m1)
        return 0

    def facial_displacement(x, z):
        # All forms affect the same continuous skin sheet.  There is no nose ball
        # or cheek sphere and no sharp cheek hollow that would age this face.
        nose_width = .0067 + .0042*math.exp(-((z-1.566)/.011)**2)
        nose = bridge(z)*math.exp(-(x/nose_width)**2)
        alae = .0040*math.exp(-((abs(x)-.0110)/.0050)**2-((z-1.560)/.0042)**2)
        nostril = .0017*math.exp(-((abs(x)-.0105)/.0032)**2-((z-1.5570)/.0022)**2)
        sockets = .0080*math.exp(-((abs(x)-.029)/.018)**2-((z-eye_z)/.0118)**2)
        brow = .0055*math.exp(-((abs(x)-.030)/.022)**2-((z-1.624)/.0070)**2)
        cheek = .0072*math.exp(-((abs(x)-.043)/.021)**2-((z-1.583)/.015)**2)
        cheek_turn = .0025*math.exp(-((abs(x)-.047)/.021)**2-((z-1.551)/.018)**2)
        temple = .0022*math.exp(-((abs(x)-.058)/.012)**2-((z-1.611)/.023)**2)
        mouth = .0047*math.exp(-(x/.027)**2-((z-1.537)/.013)**2)
        chin = .0045*math.exp(-(x/.025)**2-((z-1.511)/.008)**2)
        chin_fold = .0014*math.exp(-(x/.023)**2-((z-1.521)/.0045)**2)
        philtrum = .0013*math.exp(-(x/.0028)**2-((z-1.548)/.0065)**2)
        philtrum_ridge = .0015*math.exp(-((abs(x)-.0042)/.0023)**2-((z-1.548)/.0060)**2)
        return (sockets+nostril+chin_fold+philtrum+cheek_turn+temple
                -nose-alae-brow-cheek-mouth-chin-philtrum_ridge)

    def point_at(angle, z):
        rx, ry = profile(z)
        c = math.cos(angle)
        x = math.sin(angle)*rx
        # The facial plane is flatter than a sphere; the rear cranium remains
        # round. This retains a natural temple-to-cheek transition in 3/4 view.
        y = cy-ry*(c**.88 if c >= 0 else c)
        y += max(0, c)**2*facial_displacement(x, z)
        return x, y, z

    def surface(x, z):
        rx, _ = profile(z)
        a = math.asin(max(-.999999, min(.999999, x/rx)))
        return point_at(a, z)[1]

    def face_uv(x, z):
        rx, _ = profile(z)
        a = math.asin(max(-.999999, min(.999999, x/rx)))
        return ((a+math.pi)/math.tau, (z-chin_z)/(crown_z-chin_z))

    def skin_normal(x, z):
        step = .00001
        dx = (surface(x+step,z)-surface(x-step,z))/(step*2)
        dz = (surface(x,z+step)-surface(x,z-step))/(step*2)
        return Vector((dx,-1,dz)).normalized()

    def packed_texture(name, array, colour_space, mat, socket, strength=1):
        height, width = array.shape[:2]
        image = bpy.data.images.new(name, width, height, alpha=True)
        image.colorspace_settings.name = colour_space
        image.pixels.foreach_set(np.clip(array, 0, 1).astype(np.float32).ravel())
        image.update()
        image.file_format = 'PNG'
        image.filepath_raw = str(qa/(name+'.png'))
        image.save()
        filename=image.filepath_raw
        bpy.data.images.remove(image)
        # Re-open the encoded PNG so Blender previews use the same sRGB decode
        # as the glTF texture, rather than the generated image's float buffer.
        image=bpy.data.images.load(filename,check_existing=False)
        image.name=name
        image.colorspace_settings.name=colour_space
        image.pack()
        shader = mat.node_tree.nodes.get('Principled BSDF')
        texture = mat.node_tree.nodes.new('ShaderNodeTexImage')
        texture.image = image
        if socket == 'Normal':
            normal = mat.node_tree.nodes.new('ShaderNodeNormalMap')
            normal.inputs['Strength'].default_value = strength
            mat.node_tree.links.new(texture.outputs['Color'], normal.inputs['Color'])
            mat.node_tree.links.new(normal.outputs['Normal'], shader.inputs['Normal'])
        else:
            mat.node_tree.links.new(texture.outputs['Color'], shader.inputs[socket])
        return image

    # The atlas seam is behind the head, not through the nose. All lid meshes
    # share this chart, so their complexion is continuous with the cheeks.
    size = 512
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    zz = chin_z+yy/(size-1)*(crown_z-chin_z)
    aa = xx/(size-1)*math.tau-math.pi
    rx = np.array([profile(float(z))[0] for z in zz[:, 0]])[:, None]
    fx = np.sin(aa)*rx
    frontal = np.maximum(0, np.cos(aa))**4
    rng = np.random.default_rng(981)
    noise = rng.random((size, size), dtype=np.float32)-.5
    cheek = np.exp(-((np.abs(fx)-.042)/.022)**2-((zz-1.577)/.021)**2)*frontal
    under_eye = np.exp(-((np.abs(fx)-.029)/.020)**2-((zz-1.596)/.009)**2)*frontal
    nose_warm = np.exp(-(fx/.014)**2-((zz-1.564)/.022)**2)*frontal
    orbit = np.exp(-((np.abs(fx)-.029)/.023)**2-((zz-1.615)/.012)**2)*frontal
    jaw = np.exp(-((zz-1.515)/.032)**2)*(1-.65*np.exp(-(fx/.032)**2))*frontal
    temples = np.exp(-((np.abs(fx)-.058)/.016)**2-((zz-1.619)/.035)**2)*frontal
    forehead = np.exp(-(fx/.047)**2-((zz-1.650)/.027)**2)*frontal
    fine_mottle = (np.sin(xx*.16+np.sin(yy*.071))*np.sin(yy*.13)
                   +.45*np.sin(xx*.49+yy*.31))*.0018
    albedo = np.ones((size, size, 4), dtype=np.float32)
    base = np.array([184, 148, 125], dtype=np.float32)/255
    albedo[:, :, :3] = base+(noise*.006+fine_mottle)[:, :, None]
    albedo[:, :, 0] += .026*cheek+.018*nose_warm+.005*forehead-.020*orbit-.010*temples-.008*jaw
    albedo[:, :, 1] += -.009*cheek-.011*nose_warm-.015*under_eye-.028*orbit-.014*temples-.015*jaw+.008*forehead
    albedo[:, :, 2] += -.011*cheek-.012*nose_warm-.012*under_eye-.023*orbit-.014*temples-.012*jaw+.009*forehead
    roughness = np.ones((size, size, 4), dtype=np.float32)
    roughness[:, :, :3] = (.56+noise*.045+.035*cheek+.018*jaw-.070*nose_warm-.030*forehead)[:, :, None]
    normal = np.ones((size, size, 4), dtype=np.float32)
    dx = (np.roll(noise, 1, axis=1)-np.roll(noise, -1, axis=1))*.040
    dy = (np.roll(noise, 1, axis=0)-np.roll(noise, -1, axis=0))*.040
    normal[:, :, 0], normal[:, :, 1] = .5+dx, .5+dy
    normal[:, :, 2] = .5+.5*np.sqrt(np.maximum(0, 1-(dx*2)**2-(dy*2)**2))
    packed_texture('Hanli_reference_skin_colour', albedo, 'sRGB', M['skin_face'], 'Base Color')
    packed_texture('Hanli_reference_skin_roughness', roughness, 'Non-Color', M['skin_face'], 'Roughness')
    packed_texture('Hanli_reference_skin_micro_normal', normal, 'Non-Color', M['skin_face'], 'Normal', .22)

    # Natural iris-to-eye ratio: most of the iris is vertically covered by lids.
    n = 256
    iy, ix = np.mgrid[0:n, 0:n].astype(np.float32)
    ix, iy = (ix/(n-1)-.5)*2, (iy/(n-1)-.5)*2
    radial, theta = np.sqrt(ix*ix+iy*iy), np.arctan2(iy, ix)
    striation = (.5+.5*np.sin(theta*71+np.sin(theta*13)*1.5+radial*18))
    iris = np.ones((n, n, 4), dtype=np.float32)
    iris[:, :, :3] = np.array([.19, .125, .075])+striation[:, :, None]*np.array([.075, .045, .025])
    pupil = np.clip((radial-.42)/.035, 0, 1)
    edge = np.clip((1.0-radial)/.14, 0, 1)
    iris[:, :, :3] *= (.23+.77*pupil*edge)[:, :, None]
    packed_texture('Hanli_reference_iris', iris, 'sRGB', M['iris'], 'Base Color')

    # A slightly darker seam fades back to skin at the lip's outer boundary.
    n = 128
    ly, lx = np.mgrid[0:n, 0:n].astype(np.float32)
    uu, vv = lx/(n-1)*2-1, ly/(n-1)
    blend = np.maximum(0, 1-uu*uu)**.65*np.maximum(0, 1-vv)**.40
    lip = np.ones((n, n, 4), dtype=np.float32)
    rose = np.array([.57, .355, .325], dtype=np.float32)
    lip[:, :, :3] = base+(rose-base)*blend[:, :, None]*.93
    lip[:, :, :3] += (np.sin(lx*.83+ly*.04)*.0035*blend)[:, :, None]
    packed_texture('Hanli_reference_lip_tone', lip, 'sRGB', M['lips'], 'Base Color')

    def neck_surface(x, y, z, angle, row):
        front=max(0,math.cos(angle))
        y-=.0014*math.exp(-((z-1.433)/.014)**2)*front**8
        return x,y,z

    ring_mesh('Neck | slender anatomical transition', [
        (1.363, .035, .032, 0, .009), (1.390, .0335, .031, 0, .012),
        (1.420, .031, .029, 0, .016), (1.447, .029, .027, 0, .019),
        (1.472, .027, .026, 0, .021), (1.483, .025, .025, 0, .022),
    ], 'skin', 'neck', n=40, warp=neck_surface)

    ex_abs, half_width = .0290, .0148

    def in_eye_socket(x, y, z):
        if y > cy:
            return False
        for side in (-1, 1):
            dx = x-side*ex_abs
            dz = z-eye_z-side*dx*.085
            if (dx/.0170)**2+(dz/.0070)**2 < 1:
                return True
        return False

    # Real openings beneath the eyelid annuli avoid closed skin behind the eyes.
    verts, faces, uvs = [], [], []
    around, rows = 160, 112
    for j in range(rows+1):
        z = chin_z+(crown_z-chin_z)*j/rows
        for i in range(around+1):
            angle = -math.pi+i/around*math.tau
            verts.append(point_at(angle, z))
            uvs.append((i/around, j/rows))
    for j in range(rows):
        for i in range(around):
            k = j*(around+1)+i
            ids = (k, k+1, k+around+2, k+around+1)
            centre = tuple(sum(verts[v][axis] for v in ids)/4 for axis in range(3))
            if not in_eye_socket(*centre):
                faces.append(ids)
    faces.append(tuple(range(around, -1, -1)))
    faces.append(tuple(rows*(around+1)+i for i in range(around+1)))
    head = mesh('Face | continuous young craniofacial surface', verts, faces, 'skin_face', 'head', uv=uvs)
    bm = bmesh.new(); bm.from_mesh(head.data)
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1e-7)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces)); bm.to_mesh(head.data); bm.free()
    # At an opening the usual one-sided averaged normals create a visible ring.
    # Preserve the derivative of the shared skin surface on those boundary
    # vertices; the lid's outer edge uses exactly the same derivative below.
    head_normals = []
    for vertex in head.data.vertices:
        x,y,z = vertex.co
        rx,_ = profile(z)
        angle = math.asin(max(-1,min(1,x/rx)))
        if y>cy:
            angle = math.pi-angle if x>=0 else -math.pi-angle
        da = Vector(point_at(angle+.0001,z))-Vector(point_at(angle-.0001,z))
        dz = Vector(point_at(angle,z+.00001))-Vector(point_at(angle,z-.00001))
        normal = da.cross(dz)
        head_normals.append(tuple(normal.normalized() if normal.length>1e-12 else Vector((0,0,1))))
    head.data.normals_split_custom_set_from_vertices(head_normals)

    for side, suffix in [(-1, 'R'), (1, 'L')]:
        ex = side*ex_abs

        def eye_limits(x):
            u = max(-1, min(1, (x-ex)/half_width))
            arc = max(0, 1-u*u)**.62
            centre = eye_z+side*(x-ex)*.085
            return centre-.0039*arc, centre+.0050*arc

        def eye_surface(x, z):
            lo, hi = eye_limits(x)
            u = max(-1, min(1, (x-ex)/half_width))
            v = max(-1, min(1, (z-(lo+hi)/2)/max(.0001, (hi-lo)/2)))
            return surface(x, z)-.00072-.0042*(1-u*u)*max(0, 1-v*v)

        eye_v, eye_f, eye_uv = [], [], []
        for j in range(11):
            v = j/10
            for i in range(33):
                x = ex+(-1+i/16)*half_width
                lo, hi = eye_limits(x); z = lo+(hi-lo)*v
                eye_v.append((x, eye_surface(x, z), z)); eye_uv.append((i/32, v))
                if i < 32 and j < 10:
                    k = j*33+i; eye_f.append((k, k+1, k+34, k+33))
        mesh('Eye | inset almond sclera.'+suffix, eye_v, eye_f, 'eye', 'head', uv=eye_uv)

        # One curved iris patch carries the pupil/limbus texture. It lies on the
        # same corneal surface as the sclera, not on a protruding sphere/disc.
        centre_z, radius = eye_z-.0001, .0061
        iv = [(ex, eye_surface(ex, centre_z)-.00012, centre_z)]
        iu, iff = [(.5, .5)], []
        segments, radial_rows = 64, 5
        for j in range(1, radial_rows+1):
            rho = j/radial_rows
            for i in range(segments+1):
                a = i/segments*math.tau
                # Find the star-shaped intersection of the iris and opening.
                rr = radius
                if abs(math.sin(a)) > .01:
                    for _ in range(5):
                        test_x = ex+rr*math.cos(a)
                        lo, hi = eye_limits(test_x)
                        limit = (hi-centre_z-.0001 if math.sin(a)>0 else centre_z-lo-.0001)/abs(math.sin(a))
                        rr = max(.001, min(radius, limit))
                dx, dz = rho*rr*math.cos(a), rho*rr*math.sin(a)
                x, z = ex+dx, centre_z+dz
                iv.append((x, eye_surface(x, z)-.00015, z))
                iu.append((.5+dx/(radius*2), .5+dz/(radius*2)))
                if i < segments:
                    if j == 1:
                        iff.append((0, 1+i, 2+i))
                    else:
                        a0 = 1+(j-2)*(segments+1)+i
                        b0 = 1+(j-1)*(segments+1)+i
                        iff.append((a0, b0, b0+1, a0+1))
        mesh('Eye | embedded curved iris.'+suffix, iv, iff, 'iris', 'head', uv=iu)

        # Six continuous rings blend the skin at the opening into the orbital
        # surface. The outside overlaps the coarse cutout by several millimetres.
        lv, lf, luv = [], [], []
        segments, bands = 64, 6
        for j in range(bands+1):
            t = j/bands
            width = half_width*(1-t)+.0205*t
            for i in range(segments+1):
                a = i/segments*math.tau
                x = ex+math.cos(a)*width
                inner_h = .0050 if math.sin(a)>=0 else .0039
                outer_h = .0105 if math.sin(a)>=0 else .0090
                z = eye_z+side*(x-ex)*.085+math.sin(a)*(inner_h*(1-t)+outer_h*t)
                pad = .00001+.00071*(1-t)**2+.00050*math.sin(t*math.pi)**2*abs(math.sin(a))**.5
                # A fine upper-lid hood overlaps the cornea and casts the small
                # contact shadow seen on a recessed eye, rather than a sticker.
                pad += .0022*math.exp(-((t-.20)/.20)**2)*max(0,math.sin(a))**1.4
                y = surface(x, z)-pad
                lv.append((x, y, z)); luv.append(face_uv(x, z))
                if i < segments and j < bands:
                    k = j*(segments+1)+i; lf.append((k, k+segments+1, k+segments+2, k+1))
        lid_mesh=mesh('Lids | blended continuous orbit.'+suffix, lv, lf, 'skin_face', 'head', uv=luv)
        lid_mesh.data.update()
        custom=[]
        for index,vertex in enumerate(lid_mesh.data.vertices):
            t=(index//(segments+1))/bands
            weight=max(0,min(1,(t-.25)/.75));weight=weight*weight*(3-2*weight)
            custom.append(tuple(vertex.normal.lerp(skin_normal(vertex.co.x,vertex.co.z),weight).normalized()))
        lid_mesh.data.normals_split_custom_set_from_vertices(custom)
        lash = []
        for i in range(25):
            x = ex+(-1+i/12)*half_width*.985
            _, z = eye_limits(x)
            lash.append((x, surface(x, z)-.0010, z))
        tube('Upper lash | fine tapered margin.'+suffix, lash, .00024, 'lash', 'head', radii=[.10]+[.8]*23+[.10])
        crease=[]
        for i in range(23):
            u=-.90+i/22*1.80;x=ex+u*half_width
            _,z=eye_limits(x);z+=.0028*max(0,1-u*u)**.5
            crease.append((x,surface(x,z)-.00050,z))
        tube('Upper lid | recessed fold.'+suffix,crease,.00016,'skin_shadow','head',
             radii=[.1]+[.55]*21+[.1])
        duct_x=ex-side*half_width*.90
        lo,hi=eye_limits(duct_x);duct_z=(lo+hi)*.5
        sphere('Eye | warm tear duct.'+suffix,
               (duct_x,eye_surface(duct_x,duct_z)-.00025,duct_z),
               (.0009,.00035,.00065),'lips','head',segments=16,rings=8)

        # Soft, flattened brow surface and sparse individual hairs.
        bv, bf, bu = [], [], []
        for j in range(3):
            vv = j/2*2-1
            for i in range(25):
                u = i/24; x = side*(.0135+u*.035)
                mid = 1.622+.0035*math.sin(u*math.pi*.9)-.0018*u
                thick = .0020*math.sin(math.pi*(.035+.93*u))**.65
                z = mid+vv*thick
                bv.append((x, surface(x, z)-.00065, z)); bu.append((u, j/2))
                if i<24 and j<2:
                    k=j*25+i
                    bf.append((k,k+1,k+26,k+25) if side>0 else (k+25,k+26,k+1,k))
        mesh('Brow | restrained tapered arch.'+suffix, bv, bf, 'brow', 'head', uv=bu)
        for i in range(20):
            u=.04+i/20*.90; x=side*(.0135+u*.035)
            z=1.622+.0035*math.sin(u*math.pi*.9)-.0018*u
            endx=x+side*.0019; endz=z+.0017
            tube('Brow | individual fine hair.'+suffix,
                 [(x,surface(x,z)-.00080,z), (endx,surface(endx,endz)-.00080,endz)],
                 .00011,'brow','head',radii=[.8,.06])

        # Small wings and openings are part of the continuous nose, with only
        # the actual aperture darkened. No dark nasolabial tubes are added.
        nx, nz = side*.0105, 1.5570
        nv = [(nx, surface(nx,nz)-.00006,nz)]; nf=[]
        for i in range(25):
            a=i/24*math.tau;x=nx+math.cos(a)*.0020;z=nz+math.sin(a)*.00080
            nv.append((x,surface(x,z)-.00007,z))
            if i<24:nf.append((0,i+1,i+2))
        mesh('Nostril | discreet aperture.'+suffix,nv,nf,'nostril','head')

        # Close-fitting ears, a shallow concha and a narrow helix.
        sphere('Ear | attached pinna.'+suffix,(side*.0715,-.002,1.592),(.0105,.009,.023),'skin','head',segments=24,rings=12)
        ev, ef = [], []
        for j in range(6):
            r=j/5
            for i in range(25):
                a=i/24*math.tau
                x=side*(.075+math.cos(a)*.0066*r)
                z=1.593+math.sin(a)*.0165*r
                y=-.010+.0040*(1-r*r)
                ev.append((x,y,z))
                if i<24 and j<5:
                    k=j*25+i;ef.append((k,k+25,k+26,k+1) if side>0 else (k+1,k+26,k+25,k))
        mesh('Ear | shallow concha.'+suffix,ev,ef,'skin_shadow','head')
        helix=[]
        for i in range(25):
            a=-.35+i/24*(math.tau-.3)
            helix.append((side*(.075+math.cos(a)*.0083),-.0107,1.593+math.sin(a)*.0200))
        tube('Ear | soft helix.'+suffix,helix,.00155,'skin','head',radii=[.6]+[1]*23+[.55])
        tube('Ear | inner antihelix.'+suffix,[(side*.074,-.010,1.580),(side*.077,-.011,1.591),(side*.076,-.011,1.602)],.0010,'skin','head',radii=[.3,1,.35])

    # Thin relaxed lips with a soft cupid's bow and no protruding mouth block.
    mouth_width = .0220
    def mouth_line(u):
        return 1.5358-.00045*(1-u*u)+.00020*u
    for upper in (True,False):
        vv, ff, uv = [], [], []
        for j in range(6):
            v=j/5
            for i in range(41):
                u=-1+i/20;x=u*mouth_width
                if upper:
                    height=(.0024+.0011*math.exp(-((abs(u)-.30)/.19)**2))*(1-u*u)
                else:
                    height=-.0038*(1-u*u)
                z=mouth_line(u)+height*v
                bulge=(.0019 if upper else .0025)*(1-u*u)*math.sin(v*math.pi)
                vv.append((x,surface(x,z)-.00016-bulge,z));uv.append((i/40,v))
                if i<40 and j<5:
                    k=j*41+i;ff.append((k,k+1,k+42,k+41) if upper else (k+41,k+42,k+1,k))
        mesh(('Upper' if upper else 'Lower')+' lip | tapered rose surface',vv,ff,'lips','head',uv=uv)
    seam=[]
    for i in range(33):
        u=-1+i/16;x=u*mouth_width*.99;z=mouth_line(u)
        seam.append((x,surface(x,z)-.00024,z))
    tube('Mouth | fine closed seam',seam,.00022,'mouth_seam','head',radii=[.06]+[.65]*31+[.06])

    return {'profile':profile, 'surface':surface, 'chin_z':chin_z,
            'crown_z':crown_z, 'center_y':cy, 'eye_z':eye_z,
            'eye_x':ex_abs, 'sections':sections, 'head_mesh':head,
            'parts_created':len(parts)-start}
