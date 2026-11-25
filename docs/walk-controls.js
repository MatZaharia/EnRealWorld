import * as THREE from 'three';

export class WalkControls {
  constructor(camera, canvas, onZoom=null) {
    this.camera=camera;
    this.canvas=canvas;
    this.onZoom=onZoom;
    this.enabled=false;
    this.speed=1;
    this.multiplier=1;
    this.keys=new Set();
    this.buttons=new Set();
    this.pointers=new Map();
    this.pinch=0;
    this.euler=new THREE.Euler(0,0,0,'YXZ');
    this.listeners=new AbortController();
    const on=(target,event,fn)=>target.addEventListener(event,fn,{signal:this.listeners.signal});
    const codes=['KeyW','KeyA','KeyS','KeyD','KeyQ','KeyE','ShiftLeft','ShiftRight'];
    const keyCode=e=>e.code||({w:'KeyW',a:'KeyA',s:'KeyS',d:'KeyD',q:'KeyQ',e:'KeyE',shift:'ShiftLeft',escape:'Escape'}[e.key.toLowerCase()]);
    on(canvas,'keydown',e=>{
      if(!this.enabled)return;
      const code=keyCode(e);
      if(codes.includes(code)){e.preventDefault();this.keys.add(code);}
      if(code==='Escape'){this.clear();canvas.blur();}
    });
    on(window,'keyup',e=>this.keys.delete(keyCode(e)));
    on(canvas,'blur',()=>this.clear());
    on(window,'blur',()=>this.clear());
    on(document,'visibilitychange',()=>{if(document.hidden)this.clear();});
    on(canvas,'pointerdown',e=>{
      if(!this.enabled||e.button!==0)return;
      e.preventDefault();canvas.focus({preventScroll:true});
      this.pointers.set(e.pointerId,{x:e.clientX,y:e.clientY});
      canvas.setPointerCapture(e.pointerId);
      this.pinch=this.pointers.size===2?this.spread():0;
    });
    on(canvas,'pointermove',e=>{
      if(!this.enabled||!this.pointers.has(e.pointerId))return;
      const previous=this.pointers.get(e.pointerId);
      this.pointers.set(e.pointerId,{x:e.clientX,y:e.clientY});
      if(this.pointers.size>=2){
        const spread=this.spread();
        if(this.pinch&&spread)this.onZoom?.(-(spread-this.pinch)*.45);
        this.pinch=spread;
        return;
      }
      this.euler.setFromQuaternion(this.camera.quaternion,'YXZ');
      this.euler.y-=(e.clientX-previous.x)*.003;
      this.euler.x=THREE.MathUtils.clamp(this.euler.x-(e.clientY-previous.y)*.003,-1.5,1.5);
      this.euler.z=0;
      this.camera.quaternion.setFromEuler(this.euler);
      this.changed=true;
    });
    const release=e=>{
      if(!this.pointers.has(e.pointerId))return;
      this.pointers.delete(e.pointerId);
      if(canvas.hasPointerCapture(e.pointerId))canvas.releasePointerCapture(e.pointerId);
      this.pinch=this.pointers.size===2?this.spread():0;
    };
    on(canvas,'pointerup',release);on(canvas,'pointercancel',release);on(canvas,'lostpointercapture',release);
  }
  spread(){
    const points=[...this.pointers.values()];
    return points.length<2?0:Math.hypot(points[0].x-points[1].x,points[0].y-points[1].y);
  }
  clear(){this.keys.clear();this.buttons.clear();this.pointers.clear();this.pinch=0;}
  update(dt){
    if(!this.enabled)return false;
    const held=key=>this.keys.has(key)||this.buttons.has(key);
    const move=new THREE.Vector3(Number(held('KeyD'))-Number(held('KeyA')),Number(held('KeyE'))-Number(held('KeyQ')),Number(held('KeyS'))-Number(held('KeyW')));
    if(move.lengthSq()){
      move.normalize();
      const yaw=new THREE.Euler().setFromQuaternion(this.camera.quaternion,'YXZ').y;
      move.applyAxisAngle(new THREE.Vector3(0,1,0),yaw);
      const boost=held('ShiftLeft')||held('ShiftRight')?3:1;
      this.camera.position.addScaledVector(move,this.speed*this.multiplier*boost*Math.min(dt,.05));
      this.changed=true;
    }
    const changed=this.changed;this.changed=false;return changed;
  }
  dispose(){this.clear();this.listeners.abort();}
}
