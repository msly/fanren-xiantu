/**
 * Validate the production character viewer and battle state with the real GLBs.
 * Requires Node.js 20+ and @napi-rs/canvas for embedded image decoding.
 * Run from any directory: node tools/validate-viewer.mjs [report.json]
 * Default report: docs/viewer-verification.json (relative to this repository).
 * DOM rectangles are deterministic fixtures. This is not browser GPU, CSS layout
 * or device performance certification.
 */
import fs from 'node:fs';
import vm from 'node:vm';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const require=createRequire(import.meta.url),{loadImage}=require('@napi-rs/canvas');
const THREE=await import('../vendor/three/build/three.module.js');
const {GLTFLoader}=await import('../vendor/three/addons/loaders/GLTFLoader.js');
const {OrbitControls}=await import('../vendor/three/addons/controls/OrbitControls.js');
globalThis.self=globalThis;
globalThis.ProgressEvent??=class ProgressEvent extends Event{constructor(type,init={}){super(type);Object.assign(this,init)}};
globalThis.createImageBitmap=async blob=>{const image=await loadImage(Buffer.from(await blob.arrayBuffer()));image.close=()=>{};return image};
const base=new URL('../',import.meta.url);
const output=process.argv[2]?path.resolve(process.argv[2]):fileURLToPath(new URL('docs/viewer-verification.json',base));
const inputNames=['assets/3d/hanli.glb','assets/3d/mojiao.glb','web3d/main.js','web3d/style.css','game3d.html','tools/validate-viewer.mjs'];
const inputs=new Map(inputNames.map(name=>[name,fs.readFileSync(new URL(name,base))]));
const sha256=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
const sourceHashes=Object.fromEntries([...inputs].map(([name,bytes])=>[name,sha256(bytes)]));
assert(!inputNames.some(name=>fileURLToPath(new URL(name,base))===output),'Report path must not replace a source or model input');
async function load(name){const b=inputs.get('assets/3d/'+name+'.glb');return new GLTFLoader().parseAsync(b.buffer.slice(b.byteOffset,b.byteOffset+b.byteLength),'');}
const fixtures=await Promise.all([load('hanli'),load('mojiao')]);
const nodes=new Map(),ev=new Map();let width=1440,height=1000;
const compact=()=>width<=700&&!(width>=560&&height<=520);
function rect(id){
 if(id==='topbar')return {left:16,right:width-16,top:18,bottom:68};
 if(id==='footer')return {left:18,right:width-18,top:height-32,bottom:height-16};
 if(id==='viewer'){
  // A deliberately narrow layout fixture gains one button row when the
  // hero-only portrait control becomes visible. This models reflow timing;
  // these numbers are not a claim about a particular browser's text metrics.
  const extraRow=width<300&&!nodes.get('frame-portrait')?.classList.contains('hidden')?36:0;
  return compact()?{left:18,right:width-18,top:height-242-extraRow,bottom:height-56}:{left:width*.075,right:width*.075+Math.min(340,width*.32),top:height*.42,bottom:height-65};
 }
 return {left:0,right:width,top:0,bottom:height};
}
function node(id,dataset={}){if(!nodes.has(id)){const classes=new Set();nodes.set(id,{id,dataset,style:{},attributes:{},classList:{add:k=>classes.add(k),remove:k=>classes.delete(k),toggle(k,v){if(v===undefined)v=!classes.has(k);v?classes.add(k):classes.delete(k)},contains:k=>classes.has(k)},open:false,textContent:'',setAttribute(k,v){this.attributes[k]=v},getBoundingClientRect:()=>rect(id),showModal(){this.open=true},close(){this.open=false},addEventListener(k,fn){ev.set(id+':'+k,fn)}})}return nodes.get(id);}
const pose=['Idle','Walk','Attack'].map(p=>node('pose-'+p,{pose:p})),frames=['full','portrait','head'].map(frame=>node('frame-'+frame,{frame}));
const doc={body:node('body'),getElementById:node,querySelectorAll(selector){return selector==='[data-pose]'?pose:selector==='[data-frame]'?frames:[]}};
const sandbox={THREE,OrbitControls,document:doc,performance,console,Set,Math,clearTimeout(){},setTimeout(){},addEventListener:(k,fn)=>ev.set(k,fn),requestAnimationFrame(){},innerWidth:width,innerHeight:height,devicePixelRatio:1};
let source=inputs.get('web3d/main.js').toString('utf8').replace(/^import .*;\n/gm,'').replace('init().catch(safeError);','');
source+=`\nglobalThis.review={state,viewerState,telegraph,tickCombat,spell,bolts,finish,frameViewer,setViewerRotation,setMode,begin,resize,updateViewerAnchor,setup(fixtures){renderer={capabilities:{getMaxAnisotropy:()=>8},setSize(){},toneMappingExposure:1.12};scene=new THREE.Scene();camera=new THREE.PerspectiveCamera(43,innerWidth/innerHeight,.1,350);controls=new OrbitControls(camera);controls.enableDamping=true;controls.dampingFactor=.07;controls.autoRotateSpeed=.65;world={root:new THREE.Group(),update(){}};scene.add(world.root);sceneLights=new THREE.Group();scene.add(sceneLights);studio=createViewerStudio();hero=actor(fixtures[0]);beast=actor(fixtures[1]);setMode('scene');},hero:()=>hero,beast:()=>beast,camera:()=>camera,controls:()=>controls,scene:()=>scene,world:()=>world,studio:()=>studio,sceneLights:()=>sceneLights,renderer:()=>renderer};`;
const ctx=vm.createContext(sandbox);new vm.Script(source,{filename:'web3d/main.js'}).runInContext(ctx);const t=ctx.review;t.setup(fixtures);
const checks=[];const finite=()=>{const c=t.camera();for(const v of [...c.position.toArray(),...c.quaternion.toArray(),...c.projectionMatrix.elements,...t.controls().target.toArray()])assert(Number.isFinite(v));};
// A frame must use the panel dimensions after control visibility changes.
// Both transitions matter: beast -> hero adds a row, hero -> beast removes it.
const reflowFixtures=[];
[width,height]=[270,600];ctx.innerWidth=width;ctx.innerHeight=height;t.resize();
t.setMode('beast');
for(const mode of ['hero','beast']){
 t.setMode(mode);
 const panel=rect('viewer'),top=rect('topbar').bottom+18,bottom=panel.top-16;
 const expectedOffsetY=height/2-(top+bottom)/2;
 assert.equal(node('frame-portrait').classList.contains('hidden'),mode!=='hero');
 assert(Math.abs(t.camera().view.offsetY-expectedOffsetY)<1e-8,
  mode+' framing must measure the reflowed viewer panel after updating portrait visibility');
 reflowFixtures.push({viewport:[width,height],mode,panelTop:panel.top,offsetY:t.camera().view.offsetY});
 finite();
}
assert.equal(reflowFixtures[1].panelTop-reflowFixtures[0].panelTop,36);
t.setMode('scene');
checks.push('Narrow-screen hero/beast switches measure the reflowed panel after the portrait button is shown or hidden');
const projection=[];
for(const size of [[1440,1000],[390,844],[320,568],[844,390],[640,400]]){
 [width,height]=size;ctx.innerWidth=width;ctx.innerHeight=height;t.resize();
 for(const mode of ['hero','beast']){
  t.setMode(mode);assert.equal(t.world().root.visible,false);assert.equal(t.sceneLights().visible,false);assert.equal(t.studio().root.visible,true);assert.equal(t.scene().fog,null);
  const actor=mode==='hero'?t.hero():t.beast();assert.deepEqual(actor.root.position.toArray(),[0,0,0]);
  const bounds=new THREE.Box3().setFromObject(actor.root,true),target=t.controls().target.clone(),distance=t.camera().position.distanceTo(target),offset=t.camera().position.clone().sub(target),polar=Math.acos(offset.y/distance);
  let minX=Infinity,maxX=-Infinity,minY=Infinity,maxY=-Infinity;
  for(let turn=0;turn<24;turn++){
   const azimuth=turn/24*Math.PI*2;t.camera().position.copy(target).add(new THREE.Vector3(Math.sin(azimuth)*Math.sin(polar)*distance,Math.cos(polar)*distance,Math.cos(azimuth)*Math.sin(polar)*distance));t.camera().lookAt(target);t.camera().updateMatrixWorld(true);
   for(const x of [bounds.min.x,bounds.max.x])for(const y of [bounds.min.y,bounds.max.y])for(const z of [bounds.min.z,bounds.max.z]){
    const p=new THREE.Vector3(x,y,z).project(t.camera());const px=(p.x+1)/2*width,py=(1-p.y)/2*height;minX=Math.min(minX,px);maxX=Math.max(maxX,px);minY=Math.min(minY,py);maxY=Math.max(maxY,py);assert(p.z>-1&&p.z<1);}
  }
  const panel=rect('viewer'),head=rect('topbar'),foot=rect('footer'),left=compact()?18:Math.min(panel.right+28,width*.48),right=width-(compact()?18:32),top=head.bottom+18,bottom=Math.max(top+40,compact()?panel.top-16:foot.top-24);
  assert(minX>=left-1&&maxX<=right+1&&minY>=top-1&&maxY<=bottom+1,JSON.stringify({mode,size,projected:[minX,maxX,minY,maxY],region:[left,right,top,bottom]}));
  projection.push({viewport:size,mode,fullBodyBounds:[minX,maxX,minY,maxY].map(n=>+n.toFixed(1)),reservedRegion:[left,right,top,bottom]});
  if(mode==='hero'){
   t.frameViewer('portrait');finite();assert.equal(t.viewerState.frame,'portrait');
   t.camera().updateMatrixWorld(true);
   const points=[new THREE.Vector3(0,bounds.max.y,0),new THREE.Vector3(0,1.0,.14),new THREE.Vector3(-.24,1.30,.05),new THREE.Vector3(.24,1.30,.05)];
   for(const world of points){const p=world.project(t.camera()),px=(p.x+1)/2*width,py=(1-p.y)/2*height;assert(px>=left-1&&px<=right+1&&py>=top-1&&py<=bottom+1,'Portrait should contain crown, belt and both shoulders');}
   assert(!node('frame-portrait').classList.contains('hidden'));
  }else assert(node('frame-portrait').classList.contains('hidden'));
  t.frameViewer('head');finite();assert(t.viewerState.anchor);const anchorBefore=t.controls().target.clone();
  actor.play('Walk');actor.mixer.update(.24);t.updateViewerAnchor();const movement=anchorBefore.distanceTo(t.controls().target);assert(movement>0,mode+' portrait follows moving head');finite();
  for(const clip of ['Idle','Walk','Attack']){actor.reset();actor.play(clip);for(let i=0;i<12;i++){actor.mixer.update(.08);t.updateViewerAnchor();finite();}}
  t.setViewerRotation(true);assert.equal(t.controls().autoRotate,true);const prior=t.camera().position.clone();t.controls().update(.5);assert(t.camera().position.distanceTo(prior)>.001);t.setViewerRotation(false);assert.equal(t.controls().autoRotate,false);finite();
 }
}
checks.push('Full model bounding boxes stay inside reserved content region over 24 azimuths, two real GLBs and five viewport fixtures','Han Li portrait framing contains crown, waist and shoulders at all five viewport fixtures','Head framing follows actual animated head nodes through Idle, Walk and Attack','Real OrbitControls auto rotation starts and stops with finite camera state');
[width,height]=[1440,1000];ctx.innerWidth=width;ctx.innerHeight=height;t.resize();
const baseline=t.scene().children.length;
for(let i=0;i<25;i++){t.setMode('hero');t.frameViewer('head');t.setViewerRotation(true);t.setMode('beast');t.setMode('scene');assert.equal(t.scene().children.length,baseline);assert.equal(t.controls().autoRotate,false);assert.equal(t.camera().view.enabled,false);assert.equal(t.studio().root.visible,false);assert.equal(t.world().root.visible,true);assert.equal(t.sceneLights().visible,true);assert(t.scene().fog);assert.equal(t.renderer().toneMappingExposure,1.12);assert.deepEqual(t.hero().root.position.toArray(),[-1.25,0,3.1]);assert.deepEqual(t.beast().root.position.toArray(),[.8,0,-4.4]);finite();}
checks.push('25 repeated viewer/scene cycles reuse one studio and restore world, lights, fog, exposure, camera projection, actor placement and orbit state');
t.setMode('hero');t.frameViewer('portrait');t.setViewerRotation(true);t.begin();assert.equal(t.state.phase,'battle');assert.equal(t.state.mode,'scene');assert.equal(t.state.hp,100);assert.equal(node('pause').classList.contains('hidden'),false);
t.hero().root.position.set(0,0,2.5);t.beast().root.position.set(0,0,0);Object.assign(t.state,{bossWind:.01,bossLunge:0});t.tickCombat(.02);assert(t.state.bossLunge>0);assert.equal(t.telegraph.material.opacity,0);t.tickCombat(.04);assert.equal(t.telegraph.material.opacity,0);
const snapshot=()=>({hp:t.state.hp,bossHP:t.state.bossHP,pos:t.hero().root.position.toArray()});const battleBefore=snapshot();
ev.get('blur')();assert.equal(t.state.paused,true);assert.equal(node('pause').textContent,'继续试炼');ev.get('pause:click')();assert.equal(t.state.paused,false);assert.deepEqual(snapshot(),battleBefore);
ev.get('keydown')({code:'Escape',repeat:false,preventDefault(){}});assert.equal(t.state.paused,true);ev.get('pause:click')();assert.equal(t.state.paused,false);
const alignment=[];for(const [x,z] of [[4,0],[0,-4],[3,-4]]){t.hero().root.position.set(0,0,0);t.beast().root.position.set(x,0,z);t.state.spellCD=0;t.state.qi=100;t.spell();const b=t.bolts.at(-1),dot=new THREE.Vector3(0,0,1).applyQuaternion(b.mesh.quaternion).dot(b.velocity.clone().normalize());assert(dot>.999999);alignment.push(dot);}
for(const win of [true,false]){t.state.phase='battle';t.finish(win);assert(node('result').open);let prevented=false;ev.get('result:cancel')({preventDefault(){prevented=true}});assert(prevented);assert(!node('result').open);assert.equal(t.state.phase,'ready');assert.equal(t.state.mode,'scene');assert.equal(node('intro').classList.contains('hidden'),false);assert.equal(node('pause').classList.contains('hidden'),true);}
checks.push('Battle starts from portrait mode with default framing and controls','Boss windup/lunge telegraph, projectile direction, blur/click/Esc pause, victory/defeat cancel and retry state retain prior behavior');
for(const name of inputNames)assert.equal(sha256(fs.readFileSync(new URL(name,base))),sourceHashes[name],name+' changed during validation');
const report={result:'PASS',validatedAt:new Date().toISOString(),node:process.version,source_sha256:sourceHashes,runtime:'Unmodified Three.js r180 GLTFLoader, AnimationMixer, OrbitControls and production state functions with deterministic DOM rectangle fixtures; no browser GPU or CSS layout certification',checks,reflowFixtures,projectionFixtures:projection,projectileAlignmentDotProducts:alignment};
fs.mkdirSync(path.dirname(output),{recursive:true});
fs.writeFileSync(output,JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report,null,2));
