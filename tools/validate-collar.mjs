/**
 * Regression for the known right posterior neck/collar overlap in Han Li.
 * Uses the exported GLB, its default pose and the recorded side-profile camera.
 * This checks seven fixed rays; it is not full-angle, animation or WebGL QA.
 * Requires Node.js 20+ and the existing @napi-rs/canvas image decoder.
 * Usage: node tools/validate-collar.mjs [report.json] [hanli.glb]
 * Defaults: docs/collar-verification.json and assets/3d/hanli.glb.
 */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import * as THREE from '../vendor/three/build/three.module.js';
import {GLTFLoader} from '../vendor/three/addons/loaders/GLTFLoader.js';

const require=createRequire(import.meta.url),{loadImage}=require('@napi-rs/canvas');
const root=fileURLToPath(new URL('../',import.meta.url));
const script=fileURLToPath(import.meta.url);
const output=process.argv[2]?path.resolve(process.argv[2]):path.join(root,'docs/collar-verification.json');
const asset=process.argv[3]?path.resolve(process.argv[3]):path.join(root,'assets/3d/hanli.glb');
if([script,asset].includes(output))throw new Error('Report path must not replace the input GLB or validator');
const sha256=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
const source=fs.readFileSync(asset),scriptSource=fs.readFileSync(script);
const relativeAsset=path.relative(root,asset).replaceAll(path.sep,'/');
const assetName=relativeAsset.startsWith('../')?asset:relativeAsset;
const round=n=>+n.toFixed(7);
const report={
 result:'FAIL',validatedAt:new Date().toISOString(),node:process.version,three_revision:THREE.REVISION,
 asset:assetName,asset_sha256:sha256(source),validator:'tools/validate-collar.mjs',validator_sha256:sha256(scriptSource),
 scope:'Fixed-ray regression of the previously observed right posterior neck-base skin protrusion; exported default pose only. No complete collision, animation, all-angle, browser or GPU certification.',
 webgl_tested:false,pose:'exported default/bind pose',
 camera:{reference:'v6 GLB side-profile offline render',blender_position:[4,-.035,1.60],blender_target:[0,-.015,1.565],orthographic_scale_m:.38,resolution:[675,675]},
 expected_first_material:'Ice blue | overlapping inner silk',
 probes:[],errors:[]
};
globalThis.self=globalThis;
globalThis.ProgressEvent??=class extends Event{constructor(type,init={}){super(type);Object.assign(this,init)}};
globalThis.createImageBitmap=async blob=>{const image=await loadImage(Buffer.from(await blob.arrayBuffer()));image.close=()=>{};return image};

try{
 const gltf=await new GLTFLoader().parseAsync(source.buffer.slice(source.byteOffset,source.byteOffset+source.byteLength),'');
 gltf.scene.updateMatrixWorld(true);
 // Blender (x,y,z) maps to glTF (x,z,-y); both cameras use the same image axes.
 const camera=new THREE.OrthographicCamera(-.19,.19,.19,-.19,.1,20);
 camera.position.set(4,1.60,.035);camera.lookAt(0,1.565,.015);camera.updateMatrixWorld(true);
 const raycaster=new THREE.Raycaster();
 const points=[['exposed-center',450,640],['exposed-upper',455,620],['exposed-lower',448,650],['exposed-rear-lower',460,655],['upper-rim-control',443,608],['front-edge-control',430,640],['rear-edge-control',475,640]];
 for(const [name,x,y]of points){
  raycaster.setFromCamera(new THREE.Vector2(x/675*2-1,1-y/675*2),camera);
  const hits=raycaster.intersectObject(gltf.scene,true);
  const materialOf=hit=>{const material=hit.object.material;return(Array.isArray(material)?material[hit.face.materialIndex]:material)?.name||''};
  const evidence=hit=>hit?{mesh:hit.object.name,material:materialOf(hit),distance_m:round(hit.distance),gltf_point:hit.point.toArray().map(round),blender_point:[hit.point.x,-hit.point.z,hit.point.y].map(round)}:null;
  const first=hits[0],skin=hits.find(hit=>materialOf(hit).startsWith('Skin |'));
  const pass=Boolean(first)&&materialOf(first)===report.expected_first_material;
  report.probes.push({name,pixel:[x,y],result:pass?'PASS':'FAIL',first_hit:evidence(first),first_skin_hit:evidence(skin),skin_behind_first_surface_m:skin&&first?round(skin.distance-first.distance):null});
  if(!pass)report.errors.push(name+': expected collar first; observed '+(first?materialOf(first):'no geometry'));
 }
 if(sha256(fs.readFileSync(asset))!==report.asset_sha256)report.errors.push('Input GLB changed during validation');
 if(sha256(fs.readFileSync(script))!==report.validator_sha256)report.errors.push('Validator changed during validation');
 report.result=report.errors.length?'FAIL':'PASS';
}catch(error){report.errors.push(error.stack||String(error));}
fs.mkdirSync(path.dirname(output),{recursive:true});
fs.writeFileSync(output,JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report,null,2));
process.exitCode=report.result==='PASS'?0:1;
