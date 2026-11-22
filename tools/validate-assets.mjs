/**
 * Load the real GLBs through the vendored Three.js GLTFLoader and AnimationMixer.
 * Requires Node 20+ and @napi-rs/canvas for PNG/JPEG decoding only.
 * This is CPU asset/animation validation; it does not create a WebGL context.
 * Run: node tools/validate-assets.mjs [report.json] [asset-directory]
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';
import assert from 'node:assert/strict';
import * as THREE from '../vendor/three/build/three.module.js';
import { GLTFLoader } from '../vendor/three/addons/loaders/GLTFLoader.js';

const require=createRequire(import.meta.url);
const {loadImage,createCanvas}=require('@napi-rs/canvas');
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const out=process.argv[2]?path.resolve(process.argv[2]):path.resolve(root,'../qa3d/asset-validation.json');
const assetRoot=process.argv[3]?path.resolve(process.argv[3]):path.join(root,'assets/3d');
const decoded=[];
const pixelStats=new WeakMap();
function inspectPixels(image){
  const canvas=createCanvas(image.width,image.height),ctx=canvas.getContext('2d');
  ctx.drawImage(image,0,0);
  const rgba=ctx.getImageData(0,0,image.width,image.height).data;
  const min=[255,255,255],max=[0,0,0],sum=[0,0,0],sum2=[0,0,0];
  for(let i=0;i<rgba.length;i+=4)for(let c=0;c<3;c++){
    const value=rgba[i+c];min[c]=Math.min(min[c],value);max[c]=Math.max(max[c],value);
    sum[c]+=value;sum2[c]+=value*value;
  }
  const n=rgba.length/4,mean=sum.map(value=>value/n);
  return {min,max,mean,std:sum2.map((value,c)=>Math.sqrt(Math.max(0,value/n-mean[c]**2)))};
}
globalThis.self=globalThis;
globalThis.ProgressEvent??=class ProgressEvent extends Event {
  constructor(type,init={}){super(type);Object.assign(this,{lengthComputable:false,loaded:0,total:0},init);}
};
globalThis.createImageBitmap=async(blob,options={})=>{
  const bytes=Buffer.from(await blob.arrayBuffer());
  const img=await loadImage(bytes);
  assert(img.width>0&&img.height>0,'Texture decode returned empty dimensions');
  img.close=()=>{};
  const stats=inspectPixels(img);pixelStats.set(img,stats);
  decoded.push({bytes:bytes.length,width:img.width,height:img.height,options,rgb:stats});
  return img;
};

const finite=(values,label)=>{
  for(const v of values)assert(Number.isFinite(v),label+' contains non-finite values');
};
const vec=v=>v.toArray().map(x=>Math.round(x*1e6)/1e6);
const boxInfo=b=>({min:vec(b.min),max:vec(b.max),size:vec(b.getSize(new THREE.Vector3()))});
function checkTransforms(scene){
  scene.traverse(o=>{
    finite(o.position.toArray(),o.name+' position');
    finite(o.quaternion.toArray(),o.name+' quaternion');
    finite(o.scale.toArray(),o.name+' scale');
    finite(o.matrixWorld.elements,o.name+' matrixWorld');
    if(o.isSkinnedMesh){
      o.skeleton.update();finite(o.skeleton.boneMatrices,o.name+' skin matrices');
    }
  });
}

async function validateAsset(filename){
  const absolute=path.join(assetRoot,filename);
  const bytes=await fs.readFile(absolute);
  assert.equal(bytes.readUInt32LE(0),0x46546c67,'Bad GLB magic');
  assert.equal(bytes.readUInt32LE(4),2,'Expected glTF 2');
  assert.equal(bytes.readUInt32LE(8),bytes.length,'GLB length mismatch');
  const json=JSON.parse(bytes.subarray(20,20+bytes.readUInt32LE(12)).toString());
  assert((json.buffers||[]).every(b=>!b.uri),'Unexpected external buffer dependency');
  assert((json.images||[]).every(i=>i.bufferView!=null),'Unexpected external texture dependency');
  const textureStart=decoded.length;
  const loader=new GLTFLoader();
  const array=bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength);
  const gltf=await loader.parseAsync(array,pathToFileURL(path.dirname(absolute)+'/').href);
  const placement=new THREE.Group();placement.name='GameplayPlacement';
  placement.position.set(7,0,-4);placement.rotation.y=.63;
  placement.add(gltf.scene);
  placement.updateMatrixWorld(true);
  let meshes=0,skinnedMeshes=0,vertices=0,triangles=0,normals=0,uvVertices=0,skinWeightRows=0;
  const bones=new Set(),materials=new Set(),textures=new Set();
  gltf.scene.traverse(o=>{
    if(o.isBone)bones.add(o.uuid);
    if(!o.isMesh)return;
    meshes++;
    const geo=o.geometry,p=geo.getAttribute('position'),n=geo.getAttribute('normal'),uv=geo.getAttribute('uv');
    assert(p&&p.count>0,o.name+' missing positions');vertices+=p.count;finite(p.array,o.name+' vertices');
    assert(n&&n.count===p.count,o.name+' missing or mismatched normals');normals+=n.count;finite(n.array,o.name+' normals');
    for(let i=0;i<n.count;i++){
      const norm=Math.hypot(n.getX(i),n.getY(i),n.getZ(i));
      assert(norm>.5&&norm<1.5,o.name+' zero or invalid normal');
    }
    if(uv){uvVertices+=uv.count;assert.equal(uv.count,p.count,o.name+' UV count');finite(uv.array,o.name+' UV');}
    if(geo.index){
      finite(geo.index.array,o.name+' index');
      for(const index of geo.index.array)assert(index>=0&&index<p.count,o.name+' out-of-range index');
      assert.equal(geo.index.count%3,0,o.name+' non-triangle indices');triangles+=geo.index.count/3;
    }else triangles+=p.count/3;
    for(const m of Array.isArray(o.material)?o.material:[o.material]){
      materials.add(m.uuid);
      finite([m.roughness??0,m.metalness??0],m.name+' PBR factors');
      for(const k of ['map','normalMap','roughnessMap','metalnessMap','emissiveMap','aoMap']){
        const tex=m[k];if(!tex)continue;textures.add(tex.uuid);
        assert(uv||geo.getAttribute('uv1'),m.name+' textured mesh has no UV');
        assert(tex.image&&tex.image.width>0&&tex.image.height>0,m.name+' '+k+' missing decoded texture');
        if(k==='map'||k==='emissiveMap')assert.equal(tex.colorSpace,THREE.SRGBColorSpace,m.name+' colour texture encoding');
        else assert.equal(tex.colorSpace,THREE.NoColorSpace,m.name+' data texture encoding');
        if(k==='normalMap'){
          const stats=pixelStats.get(tex.image);
          assert(stats&&stats.mean[2]>128,m.name+' invalid tangent normal map: expected a positive mean Z component; check for an empty black texture');
        }
      }
    }
    if(o.isSkinnedMesh){
      skinnedMeshes++;
      const weights=geo.getAttribute('skinWeight'),indices=geo.getAttribute('skinIndex');
      assert(weights&&indices,o.name+' missing skin attributes');
      finite(weights.array,o.name+' skin weights');finite(indices.array,o.name+' joint indices');
      assert.equal(weights.count,p.count);assert.equal(indices.count,p.count);
      for(let i=0;i<weights.count;i++){
        let sum=0;for(let k=0;k<weights.itemSize;k++){
          const w=weights.array[i*weights.itemSize+k],index=indices.array[i*indices.itemSize+k];
          assert(w>=0&&w<=1.0001,o.name+' invalid skin weight');
          assert(index>=0&&index<o.skeleton.bones.length,o.name+' invalid bone index');sum+=w;
        }
        assert(Math.abs(sum-1)<.002,o.name+' skin weights do not sum to one');skinWeightRows++;
      }
    }
  });
  assert.deepEqual(gltf.animations.map(a=>a.name).sort(),['Attack','Idle','Walk']);
  for(const clip of gltf.animations){
    assert(clip.duration>0&&Number.isFinite(clip.duration),clip.name+' invalid duration');
    for(const tr of clip.tracks){finite(tr.times,tr.name+' times');finite(tr.values,tr.name+' values');}
  }
  checkTransforms(gltf.scene);
  const bindBox=new THREE.Box3().setFromObject(gltf.scene,true);
  finite([...bindBox.min.toArray(),...bindBox.max.toArray()],'bind bounds');
  const mixer=new THREE.AnimationMixer(gltf.scene);
  const samples=[];
  const fractions=[0,.125,.25,.375,.5,.625,.75,.875,.999,1,1.25,2.3];
  const sceneOrigin=gltf.scene.position.clone(),sceneRotation=gltf.scene.quaternion.clone();
  for(const clip of gltf.animations){
    mixer.stopAllAction();mixer.setTime(0);
    const action=mixer.clipAction(clip);action.reset().play();
    const bounds=new THREE.Box3();
    for(const fraction of fractions){
      const target=new THREE.Vector3(7+fraction,0,-4-fraction*.5);
      placement.position.copy(target);placement.rotation.y=.63+fraction*.13;
      const facing=placement.quaternion.clone(),scale=placement.scale.clone();
      mixer.setTime(fraction*clip.duration);
      placement.updateMatrixWorld(true);checkTransforms(gltf.scene);
      assert(placement.position.distanceTo(target)<1e-10,filename+' animation overwrites gameplay position');
      assert(placement.quaternion.angleTo(facing)<1e-7,filename+' animation overwrites gameplay facing');
      assert(placement.scale.distanceTo(scale)<1e-10,filename+' animation overwrites gameplay scale');
      assert(gltf.scene.position.distanceTo(sceneOrigin)<1e-10,filename+' clip animates scene root translation');
      assert(gltf.scene.quaternion.angleTo(sceneRotation)<1e-7,filename+' clip animates scene root rotation');
      const b=new THREE.Box3().setFromObject(gltf.scene,true);finite([...b.min.toArray(),...b.max.toArray()],clip.name+' sampled bounds');
      const size=b.getSize(new THREE.Vector3());assert(Math.max(...size.toArray())<20,clip.name+' implausible deformed size');
      bounds.union(b);
    }
    samples.push({clip:clip.name,duration:clip.duration,tracks:clip.tracks.length,sample_count:fractions.length,all_finite:true,placement_unchanged:true,scene_root_unchanged:true,sampled_world_bounds:boxInfo(bounds)});
  }
  mixer.stopAllAction();
  const a=mixer.clipAction(gltf.animations.find(c=>c.name==='Idle')).reset().play();
  const b=mixer.clipAction(gltf.animations.find(c=>c.name==='Walk')).reset().play();b.crossFadeFrom(a,.25,true);
  for(let i=0;i<20;i++){mixer.update(1/60);placement.updateMatrixWorld(true);checkTransforms(gltf.scene);}
  return {file:filename,sha256:crypto.createHash('sha256').update(bytes).digest('hex'),bytes:bytes.length,meshes,skinned_meshes:skinnedMeshes,bones:bones.size,vertices,triangles,normal_vertices:normals,uv_vertices:uvVertices,validated_skin_weight_rows:skinWeightRows,materials:materials.size,textures:textures.size,decoded_images:decoded.slice(textureStart),bind_world_bounds:boxInfo(bindBox),animations:samples,crossfade:'Idle to Walk, 20 finite samples',embedded_dependencies:true};
}

assert.equal(THREE.REVISION,'180','Unexpected Three revision');
const warnings=[],errors=[];
const oldWarn=console.warn,oldError=console.error;
console.warn=(...args)=>warnings.push(args.map(String).join(' '));
console.error=(...args)=>errors.push(args.map(String).join(' '));
const results=[];
try{
  for(const file of ['mojiao.glb','hanli.glb'])results.push(await validateAsset(file));
}finally{console.warn=oldWarn;console.error=oldError;}
assert.equal(errors.length,0,'Loader or mixer logged errors');
assert.equal(warnings.length,0,'Loader or mixer logged warnings');
const report={result:'PASS',three_revision:THREE.REVISION,loader:'Unmodified vendored GLTFLoader r180',animation:'Unmodified Three.js AnimationMixer r180',image_decode:'@napi-rs/canvas through createImageBitmap shim',normal_map_check:'Decoded tangent-space normal maps must have a positive mean Z component; black images fail',scope:'CPU GLB parse, real texture decode and pixel statistics, geometry/skin/material validation and animation sampling; no WebGL renderer or GPU context',webgl_tested:false,assets:results,warnings,errors};
await fs.mkdir(path.dirname(out),{recursive:true});await fs.writeFile(out,JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({result:report.result,three:report.three_revision,assets:results.map(r=>({file:r.file,meshes:r.meshes,skinned_meshes:r.skinned_meshes,bones:r.bones,triangles:r.triangles,animations:r.animations.map(a=>a.clip),samples:r.animations.reduce((n,a)=>n+a.sample_count,0),textures:r.textures,sha256:r.sha256})),warnings,errors,report:out},null,2));
