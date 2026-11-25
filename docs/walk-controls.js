import * as THREE from 'three';

export class WalkControls {
  constructor(camera, canvas) {
    this.camera=camera;
    this.canvas=canvas;
    this.enabled=false;
    this.speed=1;
    this.multiplier=1;
    this.keys=new Set();
    this.buttons=new Set();
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
      if(!this.enabled||e.button!==0||this.pointer!=null)return;
      e.preventDefault();canvas.focus({preventScroll:true});
      this.pointer=e.pointerId;this.x=e.clientX;this.y=e.clientY;
      canvas.setPointerCapture(e.pointerId);
    });
    on(canvas,'pointermove',e=>{
      if(!this.enabled||e.pointerId!==this.pointer)return;
      this.euler.setFromQuaternion(camera.quaternion,'YXZ');
      this.euler.y-=(e.clientX-this.x)*.003;
      this.euler.x=THREE.MathUtils.clamp(this.euler.x-(e.clientY-this.y)*.003,-1.5,1.5);
      this.euler.z=0;
      camera.quaternion.setFromEuler(this.euler);
      this.x=e.clientX;this.y=e.clientY;this.changed=true;
    });
    const release=e=>{
      if(e.pointerId!==this.pointer)return;
      this.pointer=null;
      if(canvas.hasPointerCapture(e.pointerId))canvas.releasePointerCapture(e.pointerId);
    };
    on(canvas,'pointerup',release);on(canvas,'pointercancel',release);on(canvas,'lostpointercapture',release);
  }
  clear(){this.keys.clear();this.buttons.clear();this.pointer=null;}
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
