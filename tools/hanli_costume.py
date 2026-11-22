"""Layered blue-green robes, pale embroidery, sculpted sash and red tassels.

The caller owns the figure, armature, exports and previews.  Geometry uses the
existing Blender -Y front / Z up convention and the original arm coordinates;
the caller's final arm-width adjustment therefore still matches the sword hand.
"""
import math
import bpy
import numpy as np
from mathutils import Vector


def build_costume(ctx):
    M = ctx['M']
    material, mesh = ctx['material'], ctx['mesh']
    sphere, tube = ctx['sphere'], ctx['tube']
    ring_mesh, limb = ctx['ring_mesh'], ctx['limb']
    PARTS, QA = ctx['PARTS'], ctx['QA']
    start = len(PARTS)
    palette = {
        'costume_outer': ('Blue jade | open silk coat', '#145b6e', .68, 0),
        'costume_sleeve': ('Deep peacock | draped sleeves', '#193d50', .74, 0),
        'costume_ink': ('Charcoal silk | inset lining', '#27323a', .90, 0),
        'costume_ice': ('Ice blue | overlapping inner silk', '#a2bcc2', .73, 0),
        'costume_blue': ('Silver blue | woven shadow panels', '#697f8d', .77, 0),
        'costume_thread': ('Muted blue | woven embroidery', '#608b97', .81, 0),
        'costume_gold': ('Pale champagne | repoussé fittings', '#bfb38e', .31, .82),
        'costume_gold_shadow': ('Aged champagne | recessed carving', '#7a806c', .49, .56),
        'costume_silver': ('Warm silver | raised feather edges', '#cbc9b3', .31, .76),
        'costume_red': ('Crimson | silk tassels and beads', '#a02d40', .68, 0),
        'costume_pearl': ('Pale jade | suspension beads', '#c8d3c3', .39, .12),
    }
    for key, args in palette.items():
        M[key] = material(*args)
    for key in ('costume_outer', 'costume_sleeve', 'costume_ice', 'costume_blue'):
        bsdf = M[key].node_tree.nodes['Principled BSDF']
        # Blender 4.3's glTF exporter emits white sheenColorFactor at full
        # strength for an unlinked Sheen Tint, losing the authored .12 weight.
        # Standard rough PBR silk preserves the deep coat/pale collar contrast
        # consistently in the editable source, GLB and Three.js.
        bsdf.inputs['Sheen Weight'].default_value = 0
        bsdf.inputs['Sheen Roughness'].default_value = .75
        bsdf.inputs['Specular IOR Level'].default_value = .24

    # Packed PBR cloth maps retain the authored blue palette in GLB.
    size = 512
    yy, xx = np.mgrid[:size, :size].astype(np.float32)
    weave = np.sin(xx * math.pi / 2) * np.cos(yy * math.pi / 2)
    grain = np.random.default_rng(720).random((size, size), dtype=np.float32) - .5
    damask = np.sin(xx * .086 + np.sin(yy * .04)) * np.sin(yy * .071)
    normal = np.ones((size, size, 4), dtype=np.float32)
    normal[:, :, 0] = .5 + .018 * np.sin(xx * math.pi / 2)
    normal[:, :, 1] = .5 + .018 * np.sin(yy * math.pi / 2)
    normal[:, :, 2] = .999

    def packed_image(name, pixels, color_space):
        image = bpy.data.images.new(name, size, size, alpha=True)
        image.colorspace_settings.name = color_space
        image.pixels.foreach_set(pixels.ravel())
        image.update()
        image.file_format = 'PNG'
        image.filepath_raw = str(QA / (name + '.png'))
        image.save()
        # Use the decoded PNG in the source scene as well as the exported GLB;
        # generated Image pixel buffers otherwise bypass the file's sRGB decode.
        decoded = bpy.data.images.load(image.filepath_raw, check_existing=False)
        decoded.name = name + '_packed'
        decoded.colorspace_settings.name = color_space
        decoded.pack()
        bpy.data.images.remove(image)
        return decoded

    normal_image = packed_image('Hanli_blue_silk_normal', normal, 'Non-Color')
    for key in ('costume_outer', 'costume_sleeve', 'costume_ice', 'costume_blue'):
        m = M[key]
        nodes, links = m.node_tree.nodes, m.node_tree.links
        bsdf = nodes['Principled BSDF']
        # Generated image pixels are serialized directly by this pipeline;
        # an sRGB image needs encoded palette values, not the BSDF's linear RGB.
        color = palette[key][1]
        base = np.array([int(color[i:i+2], 16)/255 for i in (1,3,5)], dtype=np.float32)
        pixels = np.ones((size, size, 4), dtype=np.float32)
        pixels[:, :, :3] = base[None, None, :] * (
            1 + .012 * weave[:, :, None] + .015 * grain[:, :, None] + .012 * damask[:, :, None])
        tex = nodes.new('ShaderNodeTexImage')
        tex.image = packed_image('Hanli_' + key + '_color', pixels, 'sRGB')
        links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
        tex = nodes.new('ShaderNodeTexImage')
        tex.image = normal_image
        nm = nodes.new('ShaderNodeNormalMap')
        nm.inputs['Strength'].default_value = .25
        links.new(tex.outputs['Color'], nm.inputs['Color'])
        links.new(nm.outputs['Normal'], bsdf.inputs['Normal'])

    def weighted(obj, mode):
        obj['skin_mode'] = mode
        return obj

    def solid(obj, thickness=.002):
        mod = obj.modifiers.new('Tailored fabric thickness', 'SOLIDIFY')
        mod.thickness = thickness
        mod.offset = 0
        return obj

    def sample_path(points, steps=6):
        data = [np.array(p, dtype=float) for p in points]
        result = []
        for j in range(len(data) - 1):
            p0, p1, p2, p3 = [data[k] for k in
                              (max(0, j - 1), j, j + 1, min(len(data) - 1, j + 2))]
            for k in range(steps):
                f = k / steps
                result.append(.5 * ((2*p1) + (-p0+p2)*f +
                                   (2*p0-5*p1+4*p2-p3)*f*f +
                                   (-p0+3*p1-3*p2+p3)*f*f*f))
        result.append(data[-1])
        return result

    def cord(name, points, radius, mat, bone='chest', skin='torso', sides=6,
             steps=4, taper=False):
        """Small explicit sweep, avoiding high-resolution curve tessellation."""
        path = [Vector(p) for p in sample_path(points, steps)]
        vv, ff, uv = [], [], []
        for j, p in enumerate(path):
            tangent = (path[min(j+1, len(path)-1)] - path[max(0, j-1)]).normalized()
            helper = Vector((0, 1, 0))
            if abs(tangent.dot(helper)) > .95:
                helper = Vector((1, 0, 0))
            u = tangent.cross(helper).normalized()
            v = tangent.cross(u).normalized()
            f = j / (len(path)-1)
            r = radius * (.16 + .84 * math.sin(math.pi*f)**.5 if taper else 1)
            for i in range(sides+1):
                a = i/sides*math.tau
                vv.append(tuple(p + r * (u*math.cos(a) + v*math.sin(a))))
                uv.append((i/sides, f))
                if i < sides and j < len(path)-1:
                    q = j*(sides+1)+i
                    ff.append((q, q+1, q+sides+2, q+sides+1))
        ff.extend([tuple(range(sides, -1, -1)),
                   tuple((len(path)-1)*(sides+1)+i for i in range(sides+1))])
        return mesh(name, vv, ff, mat, bone, skin, uv)

    # A closed charcoal support makes the deep neckline and armholes continuous.
    torso_profile = [(.87,.142,.100),(.97,.136,.098),(1.045,.136,.098),
                     (1.13,.151,.104),(1.23,.176,.109),(1.30,.181,.096),
                     (1.345,.151,.080),(1.385,.075,.053),(1.409,.040,.036)]
    def profile(z, table=torso_profile):
        z = max(table[0][0], min(table[-1][0], z))
        for low, high in zip(table, table[1:]):
            if low[0] <= z <= high[0]:
                f = (z-low[0])/(high[0]-low[0])
                return tuple(low[k]*(1-f)+high[k]*f for k in (1,2))
        return tuple(table[-1][1:])

    def torso_y(x, z, depth=.004):
        rx, ry = profile(z)
        return -ry * math.sqrt(max(.015, 1-(x/rx)**2)) - depth

    def drape(x, y, z, a, j):
        f = .0012*math.sin(a*9+z*21) + .0014*math.sin(a*15-z*18)
        return x+math.sin(a)*f, y-math.cos(a)*f, z

    torso_rows = []
    for low, high in zip(torso_profile, torso_profile[1:]):
        for k in range(4):
            f = k/4
            torso_rows.append((low[0]*(1-f)+high[0]*f,
                               low[1]*(1-f)+high[1]*f,
                               low[2]*(1-f)+high[2]*f, 0, 0))
    torso_rows.append((*torso_profile[-1],0,0))
    ring_mesh('Continuous charcoal under robe', torso_rows, 'costume_ink',
              n=56, skin_mode='torso', warp=drape)

    def tailored(name, rows, mat, depth, skin='torso', bone='chest'):
        """Conforming cloth patch: rows are (height, left X, right X)."""
        samples = []
        for a, b in zip(rows, rows[1:]):
            for k in range(5):
                f = k/5
                samples.append(tuple(a[i]*(1-f)+b[i]*f for i in range(3)))
        samples.append(rows[-1])
        vv, ff, uv = [], [], []
        for j, (z, left, right) in enumerate(samples):
            for k in range(9):
                u = k/8
                x = left*(1-u)+right*u
                # Diagonal tension from the crossed collar and soft gathers
                # above the sash are modeled into the cloth, not drawn lines.
                envelope=math.sin(u*math.pi)**1.4
                collar_pull=.0017*math.sin((z-1.05)*40+u*5)*math.exp(-((z-1.27)/.15)**2)
                waist_gather=.0032*math.sin(u*math.pi*5+(z-1.05)*12)*math.exp(-((z-1.09)/.075)**2)
                vv.append((x,torso_y(x,z,depth)-.001*envelope
                           -envelope*(collar_pull+waist_gather),z))
                uv.append((u,j/(len(samples)-1)))
                if k < 8 and j < len(samples)-1:
                    q = j*9+k
                    ff.append((q,q+9,q+10,q+1))
        return solid(mesh(name,vv,ff,mat,bone,skin,uv),.0017)

    tailored('Silver blue diagonal underlap',
             [(1.433,-.047,-.028),(1.383,-.069,-.014),(1.36,-.091,-.010),(1.31,-.112,.020),
              (1.25,-.115,.045),(1.20,-.110,.081),(1.08,-.119,.118)],
             'costume_blue',.005)
    tailored('Broad ice silk crossed inner robe',
             [(1.433,.025,.047),(1.383,.019,.069),(1.36,.014,.093),(1.29,-.015,.111),
              (1.19,-.061,.113),(1.09,-.110,.117),(1.010,-.127,.123)],
             'costume_ice',.009)
    # A double cloth roll defines the collar and the full diagonal overlap.
    for side in (-1,1):
        pts = [(side*x,torso_y(side*x,z,.014),z) for x,z in
               [( .035,1.434),(.041,1.410),(.048,1.386),(.062,1.356),(.072,1.33)]]
        cord('Pale collar folded edge',pts,.0019,'costume_ice')
    diagonal=[(.026,1.430),(.019,1.383),(.014,1.36),(-.015,1.29),(-.061,1.19),(-.110,1.09)]
    cord('Long woven overlap seam',[(x,torso_y(x,z,.013),z) for x,z in diagonal],
         .0011,'costume_thread',steps=6)
    collar_v,collar_f,collar_uv=[],[],[]
    for j in range(7):
        z=1.373+j*.0105
        for i in range(41):
            a=.68+i/40*(math.tau-1.36)
            collar_v.append((math.sin(a)*(.047-j*.0007),-math.cos(a)*(.044-j*.0007),
                             z-.012*(j/6)**2*max(0,math.cos(a))))
            collar_uv.append((i/40,j/6))
            if i<40 and j<6:
                q=j*41+i;collar_f.append((q,q+1,q+42,q+41))
    solid(mesh('Raised pale silk collar',collar_v,collar_f,'costume_ice','chest','torso',collar_uv))

    # Deep open coat, continuous around the back and neck.  Its front edges
    # frame the pale inner layers rather than covering them with a closed tunic.
    mantle_profile=[(1.023,.148,.109,.86),(1.10,.155,.111,.75),
                    (1.20,.181,.120,.62),(1.29,.191,.106,.55),
                    (1.345,.162,.088,.48),(1.385,.084,.061,.47),
                    (1.410,.048,.042,.50)]
    mantle_rows=[]
    for a,b in zip(mantle_profile,mantle_profile[1:]):
        for k in range(5):
            f=k/5;mantle_rows.append(tuple(a[i]*(1-f)+b[i]*f for i in range(4)))
    mantle_rows.append(mantle_profile[-1])
    def mantle_coord(u,j):
        z,rx,ry,gap=mantle_rows[j]
        a=gap+u*(math.tau-2*gap)
        waist=.0036*math.exp(-((z-1.075)/.090)**2)*math.sin(a*13+(z-1.03)*6)
        shoulder=.0024*math.exp(-((z-1.28)/.08)**2)*math.sin(a*8+z*27)
        f=.0013*math.sin(a*11+z*17)+waist+shoulder
        return math.sin(a)*(rx+f),-math.cos(a)*(ry+f),z
    vv,ff,uv=[],[],[]
    n=72
    for j in range(len(mantle_rows)):
        for i in range(n+1):
            vv.append(mantle_coord(i/n,j));uv.append((i/n,j/(len(mantle_rows)-1)))
            if i<n and j<len(mantle_rows)-1:
                q=j*(n+1)+i;ff.append((q,q+1,q+n+2,q+n+1))
    solid(mesh('Open blue jade outer robe',vv,ff,'costume_outer','chest','torso',uv),.0025)
    for u in (0,1):
        edge=[Vector(mantle_coord(u,j)) for j in range(len(mantle_rows))]
        for p in edge:p.y-=.0025
        cord('Continuous pale coat edge',edge,.0018,'costume_gold',steps=1)

    # A long grey-blue pleated undergarment is visible between the open panels.
    def skirt_warp(x,y,z,a,j):
        f=max(0,min(1,(1.03-z)/.90))
        pleat=(.0015+.0055*f)*math.sin(a*20+.25*math.sin(z*5))
        pleat+=.0020*f*math.sin(a*7+z*3)
        return x+math.sin(a)*pleat,y-math.cos(a)*pleat,z
    inner_rows=[]
    for j in range(20):
        f=j/19
        inner_rows.append((1.03-.895*f,.132+.035*f,.097+.063*f,0,.012*f))
    ring_mesh('Long finely pleated grey silk',inner_rows,'costume_blue','pelvis',
              n=80,skin_mode='inner_skirt',warp=skirt_warp)
    # Split fabric panels have separate robe bones; bindings on their trims
    # use exactly the same skirt weights as the cloth beneath.
    def skirt_panel(side):
        suffix='L' if side>0 else 'R';bone='robe.'+suffix
        rows,n=24,28
        def coord(u,f):
            a=(.86-.13*f)+(1.78-(.86-.13*f))*u
            rx=.148+.137*f**.9;ry=.111+.080*f**1.1
            folds=(.0015+.0045*f)*(math.sin(a*10+f*.9)+.25*math.sin(a*23-f))
            folds+=.0030*f**.7*math.sin(a*5-f*1.4)
            z=1.033-.89*f+.006*math.sin(a*4)*f**5
            return side*math.sin(a)*(rx+folds),-math.cos(a)*(ry+folds)+.016*f*f,z
        vv,ff,uv=[],[],[]
        for j in range(rows+1):
            for i in range(n+1):
                vv.append(coord(i/n,j/rows));uv.append((i/n,1-j/rows))
                if i<n and j<rows:
                    q=j*(n+1)+i;face=(q,q+1,q+n+2,q+n+1)
                    ff.append(face if side>0 else tuple(reversed(face)))
        solid(mesh('Open flowing coat panel.'+suffix,vv,ff,'costume_outer',bone,'skirt',uv),.0022)
        for u in (0,1):
            pts=[]
            for j in range(rows+1):
                p=Vector(coord(u,j/rows));p.y-=.002
                pts.append(p)
            cord('Pale coat panel edge.'+suffix,pts,.0016,'costume_gold',bone,'skirt',steps=1)
        cord('Blue cloth hem seam.'+suffix,[coord(i/n,.992) for i in range(n+1)],
             .001,'costume_thread',bone,'skirt',steps=1)
        return coord
    skirt_panel(1);skirt_panel(-1)
    vv,ff,uv=[],[],[]
    for j in range(23):
        f=j/22
        for i in range(43):
            a=1.70+i/42*(math.tau-3.40)
            fold=(.002+.005*f)*math.sin(a*10+f)+.0030*f*math.sin(a*5-f*.8)
            vv.append((math.sin(a)*(.148+.09*f+fold),
                       -math.cos(a)*(.111+.095*f+fold)+.015*f,1.032-.88*f))
            uv.append((i/42,1-f))
            if i<42 and j<22:
                q=j*43+i;ff.append((q,q+1,q+44,q+43))
    solid(mesh('Soft split back coat',vv,ff,'costume_sleeve','robe.back','skirt',uv),.002)

    # Relief ribbon: a convex, tapered feather or leaf following a cloth surface.
    # Four width segments produce a raised centre ridge with few triangles.
    def relief_ribbon(name, points, width, mat, surface, side=1,
                      bone='chest', skin='torso', steps=5):
        path=sample_path(points,steps)
        vv,ff,uv=[],[],[]
        for j,p in enumerate(path):
            tangent=path[min(j+1,len(path)-1)]-path[max(0,j-1)]
            norm=np.linalg.norm(tangent)
            across=np.array([-tangent[1],tangent[0]])/max(norm,1e-8)
            f=j/(len(path)-1)
            radius=width*(.10+.90*math.sin(math.pi*f)**.62)
            for k in range(5):
                t=k/4*2-1
                q=p+across*radius*t;x=side*q[0];z=q[1]
                vv.append((x,surface(x,z)-.0007-.0020*(1-t*t),z));uv.append((k/4,f))
                if k<4 and j<len(path)-1:
                    n0=j*5+k;face=(n0,n0+1,n0+6,n0+5)
                    ff.append(face if side>0 else tuple(reversed(face)))
        return solid(mesh(name,vv,ff,mat,bone,skin,uv),.0008)

    # Smooth full sleeves start inside the torso, preventing shoulder holes.
    for side,suffix in [(-1,'R'),(1,'L')]:
        path=[(side*.076,.002,1.294,.046,.058),(side*.127,0,1.310,.052,.061),
              (side*.174,-.002,1.292,.055,.060),(side*.210,-.004,1.246,.053,.057),
              (side*.244,-.006,1.190,.053,.055),(side*.269,-.007,1.123,.054,.055),
              (side*.283,-.017,1.065,.056,.056),(side*.295,-.029,1.002,.053,.053),
              (side*.300,-.037,.947,.046,.046)]
        path=sample_path(path,4)
        vv,ff,uv=[],[],[]
        n=36
        def sleeve_coord(j,a):
            x,y,z,ru,rv=path[j];center=Vector((x,y,z))
            axis=(Vector(path[min(j+1,len(path)-1)][:3])-Vector(path[max(0,j-1)][:3])).normalized()
            u=axis.cross(Vector((0,1,0))).normalized();v=axis.cross(u).normalized()
            radial=u*math.cos(a)+v*math.sin(a)
            front=max(0,-radial.y)
            inward=max(0,-side*radial.x)
            # A few broad compression folds collect at the elbow and cuff;
            # the outer upper arm remains a smoother hanging cloth surface.
            elbow=.0044*math.exp(-((z-1.125)/.052)**2)*math.sin((z-1.12)*107+a*1.6)*( .25+.75*front)
            armpit=.0036*math.exp(-((z-1.235)/.045)**2)*math.sin(z*101+a*1.3)*inward
            cuff=.0032*math.exp(-((z-.988)/.033)**2)*math.sin((z-.97)*128+a*1.8)
            fold=.0016*math.sin(a*5+j*.10)+elbow+armpit+cuff
            return center+u*math.cos(a)*(ru+fold)+v*math.sin(a)*(rv+fold)
        for j in range(len(path)):
            for i in range(n+1):
                vv.append(tuple(sleeve_coord(j,i/n*math.tau)));uv.append((i/n,j/(len(path)-1)))
                if i<n and j<len(path)-1:
                    q=j*(n+1)+i;ff.append((q,q+1,q+n+2,q+n+1))
        solid(mesh('Wide continuous silk sleeve.'+suffix,vv,ff,'costume_sleeve',
                   'upper_arm.'+suffix,'arm.'+suffix,uv),.002)
        # The folded cuff is made from the actual sleeve rings, not a detached
        # cylinder; it shares the host skin weights all the way around the arm.
        vv,ff,uv=[],[],[]
        js=[len(path)-4,len(path)-3,len(path)-2,len(path)-1]
        for j,index in enumerate(js):
            for i in range(n+1):
                p=sleeve_coord(index,i/n*math.tau)
                radial=p-Vector(path[index][:3]);p+=radial.normalized()*.0022
                vv.append(tuple(p));uv.append((i/n,j/3))
                if i<n and j<3:
                    q=j*(n+1)+i;ff.append((q,q+1,q+n+2,q+n+1))
        solid(mesh('Silver blue turned cuff.'+suffix,vv,ff,'costume_blue',
                   'upper_arm.'+suffix,'arm.'+suffix,uv),.0015)
        cord('Fine pale cuff piping.'+suffix,
             [sleeve_coord(len(path)-1,i/n*math.tau) for i in range(n+1)],
             .0012,'costume_silver','upper_arm.'+suffix,'arm.'+suffix,steps=1)
        # A restrained seam is separate from the broad geometric cloth folds.
        for angle in (1.58,):
            cord('Sleeve tailored seam.'+suffix,
                 [sleeve_coord(j,angle)+Vector((0,-.0003,0)) for j in range(9,26,2)],
                 .00035,'costume_thread','upper_arm.'+suffix,'arm.'+suffix,steps=2,taper=True)

        # Original grip and fingers retained verbatim to meet the sword handle.
        if suffix=='R':
            grip_center=Vector((-.307,-.055,.916));handle_axis=Vector((-.17,-.10,-.95)).normalized()
            h_across=Vector((1,0,-.17)).normalized();h_front=handle_axis.cross(h_across).normalized()
            sphere('Gripping palm.R',(-.304,-.031,.917),(.027,.018,.045),'skin','hand.R',segments=28)
            for i in range(4):
                d=-.027+i*.017;pts=[]
                for degree in [230,185,140,95,52]:
                    a=math.radians(degree)
                    pp=grip_center+handle_axis*d+h_across*math.cos(a)*.018+h_front*math.sin(a)*.018
                    pts.append(tuple(pp))
                tube('Closed sword finger.%d'%i,pts,.0068 if i<3 else .0059,'skin','hand.R',radii=[1,1.05,1,.92,.68])
            tube('Opposing sword thumb',[(-.282,-.035,.943),(-.282,-.060,.936),(-.294,-.075,.927),(-.310,-.072,.928)],.009,'skin','hand.R',radii=[1.1,1,.85,.65])
        else:
            sphere('Relaxed palm.L',(.303,-.037,.913),(.026,.018,.043),'skin','hand.L',segments=28)
            for i,length in enumerate([.058,.068,.064,.050]):
                x=.284+i*.013
                spread=(i-1.5)*.0012
                tube('Relaxed finger.%d'%i,
                     [(x,-.038,.894),(x+spread,-.043,.894-length*.28),
                      (x+spread,-.053,.894-length*.60),(x+spread*.6,-.066,.894-length*.84),
                      (x+spread*.35,-.071,.894-length*.92)],
                     .0066 if i<3 else .0058,'skin','hand.L',radii=[1.02,1,.88,.72,.48])
            tube('Relaxed thumb.L',[(.281,-.035,.931),(.272,-.056,.910),(.276,-.065,.892)],.008,'skin','hand.L',radii=[1.2,1,.65])

    # The reference's pale botanical trim is concentrated on the cloth shoulders
    # and lapel edges.  Thin convex blades replace round armour-like ornaments.
    def mantle_y(x,z):
        for a,b in zip(mantle_profile,mantle_profile[1:]):
            if a[0]<=z<=b[0]:
                f=(z-a[0])/(b[0]-a[0]);rx=a[1]*(1-f)+b[1]*f;ry=a[2]*(1-f)+b[2]*f
                return -ry*math.sqrt(max(.02,1-(x/rx)**2))-.004
        return torso_y(x,z,.011)

    for side,suffix in ((1,'L'),(-1,'R')):
        # Feather paths extend down the chest but remain outside the opening.
        main=[(.052,1.395),(.082,1.356),(.123,1.309),(.145,1.245),(.137,1.154)]
        relief_ribbon('Flowing silver shoulder stem.'+suffix,main,.0042,'costume_silver',mantle_y,side)
        for points,width in [
            ([(.061,1.388),(.088,1.378),(.126,1.358),(.157,1.330)],.008),
            ([(.076,1.365),(.118,1.356),(.153,1.334),(.175,1.302)],.009),
            ([(.093,1.342),(.136,1.328),(.165,1.291),(.172,1.257)],.0075),
            ([(.110,1.316),(.145,1.288),(.160,1.244),(.155,1.209)],.0065),
            ([(.126,1.278),(.142,1.256),(.150,1.208),(.144,1.170)],.005),
            ([(.108,1.334),(.096,1.319),(.100,1.297),(.122,1.286)],.005),
            ([(.132,1.304),(.139,1.329),(.158,1.332),(.173,1.315)],.005),
            ([(.150,1.279),(.164,1.300),(.179,1.288),(.176,1.266)],.0045),
        ]:
            relief_ribbon('Pale embroidered feather.'+suffix,points,width*.78,'costume_gold',mantle_y,side)
        # Long scroll on the pale inner cloth adds textile pattern without
        # changing its silhouette into a plate.
        surface=lambda x,z:torso_y(x,z,.014)
        relief_ribbon('Woven inner robe cloud.'+suffix,
                      [(.040,1.322),(.052,1.294),(.037,1.274),(.025,1.247),(.036,1.222)],
                      .0012,'costume_thread',surface,side)
        # Two quiet vertical fastening cords frame the lapel opening.
        pts=[(side*x,mantle_y(side*x,z)-.003,z) for x,z in
             [(.108,1.275),(.116,1.204),(.120,1.125),(.119,1.069)]]
        cord('Lapel woven fastening cord.'+suffix,pts,.0014,'costume_gold','chest','torso',steps=5)
        for k in range(3):
            z=1.158-k*.034;x=side*(.119+k*.001)
            sphere('Lapel fastening bead.'+suffix,(x,mantle_y(x,z)-.005,z),
                   (.0028,.0022,.0038),'costume_pearl','chest',segments=12,rings=8)['skin_mode']='torso'

    # Broad soft sash underneath the sculpted pale fittings.
    ring_mesh('Broad wrapped blue waist sash',
              [(.953,.147,.110,0,0),(.971,.149,.113,0,0),(1.025,.145,.109,0,0),(1.054,.141,.104,0,0)],
              'costume_sleeve','pelvis',n=64)
    for z in (.961,1.046):
        cord('Pale woven sash binding',[(math.sin(a)*.150,-math.cos(a)*.114,z) for a in
                                      [i/48*math.tau for i in range(49)]],
             .0015,'costume_gold','pelvis','rigid',steps=1)

    def relief_patch(name,outline,center,mat,depth=.009):
        """Three convex inset rings retain an organic, embossed silhouette."""
        ring=sample_path(outline+[outline[0]],3)[:-1]
        n=len(ring);vv,ff,uv=[],[],[]
        center=np.array(center,dtype=float)
        for j,t in enumerate((1,.68,.28)):
            for i,p in enumerate(ring):
                q=center+(p-center)*t;x,z=q
                y=-.118-depth*(1-t*t)
                vv.append((x,y,z));uv.append((x/.30+.5,(z-.80)/.27))
                if j<2:
                    ff.append((j*n+i,j*n+(i+1)%n,(j+1)*n+(i+1)%n,(j+1)*n+i))
        vv.append((center[0],-.118-depth,center[1]));uv.append((.5,.5))
        for i in range(n):ff.append((2*n+i,2*n+(i+1)%n,3*n))
        return solid(mesh(name,vv,ff,mat,'pelvis','rigid',uv),.002)

    relief_patch('Sculpted crescent belt clasp',
                 [(-.128,1.030),(-.100,1.043),(-.059,1.047),(-.024,1.053),
                  (0,1.047),(.024,1.053),(.059,1.047),(.100,1.043),(.128,1.030),
                  (.091,1.017),(.049,1.020),(0,1.009),(-.049,1.020),(-.091,1.017)],
                 (0,1.031),'costume_gold',.005)
    relief_patch('Long organic central sash pendant',
                 [(-.020,1.012),(-.056,.988),(-.070,.962),(-.053,.939),
                  (-.072,.923),(-.049,.896),(-.024,.888),(-.020,.855),(0,.834),
                  (.020,.855),(.024,.888),(.049,.896),(.072,.923),(.053,.939),
                  (.070,.962),(.056,.988),(.020,1.012)],
                 (0,.938),'costume_gold',.006)
    pendant_surface=lambda x,z:-.124
    for side in (-1,1):
        for pts,width in [
            ([(.004,1.050),(.028,1.045),(.047,1.028),(.083,1.028),(.119,1.031)],.004),
            ([(.009,1.024),(.029,1.014),(.047,.987),(.059,.974),(.046,.958)],.0045),
            ([(.018,.994),(.024,.970),(.040,.951),(.055,.935),(.045,.914)],.0055),
            ([(.048,.986),(.035,.989),(.031,.976),(.043,.965)],.003),
            ([(.018,.953),(.007,.938),(.015,.914),(.031,.904),(.042,.918)],.004),
            ([(.008,.902),(.012,.878),(.008,.857),(0,.848)],.0038),
        ]:
            relief_ribbon('Raised sash scrollwork',pts,width,'costume_silver',
                          pendant_surface,side,'pelvis','rigid',steps=4)
        cord('Fine sash engraved groove',[(side*x,-.128,z) for x,z in
                                         [(.016,1.048),(.028,1.037),(.045,1.035),(.062,1.042)]],
             .0008,'costume_gold_shadow','pelvis','rigid',steps=4)
    sphere('Central pale jade clasp inset',(0,-.136,.982),(.010,.0045,.014),
           'costume_pearl','pelvis',segments=20,rings=12)
    # Two red bead chains and fine tassel bundles; they follow the front robe
    # deformation so they remain outside the moving inner skirt.
    for side,suffix in ((-1,'R'),(1,'L')):
        bone='robe.'+suffix
        chain=[(side*.070,-.130,.973),(side*.078,-.140,.909),
               (side*.082,-.151,.841),(side*.088,-.160,.786)]
        cord('Red silk pendant chain.'+suffix,chain,.0015,'costume_red',bone,'skirt',steps=5)
        for i,z in enumerate((.948,.916,.882,.849,.813)):
            f=(.973-z)/.187;x=side*(.070+.018*f);y=-.130-.030*f
            obj=sphere('Sash red and jade bead.'+suffix,(x,y,z),
                       (.0043 if i%2 else .0053,.0037,.007 if i%2 else .009),
                       'costume_pearl' if i%2 else 'costume_red',bone,segments=12,rings=8)
            obj['skin_mode']='skirt'
        cord('Tassel knot.'+suffix,[(side*.088,-.160,.789),(side*.088,-.161,.772)],
             .007,'costume_red',bone,'skirt',sides=10,steps=2)
        for strand in range(9):
            a=strand/9*math.tau
            x0=side*.088+math.cos(a)*.0048;y0=-.160+math.sin(a)*.003
            pts=[(x0,y0,.777),(x0+side*.002,y0-.004,.728),
                 (x0+side*.008+math.cos(a)*.002,y0-.008,.676),
                 (x0+side*.014+math.cos(a)*.003,y0-.004,.637+.004*math.sin(a))]
            cord('Fine hanging crimson silk.'+suffix,pts,.0016,'costume_red',bone,'skirt',sides=5,steps=4)

    # Original palm-heaven bottle and its suspension remain on the right hip.
    bx,by,bz=.156,-.088,.907
    tube('Bottle suspension cord',[(.125,-.07,1.016),(.165,-.10,.975),(bx,by,.954)],
         .0019,'gold_dark','pelvis')
    ring_mesh('Palm-heaven jade bottle',
              [(bz-.038,.009,.009,bx,by),(bz-.031,.021,.019,bx,by),
               (bz-.006,.027,.023,bx,by),(bz+.017,.022,.020,bx,by),
               (bz+.028,.011,.010,bx,by),(bz+.046,.009,.008,bx,by)],
              'jade','pelvis',n=32)
    ring_mesh('Bottle bronze stopper',
              [(bz+.044,.010,.009,bx,by),(bz+.050,.012,.011,bx,by),
               (bz+.055,.008,.008,bx,by)],'gold','pelvis',n=24)
    for shift in (-.009,.009):
        tube('Bottle cloud engraving',[(bx-.014,by-.018,bz+shift),
             (bx-.006,by-.024,bz+shift+.007),(bx+.006,by-.024,bz+shift),
             (bx+.013,by-.020,bz+shift+.004)],.0011,'jade_dark','pelvis')
    return {'objects':len(PARTS)-start,'materials':list(palette),
            'style':'Open blue jade silk coat, pale layered collar, feather embroidery, sculpted sash and crimson tassels'}
