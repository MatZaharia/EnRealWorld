import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';

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
  constructor(element, {hero = false} = {}) {
    this.element = element;
    this.hero = hero;
    this.version = 0;
    this.visible = false;
    this.auto = hero && !reducedMotion;
    this.cut = 100;
    this.wire = false;
    this.renderer = new THREE.WebGLRenderer({antialias:true,alpha:true,powerPreference:'low-power'});
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, hero ? 1.5 : 1.8));
    this.renderer.setClearColor(0x080c12, 0);
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = .9;
    this.renderer.localClippingEnabled = true;
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.element.replaceChildren(this.renderer.domElement);
    this.renderer.domElement.setAttribute('aria-label','Interactive world geometry: drag to orbit, pinch or scroll to zoom');
    this.renderer.domElement.setAttribute('role','img');
    this.renderer.domElement.tabIndex = 0;
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(38, 1, 0.01, 250);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.needsRender = true;
    this.controls.addEventListener('change',()=>{this.needsRender=true;});
    this.controls.enableDamping = true;
    this.controls.dampingFactor = .075;
    this.controls.autoRotateSpeed = .6;
    this.controls.minDistance = .7;
    this.controls.maxDistance = 18;
    this.controls.maxPolarAngle = Math.PI * .87;
    this.controls.enablePan = !hero;
    this.controls.enableZoom = !hero;
    this.renderer.domElement.style.touchAction = hero ? 'pan-y' : 'none';
    this.scene.add(new THREE.HemisphereLight(0xcbeeff,0x29403c,.55));
    const sun = new THREE.DirectionalLight(0xffedce,1.8);
    sun.position.set(4,8,5);
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
    room.dispose();
    pmrem.dispose();
    this.grid = new THREE.GridHelper(14,40,0x42646a,0x1b343f);
    this.grid.material.transparent = true;
    this.grid.material.opacity = .32;
    this.grid.position.y = -.025;
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
      const offset=this.camera.position.clone().sub(this.controls.target);
      const s=new THREE.Spherical().setFromVector3(offset);
      if (e.key==='ArrowLeft') s.theta-=.12;
      if (e.key==='ArrowRight') s.theta+=.12;
      if (e.key==='ArrowUp') s.phi=Math.max(.15,s.phi-.1);
      if (e.key==='ArrowDown') s.phi=Math.min(2.7,s.phi+.1);
      if (e.key==='+') s.radius=Math.max(.7,s.radius*.9);
      if (e.key==='-') s.radius=Math.min(18,s.radius*1.1);
      this.camera.position.copy(this.controls.target).add(new THREE.Vector3().setFromSpherical(s));
      this.controls.update();
    });
    this.last=0;
    this.tick = time => {
      this.frame=requestAnimationFrame(this.tick);
      if (!this.visible || document.hidden || time-this.last<33) return;
      this.last=time;
      this.controls.autoRotate=this.auto;
      this.controls.update();
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
  async load(url, onProgress) {
    const version=++this.version;
    const gltf=await this.loader.loadAsync(url, event => {
      if (version===this.version) onProgress?.(event.lengthComputable ? event.loaded/event.total : null);
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
      const broad=Math.max(s.x,s.z)>180 && s.y<Math.max(s.x,s.z)*.15;
      const triangles=(o.geometry.index?.count || o.geometry.attributes.position.count)/3;
      const terrain=triangles<=12 && Math.min(s.x,s.z)>15 && s.y<Math.max(s.x,s.z)*.08;
      const sky=/sky|horizon(?!tal)|background/i.test(o.name);
      if (broad || terrain || sky) {o.visible=false;return;}
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
    this.target=new THREE.Vector3(0,this.height*.43,0);
    this.camera.fov=38;
    this.camera.position.set(5.2,this.height*.55+3.4,6.6);
    this.controls.target.copy(this.target);
    this.camera.updateProjectionMatrix();
    this.controls.update();
    this.controls.saveState();
    this.setCut(this.cut);
    let triangles=0,meshes=0;
    raw.traverse(o => {if(o.isMesh && o.visible){meshes++;triangles+=(o.geometry.index?.count || o.geometry.attributes.position.count)/3;}});
    this.stats={triangles:Math.round(triangles),meshes};
    return true;
  }
  reset() {this.controls.reset();}
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
    this.resizeObserver.disconnect();this.intersection.disconnect();this.controls.dispose();
    if(this.root) release(this.root);
    this.environment.dispose();this.grid.geometry.dispose();this.grid.material.dispose();this.renderer.dispose();
  }
}
