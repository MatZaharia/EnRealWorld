import {worldCases,walkthroughs,agents,phases,evidence,modelNames} from './data-light.js?v=20261125-ui3';
import {initCharts} from './charts-light.js?v=20261125-ui3';
import {initSelectControls} from './select-controls.js?v=20261125-ui3';
import {loadingLabel} from './loading-progress.js';
import {initRailroadGallery} from './railroad-gallery.js?v=20261125-ui3';
const $=id=>document.getElementById(id);
const motionReduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
const esc=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pressed=(group,selected)=>group.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b===selected)));
let viewerModule;
const getViewer=()=>viewerModule??=import('./viewer-light.js?v=20261125-ui3');
let heroViewer,worldViewer,category='blueprint',selectedCase=worldCases.blueprint[0],method='ours',worldEntered=false,loadVersion=0;
let cases=[],model='gpt',dataset='all',query='',page=0,activeCase,playing=false,v2wReady=false;
const PAGE_SIZE=12;
const clips=[$('v2w-src'),$('v2w-ours')];
let animation;

function openImage(path,caption,isInput=false) {
  const image=$('figure-image');
  image.src=path;image.alt=caption;image.classList.remove('zoomed');image.dataset.input=String(isInput);
  $('figure-caption').textContent=caption;
  if(!$('figure-dialog').open)$('figure-dialog').showModal();
}
function openFigure(name,caption) {openImage(`assets/fig/${name}.webp`,caption);}
function initFigures() {
  document.querySelectorAll('[data-figure]').forEach(b=>b.addEventListener('click',()=>openFigure(b.dataset.figure,b.dataset.caption)));
  $('close-figure').addEventListener('click',()=>{$('figure-dialog').close();});
  $('figure-image').addEventListener('click',e=>e.currentTarget.classList.toggle('zoomed'));
  $('figure-dialog').addEventListener('click',e=>{if(e.target===$('figure-dialog'))$('figure-dialog').close();});
}
function showWorldMessage(text,loading=true) {
  $('world-canvas').querySelector('.viewer-message')?.remove();
  const div=document.createElement('div');div.className='viewer-message';
  if(loading){const ring=document.createElement('span');ring.className='loading-ring';div.append(ring);}
  const label=document.createElement('span');label.textContent=text;label.className='message-label';div.append(label);
  if(!loading){const button=document.createElement('button');button.className='button';button.textContent='Retry loading';button.addEventListener('click',loadWorld);div.append(button);}
  $('world-canvas').append(div);
}
async function initHero() {
  const picker=document.querySelector('.hero-scene-picker');
  const featured={
    railroad:{file:'railroad-ours-claude-fable-5-2',name:'HOUSE BY THE RAILROAD',input:'A painted reference',output:'A world beyond the frame'},
    lighthouse:{file:'lighthouse-ours',name:'LIGHTHOUSE / MEASURED DRAWINGS',input:'A measured drawing',output:'A tower with interior structure'},
    ranch:{file:'ranch-ours',name:'GOODNIGHT RANCH HOUSE',input:'A measured floor plan',output:'A house you can explore'}
  };
  let version=0;
  const load=async key=>{
    const request=++version,item=featured[key];
    $('hero-scene-name').textContent='LOADING THE NEXT WORLD…';
    pressed(picker,picker.querySelector(`[data-hero-scene="${key}"]`));
    try{
      const complete=await heroViewer.load(`assets/models/${item.file}.glb`);
      if(!complete||request!==version)return;
      $('hero-scene-name').textContent=item.name;
      document.querySelector('.tag-a b').textContent=item.input;
      document.querySelector('.tag-b b').textContent=item.output;
    }catch(err){
      if(request===version)$('hero-scene-name').textContent='PREVIEW UNAVAILABLE / TRY ANOTHER WORLD';
      console.warn('Featured world unavailable:',err.message);
    }
  };
  picker.querySelectorAll('button').forEach(b=>{b.disabled=true;});
  $('hero-scene-name').setAttribute('role','status');
  try {
    const {WorldViewer}=await getViewer();
    heroViewer=new WorldViewer($('hero-canvas'),{hero:true});
    $('hero-motion').setAttribute('aria-pressed',String(heroViewer.auto));
    $('hero-motion').textContent=heroViewer.auto?'Pause rotation':'Start rotation';
    picker.addEventListener('click',e=>{const b=e.target.closest('[data-hero-scene]');if(b)load(b.dataset.heroScene);});
    picker.querySelectorAll('button').forEach(b=>{b.disabled=false;});
    await load('railroad');
  } catch(err) {
    heroViewer?.dispose();heroViewer=null;
    $('hero-canvas').innerHTML='<img src="assets/figimg/fig5/014.jpg" alt="Generated house preview" style="height:100%;width:100%;object-fit:contain;border-radius:16px">';
    $('hero-motion').hidden=true;
    $('hero-scene-name').textContent='STATIC PREVIEW / WEBGL UNAVAILABLE';
    picker.querySelectorAll('button').forEach(b=>{b.disabled=true;});
    console.warn('3D hero unavailable:',err.message);
  }
}
function modelPath() {
  const name=selectedCase[method]||`${selectedCase.model}-${method}`;
  return `assets/models/${name}.glb`;
}
function renderWorldCase() {
  if(selectedCase.compare===false)method='ours';
  const baseButton=$('world-method').querySelector('[data-method="base"]');
  baseButton.disabled=selectedCase.compare===false;
  baseButton.title=selectedCase.compare===false?'No matched Base Agent scene was supplied.':'';
  pressed($('world-method'),$('world-method').querySelector(`[data-method="${method}"]`));
  $('world-title').textContent=selectedCase.title;
  $('world-description').textContent=selectedCase.description;
  $('world-meta').textContent=selectedCase.meta;
  const ref=$('world-reference');ref.replaceChildren();
  if(selectedCase.ref){
    const img=document.createElement('img');img.src=selectedCase.ref;img.alt=`Input reference for ${selectedCase.title}`;
    img.addEventListener('click',()=>openImage(selectedCase.ref,`${selectedCase.title} · input reference`,true));
    img.tabIndex=0;img.setAttribute('role','button');img.setAttribute('aria-label',`Expand ${selectedCase.title} reference`);
    img.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();img.click();}});ref.append(img);
  }else{const p=document.createElement('div');p.className='prompt';p.textContent=selectedCase.prompt;ref.append(p);}
  $('world-download').href=modelPath();
  $('world-download').setAttribute('download',modelPath().split('/').pop());
  $('cut-control').hidden=category==='painting';
  $('world-cases').innerHTML=worldCases[category].map(c=>`<button class="case-card" data-case="${c.id}" aria-pressed="${c.id===selectedCase.id}"><img src="${c.thumb}" alt="" loading="lazy"><div><strong>${esc(c.title)}</strong><small>${esc(c.sub)}</small></div></button>`).join('');
  $('world-cases').classList.toggle('two-cases',category==='painting');
  const pairs={lighthouse:['fig3','037','048'],yates:['fig3','061','062'],ranch:['fig3','060','049'],railroad:['fig5','013','014'],studio:['fig3','025','026'],factory:['fig3','000','001'],home:['fig3','004','005']};
  const pair=pairs[selectedCase.id];
  document.querySelector('.render-comparison').hidden=!pair;
  if(pair){
    $('render-base').src=`assets/figimg/${pair[0]}/${pair[1]}.jpg`;
    $('render-ours').src=`assets/figimg/${pair[0]}/${pair[2]}.jpg`;
  }
  $('walk-help').hidden=!walkthroughs[selectedCase.id];
  if(worldEntered)loadWorld();
}
async function loadWorld() {
  worldEntered=true;
  const version=++loadVersion,path=modelPath();
  $('world-status').textContent=`Loading ${selectedCase.title} / ${method==='ours'?'EnRealWorld':'Base Agent'}…`;
  try {
    if(!worldViewer){
      const start=$('start-world');
      if(start){start.disabled=true;start.textContent='Opening viewer…';}
      const {WorldViewer}=await getViewer();
      if(version!==loadVersion)return;
      worldViewer=new WorldViewer($('world-canvas'));
    }
    if(version!==loadVersion)return;
    showWorldMessage('Loading real scene geometry…');
    const complete=await worldViewer.load(path,progress=>{
      const label=$('world-canvas').querySelector('.message-label');
      if(label&&version===loadVersion)label.textContent=loadingLabel(progress);
    },{walk:walkthroughs[selectedCase.id]?.[method]});
    if(!complete||version!==loadVersion)return;
    $('world-canvas').querySelector('.viewer-message')?.remove();
    updateNavigation();
    worldViewer.setCut(category!=='painting'?$('world-cut').value:100);
  }catch(err){
    if(version!==loadVersion)return;
    showWorldMessage('3D preview could not load. Check WebGL support and serve this page over HTTP.',false);
    $('world-status').textContent='Preview unavailable. Videos and downloadable GLB files remain available.';
    console.warn('World preview unavailable:',err.message);
  }
}
function updateNavigation(){
  const walking=worldViewer?.mode==='walk';
  $('world-orbit').setAttribute('aria-pressed',String(!walking));
  $('world-walk').setAttribute('aria-pressed',String(walking));
  $('walk-help').hidden=!walking;
  $('world-auto').disabled=walking;
  $('world-auto').setAttribute('aria-pressed',String(worldViewer?.auto||false));
  if(worldViewer?.stats)$('world-status').textContent=`${method==='ours'?'EnRealWorld':'Base Agent'} · ${worldViewer.stats.triangles.toLocaleString()} preview triangles · ${walking?'WASD move / drag to look / Q E height':'drag orbit / right-drag pan / scroll zoom'}`;
}
function initWorlds() {
  $('start-world').addEventListener('click',loadWorld);
  for(const mode of ['orbit','walk'])$('world-'+mode).addEventListener('click',()=>{
    if(!worldViewer?.root)return;
    worldViewer.setMode(mode);updateNavigation();
    if(mode==='walk'){
      $('world-cut').value=100;$('cut-value').textContent='Full';worldViewer.setCut(100);
      worldViewer.renderer.domElement.focus({preventScroll:true});
    }
  });
  $('walk-speed').addEventListener('change',e=>{if(worldViewer)worldViewer.walk.multiplier=Number(e.target.value);});
  document.querySelectorAll('[data-walk-key]').forEach(button=>{
    button.addEventListener('pointerdown',e=>{
      if(!worldViewer||worldViewer.mode!=='walk')return;
      e.preventDefault();button.setPointerCapture(e.pointerId);
      worldViewer.walk.buttons.add(button.dataset.walkKey);button.classList.add('held');
    });
    const release=()=>{worldViewer?.walk.buttons.delete(button.dataset.walkKey);button.classList.remove('held');};
    button.addEventListener('pointerup',release);button.addEventListener('pointercancel',release);button.addEventListener('lostpointercapture',release);
  });
  $('world-tabs').addEventListener('click',e=>{
    const b=e.target.closest('[data-category]');if(!b)return;
    category=b.dataset.category;selectedCase=worldCases[category][0];
    pressed($('world-tabs'),b);$('world-cut').value=100;$('cut-value').textContent='Full';renderWorldCase();
  });
  $('world-cases').addEventListener('click',e=>{
    const b=e.target.closest('[data-case]');if(!b)return;
    selectedCase=worldCases[category].find(c=>c.id===b.dataset.case);
    worldEntered=true;
    renderWorldCase();
  });
  $('world-method').addEventListener('click',e=>{
    const b=e.target.closest('[data-method]');if(!b)return;
    method=b.dataset.method;pressed($('world-method'),b);$('world-download').href=modelPath();
    $('world-download').setAttribute('download',modelPath().split('/').pop());
    if(worldEntered)loadWorld();
  });
  $('world-reset').addEventListener('click',()=>worldViewer?.reset());
  $('world-auto').addEventListener('click',e=>{
    if(!worldViewer)return;
    worldViewer.auto=!worldViewer.auto;e.currentTarget.setAttribute('aria-pressed',String(worldViewer.auto));
  });
  $('world-wire').addEventListener('click',e=>{
    if(!worldViewer)return;
    worldViewer.setWire(!worldViewer.wire);e.currentTarget.setAttribute('aria-pressed',String(worldViewer.wire));
  });
  $('world-cut').addEventListener('input',e=>{
    worldViewer?.setCut(e.target.value);$('cut-value').textContent=Number(e.target.value)===100?'Full':`${e.target.value}%`;
  });
  $('world-full').addEventListener('click',async()=>{
    const panel=$('world-canvas').parentElement;
    try{if(document.fullscreenElement)await document.exitFullscreen();else if(panel.requestFullscreen)await panel.requestFullscreen();else $('world-status').textContent='Fullscreen is not supported by this browser.';}
    catch{$('world-status').textContent='Fullscreen is unavailable in this browser context.';}
  });
  $('hero-motion').addEventListener('click',e=>{
    if(!heroViewer)return;
    heroViewer.auto=!heroViewer.auto;e.currentTarget.setAttribute('aria-pressed',String(heroViewer.auto));e.currentTarget.textContent=heroViewer.auto?'Pause rotation':'Start rotation';
  });
  const reveal=value=>{
    const p=Math.max(0,Math.min(100,Number(value)));
    $('render-slider').value=p;
    $('render-base-layer').style.clipPath=`inset(0 ${100-p}% 0 0)`;
    $('render-divider').style.left=`${p}%`;
  };
  $('render-slider').addEventListener('input',e=>reveal(e.target.value));
  const comparison=$('render-reveal');
  let pointer=null;
  const drag=e=>{
    if(e.pointerId!==pointer)return;
    const box=comparison.getBoundingClientRect();
    reveal((e.clientX-box.left)/box.width*100);
  };
  comparison.querySelectorAll('img').forEach(img=>{img.draggable=false;});
  comparison.addEventListener('dragstart',e=>e.preventDefault());
  comparison.addEventListener('pointerdown',e=>{
    if(e.button!==0||pointer!==null)return;
    e.preventDefault();
    pointer=e.pointerId;
    comparison.setPointerCapture(pointer);
    drag(e);
  });
  comparison.addEventListener('pointermove',drag);
  const end=e=>{
    if(e.pointerId!==pointer)return;
    pointer=null;
    if(comparison.hasPointerCapture(e.pointerId))comparison.releasePointerCapture(e.pointerId);
  };
  comparison.addEventListener('pointerup',end);
  comparison.addEventListener('pointercancel',end);
  comparison.addEventListener('lostpointercapture',()=>{pointer=null;});
  renderWorldCase();initHero();
}
function renderPhase(index) {
  const phase=phases[index];
  $('agent-grid').innerHTML=agents.map((agent,i)=>`<article class="agent-card" style="--agent:${agent.color}"><div class="agent-icon">${agent.icon}</div><h3>${agent.name}</h3><p>${agent.description}</p><div class="agent-task">${phase.tasks[i]}</div></article>`).join('');
  $('phase-routing').textContent=phase.routing;$('phase-outcome').textContent=phase.outcome;
}
function initMethod() {
  document.querySelector('.phase-selector').addEventListener('click',e=>{
    const b=e.target.closest('[data-phase]');if(!b)return;
    pressed(b.parentElement,b);renderPhase(Number(b.dataset.phase));
  });
  renderPhase(0);
}
function renderEvidence(index) {
  const item=evidence[index],video=$('evidence-video');
  video.pause();video.loop=item.video.startsWith('yates-barrier');video.src=`assets/video/${item.video}.mp4`;video.poster=`assets/video/${item.video}.jpg`;video.load();
  $('evidence-type').textContent=item.type;$('evidence-title').textContent=item.title;
  $('evidence-description').textContent=item.description;$('evidence-measurement').textContent=item.measurement;
  $('evidence-measurement').style.whiteSpace='pre-line';
  $('evidence-figure').hidden=!item.figure;
  $('evidence-figure').onclick=item.figure?()=>openFigure(item.figure,`${item.title} · supporting research figure`):null;
}
function initEvidence() {
  $('evidence-tabs').innerHTML=evidence.map((item,i)=>`<button data-evidence="${i}" aria-pressed="${i===0}">${item.label}</button>`).join('');
  $('evidence-tabs').addEventListener('click',e=>{
    const b=e.target.closest('[data-evidence]');if(!b)return;pressed($('evidence-tabs'),b);renderEvidence(Number(b.dataset.evidence));
  });
  renderEvidence(0);
}
function filteredCases() {
  return cases.filter(c=>c.modelKey===model&&(dataset==='all'||c.source===dataset)&&`${c.task} ${c.action} ${c.episode}`.toLowerCase().includes(query));
}
function stopPair() {
  playing=false;cancelAnimationFrame(animation);clips.forEach(v=>v.pause());$('v2w-play').textContent='Play ↗';
}
function selectVideo(c) {
  stopPair();v2wReady=false;activeCase=c;
  clips.forEach((v,i)=>{
    v.src=`${c.path}/${i===0?'src':'ours'}.mp4`;v.poster=`${c.path}/${i===0?'src':'ours'}.jpg`;v.load();
  });
  $('v2w-title').textContent=c.action||c.task;
  $('v2w-case-meta').textContent=`${modelNames[model]} / ${c.source} / ${c.srcDuration.toFixed(1)}s → ${c.oursDuration.toFixed(1)}s`;
  $('v2w-seek').value=0;$('v2w-time').textContent='0%';
  renderCaseGrid();
}
function renderCaseGrid() {
  const filtered=filteredCases(),count=filtered.length;
  page=Math.min(page,Math.max(0,Math.ceil(count/PAGE_SIZE)-1));
  const slice=filtered.slice(page*PAGE_SIZE,(page+1)*PAGE_SIZE);
  $('v2w-cases').innerHTML=slice.length?slice.map(c=>`<button class="case-card" data-video="${esc(c.id)}" aria-pressed="${c.id===activeCase?.id}"><img src="${c.path}/thumb.jpg" alt="" loading="lazy"><div><strong>${esc(c.action||c.task)}</strong><small>${esc(c.source)} / CASE ${String(c.num).padStart(2,'0')}</small></div></button>`).join(''):'<div class="empty-cases">No matching cases. Try another model, dataset, or action.</div>';
  $('v2w-count').textContent=count?`${page*PAGE_SIZE+1}–${Math.min((page+1)*PAGE_SIZE,count)} / ${count} cases`:'0 cases';
  $('v2w-prev').disabled=page===0;$('v2w-next').disabled=(page+1)*PAGE_SIZE>=count;
}
function changeVideoFilters() {
  stopPair();page=0;const filtered=filteredCases();
  if(filtered.length)selectVideo(filtered[0]);
  else{
    activeCase=null;clips.forEach(v=>{v.removeAttribute('src');v.removeAttribute('poster');v.load();});
    $('v2w-title').textContent='No matching cases';$('v2w-case-meta').textContent='Adjust the filters to continue.';renderCaseGrid();
  }
}
function syncRates() {
  const speed=Number($('v2w-speed').value);
  if(clips.every(v=>Number.isFinite(v.duration)&&v.duration>0)){
    clips[0].playbackRate=speed;
    clips[1].playbackRate=Math.min(16,Math.max(.0625,speed*clips[1].duration/clips[0].duration));
  }
}
function timeline() {
  if(!playing)return;
  const [ref,out]=clips,p=ref.duration?Math.min(ref.currentTime/ref.duration,1):0;
  $('v2w-seek').value=Math.round(p*1000);$('v2w-time').textContent=`${Math.round(p*100)}%`;
  if(Number.isFinite(out.duration)&&Math.abs(out.currentTime/out.duration-p)>.03&&!out.seeking)out.currentTime=p*out.duration;
  if(ref.ended||p>=.999){stopPair();return;}
  animation=requestAnimationFrame(timeline);
}
async function playPair() {
  if(!activeCase)return;
  if(playing){stopPair();return;}
  if(!v2wReady){$('v2w-play').textContent='Loading…';return;}
  if(clips[0].ended||Number($('v2w-seek').value)>=999)clips.forEach(v=>{v.currentTime=0;});
  syncRates();
  try{await Promise.all(clips.map(v=>v.play()));playing=true;$('v2w-play').textContent='Pause';timeline();}
  catch{stopPair();$('v2w-case-meta').textContent='Playback unavailable. Check browser media support or retry.';}
}
async function initVideo() {
  clips.forEach(v=>{
    v.addEventListener('loadedmetadata',()=>{v2wReady=clips.every(c=>c.readyState>=1&&c.duration>0);syncRates();if(v2wReady&&!playing)$('v2w-play').textContent='Play ↗';});
    v.addEventListener('error',()=>{if(activeCase){stopPair();$('v2w-case-meta').textContent='A media file could not load. Select another case or retry.';}});
  });
  $('v2w-play').addEventListener('click',playPair);
  $('v2w-restart').addEventListener('click',()=>{stopPair();clips.forEach(v=>{if(v.readyState>=1)v.currentTime=0;});$('v2w-seek').value=0;$('v2w-time').textContent='0%';});
  $('v2w-seek').addEventListener('input',e=>{
    const p=Number(e.target.value)/1000;
    clips.forEach(v=>{if(Number.isFinite(v.duration))v.currentTime=p*v.duration;});$('v2w-time').textContent=`${Math.round(p*100)}%`;
  });
  $('v2w-speed').addEventListener('change',syncRates);
  $('v2w-model').addEventListener('click',e=>{
    const b=e.target.closest('[data-model]');if(!b)return;model=b.dataset.model;pressed($('v2w-model'),b);changeVideoFilters();
  });
  $('v2w-dataset').addEventListener('change',e=>{dataset=e.target.value;changeVideoFilters();});
  $('v2w-search').addEventListener('input',e=>{query=e.target.value.trim().toLowerCase();changeVideoFilters();});
  $('v2w-cases').addEventListener('click',e=>{
    const b=e.target.closest('[data-video]');if(!b)return;const c=cases.find(x=>x.id===b.dataset.video);if(c)selectVideo(c);
  });
  $('v2w-prev').addEventListener('click',()=>{page--;renderCaseGrid();});$('v2w-next').addEventListener('click',()=>{page++;renderCaseGrid();});
  try{
    const response=await fetch('assets/v2w/cases.json');if(!response.ok)throw new Error('Case index unavailable');
    cases=await response.json();
    const sources=[...new Set(cases.map(c=>c.source))];
    sources.forEach(source=>{const option=document.createElement('option');option.value=source;option.textContent=source;$('v2w-dataset').append(option);});
    const initial=cases.find(c=>c.modelKey==='gpt'&&c.num===15)||cases.find(c=>c.modelKey===model);
    if(initial)selectVideo(initial);
  }catch(err){$('v2w-title').textContent='Case index could not load';$('v2w-case-meta').textContent='Please serve the website over HTTP.';console.warn(err.message);}
}
function initMotion() {
  const observer=new IntersectionObserver(entries=>entries.forEach(entry=>{
    if(entry.isIntersecting){entry.target.classList.add('visible');observer.unobserve(entry.target);}
  }),{threshold:.08});
  document.querySelectorAll('.section-heading,.method-principles,.resource-grid').forEach(el=>{el.classList.add('reveal');observer.observe(el);});
  const navLinks=[...document.querySelectorAll('.nav-links a')];
  const activeObserver=new IntersectionObserver(entries=>{
    for(const entry of entries)if(entry.isIntersecting){navLinks.forEach(a=>{const active=a.hash===`#${entry.target.id}`;a.classList.toggle('active',active);if(active)a.setAttribute('aria-current','location');else a.removeAttribute('aria-current');});}
  },{rootMargin:'-20% 0px -65% 0px'});
  navLinks.forEach(a=>{const section=document.querySelector(a.hash);if(section)activeObserver.observe(section);});
  const updateProgress=()=>{
    const max=document.documentElement.scrollHeight-innerHeight;
    document.querySelector('.reading-progress').style.width=`${max>0?scrollY/max*100:0}%`;
  };
  addEventListener('scroll',updateProgress,{passive:true});updateProgress();
  const counts=new IntersectionObserver(entries=>entries.forEach(entry=>{
    if(!entry.isIntersecting)return;
    const el=entry.target,end=Number(el.dataset.count),decimals=Number(el.dataset.decimals||0);
    counts.unobserve(el);
    if(motionReduced){el.textContent=end.toFixed(decimals);return;}
    const start=performance.now();
    const tick=time=>{const t=Math.min(1,(time-start)/1100);el.textContent=(end*(1-(1-t)**3)).toFixed(decimals);if(t<1)requestAnimationFrame(tick);};
    requestAnimationFrame(tick);
  }),{threshold:.7});
  document.querySelectorAll('[data-count]').forEach(el=>counts.observe(el));
  const videoVisibility=new IntersectionObserver(entries=>entries.forEach(entry=>{
    if(!entry.isIntersecting){entry.target.pause();if(clips.includes(entry.target))stopPair();}
  }),{threshold:0});
  document.querySelectorAll('video').forEach(v=>videoVisibility.observe(v));
  document.addEventListener('visibilitychange',()=>{if(document.hidden){stopPair();document.querySelectorAll('video').forEach(v=>v.pause());}});
}
function initCitation() {
  $('copy-citation').addEventListener('click',async()=>{
    try{await navigator.clipboard.writeText($('citation').textContent);$('copy-status').textContent='Copied.';}
    catch{$('copy-status').textContent='Select the citation text to copy manually.';}
  });
}
initFigures();initWorlds();initMethod();initEvidence();initCharts();initVideo();initMotion();initCitation();
const railroadGallery=initRailroadGallery(getViewer);
initSelectControls();
addEventListener('pagehide',e=>{
  stopPair();
  if(!e.persisted){heroViewer?.dispose();worldViewer?.dispose();railroadGallery.dispose();}
});
addEventListener('pageshow',e=>{
  if(e.persisted){
    if(heroViewer)heroViewer.needsRender=true;
    if(worldViewer)worldViewer.needsRender=true;
    railroadGallery.resume();
  }
});
