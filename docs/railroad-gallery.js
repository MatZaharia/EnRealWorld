import {loadingLabel} from './loading-progress.js';

export const railroadModels=[
  {id:'claude-fable-5-2',name:'Claude Fable 5.2',paired:true},
  {id:'gpt-6-1-sol',name:'GPT-6.1 Sol',paired:true},
  {id:'gpt-6-astra',name:'GPT-6 Astra',paired:true},
  {id:'gemini-4-neon',name:'Gemini 4 Neon',paired:true},
  {id:'gpt-6-2-astra',name:'GPT-6.2 Astra',paired:false}
];

export function initRailroadGallery(getViewer) {
  const $=id=>document.getElementById(id);
  let viewer=null,entered=false,version=0,selected=railroadModels[0],method='ours';
  const buttons=[...$('railroad-method').querySelectorAll('button')];
  $('railroad-models').replaceChildren(...railroadModels.map(item=>{
    const button=document.createElement('button');button.dataset.railModel=item.id;button.textContent=item.name;
    button.setAttribute('aria-pressed',String(item===selected));
    button.addEventListener('click',()=>{selected=item;sync();if(entered)load();});return button;
  }));
  const path=()=>`assets/models/railroad-${method}-${selected.id}.glb`;
  const sync=()=>{
    if(!selected.paired)method='base';
    $('railroad-models').querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.railModel===selected.id)));
    buttons.forEach(b=>{b.disabled=b.dataset.railMethod==='ours'&&!selected.paired;b.setAttribute('aria-pressed',String(b.dataset.railMethod===method));});
    $('railroad-title').textContent=selected.name;
    $('railroad-note').textContent=selected.paired?'Matched Base Agent / EnRealWorld scene exports. Switch methods and inspect the geometry.':'Base Agent only: the EnRealWorld run was interrupted and no executable scene was supplied. No substitute model is used.';
    $('railroad-download').href=path()+'?v=20261125-materials';$('railroad-download').download=path().split('/').pop();
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
    $('railroad-status').textContent=`Loading ${selected.name} / ${method==='ours'?'EnRealWorld':'Base Agent'}…`;
    try{
      if(!viewer){
        const start=$('railroad-start');if(start){start.disabled=true;start.textContent='Opening viewer…';}
        const {WorldViewer}=await getViewer();if(request!==version)return;
        viewer=new WorldViewer($('railroad-canvas'));
      }
      overlay('Loading geometry…');
      const complete=await viewer.load(url+'?v=20261125-materials',progress=>{
        if(request===version){const label=$('railroad-canvas').querySelector('.message-label');if(label)label.textContent=loadingLabel(progress);}
      });
      if(!complete||request!==version)return;
      $('railroad-canvas').querySelector('.viewer-message')?.remove();
      $('railroad-status').textContent=`${selected.name} / ${method==='ours'?'EnRealWorld':'Base Agent'} · ${viewer.stats.triangles.toLocaleString()} preview triangles · drag to orbit`;
    }catch(err){
      if(request!==version)return;
      overlay('Preview unavailable. You can still download the GLB.',true);
      $('railroad-status').textContent='Could not load this model. Retry or choose another result.';
      console.warn('Railroad gallery:',err.message);
    }
  }
  $('railroad-start').addEventListener('click',load);
  buttons.forEach(b=>b.addEventListener('click',()=>{method=b.dataset.railMethod;sync();if(entered)load();}));
  $('railroad-reset').addEventListener('click',()=>viewer?.reset());
  $('railroad-wire').addEventListener('click',e=>{if(viewer){viewer.setWire(!viewer.wire);e.currentTarget.setAttribute('aria-pressed',String(viewer.wire));}});
  $('railroad-auto').addEventListener('click',e=>{if(viewer){viewer.auto=!viewer.auto;e.currentTarget.setAttribute('aria-pressed',String(viewer.auto));}});
  $('railroad-full').addEventListener('click',async()=>{
    try{if(document.fullscreenElement)await document.exitFullscreen();else await $('railroad-panel').requestFullscreen();}
    catch{$('railroad-status').textContent='Fullscreen is unavailable in this browser.';}
  });
  sync();
  return {dispose(){++version;viewer?.dispose();},resume(){if(viewer)viewer.needsRender=true;}};
}
