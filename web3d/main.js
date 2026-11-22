import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { createEnvironment } from './environment.js';

const $=id=>document.getElementById(id),canvas=$('scene');
const state={mode:'scene',phase:'loading',time:0,hp:100,qi:100,bossHP:360,attack:0,attackHit:false,spellCD:0,dodge:0,dodgeCD:0,bossCD:2,bossWind:0,bossLunge:0,bossHit:false,paused:false,quality:'balanced'};
const keys=new Set(),up=new THREE.Vector3(0,1,0),move=new THREE.Vector3(),dodgeDir=new THREE.Vector3(0,0,-1),bossDir=new THREE.Vector3();
let renderer,scene,camera,controls,world,hero,beast,last=performance.now(),toastTimer,follow=true;
const effects=[],bolts=[],mixers=[];
const hide=(id,v)=>$(id).classList.toggle('hidden',v);
const safeError=e=>{console.error(e);$('loading').classList.add('hidden');$('failure-text').textContent=String(e.message||'').includes('WebGL')?'此设备暂未能开启三维画面。请使用支持硬件加速的浏览器，再次进入。':'人物或场景加载未完成，请刷新重试。';if(!$('failure').open)$('failure').showModal();};
function toast(s){$('toast').textContent=s;$('toast').classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').classList.remove('show'),1700)}
function updatePauseButton(){const button=$('pause');hide('pause',state.mode!=='scene'||state.phase!=='battle');button.textContent=state.paused?'继续试炼':'暂停';button.setAttribute('aria-pressed',String(state.paused));button.classList.toggle('active',state.paused);}
function setPaused(paused){if(state.mode!=='scene'||state.phase!=='battle')return;keys.clear();if(state.paused===paused)return;state.paused=paused;updatePauseButton();toast(paused?'已暂停 · 点击继续试炼':'继续试炼');}
function turnTo(model,yaw,dt,rate=12){const d=Math.atan2(Math.sin(yaw-model.rotation.y),Math.cos(yaw-model.rotation.y));model.rotation.y+=d*(1-Math.exp(-dt*rate))}
function displayMode(mode){
 state.mode=mode;for(const k of ['scene','hero','beast'])$('view-'+k).classList.toggle('active',mode===k);
 hide('intro',mode!=='scene'||state.phase==='battle');hide('viewer',mode==='scene');
 hide('hero-hud',mode!=='scene'||state.phase!=='battle');hide('boss-hud',mode!=='scene'||state.phase!=='battle');hide('combat-actions',mode!=='scene'||state.phase!=='battle');hide('touch-pad',mode!=='scene'||state.phase!=='battle');
 updatePauseButton();
 controls.mouseButtons.LEFT=mode==='scene'&&state.phase==='battle'?null:THREE.MOUSE.ROTATE;controls.mouseButtons.RIGHT=THREE.MOUSE.ROTATE;
 if(hero)hero.root.visible=mode!=='beast';if(beast)beast.root.visible=mode!=='hero';
 $('help').textContent=mode==='scene'&&state.phase==='battle'?'WASD 移动 · J/左键斩击 · Q 剑芒 · 空格闪避 · 右键环绕 · Esc 暂停':'拖动环绕观察 · 滚轮拉近';
}
function setMode(mode){
 if(!hero||!beast)return;keys.clear();state.paused=false;state.phase='ready';state.attack=state.dodge=state.bossWind=state.bossLunge=0;clearEffects();hero.play('Idle');beast.play('Idle');
 for(const b of document.querySelectorAll('[data-pose]'))b.classList.toggle('active',b.dataset.pose==='Idle');
 if(mode==='scene'){hero.root.position.set(-1.25,0,3.1);hero.root.rotation.y=Math.PI;beast.root.position.set(.8,0,-4.4);beast.root.rotation.y=.1;camera.position.set(8.8,5.2,11.2);controls.target.set(.2,1,-.5);controls.minDistance=3;controls.maxDistance=32;follow=true;}
 else{const a=mode==='hero'?hero:beast;const center=a.root.position.clone().add(new THREE.Vector3(0,mode==='hero'?1.05:1.1,0));const front=new THREE.Vector3(0,0,1).applyQuaternion(a.root.quaternion);const side=new THREE.Vector3(1,0,0).applyQuaternion(a.root.quaternion);camera.position.copy(center).addScaledVector(front,mode==='hero'?3.6:6).addScaledVector(side,mode==='hero'?1.5:3.2).add(new THREE.Vector3(0,.45,0));controls.target.copy(center);controls.minDistance=mode==='hero'?.75:1.6;controls.maxDistance=14;follow=false;
  $('viewer-name').textContent=mode==='hero'?'韩立':'墨蛟';$('viewer-sub').textContent=mode==='hero'?'青竹剑修 · 掌天瓶之主':'血色禁地 · 墨鳞蛟兽';$('viewer-desc').textContent=mode==='hero'?'青衣、长剑与一只碧色小瓶。凝神看清衣袍、发束与剑锋，再走进他的仙途。':'墨鳞覆体，角须生风。看清颌骨、鳞甲与利爪，亦看清它蓄势时的姿态。';}
 controls.update();displayMode(mode);
}
function begin(){if(!hero||!beast)return;if($('result').open)$('result').close();setMode('scene');Object.assign(state,{phase:'battle',hp:100,qi:100,bossHP:360,attack:0,spellCD:0,dodge:0,dodgeCD:0,bossCD:2,bossWind:0,bossLunge:0,paused:false});displayMode('scene');toast('试炼开始');updateHUD();}
function finish(win){state.phase=win?'victory':'defeat';keys.clear();state.bossWind=state.bossLunge=0;hero.play('Idle');beast.play('Idle');hide('combat-actions',true);hide('touch-pad',true);updatePauseButton();$('result-title').textContent=win?'剑意初成':'胜负未定';$('result-text').textContent=win?'墨蛟的攻势已被化解。这一场试剑，记住它蓄势的瞬间。':'留心墨蛟蓄势时的赤色范围，以罗烟步避过，再寻出剑的时机。';$('result').showModal();}
function actor(gltf){const root=gltf.scene;root.traverse(o=>{if(o.isMesh){o.castShadow=true;o.receiveShadow=true;if(o.material){const mats=Array.isArray(o.material)?o.material:[o.material];for(const m of mats){m.envMapIntensity=.75;if(m.map)m.map.anisotropy=Math.min(8,renderer.capabilities.getMaxAnisotropy());}}}});scene.add(root);const mixer=new THREE.AnimationMixer(root),actions={};for(const clip of gltf.animations)actions[clip.name]=mixer.clipAction(clip);mixers.push(mixer);let playing='';return{root,mixer,actions,play(name,once=false){if(!actions[name])name=Object.keys(actions).find(n=>n.toLowerCase().includes(name.toLowerCase()))||Object.keys(actions)[0];if(!name)return;if(playing===name&&!once)return;const next=actions[name];if(playing&&actions[playing])actions[playing].fadeOut(.16);next.reset().setEffectiveTimeScale(1).setEffectiveWeight(1);next.setLoop(once?THREE.LoopOnce:THREE.LoopRepeat,once?1:Infinity);next.clampWhenFinished=once;next.fadeIn(.16).play();playing=name;},reset(){playing='';mixer.stopAllAction()}};}
function updateHUD(){$('hero-hp').style.width=Math.max(0,state.hp)+'%';$('hero-qi').style.width=Math.max(0,state.qi)+'%';$('boss-hp').style.width=Math.max(0,state.bossHP/3.6)+'%';$('hero-health').textContent='气血 '+Math.ceil(state.hp);$('hero-mana').textContent='法力 '+Math.floor(state.qi);$('spell-cd').textContent=state.spellCD>0?state.spellCD.toFixed(1):'';}
function ring(pos,color,r=1.6,duration=.5){const mesh=new THREE.Mesh(new THREE.RingGeometry(r*.85,r,64),new THREE.MeshBasicMaterial({color,transparent:true,opacity:.8,side:THREE.DoubleSide,depthWrite:false,blending:THREE.AdditiveBlending}));mesh.rotation.x=-Math.PI/2;mesh.position.copy(pos);mesh.position.y=.035;scene.add(mesh);effects.push({mesh,life:duration,max:duration,expand:true});return mesh;}
function slash(){const mesh=new THREE.Mesh(new THREE.TorusGeometry(1.35,.035,6,48,Math.PI*1.4),new THREE.MeshBasicMaterial({color:0xaee9cd,transparent:true,opacity:.85,depthWrite:false,blending:THREE.AdditiveBlending}));const group=new THREE.Group();group.position.copy(hero.root.position);group.position.y=1.02;group.rotation.y=hero.root.rotation.y;mesh.rotation.x=Math.PI/2;mesh.rotation.z=-Math.PI*.2;mesh.position.z=.6;group.add(mesh);scene.add(group);effects.push({mesh:group,life:.24,max:.24});}
function hitBoss(dmg){if(state.phase!=='battle')return;state.bossHP=Math.max(0,state.bossHP-dmg);ring(beast.root.position,0x84cfce,1.15,.28);if(state.bossHP===0)finish(true);}
function strike(){if(state.mode!=='scene'||state.phase!=='battle'||state.paused||state.attack>0||state.dodge>0)return;state.attack=.6;state.attackHit=false;const delta=beast.root.position.clone().sub(hero.root.position);hero.root.rotation.y=Math.atan2(delta.x,delta.z);hero.play('Attack',true);slash();}
function spell(){if(state.mode!=='scene'||state.phase!=='battle'||state.paused||state.spellCD>0)return;if(state.qi<22){toast('法力不足');return}state.qi-=22;state.spellCD=3.6;hero.play('Attack',true);state.attack=.5;state.attackHit=true;const direction=beast.root.position.clone().sub(hero.root.position).normalize();hero.root.rotation.y=Math.atan2(direction.x,direction.z);const mesh=new THREE.Mesh(new THREE.SphereGeometry(.19,12,8),new THREE.MeshBasicMaterial({color:0xb9f5d0}));mesh.scale.set(1,1,3);mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0,0,1),direction);mesh.position.copy(hero.root.position).add(new THREE.Vector3(0,.95,0)).addScaledVector(direction,.8);scene.add(mesh);bolts.push({mesh,velocity:direction.multiplyScalar(15),life:1.4});ring(hero.root.position,0x86dab3,.9,.28);}
function dodge(){if(state.mode!=='scene'||state.phase!=='battle'||state.paused||state.dodgeCD>0)return;if(state.qi<14){toast('法力不足');return}state.qi-=14;state.dodge=.28;state.dodgeCD=.72;if(move.lengthSq()>.01)dodgeDir.copy(move).normalize();else dodgeDir.set(Math.sin(hero.root.rotation.y),0,Math.cos(hero.root.rotation.y));hero.play('Walk');ring(hero.root.position,0x80bca8,.7,.22);}
function clearEffects(){for(const e of effects)disposeEffect(e.mesh);for(const b of bolts)disposeEffect(b.mesh);effects.length=bolts.length=0;}
function disposeEffect(mesh){scene.remove(mesh);mesh.traverse(o=>{o.geometry?.dispose();if(o.material)(Array.isArray(o.material)?o.material:[o.material]).forEach(m=>m.dispose())});}
const telegraph=new THREE.Mesh(new THREE.RingGeometry(2.45,2.52,72),new THREE.MeshBasicMaterial({color:0xe4a66f,transparent:true,opacity:0,side:THREE.DoubleSide,depthWrite:false}));telegraph.rotation.x=-Math.PI/2;
function tickCombat(dt){
 state.qi=Math.min(100,state.qi+7*dt);state.spellCD=Math.max(0,state.spellCD-dt);state.dodgeCD=Math.max(0,state.dodgeCD-dt);
 const forward=new THREE.Vector3();camera.getWorldDirection(forward);forward.y=0;forward.normalize();const right=new THREE.Vector3().crossVectors(forward,up);
 const mx=(keys.has('KeyD')?1:0)-(keys.has('KeyA')?1:0),mz=(keys.has('KeyW')?1:0)-(keys.has('KeyS')?1:0);move.copy(forward).multiplyScalar(mz).addScaledVector(right,mx);if(move.lengthSq()>0)move.normalize();
 if(state.dodge>0){state.dodge-=dt;hero.root.position.addScaledVector(dodgeDir,10*dt);}
 else if(state.attack>0){state.attack-=dt;if(!state.attackHit&&state.attack<.38){state.attackHit=true;if(hero.root.position.distanceTo(beast.root.position)<3.2)hitBoss(31);}}
 else if(move.lengthSq()>0){hero.root.position.addScaledVector(move,4.1*dt);turnTo(hero.root,Math.atan2(move.x,move.z),dt);hero.play('Walk');}
 else hero.play('Idle');
 const radius=Math.hypot(hero.root.position.x,hero.root.position.z);if(radius>11.2){hero.root.position.x*=11.2/radius;hero.root.position.z*=11.2/radius;}
 if(state.phase!=='battle')return;
 const delta=hero.root.position.clone().sub(beast.root.position);delta.y=0;const distance=delta.length();
 if(state.bossLunge>0){state.bossLunge-=dt;beast.root.position.addScaledVector(bossDir,5.8*dt);if(!state.bossHit&&hero.root.position.distanceTo(beast.root.position)<2.05){state.bossHit=true;if(state.dodge<=0){state.hp=Math.max(0,state.hp-22);toast('墨蛟扑击');ring(hero.root.position,0xe7ac84,.8,.3);if(state.hp===0)finish(false)}else toast('罗烟无踪')};if(state.bossLunge<=0)state.bossCD=1.8;}
 else if(state.bossWind>0){state.bossWind-=dt;beast.play('Attack');telegraph.position.copy(beast.root.position);telegraph.position.y=.045;telegraph.material.opacity=.35+Math.sin(state.time*16)*.2;if(state.bossWind<=0){telegraph.material.opacity=0;state.bossLunge=.5;state.bossHit=false;bossDir.copy(delta).normalize();beast.root.rotation.y=Math.atan2(bossDir.x,bossDir.z);beast.play('Attack',true)}}
 else{telegraph.material.opacity=0;state.bossCD-=dt;turnTo(beast.root,Math.atan2(delta.x,delta.z),dt,3.5);if(distance>3.4){beast.root.position.addScaledVector(delta.normalize(),1.35*dt);beast.play('Walk')}else{beast.play('Idle');if(state.bossCD<=0){state.bossWind=.95;toast('墨蛟蓄势')}}}
 const br=beast.root.position.length();if(br>10.8)beast.root.position.multiplyScalar(10.8/br);
 if(follow){const target=hero.root.position.clone().lerp(beast.root.position,.28).add(new THREE.Vector3(0,.9,0));const shift=target.clone().sub(controls.target).multiplyScalar(1-Math.exp(-dt*2.2));controls.target.add(shift);camera.position.add(shift)}
 updateHUD();
}
function animate(now){requestAnimationFrame(animate);const dt=Math.min((now-last)/1000,.04);last=now;if(!renderer||!hero||!beast)return;
 if(!state.paused){state.time+=dt;world.update?.(dt,state.time);for(const m of mixers)m.update(dt);if(state.mode==='scene'&&state.phase==='battle')tickCombat(dt);else telegraph.material.opacity=0;
  for(let i=effects.length-1;i>=0;i--){const e=effects[i];e.life-=dt;if(e.life<=0){disposeEffect(e.mesh);effects.splice(i,1);continue}e.mesh.traverse(o=>{if(o.material)o.material.opacity=Math.max(0,e.life/e.max)*.8});if(e.expand)e.mesh.scale.setScalar(1+(1-e.life/e.max)*.65)}
  for(let i=bolts.length-1;i>=0;i--){const b=bolts[i];b.life-=dt;b.mesh.position.addScaledVector(b.velocity,dt);const delta=b.mesh.position.clone().sub(beast.root.position);delta.y=0;if(delta.length()<1.6&&state.phase==='battle'){hitBoss(54);b.life=0}if(b.life<=0){disposeEffect(b.mesh);bolts.splice(i,1)}}
 }
 controls.update();renderer.render(scene,camera);
}
function resize(){if(!renderer)return;renderer.setSize(innerWidth,innerHeight,false);camera.aspect=innerWidth/innerHeight;camera.updateProjectionMatrix();}
async function init(){
 renderer=new THREE.WebGLRenderer({canvas,antialias:true,powerPreference:'high-performance'});renderer.setPixelRatio(Math.min(devicePixelRatio,1.25));renderer.shadowMap.enabled=true;renderer.shadowMap.type=THREE.PCFSoftShadowMap;renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.12;renderer.outputColorSpace=THREE.SRGBColorSpace;
 scene=new THREE.Scene();scene.background=new THREE.Color(0x0c2028);scene.fog=new THREE.FogExp2(0x122b31,.018);camera=new THREE.PerspectiveCamera(43,innerWidth/innerHeight,.1,350);camera.position.set(8.8,5.2,11.2);resize();
 controls=new OrbitControls(camera,canvas);controls.enableDamping=true;controls.dampingFactor=.07;controls.enablePan=false;controls.maxPolarAngle=Math.PI*.48;controls.minPolarAngle=.15;controls.target.set(0,1,0);controls.minDistance=3;controls.maxDistance=32;
 const hemi=new THREE.HemisphereLight(0xb6d9e5,0x35473d,1.4);scene.add(hemi);const key=new THREE.DirectionalLight(0xc7e4eb,3.3);key.position.set(-9,17,8);key.castShadow=true;key.shadow.mapSize.set(2048,2048);Object.assign(key.shadow.camera,{left:-17,right:17,top:17,bottom:-17,near:1,far:65});key.shadow.normalBias=.03;key.shadow.bias=-.0002;scene.add(key);const rim=new THREE.DirectionalLight(0x90b9a8,1.8);rim.position.set(5,8,-10);scene.add(rim);
 const pmrem=new THREE.PMREMGenerator(renderer),room=new RoomEnvironment();const envMap=pmrem.fromScene(room,.04);scene.environment=envMap.texture;scene.environmentIntensity=.45;room.dispose();pmrem.dispose();
 world=createEnvironment(THREE,scene,renderer);scene.add(telegraph);
 const loader=new GLTFLoader();const [a,b]=await Promise.all([loader.loadAsync('./assets/3d/hanli.glb',p=>{if(p.total)$('load-text').textContent='青衫入画 · '+Math.round(p.loaded/p.total*100)+'%'}),loader.loadAsync('./assets/3d/mojiao.glb')]);
 hero=actor(a);beast=actor(b);state.phase='ready';setMode('scene');hide('loading',true);$('begin').disabled=false;$('begin').textContent='开始试炼';$('intro-hero').disabled=false;
 window.__xiantu3d={state,hero,beast,scene,camera,renderer,begin,setMode,attack:strike,dodge,spell,getStatus:()=>({ready:true,mode:state.mode,phase:state.phase,heroClips:Object.keys(hero.actions),beastClips:Object.keys(beast.actions),drawCalls:renderer.info.render.calls,triangles:renderer.info.render.triangles,hp:state.hp,bossHP:state.bossHP})};
 last=performance.now();requestAnimationFrame(animate);
}
$('begin').addEventListener('click',begin);$('retry').addEventListener('click',begin);$('intro-hero').addEventListener('click',()=>setMode('hero'));
for(const k of ['scene','hero','beast'])$('view-'+k).addEventListener('click',()=>setMode(k));
function returnToScene(){if($('result').open)$('result').close();setMode('scene');}
$('return-scene').addEventListener('click',returnToScene);
$('result').addEventListener('cancel',e=>{e.preventDefault();returnToScene()});
$('pause').addEventListener('click',()=>setPaused(!state.paused));
$('strike').addEventListener('click',strike);$('spell').addEventListener('click',spell);$('dodge').addEventListener('click',dodge);
document.querySelectorAll('[data-pose]').forEach(b=>b.addEventListener('click',()=>{if(state.mode==='scene')return;const a=state.mode==='hero'?hero:beast;a.play(b.dataset.pose,b.dataset.pose==='Attack');document.querySelectorAll('[data-pose]').forEach(n=>n.classList.toggle('active',n===b))}));
document.querySelectorAll('[data-key]').forEach(b=>{const clear=()=>keys.delete(b.dataset.key);b.addEventListener('pointerdown',e=>{e.preventDefault();keys.add(b.dataset.key);b.setPointerCapture(e.pointerId)});for(const ev of ['pointerup','pointercancel','lostpointercapture'])b.addEventListener(ev,clear)});
addEventListener('keydown',e=>{if(state.phase!=='battle'||state.mode!=='scene')return;if(['Space','Tab','ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(e.code))e.preventDefault();if(e.repeat)return;if(e.code==='Escape'){setPaused(!state.paused);return}keys.add(e.code);if(e.code==='KeyJ')strike();if(e.code==='KeyQ')spell();if(e.code==='Space'||e.code==='KeyK')dodge();});
addEventListener('keyup',e=>keys.delete(e.code));addEventListener('blur',()=>{keys.clear();if(state.phase==='battle')setPaused(true)});
canvas.addEventListener('pointerdown',e=>{if(e.button===0&&state.mode==='scene'&&state.phase==='battle')strike()});canvas.addEventListener('contextmenu',e=>e.preventDefault());
$('quality').addEventListener('click',()=>{if(!renderer)return;state.quality=state.quality==='balanced'?'high':'balanced';renderer.setPixelRatio(Math.min(devicePixelRatio,state.quality==='high'?2:1.25));$('quality').textContent='画质 · '+(state.quality==='high'?'精细':'均衡');resize()});
addEventListener('resize',resize);canvas.addEventListener('webglcontextlost',e=>{e.preventDefault();safeError(new Error('WebGL context lost'))});
init().catch(safeError);
