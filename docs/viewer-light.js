import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { WalkControls } from './walk-controls.js?v=20261126-ui7';
import { normalizedProgress } from './loading-progress.js';

const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;

function release(root) {
  const geometries = new Set(), materials = new Set(), textures = new Set();
  root.traverse(o => {
    if (!o.isMesh) return;
    geometries.add(o.geometry);
    for (const m of Array.isArray(o.material) ? o.material : [o.material]) {
      materials.add(m);
      for (const v of Object.values(m)) if (v?.isTexture) textures.add(v);
    }
  });
  for (const item of [...geometries, ...materials, ...textures]) item.dispose();
}

export class WorldViewer {
  constructor(element, {hero = false, freeWalk = false} = {}) {
    this.element = element;
    this.hero = hero;
    this.freeWalk = freeWalk;
    this.version = 0;
    this.visible = false;
    this.auto = hero && !reducedMotion;
    this.cut = 100;
    this.wire = false;
    this.renderer = new THREE.WebGLRenderer({antialias:true,alpha:true,powerPreference:'low-power'});
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, hero ? 1.5 : 1.8));
    this.renderer.setClearColor(0xf5f7f4, 0);
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = .9;
    this.renderer.localClippingEnabled = true;
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.element.replaceChildren(this.renderer.domElement);
    this.renderer.domElement.setAttribute('aria-label','Interactive world geometry: drag to look, WASD to move, scroll to zoom');
    this.renderer.domElement.setAttribute('role','img');
    this.renderer.domElement.tabIndex = 0;
    if (freeWalk) this.renderer.domElement.addEventListener('wheel', e => {
      if (!this.root || this.mode !== 'walk') return;
      e.preventDefault();
      this.zoomBy(Math.sign(e.deltaY) * 4);
    }, {passive:false});
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(38, 1, 0.01, 250);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.walk=new WalkControls(this.camera,this.renderer.domElement,delta=>this.zoomBy(delta));
    this.mode='orbit';
    this.needsRender = true;
    this.controls.addEventListener('change',()=>{this.needsRender=true;});
    this.controls.enableDamping = true;
    this.controls.dampingFactor = .075;
    this.controls.autoRotateSpeed = .6;
    this.controls.minDistance = freeWalk ? .25 : .7;
    this.controls.maxDistance = freeWalk ? 36 : 18;
    this.controls.maxPolarAngle = Math.PI * .87;
    this.controls.enablePan = !hero;
    this.controls.enableZoom = !hero;
    this.renderer.domElement.style.touchAction = hero ? 'pan-y' : 'none';
    this.scene.add(new THREE.HemisphereLight(0xf4f9ff,0xc2d0bc,.55));
    const sun = new THREE.DirectionalLight(0xfff3de,1.8);
    sun.position.set(-3,8,4);
    sun.castShadow = true;
    sun.shadow.mapSize.set(1024,1024);
    Object.assign(sun.shadow.camera,{left:-5,right:5,top:5,bottom:-5,near:.1,far:25});
    sun.shadow.bias = -.0003;
    this.scene.add(sun);
    const rim = new THREE.DirectionalLight(0x88ccff,.7);
    rim.position.set(-5,3,-4);
    this.scene.add(rim);
    const pmrem = new THREE.PMREMGenerator(this.renderer);
    const room = new RoomEnvironment();
    this.environment = pmrem.fromScene(room,.04);
    this.scene.environment = this.environment.texture;
    this.scene.environmentIntensity = .55;
    room.dispose();
    pmrem.dispose();
    this.stage = new THREE.Group();
    const pedestal = new THREE.Mesh(new THREE.CylinderGeometry(4.3,4.3,.15,96),new THREE.MeshStandardMaterial({color:0xe1e9dd,roughness:.85}));
    pedestal.position.y=-.115;
    pedestal.receiveShadow=true;
    this.stage.add(pedestal);
    const edge = new THREE.Mesh(new THREE.TorusGeometry(4.3,.009,6,128),new THREE.MeshBasicMaterial({color:0x88aca0,transparent:true,opacity:.4}));
    edge.rotation.x=Math.PI/2;
    edge.position.y=-.035;
    this.stage.add(edge);
    const ground = new THREE.Mesh(new THREE.PlaneGeometry(30,30),new THREE.ShadowMaterial({opacity:.12}));
    ground.rotation.x=-Math.PI/2;
    ground.position.y=-.195;
    ground.receiveShadow=true;
    this.stage.add(ground);
    this.scene.add(this.stage);
    this.grid = new THREE.GridHelper(8.5,28,0x8eafa0,0xb4c7b4);
    this.grid.material.transparent = true;
    this.grid.material.opacity = .16;
    this.grid.position.y = -.028;
    this.scene.add(this.grid);
    this.plane = new THREE.Plane(new THREE.Vector3(0,-1,0), 10);
    this.loader = new GLTFLoader().setMeshoptDecoder(MeshoptDecoder);
    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(element);
    this.intersection = new IntersectionObserver(([entry]) => {this.visible=entry.isIntersecting;},{rootMargin:'80px'});
    this.intersection.observe(element);
    this.resize();
    this.renderer.domElement.addEventListener('keydown', e => {
      if (!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','+','-','Home'].includes(e.key)) return;
      e.preventDefault();
      if (e.key==='Home') {this.reset();return;}
      if(this.mode==='walk'){
        if(e.key==='+'||e.key==='-')this.zoomBy(e.key==='+'?-4:4);
        return;
      }
      const offset=this.camera.position.clone().sub(this.controls.target);
      const s=new THREE.Spherical().setFromVector3(offset);
      if (e.key==='ArrowLeft') s.theta-=.12;
      if (e.key==='ArrowRight') s.theta+=.12;
      if (e.key==='ArrowUp') s.phi=Math.max(.15,s.phi-.1);
      if (e.key==='ArrowDown') s.phi=Math.min(2.7,s.phi+.1);
      if (e.key==='+') s.radius=Math.max(this.controls.minDistance,s.radius*.9);
      if (e.key==='-') s.radius=Math.min(this.controls.maxDistance,s.radius*1.1);
      this.camera.position.copy(this.controls.target).add(new THREE.Vector3().setFromSpherical(s));
      this.controls.update();
    });
    this.last=0;
    this.tick = time => {
      this.frame=requestAnimationFrame(this.tick);
      if (!this.visible || document.hidden || time-this.last<33) return;
      const dt=Math.min((time-this.last)/1000,.05);
      this.last=time;
      this.controls.autoRotate=this.auto&&this.mode==='orbit';
      if(this.walk.update(dt))this.needsRender=true;
      if(this.mode==='orbit')this.controls.update();
      if(this.needsRender || this.auto){
        this.renderer.render(this.scene,this.camera);
        this.needsRender=false;
      }
    };
    this.frame=requestAnimationFrame(this.tick);
  }
  resize() {
    const w=this.element.clientWidth,h=this.element.clientHeight;
    if (!w || !h) return;
    this.renderer.setSize(w,h,false);
    this.camera.aspect=w/h;
    this.camera.updateProjectionMatrix();
    this.needsRender=true;
  }
  async load(url, onProgress, {walk=null, initialMode=walk?'walk':'orbit'}={}) {
    const version=++this.version;
    const gltf=await this.loader.loadAsync(url, event => {
      if (version===this.version) onProgress?.(event.lengthComputable ? normalizedProgress(event.loaded,event.total) : null);
    });
    if (version!==this.version) {release(gltf.scene);return false;}
    if (this.root) {this.scene.remove(this.root);release(this.root);}
    const raw=gltf.scene;
    raw.updateMatrixWorld(true);
    const box=new THREE.Box3(),focusBox=new THREE.Box3();
    raw.traverse(o => {
      if (!o.isMesh) return;
      const b=new THREE.Box3().setFromObject(o);
      const s=b.getSize(new THREE.Vector3());
      const broad=Math.max(s.x,s.z)>180 && s.y<Math.max(s.x,s.z)*.2;
      const triangles=(o.geometry.index?.count || o.geometry.attributes.position.count)/3;
      const terrain=!walk && triangles<=12 && Math.min(s.x,s.z)>15 && s.y<Math.max(s.x,s.z)*.08;
      const sky=/sky|horizon|background/i.test(o.name);
      const detachedTie=url.includes('railroad-ours-claude-fable-5-2') && /^Loose_SpareTie_\d+$/.test(o.name);
      const astraTerrain=url.includes('railroad-ours-gpt-6-astra.glb') && o.name==='mesh_65' && o.material?.name==='Dry ochre ballast';
      if (broad || terrain || sky || detachedTie || astraTerrain) {o.visible=false;return;}
      o.castShadow=true;
      o.receiveShadow=true;
      box.union(b);
      if(s.y>1 && s.y>Math.max(s.x,s.z)*.14) focusBox.union(b);
      const mats=Array.isArray(o.material)?o.material:[o.material];
      for (const m of mats) {
        m.side=THREE.DoubleSide;
        m.clippingPlanes=[];
        m.wireframe=this.wire;
      }
    });
    if (box.isEmpty()) throw new Error('No visible geometry in this preview.');
    if(!focusBox.isEmpty()) box.copy(focusBox);
    const size=box.getSize(new THREE.Vector3()),center=box.getCenter(new THREE.Vector3());
    const scale=5/Math.max(size.x,size.y,size.z);
    this.root=new THREE.Group();
    raw.position.set(-center.x,-box.min.y,-center.z);
    this.root.add(raw);
    this.root.scale.setScalar(scale);
    this.scene.add(this.root);
    this.height=size.y*scale;
    this.sourceScale=scale;
    const overviewTarget=new THREE.Vector3(0,this.height*.43,0);
    const overviewPosition=new THREE.Vector3(5.2,this.height*.55+3.4,6.6);
    const insidePosition=walk?.position
      ? new THREE.Vector3(...walk.position).add(raw.position).multiplyScalar(scale)
      : new THREE.Vector3(0,Math.min(this.height*.4,1.65*scale),0);
    this.walkHome={position:insidePosition,lookAt:insidePosition.clone().add(new THREE.Vector3(...(walk?.forward||[0,0,-1])))};
    this.walk.speed=(walk?.speed||1.8)*scale;
    this.camera.position.copy(overviewPosition);
    this.controls.target.copy(overviewTarget);
    this.controls.saveState();
    this.setMode(initialMode);
    this.setCut(this.cut);
    let triangles=0,meshes=0;
    raw.traverse(o => {if(o.isMesh && o.visible){meshes++;triangles+=(o.geometry.index?.count || o.geometry.attributes.position.count)/3;}});
    this.stats={triangles:Math.round(triangles),meshes};
    return true;
  }
  setMode(mode) {
    if(!this.root)return;
    this.mode=mode;
    const walking=mode==='walk';
    this.walk.clear();
    this.walk.enabled=walking||this.freeWalk;
    this.walk.orbitTarget=walking?null:this.controls.target;
    this.controls.enabled=!walking;
    this.stage.visible=!walking;
    this.grid.visible=!walking;
    if(walking){this.auto=false;this.controls.autoRotate=false;}
    this.camera.near=walking?Math.max(.0001,this.sourceScale*.015):.01;
    if(!walking){
      this.camera.fov=38;
      this.camera.updateProjectionMatrix();
    }
    this.renderer.domElement.dataset.navigation=mode;
    this.renderer.domElement.setAttribute('aria-label',walking?'First-person world viewer. Click to focus; WASD move, drag to look, Q and E down and up, Shift faster, Home reset.':'World overview. Drag to orbit, right-drag to pan, scroll to zoom.');
    this.reset();
  }
  reset() {
    this.walk.clear();
    if(this.mode==='walk'&&this.walkHome){
      this.camera.position.copy(this.walkHome.position);
      this.camera.lookAt(this.walkHome.lookAt);
      this.camera.fov=68;
      this.camera.updateProjectionMatrix();
    }else if(this.root){
      const {enableDamping,autoRotate}=this.controls;
      this.controls.enableDamping=false;
      this.controls.autoRotate=false;
      this.controls.update();
      this.controls.reset();
      Object.assign(this.controls,{enableDamping,autoRotate});
    }
    this.needsRender=true;
  }
  zoomBy(delta) {
    if(!this.root)return;
    if(this.mode==='walk'){
      this.camera.fov=THREE.MathUtils.clamp(this.camera.fov+delta,12,105);
      this.camera.updateProjectionMatrix();
    }else{
      const offset=this.camera.position.clone().sub(this.controls.target);
      const radius=THREE.MathUtils.clamp(offset.length()*Math.exp(delta/40),this.controls.minDistance,this.controls.maxDistance);
      this.camera.position.copy(this.controls.target).add(offset.setLength(radius));
      this.controls.update();
    }
    this.needsRender=true;
  }
  setWire(value) {
    this.needsRender=true;
    this.wire=value;
    this.root?.traverse(o => {
      if (o.isMesh) for (const m of Array.isArray(o.material)?o.material:[o.material]) m.wireframe=value;
    });
  }
  setCut(value) {
    this.needsRender=true;
    this.cut=Number(value);
    this.plane.constant=this.height*this.cut/100+.005;
    this.root?.traverse(o => {
      if (o.isMesh) for (const m of Array.isArray(o.material)?o.material:[o.material]) m.clippingPlanes=this.cut>=100?[]:[this.plane];
    });
  }
  dispose() {
    ++this.version;
    cancelAnimationFrame(this.frame);
    this.resizeObserver.disconnect();this.intersection.disconnect();this.controls.dispose();this.walk.dispose();
    if(this.root) release(this.root);
    release(this.stage);
    this.environment.dispose();this.grid.geometry.dispose();this.grid.material.dispose();this.renderer.dispose();
  }
}
