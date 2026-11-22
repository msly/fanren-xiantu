"""Build the original Mojiao prototype, editable Blender source, and glTF asset.

Blender 4.3+. Run: blender -b --factory-startup --python tools/build_mojiao.py
Procedural geometry and authored PBR colours; no third-party models or textures.
The mesh is an art prototype, not a claim of production AAA character quality.
"""
from pathlib import Path
import bpy
import math
import json
import numpy as np
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
PREVIEW = ROOT.parent / 'qa3d'
for p in [ROOT/'art', ROOT/'assets/3d', PREVIEW]: p.mkdir(parents=True, exist_ok=True)
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
for m in bpy.data.materials: bpy.data.materials.remove(m)
scene=bpy.context.scene
scene.render.fps=30

def material(name, color, rough=.5, metal=0, emission=None):
    m=bpy.data.materials.new(name);m.use_nodes=True
    b=m.node_tree.nodes.get('Principled BSDF')
    b.inputs['Base Color'].default_value=(*color,1)
    b.inputs['Metallic'].default_value=metal
    b.inputs['Roughness'].default_value=rough
    if emission:
        b.inputs['Emission Color'].default_value=(*emission,1)
        b.inputs['Emission Strength'].default_value=2.2
    m.diffuse_color=(*color,1)
    return m

skin=material('Obsidian teal • hide',(.019,.058,.064),.58,.08)
plate=material('Blue jade • dorsal scales',(.012,.036,.041),.66,.10)
plate_dark=material('Obsidian • shield edges',(.009,.021,.026),.7,.06)
plate_light=material('Verdigris • scale highlight',(.018,.051,.054),.62,.10)
belly=material('Basalt • ventral armour',(.07,.105,.11),.58,.15)
horn=material('Ancient horn',(.075,.086,.076),.68,.03)
ivory=material('Worn ivory • teeth and claws',(.28,.28,.21),.59,.02)
mouth=material('Mouth cavity',(.023,.009,.012),.54)
eye=material('Jade eye',(.025,.12,.16),.35,.06,(.01,.08,.12))
pupil=material('Eye slit',(.002,.005,.008),.18)
glint=material('Subtle azure rune',(.05,.25,.31),.4,.22,(.015,.10,.15))

# A packed, repeatable skin texture adds scale pores, bevel normals and varied roughness.
texsize=512
yy,xx=np.mgrid[0:texsize,0:texsize].astype(np.float32)
cy=yy/texsize*16;cx=xx/texsize*16+(np.floor(cy)%2)*.5
dx=cx%1-.5;dy=cy%1-.5
dist=np.sqrt((dx/.5)**2+(dy/.58)**2)
edge=np.clip((1-dist)/.23,0,1);edge=edge*edge*(3-2*edge)
rng=np.random.default_rng(1928);grain=rng.random((texsize,texsize),dtype=np.float32)
height=edge*.7+grain*.025
gy,gx=np.gradient(height)
norm=np.stack([-gx*3,gy*3,np.ones_like(gx)],axis=-1);norm/=np.linalg.norm(norm,axis=-1,keepdims=True)
normal=np.concatenate([norm*.5+.5,np.ones((texsize,texsize,1),dtype=np.float32)],axis=-1)
color=np.zeros((texsize,texsize,4),dtype=np.float32)
for i,b in enumerate([.075,.145,.15]):color[:,:,i]=b*(.68+edge*.32)+(grain-.5)*.012
color[:,:,3]=1
roughness=np.ones_like(color);roughness[:,:,:3]=(.64-edge*.12+grain*.06)[:,:,None]
def packed_texture(name,values,color_space):
    im=bpy.data.images.new(name,width=texsize,height=texsize,alpha=True)
    im.colorspace_settings.name=color_space;im.pixels.foreach_set(values.ravel());im.update()
    im.filepath_raw=str(PREVIEW/(name+'.png'));im.file_format='PNG';im.save();im.pack()
    return im
skin_images=[packed_texture('mojiao-hide-color',color,'sRGB'),packed_texture('mojiao-hide-normal',normal,'Non-Color'),packed_texture('mojiao-hide-roughness',roughness,'Non-Color')]
bsdf=skin.node_tree.nodes.get('Principled BSDF')
for i,im in enumerate(skin_images):
    tex=skin.node_tree.nodes.new('ShaderNodeTexImage');tex.image=im;tex.extension='REPEAT'
    if i==0:skin.node_tree.links.new(tex.outputs['Color'],bsdf.inputs['Base Color'])
    elif i==1:
        nm=skin.node_tree.nodes.new('ShaderNodeNormalMap');nm.inputs['Strength'].default_value=.6
        skin.node_tree.links.new(tex.outputs['Color'],nm.inputs['Color']);skin.node_tree.links.new(nm.outputs['Normal'],bsdf.inputs['Normal'])
    else:skin.node_tree.links.new(tex.outputs['Color'],bsdf.inputs['Roughness'])

model_objects=[]
nodes={}
def node(name, point, parent=None):
    o=bpy.data.objects.new(name,None);bpy.context.collection.objects.link(o)
    o.empty_display_type='PLAIN_AXES';o.empty_display_size=.12
    o.location=point
    if parent:
        bpy.context.view_layer.update()
        o.parent=parent;o.matrix_parent_inverse=parent.matrix_world.inverted()
    model_objects.append(o);nodes[name]=o
    bpy.context.view_layer.update()
    return o

root=node('Mojiao',(0,0,0))
body_node=node('body',(0,0,1),root)
head_node=node('head',(0,-1.03,1.48),body_node)
jaw_node=node('jaw',(0,-1.38,1.29),head_node)

def adopt(o,parent):
    if parent:
        bpy.context.view_layer.update()
        o.parent=parent;o.matrix_parent_inverse=parent.matrix_world.inverted()
    model_objects.append(o)
    return o

def mesh(name, verts, faces, mat, parent, smooth=True):
    data=bpy.data.meshes.new(name);data.from_pydata(verts,[],faces);data.materials.append(mat);data.update()
    ob=bpy.data.objects.new(name,data);bpy.context.collection.objects.link(ob)
    for p in data.polygons:p.use_smooth=smooth
    return adopt(ob,parent)

def tube(name, centers, radii, mat, parent, sides=14):
    centers=[Vector(p) for p in centers];verts=[];faces=[]
    for i,c in enumerate(centers):
        t=(centers[min(i+1,len(centers)-1)]-centers[max(0,i-1)]).normalized()
        guide=Vector((0,0,1)) if abs(t.z)<.94 else Vector((0,1,0))
        u=t.cross(guide).normalized();v=t.cross(u).normalized()
        r=radii[i];rx,ry=(r,r) if isinstance(r,(float,int)) else r
        for j in range(sides):
            a=j*math.tau/sides
            verts.append(tuple(c+u*math.cos(a)*rx+v*math.sin(a)*ry))
    for i in range(len(centers)-1):
        for j in range(sides):
            a=i*sides+j;b=i*sides+(j+1)%sides
            faces.append((a,b,b+sides,a+sides))
    faces.append(tuple(reversed(range(sides))));faces.append(tuple((len(centers)-1)*sides+j for j in range(sides)))
    ob=mesh(name,verts,faces,mat,parent)
    uv=ob.data.uv_layers.new(name='ScaleUV')
    distances=[0.0]
    for i in range(1,len(centers)):distances.append(distances[-1]+(centers[i]-centers[i-1]).length)
    avgr=sum((r[0]+r[1])*.5 if isinstance(r,(tuple,list)) else r for r in radii)/len(radii)
    circumference=max(.3,avgr*math.tau)
    for face in ob.data.polygons:
        angles=[v%sides for v in face.vertices];wrap=0 in angles and sides-1 in angles
        for li in face.loop_indices:
            vi=ob.data.loops[li].vertex_index;j=vi%sides
            u=(1.0 if wrap and j==0 else j/sides)*circumference
            uv.data[li].uv=(u,distances[vi//sides])
    return ob

def sphere(name,p,size,mat,parent):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=20,ring_count=12,location=p)
    o=bpy.context.object;o.name=name;o.scale=size
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    o.data.materials.append(mat)
    for f in o.data.polygons:f.use_smooth=True
    return adopt(o,parent)

class Plates:
    def __init__(self):self.vertices=[];self.faces=[]
    def add(self,c,u,v,n,w,h,raise_by=.025):
        c=Vector(c);u=Vector(u).normalized();v=Vector(v).normalized();n=Vector(n).normalized()
        shape=[(-.47,-.46),(.47,-.46),(.58,.08),(0,.67),(-.58,.08)]
        idx=len(self.vertices)
        for x,y in shape:self.vertices.append(tuple(c+u*x*w+v*y*h))
        self.vertices.append(tuple(c+n*raise_by-v*h*.08))
        for j in range(5):
            tri=(idx+j,idx+(j+1)%5,idx+5)
            self.faces.append(tri if u.cross(v).dot(n)>=0 else tuple(reversed(tri)))
    def build(self,name,mat,parent):return mesh(name,self.vertices,self.faces,mat,parent,True)

# Continuous torso: shoulder, rib cage, lumbar region and pelvis.
body_profile=[(-1.03,1.38,.23,.28),(-.82,1.35,.35,.37),(-.55,1.23,.48,.46),(-.15,1.1,.5,.44),(.25,1.02,.42,.36),(.63,1.0,.42,.38),(.95,1.02,.28,.29),(1.16,1.02,.17,.19)]
tube('Torso • continuous quad surface',[(0,y,z) for y,z,rx,rz in body_profile],[(rx,rz) for y,z,rx,rz in body_profile],skin,body_node,24)

def body_dims(y):
    for i in range(len(body_profile)-1):
        a,b=body_profile[i],body_profile[i+1]
        if a[0]<=y<=b[0]:
            t=(y-a[0])/(b[0]-a[0]);return tuple(a[j]*(1-t)+b[j]*t for j in [1,2,3])
    return (1,.25,.2)

scales=[Plates(),Plates(),Plates()]
for row in range(15):
    y=-.85+row*.135;z,rx,rz=body_dims(y)
    for k in range(13):
        a=-1.5+k*.25+(row%2)*.06
        c=(math.sin(a)*rx,y,z+math.cos(a)*rz)
        n=Vector((math.sin(a)/rx,0,math.cos(a)/rz)).normalized()
        u=Vector((0,1,0)).cross(n).normalized()
        scales[(row+k)%3].add(Vector(c)+n*.018,u,(0,1,0),n,.095,.14,.008)
for i,(s,m) in enumerate(zip(scales,[plate,plate_dark,plate_light])):s.build('Dorsal scale courses '+str(i),m,body_node)

ventral=Plates()
for row in range(11):
    y=-.63+row*.15;z,rx,rz=body_dims(y)
    ventral.add((0,y,z-rz*.97),(1,0,0),(0,1,0),(0,0,-1),rx*1.55,.18,.028)
ventral.build('Segmented belly plates',belly,body_node)

for i in range(10):
    y=-.81+i*.205;z,rx,rz=body_dims(y)
    height=.26 if i<5 else .19
    tube('Dorsal crest %02d'%i,[(0,y,z+rz-.025),(0,y+.09,z+rz+height*.65),(0,y+.2,z+rz+height)], [.075,.05,.003],horn,body_node,10)

# Angular, elongated skull and cheek armour; the two jaws are independent.
tube('Head • elongated skull',[(0,-.98,1.44),(0,-1.2,1.58),(0,-1.42,1.6),(0,-1.66,1.48),(0,-1.92,1.43),(0,-2.12,1.4)],[(.23,.25),(.32,.3),(.35,.27),(.3,.2),(.235,.13),(.19,.1)],skin,head_node,24)
tube('Lower jaw',[(0,-1.35,1.29),(0,-1.53,1.22),(0,-1.83,1.22),(0,-2.09,1.29)],[(.21,.11),(.255,.09),(.21,.065),(.16,.055)],belly,jaw_node,18)
tube('Inner mouth',[(0,-1.48,1.31),(0,-1.8,1.29),(0,-2.07,1.34)],[(.20,.025),(.20,.025),(.14,.015)],mouth,jaw_node,14)
skullplates=Plates()
for row in range(5):
    y=-1.23-row*.16;zc=1.88-row*.081
    for col in range(3):
        x=(col-1)*(.14-row*.01)
        skullplates.add((x,y,zc),(1,0,0),(0,1,-.35),(x*.8,-.2,1),.17,.2,.032)
skullplates.build('Forehead and muzzle shields',plate,head_node)

for side in [-1,1]:
    # Layered cheek guard that sweeps back away from the eye.
    tube('Cheek ridge '+str(side),[(side*.26,-1.55,1.55),(side*.35,-1.31,1.58),(side*.5,-1.02,1.69),(side*.56,-.92,1.75)],[.085,.1,.07,.004],plate,head_node,10)
    sphere('Eye '+str(side),(side*.329,-1.49,1.66),(.028,.045,.029),eye,head_node)
    sphere('Pupil '+str(side),(side*.354,-1.49,1.661),(.006,.010,.024),pupil,head_node)
    tube('Heavy brow '+str(side),[(side*.29,-1.57,1.72),(side*.35,-1.49,1.74),(side*.35,-1.37,1.76),(side*.29,-1.26,1.78)],[.041,.045,.05,.022],plate_dark,head_node,10)
    tube('Crown horn '+str(side),[(side*.22,-1.23,1.8),(side*.34,-1.06,2.0),(side*.45,-.85,2.21),(side*.43,-.63,2.39),(side*.31,-.51,2.48)],[.13,.11,.075,.04,.002],horn,head_node,16)
    for j in range(4):
        z=1.87+j*.11;y=-1.18+j*.11;x=side*(.265+j*.037)
        # Dark transverse bands on the broad horn root.
        tube('Horn growth ridge %s %s'%(side,j),[(x-.04,y-.025,z),(x+.04,y+.025,z+.02)],[.014,.009],plate_dark,head_node,8)
    sphere('Nostril '+str(side),(side*.12,-2.129,1.428),(.039,.013,.022),pupil,head_node)
    tube('Nasal ridge '+str(side),[(side*.08,-2.13,1.47),(side*.13,-1.98,1.5),(side*.18,-1.82,1.56)],[.015,.022,.03],plate,head_node,8)
    tube('Long sensory barbel '+str(side),[(side*.13,-2.04,1.31),(side*.31,-2.2,1.22),(side*.51,-2.24,1.1),(side*.64,-2.14,.99)],[.025,.019,.012,.0015],horn,head_node,10)
    for j in range(7):
        y=-1.49-j*.082;x=side*(.235-j*.009);z=1.355+j*.003
        h=.10 if j not in (0,2) else .145
        tube('Upper tooth %s %s'%(side,j),[(x,y,z),(x*.96,y-.018,z-h*.6),(x*.91,y-.03,z-h)],[.028,.019,.001],ivory,head_node,8)
    for j in range(5):
        y=-1.59-j*.09;x=side*(.22-j*.013);z=1.25+j*.006
        tube('Lower tooth %s %s'%(side,j),[(x,y,z),(x*.96,y-.015,z+.065),(x*.93,y-.023,z+.09)],[.022,.014,.001],ivory,jaw_node,8)

# Four articulated legs, bent joints, broad feet and separated talons.
leg_nodes=[]
for front in [True,False]:
    for side,suffix in [(-1,'L'),(1,'R')]:
        key=('front' if front else 'rear')+'_leg_'+suffix
        shoulder=(side*.38,-.59,1.27) if front else (side*.36,.66,1.05)
        knee=(side*.65,-.58,.70) if front else (side*.67,1.03,.7)
        ankle=(side*.58,-.86,.20) if front else (side*.62,.62,.22)
        foot=(side*.61,-.99,.085) if front else (side*.65,.45,.085)
        ln=node(key,shoulder,body_node);leg_nodes.append(ln)
        low=node(key+'_lower',knee,ln)
        tube(key+' • upper', [shoulder,((shoulder[0]+knee[0])*.5,(shoulder[1]+knee[1])*.5,(shoulder[2]+knee[2])*.5),knee],[(.23,.23),(.24,.19),(.16,.16)],skin,ln,16)
        tube(key+' • lower', [knee,((knee[0]+ankle[0])*.5,(knee[1]+ankle[1])*.5,(knee[2]+ankle[2])*.5),ankle,foot],[(.16,.16),(.125,.13),(.09,.1),(.14,.065)],skin,low,14)
        sh=Plates()
        for j in range(3):
            t=(j+.4)/3;p=Vector(shoulder).lerp(Vector(knee),t)
            p.x+=side*.25
            sh.add(p,(0,1,0),(side*.1,0,-1),(side,0,.1),.27,.23,.04)
        sh.build(key+' • upper armour',plate,ln)
        arm=Plates()
        for j in range(3):
            p=Vector(knee).lerp(Vector(ankle),(j+.5)/3);p.x+=side*.145
            arm.add(p,(0,1,0),(0,0,-1),(side,0,0),.21,.18,.03)
        arm.build(key+' • shin armour',plate_dark,low)
        tube(key+' • foot',[(foot[0],foot[1]+.12,.13),foot,(foot[0],foot[1]-.17,.06)],[(.11,.065),(.18,.07),(.16,.045)],skin,low,12)
        for toe in [-1,0,1]:
            x=foot[0]+toe*.13;fy=foot[1]-.12+abs(toe)*.025
            tube(key+' • toe '+str(toe),[(x,fy,.085),(x+toe*.025,fy-.14,.07),(x+toe*.035,fy-.22,.04)],[.055,.047,.023],skin,low,10)
            tube(key+' • claw '+str(toe),[(x+toe*.03,fy-.18,.063),(x+toe*.043,fy-.27,.065),(x+toe*.05,fy-.34,.018)],[.032,.022,.001],ivory,low,10)

# Three tail sections preserve editable hierarchy and a continuous silhouette.
tail_sections=[
    ([(0,1.04,1.02),(.08,1.32,.94),(.22,1.62,.82)],[.22,.19,.145]),
    ([(.22,1.62,.82),(.38,1.92,.68),(.56,2.21,.63)],[.145,.12,.09]),
    ([(.56,2.21,.63),(.79,2.46,.7),(1.04,2.62,.88),(1.22,2.61,1.03)],[.09,.065,.04,.0015])]
tail_parent=body_node
for i,(points,rads) in enumerate(tail_sections):
    tn=node('tail_%02d'%(i+1),points[0],tail_parent);tail_parent=tn
    tube('Tail section %02d'%i,points,rads,skin,tn,16)
    plates=Plates()
    for seg in range(len(points)-1):
        for j in range(4):
            k=(j+.15)/4;center=Vector(points[seg]).lerp(Vector(points[seg+1]),k);rad=rads[seg]*(1-k)+rads[seg+1]*k
            for a in [-.8,0,.8]:
                n=Vector((math.sin(a),0,math.cos(a)));c=center+n*rad
                plates.add(c,(1,0,-math.sin(a)),(0,1,0),n,rad*.95,.13,.015)
    plates.build('Tail shields %02d'%i,plate,tn)
    for j,p in enumerate(points[:-1]):
        r=rads[j]
        tube('Tail crest %s %s'%(i,j),[(p[0],p[1],p[2]+r),(p[0],p[1]+.08,p[2]+r+.15),(p[0],p[1]+.17,p[2]+r+.18)],[.04,.028,.001],horn,tn,10)

# Very limited emissive inlays; the creature remains legible without bloom.
for side in [-1,1]:
    tube('Azure gill groove '+str(side),[(side*.35,-1.13,1.62),(side*.40,-1.01,1.5),(side*.35,-.88,1.39)],[.008,.01,.007],glint,head_node,8)

# Merge static mesh pieces that share both articulation parent and PBR material.
# This keeps horns, teeth and small scales editable without individual draw calls.
groups={}
for ob in model_objects:
    if ob.type=='MESH':groups.setdefault((ob.parent,ob.data.materials[0]),[]).append(ob)
for (parent,mat),parts in groups.items():
    if len(parts)<2:continue
    bpy.ops.object.select_all(action='DESELECT')
    for ob in parts:ob.select_set(True)
    bpy.context.view_layer.objects.active=parts[0]
    bpy.ops.object.join()
    bpy.context.object.name=parent.name+' • '+mat.name
model_objects=[root]+list(root.children_recursive)

# Named NLA clips let Three.js AnimationMixer play the authored hierarchy.
animated=[body_node,head_node,jaw_node]+leg_nodes+[nodes[n.name+'_lower'] for n in leg_nodes]+[nodes['tail_%02d'%i] for i in range(1,4)]
base={o.name:(o.location.copy(),o.rotation_euler.copy()) for o in animated}
for clip,end in [('Idle',120),('Walk',36),('Attack',42)]:
    for ob in animated:
        ob.animation_data_create();ob.animation_data.action=bpy.data.actions.new(ob.name+'_'+clip)
    for frame in range(1,end+1,3):
        f=(frame-1)/(end-1);a=f*math.tau
        for ob in animated:ob.location=base[ob.name][0];ob.rotation_euler=base[ob.name][1]
        body_node.location.z+=math.sin(a)*(.014 if clip=='Idle' else .025)
        head_node.rotation_euler.x=math.sin(a)*(.022 if clip=='Idle' else .045)
        jaw_node.rotation_euler.x=.035
        for i in range(1,4):nodes['tail_%02d'%i].rotation_euler.z=math.sin(a-i*.55)*(.055 if clip=='Idle' else .1)
        if clip=='Walk':
            for ob in leg_nodes:
                phase=0 if ob.name in ['front_leg_L','rear_leg_R'] else math.pi
                ob.rotation_euler.x=math.sin(a+phase)*.24
                nodes[ob.name+'_lower'].rotation_euler.x=max(0,-math.sin(a+phase))*.23
        if clip=='Attack':
            charge=math.sin(math.pi*min(f/.45,1))
            bite=math.sin(math.pi*max(0,min((f-.35)/.4,1)))
            body_node.rotation_euler.x=-.045*charge+.09*bite
            head_node.rotation_euler.x=-.14*charge+.22*bite
            jaw_node.rotation_euler.x=.035+.42*charge-.035*bite
        for ob in animated:
            ob.keyframe_insert(data_path='location',frame=frame)
            ob.keyframe_insert(data_path='rotation_euler',frame=frame)
    # Explicit loop endpoint avoids drift when ActionSampler reaches the final key.
    for ob in animated:
        ob.location=base[ob.name][0];ob.rotation_euler=base[ob.name][1]
        if ob is jaw_node:ob.rotation_euler.x=.035
        ob.keyframe_insert(data_path='location',frame=end)
        ob.keyframe_insert(data_path='rotation_euler',frame=end)
        action=ob.animation_data.action
        for fc in action.fcurves:
            for key in fc.keyframe_points:key.interpolation='BEZIER'
        tr=ob.animation_data.nla_tracks.new();tr.name=clip
        strip=tr.strips.new(clip,1,action);strip.name=clip
        ob.animation_data.action=None;tr.mute=True

scene.frame_start=1;scene.frame_end=120;scene.frame_set(1)
for ob in animated:
    ob.location=base[ob.name][0];ob.rotation_euler=base[ob.name][1]
jaw_node.rotation_euler.x=.035
bpy.context.view_layer.update()

# Export model only. NLA tracks are temporarily unmuted for named clip discovery.
for ob in animated:
    for tr in ob.animation_data.nla_tracks:tr.mute=False
bpy.ops.object.select_all(action='DESELECT')
for ob in model_objects:ob.select_set(True)
bpy.context.view_layer.objects.active=root
out=ROOT/'assets/3d/mojiao.glb'
bpy.ops.export_scene.gltf(filepath=str(out),export_format='GLB',use_selection=True,export_animations=True,export_animation_mode='NLA_TRACKS',export_force_sampling=True,export_yup=True,export_apply=False)
for ob in animated:
    for tr in ob.animation_data.nla_tracks:tr.mute=True
    ob.location=base[ob.name][0];ob.rotation_euler=base[ob.name][1]
jaw_node.rotation_euler.x=.035

# A reproducible studio render is included in the editable .blend presentation.
floor=material('Studio slate',(.018,.024,.028),.74,.08)
bpy.ops.mesh.primitive_plane_add(size=200,location=(0,0,-.015));bpy.context.object.name='Studio floor';bpy.context.object.data.materials.append(floor)
def light(name,p,power,color,size):
    data=bpy.data.lights.new(name,'AREA');data.energy=power;data.color=color;data.shape='DISK';data.size=size
    o=bpy.data.objects.new(name,data);bpy.context.collection.objects.link(o);o.location=p
    o.rotation_euler=(Vector((0,0,1))-o.location).to_track_quat('-Z','Y').to_euler()
light('Warm key',(-4,-5,7),1250,(1,.84,.64),5)
light('Cool rim',(4,3,5),1400,(.4,.72,1),4)
light('Front fill',(4,-5,3),580,(.58,.8,1),4)
world=bpy.data.worlds.new('Mojiao studio world');world.use_nodes=True;world.node_tree.nodes['Background'].inputs[0].default_value=(.09,.12,.15,1);world.node_tree.nodes['Background'].inputs[1].default_value=.22;scene.world=world
camera_data=bpy.data.cameras.new('Presentation camera');camera=bpy.data.objects.new('Presentation camera',camera_data);bpy.context.collection.objects.link(camera)
camera.location=(6.3,-7.7,4.2);target=Vector((.1,.05,1.1));camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler();camera.data.type='ORTHO';camera.data.ortho_scale=6.35;scene.camera=camera
scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=64;scene.cycles.use_denoising=False
scene.render.resolution_x=1200;scene.render.resolution_y=900;scene.render.resolution_percentage=100
scene.view_settings.view_transform='AgX';scene.render.image_settings.file_format='PNG';scene.render.filepath=str(PREVIEW/'mojiao-preview.png')
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'art/mojiao.blend'),compress=True)
vertices=sum(len(o.data.vertices) for o in model_objects if o.type=='MESH')
triangles=sum(sum(len(p.vertices)-2 for p in o.data.polygons) for o in model_objects if o.type=='MESH')
manifest={'asset':'Mojiao','blender_version':bpy.app.version_string,'source':'original procedural geometry','orientation':'Blender -Y forward, glTF +Z forward; Blender Z up to glTF Y up','vertices':vertices,'triangles':triangles,'mesh_objects':sum(o.type=='MESH' for o in model_objects),'animations':['Idle','Walk','Attack'],'glb_bytes':out.stat().st_size,'notes':'Editable layered mesh and articulated transform animation; production-style prototype, not a AAA finished asset.'}
(PREVIEW/'mojiao-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
print('MOJIAO_BUILD',json.dumps(manifest))
bpy.ops.render.render(write_still=True)
print('MOJIAO_PREVIEW',scene.render.filepath)
