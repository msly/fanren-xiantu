"""Anatomical Han Li head built from the CC0 MakeHuman hm08 topology.

The source mesh, age/sex/ethnicity morphs, fitted eyeballs and texture are kept
under art/source/makehuman with their original licensing and provenance.  Only
head/neck body faces are used; helper geometry is never exported.  Geometry is
in the existing unshifted Blender frame and the shared build applies -36 mm.
"""
import math
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree


def read_obj(path):
    vertices, texcoords, faces = [], [], []
    group = 'default'
    for line in path.read_text().splitlines():
        row = line.split()
        if not row or row[0].startswith('#'):
            continue
        if row[0] == 'v':
            vertices.append(tuple(float(v) for v in row[1:4]))
        elif row[0] == 'vt':
            texcoords.append(tuple(float(v) for v in row[1:3]))
        elif row[0] == 'g':
            group = ' '.join(row[1:])
        elif row[0] == 'f':
            indices, uv = [], []
            for item in row[1:]:
                parts = item.split('/')
                indices.append(int(parts[0]) - 1)
                uv.append(int(parts[1]) - 1 if len(parts) > 1 and parts[1] else 0)
            faces.append((group, tuple(indices), tuple(uv)))
    return np.asarray(vertices, dtype=np.float64), texcoords, faces


def build_face(ctx):
    mesh, material = ctx['mesh'], ctx['material']
    M, parts = ctx['M'], ctx['PARTS']
    source = Path(__file__).resolve().parents[1] / 'art' / 'source' / 'makehuman'
    start = len(parts)
    original, uv, source_faces = read_obj(source / 'base.obj')
    shaped = original.copy()
    morphs = (
        ('asian-male-young.target', 1.0),
        ('universal-male-young-averagemuscle-minweight.target', .20),
        ('male-young-averagemuscle-minweight-idealproportions.target', .12),
        ('asian-mouth-compression.target', .28),
        ('mouth-upperlip-middle-down.target', .10),
    )
    for filename, amount in morphs:
        for line in (source / filename).read_text().splitlines():
            row = line.split()
            if len(row) == 4 and row[0].isdigit():
                shaped[int(row[0])] += amount * np.asarray(row[1:], dtype=float)

    # The expression target changes vermilion volume but leaves hm08's inner
    # lip margins (537/520) apart. Compress only a 3.8 mm neighbourhood of the
    # measured seam; the monotonic mapping preserves lip order and volume at
    # the outer borders, while the horizontal falloff leaves corners neutral.
    seam_y = float((shaped[537,1] + shaped[520,1]) * .5)
    seam_delta = shaped[:,1] - seam_y
    central = np.exp(-(np.abs(shaped[:,0]) / .18) ** 6)
    oral_front = np.clip((shaped[:,2] - 1.25) / .15, 0, 1)
    oral_front = oral_front * oral_front * (3 - 2 * oral_front)
    closure = .80 * np.exp(-(seam_delta / .038) ** 4) * central * oral_front
    shaped[:,1] -= seam_delta * closure

    def group_vertices(name):
        indices = sorted({index for group, face, _ in source_faces if group == name for index in face})
        if not indices:
            raise ValueError('Missing MakeHuman group: ' + name)
        return shaped[indices]

    body_ids = sorted({index for group, face, _ in source_faces if group == 'body' for index in face})
    body_points = shaped[body_ids]
    raw_crown = float(body_points[:, 1].max())
    chin_candidates = body_points[(np.abs(body_points[:, 0]) < .15)
                                 & (body_points[:, 2] > 1.10)
                                 & (body_points[:, 1] > 5.50)
                                 & (body_points[:, 1] < 6.40)]
    raw_chin = float(chin_candidates[:, 1].min())
    raw_eye = float(group_vertices('joint-l-eye')[:, 1].mean())
    chin_z, crown_z, eye_z, cy = 1.496, 1.705, 1.609, -.013

    def transform(points):
        """Fit anatomical landmarks, retaining the mesh's actual facial forms."""
        data = np.asarray(points, dtype=float)
        z = np.interp(data[:, 1],
                      [5.35, raw_chin - .35, raw_chin, raw_eye, raw_crown],
                      [1.365, 1.445, chin_z, eye_z, crown_z])
        # A restrained lower-jaw taper suits the youthful reference; this does
        # not replace nasal, orbital or oral anatomy with analytic bumps.
        jaw = 1 - .040 * np.exp(-((data[:, 1] - (raw_chin + .23)) / .42) ** 2)
        x = data[:, 0] * .096 * jaw
        y = cy - (data[:, 2] - .40) * .082
        blend = np.clip((z - 1.445) / .053, 0, 1)
        blend = blend * blend * (3 - 2 * blend)
        neck_width = .70 + .30 * blend
        x *= neck_width
        y = cy + (y - cy) * neck_width + .025 * (1 - blend)
        # The anatomical mesh includes the flared neck base beneath the robe.
        # Fit only its concealed rear half inside the turned collar after the
        # shared 36 mm head offset; keep the rim, exposed neck and face intact.
        final_z = z - .036
        collar_f = np.clip((final_z - 1.374) / .047, 0, 1)
        collar_cy = .005 + .016 * collar_f
        collar_rx = .084 - .017 * collar_f - .006
        collar_ry = .063 - .022 * collar_f - .006
        rear = np.clip((y - collar_cy) / .020, 0, 1)
        rear = rear * rear * (3 - 2 * rear)
        rim = np.clip((final_z - 1.414) / .007, 0, 1)
        concealed = rear * (1 - rim * rim * (3 - 2 * rim))
        radius = np.sqrt((x / collar_rx) ** 2 + ((y - collar_cy) / collar_ry) ** 2)
        fit = 1 + concealed * (np.minimum(1, 1 / np.maximum(radius, 1e-8)) - 1)
        x *= fit
        y = collar_cy + (y - collar_cy) * fit
        return np.column_stack((x, y, z))

    positioned = transform(shaped)

    def rgba(value):
        rgb = [int(value[k:k+2], 16) / 255 for k in (1, 3, 5)]
        return tuple(c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in rgb) + (1,)

    def set_material(key, label, colour, roughness, spec=.30, coat=0):
        mat = M.get(key)
        if mat is None:
            mat = material(label, colour, roughness)
            M[key] = mat
        mat.name = label
        shader = mat.node_tree.nodes.get('Principled BSDF')
        shader.inputs['Base Color'].default_value = rgba(colour)
        shader.inputs['Roughness'].default_value = roughness
        shader.inputs['Metallic'].default_value = 0
        shader.inputs['Specular IOR Level'].default_value = spec
        shader.inputs['Coat Weight'].default_value = coat
        mat.diffuse_color = rgba(colour)
        return mat

    set_material('skin', 'Skin | warm natural complexion', '#bd9987', .52)
    face_mat = set_material('skin_face', 'Skin | anatomical young male', '#bd9987', .51)
    face_shader = face_mat.node_tree.nodes.get('Principled BSDF')
    face_shader.inputs['Subsurface Weight'].default_value = .045
    brow_mat = set_material('brow', 'Brows | natural tapered dark hair', '#29201d', .76, .20)
    eye_mat = set_material('eye_anatomical', 'Eyes | fitted dark brown anatomical globes', '#ffffff', .17, .40, .22)

    def attach_image(mat, path, name):
        image = bpy.data.images.load(str(path), check_existing=False)
        image.name = name
        image.colorspace_settings.name = 'sRGB'
        image.pack()
        tex = mat.node_tree.nodes.new('ShaderNodeTexImage')
        tex.name = name
        tex.image = image
        shader = mat.node_tree.nodes.get('Principled BSDF')
        mat.node_tree.links.new(tex.outputs['Color'], shader.inputs['Base Color'])
        return image

    skin_path = source / 'young_lightskinned_male_diffuse3.png'
    if skin_path.exists():
        attach_image(face_mat, skin_path, 'MakeHuman CC0 | young male skin')
    eye_image = attach_image(eye_mat, source / 'brown_eye.png', 'MakeHuman CC0 | brown iris and sclera')

    # Preserve original per-corner UVs, including its real seams. Reprojecting
    # this texture into a spherical atlas would discard the authored anatomy.
    def obj_mesh(name, coordinates, selected_faces, texcoords, mat_key, mode='rigid'):
        used = sorted({index for _, face, _ in selected_faces for index in face})
        index_map = {old: new for new, old in enumerate(used)}
        faces = [tuple(index_map[v] for v in face) for _, face, _ in selected_faces]
        obj = mesh(name, [tuple(coordinates[i]) for i in used], faces, mat_key, 'head', mode)
        layer = obj.data.uv_layers.new(name='UVMap')
        for polygon, (_, _, uv_ids) in zip(obj.data.polygons, selected_faces):
            for loop, uv_id in zip(polygon.loop_indices, uv_ids):
                layer.data[loop].uv = texcoords[uv_id]
        return obj, used

    selected = [(group, face, tex) for group, face, tex in source_faces
                if group == 'body' and min(shaped[v, 1] for v in face) >= 5.35]
    head, used = obj_mesh('Face | anatomical CC0 head and neck', positioned,
                          selected, uv, 'skin_face', 'head_neck')
    subdivision = head.modifiers.new('Anatomical surface subdivision', 'SUBSURF')
    subdivision.subdivision_type = 'CATMULL_CLARK'
    subdivision.levels = 2
    subdivision.render_levels = 2
    bpy.context.view_layer.objects.active = head
    bpy.ops.object.modifier_apply(modifier=subdivision.name)
    bm = bmesh.new()
    bm.from_mesh(head.data)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(head.data)
    bm.free()
    for polygon in head.data.polygons:
        polygon.use_smooth = True
    head.data.update()
    head_vertices = [v.co.copy() for v in head.data.vertices]
    head_faces = [tuple(p.vertices) for p in head.data.polygons]
    head_bvh = BVHTree.FromPolygons(head_vertices, head_faces, all_triangles=False)

    # Hair should follow the cranium, not expand to the ear tips. Keep the full
    # head BVH for facial sampling and provide a separate ear-filtered scalp.
    scalp_faces = []
    for poly in head_faces:
        center = sum((head_vertices[i] for i in poly), Vector()) / len(poly)
        ear_region = abs(center.x) > .066 and 1.545 < center.z < 1.633 and center.y > -.050
        if not ear_region:
            scalp_faces.append(poly)
    scalp_bvh = BVHTree.FromPolygons(head_vertices, scalp_faces, all_triangles=False)

    def ray_surface(x, z):
        hit, _, _, _ = head_bvh.ray_cast(Vector((float(x), -.5, float(z))), Vector((0, 1, 0)))
        return hit

    def surface(x, z):
        hit = ray_surface(x, z)
        if hit is not None:
            return float(hit.y)
        # Outside a nasal/cranial silhouette, find its nearest boundary rather
        # than accidentally treating the back of the skull as the forehead.
        point, _, _, _ = head_bvh.find_nearest(Vector((float(x), -.10, float(z))))
        return float(point.y) if point is not None else cy - .05

    def skin_normal(x, z):
        _, normal, _, _ = head_bvh.ray_cast(Vector((float(x), -.5, float(z))), Vector((0, 1, 0)))
        return normal if normal is not None else Vector((0, -1, 0))

    samples = []
    for height in np.linspace(chin_z, crown_z - .0002, 180):
        right, right_normal, _, _ = scalp_bvh.ray_cast(Vector((.3, cy, height)), Vector((-1, 0, 0)))
        left, left_normal, _, _ = scalp_bvh.ray_cast(Vector((-.3, cy, height)), Vector((1, 0, 0)))
        front, _, _, _ = scalp_bvh.ray_cast(Vector((0, -.4, height)), Vector((0, 1, 0)))
        back, _, _, _ = scalp_bvh.ray_cast(Vector((0, .4, height)), Vector((0, -1, 0)))
        widths = []
        if right is not None and right.x > 0 and right_normal.x > 0:
            widths.append(right.x)
        if left is not None and left.x < 0 and left_normal.x < 0:
            widths.append(-left.x)
        rx = max(widths) if widths else float('nan')
        if 1.545 < height < 1.633 or rx > .078:
            rx = float('nan')
        depths = [abs(p.y-cy) for p in (front, back) if p is not None]
        ry = max(depths) if depths else float('nan')
        # Missing ear-region sections are interpolated below. They must never
        # become a made-up narrow ring that folds the hair cap through the face.
        samples.append((float(height), float(rx), float(ry)))
    samples.append((crown_z, .001, .003))
    profile_table = np.asarray(samples)
    for axis in (1,2):
        valid = np.isfinite(profile_table[:,axis])
        if valid.sum() < 2:
            raise ValueError('Insufficient valid cranial cross sections')
        profile_table[:,axis] = np.interp(profile_table[:,0], profile_table[valid,0], profile_table[valid,axis])
    samples = [tuple(row) for row in profile_table]

    def profile(z):
        return (float(np.interp(z, profile_table[:, 0], profile_table[:, 1])),
                float(np.interp(z, profile_table[:, 0], profile_table[:, 2])))

    # Official fitting weights deform both eyeballs with the same morphs as
    # the head, preserving the relation between globe and eyelid openings.
    eye_original, eye_uv, eye_faces = read_obj(source / 'high-poly.obj')
    fit_lines = (source / 'high-poly.mhclo').read_text().splitlines()
    offsets = np.ones(3)
    fitting = []
    reading = False
    for line in fit_lines:
        row = line.split()
        if not row or row[0].startswith('#'):
            continue
        if row[0] in ('x_scale', 'y_scale', 'z_scale'):
            axis = {'x_scale': 0, 'y_scale': 1, 'z_scale': 2}[row[0]]
            a, b, span = int(row[1]), int(row[2]), float(row[3])
            offsets[axis] = abs(shaped[a, axis] - shaped[b, axis]) / span
        elif row[0] == 'verts':
            reading = True
        elif reading and row[0].lstrip('-').isdigit():
            if len(row) == 9:
                indices = [int(x) for x in row[:3]]
                weights = np.asarray(row[3:6], dtype=float)
                offset = np.asarray(row[6:9], dtype=float)
                fitting.append(np.sum(shaped[indices] * weights[:, None], axis=0) + offset * offsets)
            elif len(row) == 1:
                fitting.append(shaped[int(row[0])])
            else:
                raise ValueError('Unsupported anatomical eye fitting row')
        elif reading:
            break
    if len(fitting) != len(eye_original):
        raise ValueError(f'Eyeball fitting count mismatch: {len(fitting)} != {len(eye_original)}')
    # The official texture reserves a blue, fully transparent island for the
    # outer corneal shell. It must not render as opaque blue over the iris.
    # The inner textured globe already carries the required curved surface;
    # discard only faces whose entire atlas footprint is fully transparent.
    pixels = np.asarray(eye_image.pixels[:], dtype=np.float32).reshape(eye_image.size[1], eye_image.size[0], 4)
    def alpha_at(coord):
        x = min(eye_image.size[0]-1, max(0, round(coord[0] * (eye_image.size[0]-1))))
        y = min(eye_image.size[1]-1, max(0, round(coord[1] * (eye_image.size[1]-1))))
        return float(pixels[y,x,3])
    eye_faces = [entry for entry in eye_faces
                 if any(alpha_at(eye_uv[index]) > .01 for index in entry[2])]
    eyes, _ = obj_mesh('Eyes | fitted anatomical globes', transform(fitting),
                       eye_faces, eye_uv, 'eye_anatomical')
    for polygon in eyes.data.polygons:
        polygon.use_smooth = True

    # Fine brows supply depth over the matching skin atlas. All strokes are
    # packed into one mesh per side to avoid hundreds of curve objects.
    brow_z = eye_z + .0118
    for side, suffix in ((-1, 'R'), (1, 'L')):
        vertices, faces = [], []
        for row in range(3):
            for i in range(58):
                u = .02 + (i + .33 * row) / 58 * .95
                x = side * (.0110 + u * .0375)
                arch = brow_z + .0028 * math.sin(u * math.pi * .92) - .0018 * u
                width = .0023 * math.sin(math.pi * (.04 + .93 * u)) ** .6
                z = arch - width * .80 + row * width * .50
                endx, endz = x + side * (.0010 + .0020 * u), z + width * (1.3 - .3 * row)
                midx, midz = (x + endx) * .5, (z + endz) * .5 + .00016
                stroke = [Vector((x, surface(x, z) - .00020, z)),
                          Vector((midx, surface(midx, midz) - .00028, midz)),
                          Vector((endx, surface(endx, endz) - .00020, endz))]
                first = len(vertices)
                for k, point in enumerate(stroke):
                    tangent = (stroke[min(2, k+1)] - stroke[max(0, k-1)]).normalized()
                    outward = skin_normal(point.x, point.z)
                    across = tangent.cross(outward).normalized()
                    outward = across.cross(tangent).normalized()
                    radius = (.00010, .00013, .000006)[k]
                    for ring in range(4):
                        angle = ring / 4 * math.tau
                        vertices.append(tuple(point + (across * math.cos(angle) + outward * math.sin(angle)) * radius))
                        if k < 2:
                            a = first + k*4 + ring
                            b = first + k*4 + (ring+1) % 4
                            faces.append((a, b, b+4, a+4))
        mesh('Brows | fine fitted hairs.' + suffix, vertices, faces, 'brow', 'head')

    return {'profile': profile, 'surface': surface, 'chin_z': chin_z,
            'crown_z': crown_z, 'center_y': cy, 'eye_z': eye_z,
            'eye_x': float(transform(group_vertices('joint-l-eye'))[:, 0].mean()),
            'sections': samples, 'head_mesh': head, 'head_bvh': head_bvh,
            'scalp_bvh': scalp_bvh, 'parts_created': len(parts) - start,
            'source_topology': 'MakeHuman hm08 CC0',
            'morphs': dict(morphs), 'skin_texture': skin_path.name if skin_path.exists() else None}
