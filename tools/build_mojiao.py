"""Build the original, editable Mojiao creature, revision 2.

Blender 4.3+: blender -b --factory-startup --python tools/build_mojiao.py
Real geometry / embedded PBR textures / hierarchical Idle, Walk and Attack clips.
This is an authored procedural game asset, not a claim of AAA finished art.
"""
from pathlib import Path
import bpy
import math
import json
import hashlib
import os
import numpy as np
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[1]
PREVIEW=ROOT.parent/'qa3d'
QA=PREVIEW/'polish-v2'
for p in [ROOT/'art',ROOT/'assets/3d',PREVIEW,QA]:p.mkdir(parents=True,exist_ok=True)
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
for m in list(bpy.data.materials):bpy.data.materials.remove(m)
scene=bpy.context.scene;scene.render.fps=30

def linear(c):return c/12.92 if c<.04045 else ((c+.055)/1.055)**2.4

def material(name,color,rough=.6,metal=0,emission=None):
    if isinstance(color,str):color=tuple(linear(int(color[i:i+2],16)/255) for i in (1,3,5))
    m=bpy.data.materials.new(name);m.use_nodes=True
    b=m.node_tree.nodes.get('Principled BSDF')
    b.inputs['Base Color'].default_value=(*color,1);b.inputs['Roughness'].default_value=rough;b.inputs['Metallic'].default_value=metal
    if emission:
        b.inputs['Emission Color'].default_value=(*emission,1);b.inputs['Emission Strength'].default_value=.25
    m.diffuse_color=(*color,1)
    return m

skin=material('Ink green • living scale hide','#263c35',.68,.015)
plate=material('Dorsal scutes • dark jade','#253c35',.68,.035)
plate_dark=material('Dorsal scutes • charcoal','#20332e',.73,.015)
plate_light=material('Dorsal scutes • weathered edges','#30463b',.67,.025)
belly=material('Ventral plates • warm basalt','#41413a',.79,.015)
horn=material('Old keratin • growth rings','#454336',.76,.015)
horn_dark=material('Horn roots • worn charcoal','#292d25',.8,0)
ivory=material('Aged fang tips','#7a7053',.55,.01)
mouth=material('Mouth and nasal recess','#0b1210',.8,0)
eye=material('Amber iris','#9b9a47',.33,.03,(.17,.16,.025))
pupil=material('Vertical pupil','#080d09',.25)

# A compact seamless scale texture: broad low relief, restrained mottle, no painted shine.
N=512;yy,xx=np.mgrid[0:N,0:N].astype(np.float32)
cy=yy/N*16;cx=xx/N*16+(np.floor(cy)%2)*.5
sx=cx%1-.5;sy=cy%1-.5
radius=(np.abs(sx/.51)**2.5+np.abs(sy/.54)**2.5)**(1/2.5)
edge=np.clip((1-radius)/.26,0,1);edge=edge*edge*(3-2*edge)
rng=np.random.default_rng(3412)
small=rng.random((64,64),dtype=np.float32)
grain=np.repeat(np.repeat(small,8,axis=0),8,axis=1)
# Smooth grain without a costly dependency; periodic rolls preserve tile borders.
for _ in range(4):grain=(grain+np.roll(grain,1,0)+np.roll(grain,-1,0)+np.roll(grain,1,1)+np.roll(grain,-1,1))/5
mottle=.045*np.sin(xx*.037+np.sin(yy*.028))+.03*np.cos(yy*.049+xx*.013)
height=edge*.29+(grain-.5)*.025
gy,gx=np.gradient(height)
norm=np.stack([-gx*2.4,gy*2.4,np.ones_like(gx)],axis=-1);norm/=np.linalg.norm(norm,axis=-1,keepdims=True)
normal=np.concatenate([norm*.5+.5,np.ones((N,N,1),dtype=np.float32)],axis=-1)
color=np.zeros((N,N,4),dtype=np.float32)
for i,b in enumerate([.128,.192,.154]):color[:,:,i]=np.clip(b*(.88+edge*.16+mottle)+(grain-.5)*.010,0,1)
color[:,:,3]=1
rough=np.ones_like(color);rough[:,:,:3]=(.77-edge*.08+(grain-.5)*.045)[:,:,None]

def packed_texture(name,values,color_space):
    im=bpy.data.images.new(name,width=N,height=N,alpha=True)
    im.colorspace_settings.name=color_space;im.pixels.foreach_set(values.ravel());im.update()
    im.filepath_raw=str(QA/(name+'.png'));im.file_format='PNG';im.save();im.pack();return im

skin_images=[packed_texture('mojiao-v2-hide-color',color,'sRGB'),packed_texture('mojiao-v2-hide-normal',normal,'Non-Color'),packed_texture('mojiao-v2-hide-roughness',rough,'Non-Color')]
bsdf=skin.node_tree.nodes.get('Principled BSDF')
for i,im in enumerate(skin_images):
    tex=skin.node_tree.nodes.new('ShaderNodeTexImage');tex.image=im;tex.extension='REPEAT'
    if i==0:skin.node_tree.links.new(tex.outputs['Color'],bsdf.inputs['Base Color'])
    elif i==1:
        nm=skin.node_tree.nodes.new('ShaderNodeNormalMap');nm.inputs['Strength'].default_value=.45
        skin.node_tree.links.new(tex.outputs['Color'],nm.inputs['Color']);skin.node_tree.links.new(nm.outputs['Normal'],bsdf.inputs['Normal'])
    else:skin.node_tree.links.new(tex.outputs['Color'],bsdf.inputs['Roughness'])

model_objects=[];nodes={}
def node(name,point,parent=None):
    ob=bpy.data.objects.new(name,None);bpy.context.collection.objects.link(ob);ob.empty_display_size=.10;ob.location=point
    if parent:
        bpy.context.view_layer.update();ob.parent=parent;ob.matrix_parent_inverse=parent.matrix_world.inverted()
    model_objects.append(ob);nodes[name]=ob;bpy.context.view_layer.update();return ob

root=node('Mojiao',(0,0,0));body_node=node('body',(0,0,.84),root)
head_node=node('head',(0,-.95,1.08),body_node);jaw_node=node('jaw',(0,-1.22,.98),head_node)

def adopt(ob,parent):
    if parent:
        bpy.context.view_layer.update();ob.parent=parent;ob.matrix_parent_inverse=parent.matrix_world.inverted()
    model_objects.append(ob);return ob

def mesh(name,verts,faces,mat,parent,uv=None,smooth=True):
    data=bpy.data.meshes.new(name);data.from_pydata(verts,[],faces);data.materials.append(mat);data.update()
    ob=bpy.data.objects.new(name,data);bpy.context.collection.objects.link(ob)
    for p in data.polygons:p.use_smooth=smooth
    if uv:
        lay=data.uv_layers.new(name='ScaleUV')
        for face in data.polygons:
            for li in face.loop_indices:lay.data[li].uv=uv[data.loops[li].vertex_index]
            # Loft/tube end rings share one longitudinal UV coordinate. Give only
            # those collapsed caps their own face projection so tangent-space
            # normal maps have two independent directions; retain side UVs.
            loops=list(face.loop_indices)
            coordinates=[lay.data[li].uv.copy() for li in loops]
            area=sum(a.x*b.y-b.x*a.y for a,b in zip(coordinates,coordinates[1:]+coordinates[:1]))
            if abs(area)<1e-10 and face.area>1e-10:
                normal=face.normal.normalized()
                guide=Vector((0,0,1)) if abs(normal.z)<.94 else Vector((0,1,0))
                u=guide.cross(normal).normalized();v=normal.cross(u).normalized()
                origin=data.vertices[face.vertices[0]].co
                for li in loops:
                    delta=data.vertices[data.loops[li].vertex_index].co-origin
                    lay.data[li].uv=(delta.dot(u),delta.dot(v))
    return adopt(ob,parent)

def catmull(a,b,c,d,t):return .5*((2*b)+(-a+c)*t+(2*a-5*b+4*c-d)*t*t+(-a+3*b-3*c+d)*t*t*t)

def smooth_path(points,radii,steps=4):
    points=[Vector(p) for p in points];radii=[Vector((r,r)) if isinstance(r,(int,float)) else Vector(r) for r in radii]
    out=[];rs=[]
    for i in range(len(points)-1):
        for k in range(steps):
            t=k/steps
            out.append(catmull(points[max(0,i-1)],points[i],points[i+1],points[min(i+2,len(points)-1)],t))
            rr=catmull(radii[max(0,i-1)],radii[i],radii[i+1],radii[min(i+2,len(points)-1)],t)
            rs.append((max(.0005,rr.x),max(.0005,rr.y)))
    out.append(points[-1]);rs.append(tuple(radii[-1]));return out,rs

def tube(name,points,radii,mat,parent,sides=18,steps=3,rings=0):
    centers,rs=smooth_path(points,radii,steps);verts=[];faces=[];uv=[]
    distances=[0]
    for i in range(1,len(centers)):distances.append(distances[-1]+(centers[i]-centers[i-1]).length)
    u=None
    for i,c in enumerate(centers):
        t=(centers[min(i+1,len(centers)-1)]-centers[max(0,i-1)]).normalized()
        if u is None:
            guide=Vector((0,0,1)) if abs(t.z)<.94 else Vector((0,1,0));u=t.cross(guide).normalized()
        else:u=(u-t*u.dot(t)).normalized()
        v=t.cross(u).normalized();rx,ry=rs[i]
        growth=1+.065*math.sin(i/max(1,len(centers)-1)*math.pi*rings*2) if rings else 1
        for j in range(sides+1):
            a=j*math.tau/sides
            verts.append(tuple(c+u*math.cos(a)*rx*growth+v*math.sin(a)*ry*growth))
            uv.append((j/sides*math.tau*(rx+ry)/2,distances[i]))
            if i<len(centers)-1 and j<sides:
                k=i*(sides+1)+j;faces.append((k,k+1,k+sides+2,k+sides+1))
    faces.append(tuple(reversed(range(sides))))
    faces.append(tuple((len(centers)-1)*(sides+1)+j for j in range(sides)))
    return mesh(name,verts,faces,mat,parent,uv)

def sphere(name,point,size,mat,parent,segments=24,rings=12):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments,ring_count=rings,location=point)
    ob=bpy.context.object;ob.name=name;ob.scale=size;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    ob.data.materials.append(mat)
    for p in ob.data.polygons:p.use_smooth=True
    # Approximate metres for consistent scale pores on all rounded anatomy.
    if ob.data.uv_layers:
        factor=max(size)*math.tau
        for loop in ob.data.uv_layers.active.data:loop.uv*=factor
    return adopt(ob,parent)

# Cross-sections are smooth in Y. Their analytic surfaces are also used for armour.
body_profile=[(-1.05,1.04,.24,.27),(-.82,1.03,.35,.34),(-.57,.92,.47,.39),(-.24,.84,.53,.41),(.15,.80,.51,.39),(.5,.77,.46,.36),(.8,.77,.40,.34),(1.03,.76,.28,.25),(1.20,.75,.18,.17)]
head_profile=[(-2.335,1.015,.007,.012),(-2.305,1.015,.09,.055),(-2.28,1.015,.17,.085),(-2.17,1.025,.235,.105),(-1.97,1.06,.27,.125),(-1.78,1.12,.30,.16),(-1.58,1.20,.34,.235),(-1.35,1.23,.345,.27),(-1.15,1.19,.30,.26),(-.95,1.105,.22,.22)]

def dims(profile,y):
    y=max(profile[0][0],min(profile[-1][0],y))
    for i in range(len(profile)-1):
        if profile[i][0]<=y<=profile[i+1][0]:
            t=(y-profile[i][0])/(profile[i+1][0]-profile[i][0])
            a=Vector(profile[max(0,i-1)][1:]);b=Vector(profile[i][1:]);c=Vector(profile[i+1][1:]);d=Vector(profile[min(i+2,len(profile)-1)][1:])
            p=catmull(a,b,c,d,t);return p.x,max(.02,p.y),max(.02,p.z)
    return profile[-1][1:]

def surface_point(profile,y,a):
    z,rx,rz=dims(profile,y);sn=math.sin(a);cs=math.cos(a)
    if profile is head_profile:
        x=math.copysign(abs(sn)**.75,sn)*rx
        zz=z+math.copysign(abs(cs)**.85,cs)*rz
        # Two shallow recessed nares are part of the skull surface.
        dent=sum(.013*math.exp(-((y+2.18)/.033)**2-((a-side*.60)/.14)**2) for side in [-1,1])
        return Vector((x-sn*dent,y,zz-cs*dent))
    if profile is not body_profile:
        # Broad chin planes, not an elliptical pipe around the mouth.
        return Vector((math.copysign(abs(sn)**.55,sn)*rx,y,z+math.copysign(abs(cs)**.65,cs)*rz))
    return Vector((sn*rx,y,z+cs*rz))

def surface(profile,y,a):
    p=surface_point(profile,y,a);e=.001
    across=(surface_point(profile,y,a+e)-surface_point(profile,y,a-e))/(2*e)
    along=(surface_point(profile,y+e,a)-surface_point(profile,y-e,a))/(2*e)
    n=across.cross(along).normalized()
    if n.length<.1:n=Vector((math.sin(a),0,math.cos(a)))
    return p,n

def loft(name,profile,mat,parent,rows=48,sides=40):
    verts=[];uv=[];faces=[]
    for i in range(rows+1):
        y=profile[0][0]+(profile[-1][0]-profile[0][0])*i/rows;z,rx,rz=dims(profile,y)
        for j in range(sides+1):
            a=j*math.tau/sides;p,n=surface(profile,y,a)
            verts.append(tuple(p));uv.append((j/sides*math.pi*(rx+rz),y-profile[0][0]))
            if i<rows and j<sides:
                k=i*(sides+1)+j;faces.append((k,k+sides+1,k+sides+2,k+1))
    # Positive outward normals: surface across x along points out.
    faces.append(tuple(range(sides)))
    faces.append(tuple((rows)*(sides+1)+j for j in range(sides-1,-1,-1)))
    return mesh(name,verts,faces,mat,parent,uv)

loft('Torso • low stalking ribcage',body_profile,skin,body_node)
loft('Skull • continuous cranial and snout planes',head_profile,skin,head_node,48,40)

class Scutes:
    """Closed, rounded scales sampled on the anatomical surface; no flat shards."""
    def __init__(self):self.v=[];self.f=[]
    def add(self,profile,y,a,width,length,thickness=.008):
        z,rx,rz=dims(profile,y);radius=max(.09,math.hypot(rx*math.cos(a),rz*math.sin(a)))
        start=len(self.v);segments=10
        # Rounded teardrop, narrowing toward the tail. Three rings round the bevel.
        for ring,bulge in [(1,0),(.84,.68),(.45,1)]:
            for k in range(segments):
                t=k*math.tau/segments
                longitudinal=math.cos(t)
                lateral=math.sin(t)*(.78-.22*longitudinal)
                yp=y+longitudinal*length*.5*ring
                ap=a+lateral*width*.5/radius*ring
                p,n=surface(profile,yp,ap)
                self.v.append(tuple(p+n*(.002+thickness*bulge)))
        p,n=surface(profile,y-length*.045,a);self.v.append(tuple(p+n*(.002+thickness*1.12)));center=start+segments*3
        # In this ordering the boundary follows tail → right flank → neck.
        for ring in range(2):
            for k in range(segments):
                a0=start+ring*segments+k;b0=start+ring*segments+(k+1)%segments
                self.f.append((a0,b0,b0+segments,a0+segments))
        for k in range(segments):self.f.append((start+2*segments+k,start+2*segments+(k+1)%segments,center))
        # Close underside just below skin. Shared curved boundary eliminates black gaps.
        for k in range(segments):
            p=Vector(self.v[start+k]);_,n=surface(profile,y,a);self.v.append(tuple(p-n*.006))
        bottom=center+1
        for k in range(segments):self.f.append((start+(k+1)%segments,start+k,bottom+k,bottom+(k+1)%segments))
        self.f.append(tuple(bottom+k for k in range(segments-1,-1,-1)))
    def build(self,name,mat,parent):
        ob=mesh(name,self.v,self.f,mat,parent)
        # Recalculate all face normals after closing separate shells.
        bpy.context.view_layer.objects.active=ob;ob.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='SELECT');bpy.ops.mesh.normals_make_consistent(inside=False);bpy.ops.object.mode_set(mode='OBJECT');ob.select_set(False)
        return ob

courses=[Scutes(),Scutes(),Scutes()]
for row in range(24):
    y=-.93+row*.083
    z,rx,rz=dims(body_profile,y)
    for col in range(15):
        a=-1.38+col*.197+(row%2)*.065
        courses[(row+col*2)%3].add(body_profile,y,a,.105 if abs(a)<.8 else .09,.123,.007 if abs(a)<.9 else .0045)
for i,(s,m) in enumerate(zip(courses,[plate,plate_dark,plate_light])):s.build('Fitted overlapping dorsal scutes '+str(i),m,body_node)

# Belly scales remain broad, shallow and horizontal.
ventral=Scutes()
for row in range(15):
    y=-.69+row*.112;z,rx,rz=dims(body_profile,y)
    for a in [math.pi-.40,math.pi,math.pi+.40]:ventral.add(body_profile,y,a,rx*.54,.14,.004)
ventral.build('Broad ventral scale courses',belly,body_node)

# Broad short nuchal/spinal crests follow a smooth silhouette, never a row of cones.
for i in range(9):
    y=-.80+i*.22;z,rx,rz=dims(body_profile,y);h=.12+.045*math.sin(i/8*math.pi)
    tube('Swept dorsal crest %02d'%i,[(0,y,z+rz-.025),(0,y+.04,z+rz+h*.65),(0,y+.16,z+rz+h)],[(.047,.085),(.032,.055),(.001,.001)],horn,body_node,14,4)

# Thick closed lower jaw replaces the toy-like white smile. Jaw remains independently animated.
jaw_profile=[(-2.285,.93,.01,.012),(-2.265,.925,.10,.04),(-2.25,.925,.155,.05),(-2.12,.92,.218,.068),(-1.90,.925,.25,.08),(-1.65,.94,.28,.09),(-1.42,.995,.29,.13),(-1.22,1.02,.21,.15)]
loft('Mandible • deep continuous lower jaw',jaw_profile,skin,jaw_node,32,32)
# A dark tapered mouth seam and skin lip sit tightly against the jaw line.
for side in [-1,1]:
    tube('Mouth seam '+str(side),[(side*.15,-2.255,.968),(side*.235,-2.10,.981),(side*.27,-1.86,1.0),(side*.29,-1.63,1.02),(side*.29,-1.50,1.015)],[.003,.004,.005,.006,.001],mouth,head_node,10,4)

# Broad forehead armour uses the same skull surface as its support, not a flat stack.
skull=Scutes()
for row in range(8):
    y=-2.06+row*.118
    for col in range(5):skull.add(head_profile,y,(col-2)*.31+(row%2)*.08,.09,.145,.008)
skull.build('Cranial shields • close fitting',plate,head_node)

for side in [-1,1]:
    # Temporal muscle, cheek arch and swept cheek horn make a reptile skull.
    tube('Temporal cheek arch '+str(side),[(side*.245,-1.78,1.15),(side*.30,-1.53,1.17),(side*.31,-1.29,1.18),(side*.25,-1.06,1.10)],[(.008,.01),(.05,.065),(.075,.10),(.012,.015)],skin,head_node,18,4)
    tube('Cheek horn '+str(side),[(side*.32,-1.38,1.20),(side*.43,-1.10,1.28),(side*.53,-.86,1.25)],[(.075,.055),(.055,.035),(.002,.002)],horn,head_node,18,7,rings=8)
    # Half-buried small eyes: both eyelids wrap over the eyeball.
    eye_point=(side*.325,-1.565,1.305)
    sphere('Eye socket '+str(side),eye_point,(.021,.065,.040),mouth,head_node)
    sphere('Amber eye '+str(side),(side*.340,-1.565,1.309),(.016,.042,.023),eye,head_node)
    sphere('Pupil '+str(side),(side*.355,-1.572,1.309),(.0035,.007,.018),pupil,head_node,16,10)
    tube('Upper orbital brow '+str(side),[(side*.302,-1.67,1.335),(side*.35,-1.60,1.352),(side*.36,-1.50,1.36),(side*.33,-1.36,1.38)],[(.012,.012),(.028,.020),(.030,.022),(.012,.012)],plate_dark,head_node,16,5)
    tube('Lower eyelid '+str(side),[(side*.321,-1.63,1.297),(side*.351,-1.57,1.285),(side*.349,-1.51,1.298)],[.012,.014,.011],skin,head_node,12,5)
    # Curved keratin horns with real transverse growth ridges and a tapered base.
    horn_points=[(side*.22,-1.25,1.44),(side*.31,-1.03,1.60),(side*.39,-.78,1.77),(side*.45,-.49,1.84),(side*.48,-.20,1.79),(side*.50,-.06,1.72)]
    tube('Curved crown horn '+str(side),horn_points,[.126,.108,.078,.047,.023,.0015],horn,head_node,24,9,rings=19)
    # Recessed nostril with a rim, not a black ball stuck onto a snout.
    # The dark liner follows the real indentation; its edge is inside the skull.
    nasal=[]
    for k in range(17):
        t=k*math.tau/16;yp=-2.18+math.sin(t)*.020;ap=side*.60+math.cos(t)*.080
        pp,nn=surface(head_profile,yp,ap);nasal.append(tuple(pp+nn*.0006))
    nasal.append(tuple(surface(head_profile,-2.18,side*.60)[0]+surface(head_profile,-2.18,side*.60)[1]*.0007))
    mesh('Recessed nostril liner '+str(side),nasal,[(k,k+1,17) for k in range(16)],mouth,head_node)
    # A restrained pair of long, low barbels keeps the xianxia dragon identity.
    tube('Sensory barbel '+str(side),[(side*.20,-2.06,.98),(side*.34,-2.15,.91),(side*.49,-2.12,.84),(side*.62,-1.96,.81)],[.021,.016,.010,.0015],horn,head_node,12,5)
    # Two upper fangs and one lower fang per side; no repeated white grin.
    for j,(y,x,z,h) in enumerate([(-1.74,.264,1.035,.095),(-1.97,.238,.997,.05)]):
        tube('Upper fang %s %s'%(side,j),[(side*x,y,z),(side*(x+.004),y-.008,z-h*.52),(side*(x-.012),y-.026,z-h)],[.024 if j==0 else .016,.016 if j==0 else .011,.001],ivory,head_node,12,5)
    tube('Lower canine '+str(side),[(side*.28,-1.57,.995),(side*.279,-1.61,1.047),(side*.265,-1.63,1.073)],[.02,.013,.001],ivory,jaw_node,12,5)

# Four low, weight-bearing articulated legs; overlapping smooth muscle volumes.
leg_nodes=[];leg_info=[]
for front in [True,False]:
    for side,suffix in [(-1,'L'),(1,'R')]:
        name=('front' if front else 'rear')+'_leg_'+suffix
        shoulder=(side*.36,-.55,.96) if front else (side*.34,.66,.84)
        elbow=(side*.72,-.35,.49) if front else (side*.74,1.02,.46)
        wrist=(side*.70,-.91,.15) if front else (side*.72,.51,.15)
        foot=(side*.74,-1.07,.075) if front else (side*.77,.32,.075)
        upper=node(name,shoulder,body_node);lower=node(name+'_lower',elbow,upper);leg_nodes.append(upper)
        foot_node=node(name+'_foot',foot,lower)
        leg_info.append({'name':name,'upper':upper,'lower':lower,'foot_node':foot_node,'hip':Vector(shoulder),'elbow':Vector(elbow),'foot':Vector(foot)})
        mid=(side*.57,shoulder[1]+(.08 if front else .13),.74 if front else .67)
        tube(name+' • scapula and biceps',[shoulder,mid,elbow],[(.245,.23),(.22,.22),(.14,.15)],skin,upper,26,7)
        middle=(side*.75,(elbow[1]+wrist[1])*.5,.32)
        tube(name+' • forearm and wrist',[elbow,middle,wrist,foot],[(.145,.15),(.13,.105),(.095,.08),(.13,.06)],skin,lower,24,7)
        # A recessed tendon line along the outer forearm, fading into the ankle.
        tube(name+' • extensor tendon',[(side*.79,elbow[1]-.02,.46),(side*.83,middle[1],.31),(side*.77,wrist[1],.17)],[.026,.024,.013],plate_dark,lower,12,6)
        # Rounded elbow and shoulder shields, embedded rather than dangling planar plates.
        sphere(name+' • elbow scale',(side*.78,elbow[1]+.01,.50),(.037,.13,.13),plate,upper,22,12)
        sphere(name+' • shoulder shield',(side*.53,shoulder[1],.86 if front else .75),(.09,.21,.18),plate_dark,upper,24,12)
        tube(name+' • palm',[(foot[0],foot[1]+.15,.13),foot,(foot[0],foot[1]-.13,.055)],[(.11,.07),(.18,.065),(.17,.045)],skin,foot_node,24,6)
        for toe in [-1,0,1]:
            base_x=foot[0]+toe*.105;fy=foot[1]-.10+abs(toe)*.035
            toe_x=base_x+toe*.07;tip_x=base_x+toe*.10
            tube(name+' • toe '+str(toe),[(base_x,fy,.085),(toe_x,fy-.12,.082),(tip_x,fy-.22,.043)],[(.06,.05),(.05,.045),(.027,.025)],skin,foot_node,16,5)
            tube(name+' • talon '+str(toe),[(tip_x,fy-.20,.055),(tip_x+toe*.015,fy-.28,.052),(tip_x+toe*.025,fy-.35,.018)],[.032,.021,.001],horn,foot_node,16,6,rings=3)
        # Short inner dewclaw gives feet a purposeful asymmetry.
        tube(name+' • dewclaw',[(foot[0]-side*.16,foot[1]+.035,.14),(foot[0]-side*.23,foot[1]-.03,.095),(foot[0]-side*.23,foot[1]-.12,.05)],[.04,.029,.001],horn,foot_node,14,5)

# Smooth, articulated tail with aligned shallow scale courses.
tail_sections=[
 ([(0,1.05,.77),(.05,1.35,.70),(.20,1.68,.56)],[.22,.18,.14]),
 ([(.20,1.68,.56),(.39,2.00,.46),(.60,2.30,.47)],[.14,.11,.075]),
 ([(.60,2.30,.47),(.83,2.55,.58),(1.06,2.68,.79),(1.18,2.67,.97)],[.075,.055,.032,.0015])]
tail_parent=body_node
for i,(points,rads) in enumerate(tail_sections):
    tn=node('tail_%02d'%(i+1),points[0],tail_parent);tail_parent=tn
    tube('Tail flowing section %02d'%i,points,rads,skin,tn,28,7)
    # Small broad ridge scales hug the tail rather than standing like razor fins.
    for seg in range(len(points)-1):
        for j in range(3):
            t=(j+.2)/3;c=Vector(points[seg]).lerp(Vector(points[seg+1]),t);r=rads[seg]*(1-t)+rads[seg+1]*t
            for a in [-.65,0,.65]:
                q=c+Vector((math.sin(a)*r,0,math.cos(a)*r))
                sphere('Tail fitted shield %s %s %s %s'%(i,seg,j,a),q,(r*.33,.066,max(.004,r*.035)),plate if j%2 else plate_dark,tn,12,6)
    for j,p in enumerate(points[:-1]):
        r=rads[j];h=min(.11,r*.6)
        tube('Swept tail crest %s %s'%(i,j),[(p[0],p[1],p[2]+r-.015),(p[0],p[1]+.06,p[2]+r+h),(p[0],p[1]+.14,p[2]+r+h*.8)],[(.03,.04),(.016,.025),(.001,.001)],horn,tn,12,5)

# Compact draw calls: pieces sharing an articulation node and material become one mesh.
groups={}
for ob in model_objects:
    if ob.type=='MESH':groups.setdefault((ob.parent,ob.data.materials[0]),[]).append(ob)
for (parent,mat),parts in groups.items():
    if len(parts)<2:continue
    bpy.ops.object.select_all(action='DESELECT')
    for ob in parts:ob.select_set(True)
    bpy.context.view_layer.objects.active=parts[0];bpy.ops.object.join();bpy.context.object.name=parent.name+' • '+mat.name
model_objects=[root]+list(root.children_recursive)

animated=[body_node,head_node,jaw_node]+leg_nodes+[nodes[n.name+'_lower'] for n in leg_nodes]+[d['foot_node'] for d in leg_info]+[nodes['tail_%02d'%i] for i in range(1,4)]
base={o.name:(o.location.copy(),o.rotation_euler.copy()) for o in animated}
bpy.context.view_layer.update();body_bind_inverse=body_node.matrix_world.inverted()

def plant_feet(clip,phase):
    # Solve two segment YZ chains and counter-rotate each foot. The export is baked,
    # so no runtime constraints or IK extension are required by Three.js.
    bpy.context.view_layer.update()
    delta=body_node.matrix_world @ body_bind_inverse
    inverse_rotation=body_node.matrix_world.to_quaternion().inverted()
    for leg in leg_info:
        target=leg['foot'].copy()
        if clip=='Walk':
            offset=0 if leg['name'] in ['front_leg_L','rear_leg_R'] else math.pi
            wave=math.sin(phase+offset);target.y+=wave*.13;target.z+=max(0,wave)*.075
        hip=delta @ leg['hip'];d=inverse_rotation @ (target-hip)
        upper=leg['elbow']-leg['hip'];lower=leg['foot']-leg['elbow']
        l1=math.hypot(upper.y,upper.z);l2=math.hypot(lower.y,lower.z)
        distance=min(l1+l2-.0001,max(abs(l1-l2)+.0001,math.hypot(d.y,d.z)))
        phi=math.atan2(d.z,d.y)
        alpha=math.acos(max(-1,min(1,(l1*l1+distance*distance-l2*l2)/(2*l1*distance))))
        first=phi+alpha;second=math.atan2(d.z-l1*math.sin(first),d.y-l1*math.cos(first))
        r1=first-math.atan2(upper.z,upper.y);r2=second-math.atan2(lower.z,lower.y)-r1
        leg['upper'].rotation_euler.x=r1;leg['lower'].rotation_euler.x=r2
        leg['foot_node'].rotation_euler.x=-(body_node.rotation_euler.x+r1+r2)

for clip,end in [('Idle',120),('Walk',36),('Attack',42)]:
    first_pose=None
    for ob in animated:
        ob.animation_data_create();ob.animation_data.action=bpy.data.actions.new(ob.name+'_'+clip)
    for frame in range(1,end+1):
        f=(frame-1)/(end-1);a=f*math.tau
        for ob in animated:ob.location=base[ob.name][0];ob.rotation_euler=base[ob.name][1]
        body_node.location.z+=math.sin(a)*(.009 if clip=='Idle' else .019)
        head_node.rotation_euler.x=math.sin(a)*(.016 if clip=='Idle' else .035)
        for i in range(1,4):nodes['tail_%02d'%i].rotation_euler.z=math.sin(a-i*.55)*(.04 if clip=='Idle' else .085)
        if clip=='Attack':
            charge=math.sin(math.pi*min(f/.45,1));bite=math.sin(math.pi*max(0,min((f-.35)/.4,1)))
            body_node.rotation_euler.x=-.035*charge+.075*bite
            head_node.rotation_euler.x=-.12*charge+.18*bite
            jaw_node.rotation_euler.x=.32*charge
        plant_feet(clip,a)
        if frame==1:first_pose={o.name:(o.location.copy(),o.rotation_euler.copy()) for o in animated}
        for ob in animated:ob.keyframe_insert(data_path='location',frame=frame);ob.keyframe_insert(data_path='rotation_euler',frame=frame)
    for ob in animated:
        # Tail segments start at different phases. Closing on the bind pose creates
        # a visible snap; repeat the actual first pose, including the planted feet.
        ob.location=first_pose[ob.name][0];ob.rotation_euler=first_pose[ob.name][1]
        ob.keyframe_insert(data_path='location',frame=end);ob.keyframe_insert(data_path='rotation_euler',frame=end)
        action=ob.animation_data.action
        for fc in action.fcurves:
            for key in fc.keyframe_points:key.interpolation='LINEAR'
        track=ob.animation_data.nla_tracks.new();track.name=clip
        strip=track.strips.new(clip,1,action);strip.name=clip
        ob.animation_data.action=None;track.mute=True
scene.frame_start=1;scene.frame_end=120;scene.frame_set(1)
for ob in animated:ob.location=base[ob.name][0];ob.rotation_euler=base[ob.name][1]
bpy.context.view_layer.update()
for ob in animated:
    for track in ob.animation_data.nla_tracks:track.mute=False
bpy.ops.object.select_all(action='DESELECT')
for ob in model_objects:ob.select_set(True)
bpy.context.view_layer.objects.active=root
out=ROOT/'assets/3d/mojiao.glb'
bpy.ops.export_scene.gltf(filepath=str(out),export_format='GLB',use_selection=True,export_animations=True,export_animation_mode='NLA_TRACKS',export_force_sampling=True,export_yup=True,export_apply=False)
for ob in animated:
    for track in ob.animation_data.nla_tracks:track.mute=True
    ob.location=base[ob.name][0];ob.rotation_euler=base[ob.name][1]

# Same light/camera/AgX configuration as the first version for an honest comparison.
floor=material('Studio slate',(.018,.024,.028),.74,.08)
bpy.ops.mesh.primitive_plane_add(size=200,location=(0,0,-.015));bpy.context.object.name='Studio floor';bpy.context.object.data.materials.append(floor)
def light(name,p,power,color,size):
    data=bpy.data.lights.new(name,'AREA');data.energy=power;data.color=color;data.shape='DISK';data.size=size
    ob=bpy.data.objects.new(name,data);bpy.context.collection.objects.link(ob);ob.location=p
    ob.rotation_euler=(Vector((0,0,1))-ob.location).to_track_quat('-Z','Y').to_euler()
light('Warm key',(-4,-5,7),1250,(1,.84,.64),5)
light('Cool rim',(4,3,5),1400,(.4,.72,1),4)
light('Front fill',(4,-5,3),580,(.58,.8,1),4)
world=bpy.data.worlds.new('Mojiao studio world');world.use_nodes=True
world.node_tree.nodes['Background'].inputs[0].default_value=(.09,.12,.15,1);world.node_tree.nodes['Background'].inputs[1].default_value=.22;scene.world=world
camera_data=bpy.data.cameras.new('Presentation camera');camera=bpy.data.objects.new('Presentation camera',camera_data);bpy.context.collection.objects.link(camera)
def camera_at(location,target,scale):
    camera.location=location;camera.rotation_euler=(Vector(target)-camera.location).to_track_quat('-Z','Y').to_euler();camera.data.type='ORTHO';camera.data.ortho_scale=scale
camera_at((6.3,-7.7,4.2),(.1,.05,1.1),6.35);scene.camera=camera
scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=64;scene.cycles.use_denoising=False
scene.render.resolution_x=1200;scene.render.resolution_y=900;scene.render.resolution_percentage=100
scene.view_settings.view_transform='AgX';scene.view_settings.exposure=0;scene.render.image_settings.file_format='PNG';scene.render.filepath=str(QA/'mojiao-v2-full.png')
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'art/mojiao.blend'),compress=True)
vertices=sum(len(o.data.vertices) for o in model_objects if o.type=='MESH')
triangles=sum(sum(len(p.vertices)-2 for p in o.data.polygons) for o in model_objects if o.type=='MESH')
manifest={'asset':'Mojiao','revision':2,'blender_version':bpy.app.version_string,'source':'original procedural geometry','orientation':'Blender -Y forward, glTF +Z forward; Blender Z up to glTF Y up','vertices':vertices,'triangles':triangles,'mesh_objects':sum(o.type=='MESH' for o in model_objects),'animations':['Idle','Walk','Attack'],'glb_bytes':out.stat().st_size,'notes':'Editable articulated 3D asset with fitted closed scutes and original embedded textures; not a finished AAA character.'}
manifest.update({'animation_revision':2,'uv_revision':2,'loop_endpoints':'Exact first-pose match for all three clips','generator':'tools/build_mojiao.py','generator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'glb_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'blend_sha256':hashlib.sha256((ROOT/'art/mojiao.blend').read_bytes()).hexdigest()})
(QA/'mojiao-v2-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
(ROOT/'assets/3d/mojiao-info.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
print('MOJIAO_BUILD',json.dumps(manifest))
if os.environ.get('MOJIAO_SKIP_RENDER')!='1':
    bpy.ops.render.render(write_still=True)
    camera_at((3.3,-5.9,2.5),(0,-1.40,1.22),2.4);scene.render.filepath=str(QA/'mojiao-v2-head.png');bpy.ops.render.render(write_still=True)
    camera_at((6.3,-7.7,4.2),(.1,.05,1.1),6.35)
    for ob in animated:
        for track in ob.animation_data.nla_tracks:track.mute=track.name!='Attack'
    scene.frame_set(12);scene.render.filepath=str(QA/'mojiao-v2-attack.png');bpy.ops.render.render(write_still=True)
print('MOJIAO_FINISHED')
