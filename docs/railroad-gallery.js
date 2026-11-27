import {loadingLabel} from './loading-progress.js';
import {bindWalkPad} from './walk-pad.js';

export const railroadModels=[
  {id:'claude-fable-5-2',name:'Claude Fable 5.2'},
  {id:'gemini-4-neon',name:'Gemini 4 Neon',nativeScene:true},
  {id:'gpt-6-2-astra',name:'GPT-6.2 Astra',nativeScene:true},
  {id:'gpt-6-1-sol',name:'GPT-6.1 Sol',oursSourceCamera:true}
];

export function initRailroadGallery(getViewer) {
  const $=id=>document.getElementById(id);
  let viewer=null,entered=false,version=0,selected=railroadModels[0],method='ours';
  let navigationMode='orbit';
  const setWalkReady=bindWalkPad($('railroad-walk-help'),()=>viewer,'railroad-walk-speed');
  const navigationButtons={orbit:$('railroad-orbit'),walk:$('railroad-walk')};
  const autoButton=$('railroad-auto');
  const updateNavigation=ready=>{
    for(const [mode,button] of Object.entries(navigationButtons)){
      button.disabled=!ready;
      button.setAttribute('aria-pressed',String(mode===navigationMode));
    }
    autoButton.disabled=!ready||navigationMode==='walk';
    autoButton.setAttribute('aria-pressed',String(viewer?.auto??false));
    $('railroad-reset').parentElement.hidden=!ready;
    $('railroad-wire').disabled=!ready;
    setWalkReady(ready);
  };
  for(const [mode,button] of Object.entries(navigationButtons)){
    button.addEventListener('click',()=>{
      if(navigationMode!==mode)viewer.setMode(mode);
      navigationMode=mode;updateNavigation(true);
      viewer.renderer.domElement.focus({preventScroll:true});
    });
  }
  const buttons=[...document.querySelectorAll('#railroad-method button')];
  $('railroad-models').replaceChildren(...railroadModels.map(item=>{
    const button=document.createElement('button');button.dataset.railModel=item.id;button.textContent=item.name;
    button.setAttribute('aria-pressed',String(item===selected));
    button.addEventListener('click',()=>{selected=item;sync();if(entered)load();});return button;
  }));
  const path=()=>`assets/models/railroad-${method}-${selected.id}.glb`;
  const sync=()=>{
    $('railroad-models').querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.railModel===selected.id)));
    buttons.forEach(b=>{b.setAttribute('aria-pressed',String(b.dataset.railMethod===method));});
    $('railroad-title').textContent=selected.name;
    const render=$('railroad-render');
    const src=`assets/img/railroad-${method}-${selected.id}-preview.jpg`;
    render.href=src;
    const img=render.querySelector('img');
    img.src=src;
    img.alt=`${selected.name} / ${method==='ours'?'EnRealWorld':'Base Agent'} original render`;
    if(!entered)$('railroad-status').textContent='Choose a model, then enter the 3D comparison.';
  };
  const overlay=(message,retry=false)=>{
    $('railroad-canvas').querySelector('.viewer-message')?.remove();
    const div=document.createElement('div');div.className='viewer-message';
    const label=document.createElement('span');label.className='message-label';label.textContent=message;div.append(label);
    if(retry){const button=document.createElement('button');button.className='button';button.textContent='Retry';button.onclick=load;div.append(button);}
    $('railroad-canvas').append(div);
  };
  async function load(){
    entered=true;const request=++version,url=path();
    updateNavigation(false);
    $('railroad-status').textContent=`Loading ${selected.name} / ${method==='ours'?'EnRealWorld':'Base Agent'}…`;
    try{
      if(!viewer){
        const start=$('railroad-start');if(start){start.disabled=true;start.textContent='Opening viewer…';}
        const {WorldViewer}=await getViewer();if(request!==version)return;
        viewer=new WorldViewer($('railroad-canvas'),{freeWalk:true});
      }
      overlay('Loading geometry…');
      let sceneMetadata=null;
      if(selected.nativeScene || (selected.oursSourceCamera && method==='ours')){
        const response=await fetch(url.replace(/\.glb$/,'.json')+'?v=20261126-gallery2');
        if(!response.ok)throw new Error('Scene metadata unavailable');
        sceneMetadata=await response.json();
        if(request!==version)return;
      }
      const complete=await viewer.load(url+'?v=20261126-gallery2',progress=>{
        if(request===version){const label=$('railroad-canvas').querySelector('.message-label');if(label)label.textContent=loadingLabel(progress);}
      },{sceneMetadata,initialMode:navigationMode,walkFromOverview:true});
      if(!complete||request!==version)return;
      $('railroad-canvas').querySelector('.viewer-message')?.remove();
      updateNavigation(true);
      $('railroad-status').textContent=`${selected.name} / ${method==='ours'?'EnRealWorld':'Base Agent'} · ${viewer.stats.triangles.toLocaleString()} preview triangles`;
    }catch(err){
      if(request!==version)return;
      overlay('Preview unavailable.',true);
      $('railroad-status').textContent='Could not load this model. Retry or choose another result.';
      console.warn('Railroad gallery:',err.message);
    }
  }
  $('railroad-start').addEventListener('click',load);
  buttons.forEach(b=>b.addEventListener('click',()=>{method=b.dataset.railMethod;sync();if(entered)load();}));
  $('railroad-zoom-in').addEventListener('click',()=>viewer?.zoomBy(-8));
  $('railroad-zoom-out').addEventListener('click',()=>viewer?.zoomBy(8));
  $('railroad-reset').addEventListener('click',()=>viewer?.reset());
  $('railroad-wire').addEventListener('click',e=>{if(viewer){viewer.setWire(!viewer.wire);e.currentTarget.setAttribute('aria-pressed',String(viewer.wire));}});
  autoButton.addEventListener('click',()=>{viewer.auto=!viewer.auto;updateNavigation(true);});
  $('railroad-full').addEventListener('click',async()=>{
    try{if(document.fullscreenElement)await document.exitFullscreen();else await $('railroad-panel').requestFullscreen();}
    catch{$('railroad-status').textContent='Fullscreen is unavailable in this browser.';}
  });
  sync();updateNavigation(false);
  return {dispose(){++version;viewer?.dispose();},resume(){if(viewer)viewer.needsRender=true;}};
}
