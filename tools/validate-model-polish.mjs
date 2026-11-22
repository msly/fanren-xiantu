/**
 * Additional, reproducible motion checks for the actual exported game GLBs.
 * Run after validate-assets.mjs; that script validates weights, PNG pixels,
 * normal-map contents, material colour spaces and all geometry attributes.
 *
 * node tools/validate-model-polish.mjs [report.json] [asset-directory]
 * Requires Node 20+ and @napi-rs/canvas. No browser or GPU is created.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
import * as THREE from '../vendor/three/build/three.module.js';
import {GLTFLoader} from '../vendor/three/addons/loaders/GLTFLoader.js';

const require=createRequire(import.meta.url),{loadImage}=require('@napi-rs/canvas');
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const out=path.resolve(process.argv[2]||path.join(root,'../qa3d/model-polish-validation.json'));
const assetRoot=path.resolve(process.argv[3]||path.join(root,'assets/3d'));
globalThis.self=globalThis;
globalThis.ProgressEvent??=class extends Event {constructor(type,init={}){super(type);Object.assign(this,init)}};
globalThis.createImageBitmap=async blob=>{
  const image=await loadImage(Buffer.from(await blob.arrayBuffer()));image.close=()=>{};return image;
};

const footHz=60,wholeMeshSamples=25,groundTolerance=.005,loopTolerance=.01;
const hanliWalkSupportClearance=.012;
const round=n=>Math.round(n*1e7)/1e7;
const v3=v=>v.toArray().map(round);
const boxData=box=>({min:v3(box.min),max:v3(box.max),size:v3(box.getSize(new THREE.Vector3()))});
const finite=(values,label)=>assert(values.every(Number.isFinite),label+' contains non-finite numbers');
const warnings=[],errors=[];
const check=(condition,message)=>{if(!condition)errors.push(message)};

function texturedUVCheck(mesh){
  const g=mesh.geometry,material=mesh.material;
  if(!material.normalMap)return null;
  const uvName=material.normalMap.channel?'uv'+material.normalMap.channel:'uv';
  const uv=g.getAttribute(uvName),pos=g.getAttribute('position');
  assert(uv,mesh.name+' normal texture has no '+uvName);
  const index=g.index,count=index?index.count:pos.count;
  let triangles=0,singular=0,totalArea=0,singularArea=0;
  const a=new THREE.Vector3(),b=new THREE.Vector3(),c=new THREE.Vector3();
  for(let n=0;n<count;n+=3){
    const ia=index?index.getX(n):n,ib=index?index.getX(n+1):n+1,ic=index?index.getX(n+2):n+2;
    a.fromBufferAttribute(pos,ia);b.fromBufferAttribute(pos,ib);c.fromBufferAttribute(pos,ic);
    const area=b.sub(a).cross(c.sub(a)).length()*.5;
    if(area<1e-12)continue;
    const du1=uv.getX(ib)-uv.getX(ia),dv1=uv.getY(ib)-uv.getY(ia);
    const du2=uv.getX(ic)-uv.getX(ia),dv2=uv.getY(ic)-uv.getY(ia);
    triangles++;totalArea+=area;
    if(Math.abs(du1*dv2-du2*dv1)<1e-12){singular++;singularArea+=area}
  }
  check(triangles>0&&singular<triangles,mesh.name+' has no usable tangent UV triangles');
  if(singularArea/totalArea>.01)warnings.push(mesh.name+' has singular normal-map UVs on '+round(singularArea/totalArea*100)+'% of geometric area; includes closed caps');
  return {mesh:mesh.name,material:material.name,uv:uvName,triangles,singularTriangles:singular,singularAreaFraction:round(singularArea/totalArea)};
}

function selectFeet(name,meshes){
  const groups=new Map();
  if(name==='hanli'){
    for(const mesh of meshes){
      if(!mesh.isSkinnedMesh||!/boot soles/i.test(mesh.material.name))continue;
      const indices=mesh.geometry.getAttribute('skinIndex'),weights=mesh.geometry.getAttribute('skinWeight');
      for(let i=0;i<indices.count;i++){
        let weight=0,bone='';
        for(let j=0;j<4;j++){
          const k=i*4+j,n=mesh.skeleton.bones[indices.array[k]].name,w=weights.array[k];
          if(/^foot[._]?[LR]$/.test(n)&&w>weight){weight=w;bone=n}
        }
        if(weight>=.5){if(!groups.has(bone))groups.set(bone,[]);groups.get(bone).push({mesh,index:i})}
      }
    }
    assert.equal(groups.size,2,'Hanli must have two independently selected sole groups');
  }else{
    for(const mesh of meshes){
      const group=mesh.name.match(/^(front|rear)_leg_[LR]_foot/)?.[0];if(!group)continue;
      if(!groups.has(group))groups.set(group,[]);
      for(let index=0;index<mesh.geometry.getAttribute('position').count;index++)groups.get(group).push({mesh,index});
    }
    assert.equal(groups.size,4,'Mojiao must have four independently selected foot groups');
  }
  for(const [group,vertices] of groups)assert(vertices.length>=20,group+' has too few foot vertices');
  return groups;
}

function update(model){
  model.updateMatrixWorld(true);
  model.traverse(o=>{finite(o.matrixWorld.elements,o.name+' matrix');if(o.isSkinnedMesh){o.skeleton.update();finite(o.skeleton.boneMatrices,o.name+' skin matrix')}});
}
const point=new THREE.Vector3();
function footPositions(groups){
  const result={};
  for(const [group,vertices] of groups){
    let min=Infinity;
    for(const {mesh,index} of vertices){mesh.getVertexPosition(index,point).applyMatrix4(mesh.matrixWorld);finite(point.toArray(),group+' posed foot');min=Math.min(min,point.y)}
    result[group]=min;
  }
  return result;
}
function capture(meshes,all=false){
  const values=[];
  for(const mesh of meshes){
    const n=mesh.geometry.getAttribute('position').count,step=all?1:Math.max(1,Math.floor(n/40));
    for(let i=0;i<n;i+=step){mesh.getVertexPosition(i,point).applyMatrix4(mesh.matrixWorld);values.push(point.x,point.y,point.z)}
  }
  finite(values,'posed geometry');return Float64Array.from(values);
}
function maximumDifference(a,b){
  assert.equal(a.length,b.length);let maximum=0;
  for(let i=0;i<a.length;i+=3)maximum=Math.max(maximum,Math.hypot(a[i]-b[i],a[i+1]-b[i+1],a[i+2]-b[i+2]));
  return maximum;
}

async function validate(name){
  const bytes=await fs.readFile(path.join(assetRoot,name+'.glb'));
  const gltf=await new GLTFLoader().parseAsync(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength),'');
  const model=gltf.scene,mixer=new THREE.AnimationMixer(model),meshes=[];
  model.traverse(o=>{if(o.isMesh)meshes.push(o)});
  const feet=selectFeet(name,meshes),uvChecks=meshes.map(texturedUVCheck).filter(Boolean);
  update(model);
  const origin=model.position.clone(),rotation=model.quaternion.clone(),scale=model.scale.clone();
  const report={file:name+'.glb',sha256:crypto.createHash('sha256').update(bytes).digest('hex'),bytes:bytes.length,
    footSelection:name==='hanli'?'Every Boot soles vertex with at least 0.5 weight on footL/footR (exported bone names).':'Every vertex in the four front/rear leg L/R foot meshes, including hide and claws; forearms are excluded from foot contact.',
    footVertexCounts:Object.fromEntries([...feet].map(([key,vertices])=>[key,vertices.length])),normalMappedUVs:uvChecks,clips:[]};
  function setClip(clip){mixer.stopAllAction();mixer.setTime(0);const a=mixer.clipAction(clip).reset().setLoop(THREE.LoopOnce,1);a.clampWhenFinished=true;a.play();mixer.setTime(0);update(model)}
  for(const clip of gltf.animations){
    setClip(clip);
    const first=capture(meshes,true),initial=capture(meshes),bounds=new THREE.Box3(),counts=Math.ceil(clip.duration*footHz)+1;
    const result={name:clip.name,duration:round(clip.duration),footSamples:counts,wholeMeshSamples,
      footMinY:Infinity,footMaxLowestY:-Infinity,worstFoot:{},perFootMinY:Object.fromEntries([...feet.keys()].map(key=>[key,Infinity])),wholeGeometryMinY:Infinity,maxSampledVertexMovementM:0};
    for(let i=0;i<counts;i++){
      const time=Math.min(i/footHz,clip.duration-1e-7);mixer.setTime(time);update(model);
      const positions=footPositions(feet),lowest=Math.min(...Object.values(positions));
      result.footMaxLowestY=Math.max(result.footMaxLowestY,lowest);
      for(const [foot,y] of Object.entries(positions)){
        result.perFootMinY[foot]=Math.min(result.perFootMinY[foot],y);
        if(y<result.footMinY){result.footMinY=y;result.worstFoot={time:round(time),foot,y:round(y)}}
      }
      assert(model.position.distanceTo(origin)<1e-8&&model.quaternion.angleTo(rotation)<1e-7&&model.scale.distanceTo(scale)<1e-8,clip.name+' moved the model scene root');
    }
    for(let i=0;i<wholeMeshSamples;i++){
      mixer.setTime((clip.duration-1e-7)*i/(wholeMeshSamples-1));update(model);
      const b=new THREE.Box3().setFromObject(model,true);finite([...b.min.toArray(),...b.max.toArray()],clip.name+' full bounds');bounds.union(b);
      result.wholeGeometryMinY=Math.min(result.wholeGeometryMinY,b.min.y);
      result.maxSampledVertexMovementM=Math.max(result.maxSampledVertexMovementM,maximumDifference(initial,capture(meshes)));
    }
    result.loopEndpointMaxDeltaM=maximumDifference(first,capture(meshes,true));
    result.wholeGeometryBounds=boxData(bounds);
    check(result.footMinY>=-groundTolerance,name+' '+clip.name+' feet penetrate the ground by '+round(-result.footMinY)+' m');
    check(result.wholeGeometryMinY>=-groundTolerance,name+' '+clip.name+' whole geometry penetrates the ground by '+round(-result.wholeGeometryMinY)+' m (includes sword and cloth)');
    if(name==='hanli'&&clip.name==='Walk'){
      result.supportFootClearanceLimitM=hanliWalkSupportClearance;
      check(result.footMaxLowestY<=hanliWalkSupportClearance,
        'hanli Walk lowest supporting foot rises '+round(result.footMaxLowestY)+' m above ground; limit '+hanliWalkSupportClearance+' m');
    }
    check(result.maxSampledVertexMovementM>1e-5,name+' '+clip.name+' has no visible vertex motion');
    if(clip.name==='Idle'||clip.name==='Walk')check(result.loopEndpointMaxDeltaM<=loopTolerance,name+' '+clip.name+' loop jumps '+round(result.loopEndpointMaxDeltaM)+' m');
    for(const k of ['footMinY','footMaxLowestY','wholeGeometryMinY','maxSampledVertexMovementM','loopEndpointMaxDeltaM'])result[k]=round(result[k]);
    for(const k of Object.keys(result.perFootMinY))result.perFootMinY[k]=round(result.perFootMinY[k]);
    report.clips.push(result);
  }
  report.crossfades=[];
  for(const [from,to] of [['Idle','Walk'],['Walk','Idle'],['Idle','Attack'],['Attack','Idle']]){
    mixer.stopAllAction();mixer.setTime(0);
    const a=mixer.clipAction(gltf.animations.find(c=>c.name===from)).reset().setLoop(THREE.LoopRepeat,Infinity).play();
    mixer.update(.19);
    const b=mixer.clipAction(gltf.animations.find(c=>c.name===to)).reset().setLoop(THREE.LoopRepeat,Infinity).play();b.crossFadeFrom(a,.25,false);
    const result={from,to,samples:31,minFootY:Infinity,maxLowestFootY:-Infinity};
    for(let i=0;i<31;i++){
      mixer.update(1/60);update(model);
      const lowest=Math.min(...Object.values(footPositions(feet)));result.minFootY=Math.min(result.minFootY,lowest);result.maxLowestFootY=Math.max(result.maxLowestFootY,lowest);
    }
    check(result.minFootY>=-groundTolerance,name+' '+from+'→'+to+' crossfade feet penetrate ground by '+round(-result.minFootY)+' m');
    result.minFootY=round(result.minFootY);result.maxLowestFootY=round(result.maxLowestFootY);report.crossfades.push(result);
  }
  if(name==='hanli'){
    // A stop can occur anywhere in the stride. A single starting phase can
    // miss the nonlinear foot dip introduced by blending bone transforms.
    const phases=24,hz=120;
    report.walkTransitionPhaseSweep={phases,samplingHz:hz,
      fadeDurationsS:[.16,.25],
      scope:'Idle/Walk in both directions over a full cycle; .16 s matches production actor crossfades and .25 s is a longer transition stress case.',
      minFootY:Infinity,maxLowestFootY:-Infinity,worst:null,samples:0,cases:[]};
    const sweep=report.walkTransitionPhaseSweep;
    for(const duration of sweep.fadeDurationsS)for(const [from,to] of [['Walk','Idle'],['Idle','Walk']])for(let phase=0;phase<phases;phase++){
      mixer.stopAllAction();mixer.setTime(0);
      const source=gltf.animations.find(c=>c.name===from),target=gltf.animations.find(c=>c.name===to);
      const a=mixer.clipAction(source).reset().setLoop(THREE.LoopRepeat,Infinity).play();
      mixer.update(source.duration*phase/phases);
      const b=mixer.clipAction(target).reset().setLoop(THREE.LoopRepeat,Infinity).play();b.crossFadeFrom(a,duration,false);
      const result={from,to,duration,sourcePhase:phase/phases,samples:Math.ceil(duration*hz)+2,minFootY:Infinity,maxLowestFootY:-Infinity,worstTime:0};
      for(let i=0;i<result.samples;i++){
        mixer.update(1/hz);update(model);
        const lowest=Math.min(...Object.values(footPositions(feet)));
        if(lowest<result.minFootY){result.minFootY=lowest;result.worstTime=(i+1)/hz}
        result.maxLowestFootY=Math.max(result.maxLowestFootY,lowest);
      }
      if(result.minFootY<sweep.minFootY){sweep.minFootY=result.minFootY;sweep.worst={from,to,duration,sourcePhase:round(result.sourcePhase),time:round(result.worstTime)}}
      sweep.maxLowestFootY=Math.max(sweep.maxLowestFootY,result.maxLowestFootY);sweep.samples+=result.samples;
      for(const key of ['sourcePhase','minFootY','maxLowestFootY','worstTime'])result[key]=round(result[key]);
      sweep.cases.push(result);
    }
    check(sweep.minFootY>=-groundTolerance,'hanli Walk/Idle phase-swept transitions penetrate ground by '+round(-sweep.minFootY)+' m');
    sweep.minFootY=round(sweep.minFootY);sweep.maxLowestFootY=round(sweep.maxLowestFootY);
  }
  return report;
}

assert.equal(THREE.REVISION,'180');
const report={scope:'Actual GLTFLoader/AnimationMixer r180 and CPU posed geometry; no browser/GPU render or performance test.',
  prerequisites:'Run tools/validate-assets.mjs for skin weights, full attributes and decoded texture/colour-space validation.',
  groundPlaneY:0,groundToleranceM:groundTolerance,loopEndpointToleranceM:loopTolerance,footSamplingHz:footHz,
  hanliWalkSupportClearanceLimitM:hanliWalkSupportClearance,
  wholeMeshSampling:'25 evenly spaced times per clip; all vertices, including the sword and cloth.',
  footContactInterpretation:'Reported footMinY checks penetration. footMaxLowestY is the maximum height of the lowest foot, not a claim of physically correct weight transfer or planted contact.',
  webglTested:false,assets:[]};
for(const name of ['hanli','mojiao'])report.assets.push(await validate(name));
report.warnings=warnings;report.errors=errors;report.result=errors.length?'FAIL':'PASS';
await fs.mkdir(path.dirname(out),{recursive:true});await fs.writeFile(out,JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({result:report.result,assets:report.assets.map(a=>({file:a.file,sha256:a.sha256,feet:a.footVertexCounts,clips:a.clips.map(c=>({name:c.name,footSamples:c.footSamples,footMinY:c.footMinY,footMaxLowestY:c.footMaxLowestY,wholeGeometryMinY:c.wholeGeometryMinY,loopEndpointMaxDeltaM:c.loopEndpointMaxDeltaM})),crossfades:a.crossfades})),warnings,errors,report:out},null,2));
if(errors.length)process.exitCode=1;
