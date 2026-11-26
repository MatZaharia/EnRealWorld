import {worldCases,probes,modelNames} from './data-dark.js';
import {initCharts} from './charts-dark.js';
const $=id=>document.getElementById(id);
const motionReduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
const esc=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pressed=(group,selected)=>group.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b===selected)));
let viewerModule;
const getViewer=()=>viewerModule??=import('./viewer-dark.js');
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
  try {
    const {WorldViewer}=await getViewer();
    heroViewer=new WorldViewer($('hero-canvas'),{hero:true});
    $('hero-motion').setAttribute('aria-pressed',String(heroViewer.auto));
    $('hero-motion').textContent=heroViewer.auto?'Pause rotation':'Start rotation';
    await heroViewer.load('assets/models/railroad-ours-claude-fable-5-2.glb');
  } catch(err) {
    $('hero-canvas').innerHTML='<img src="assets/video/three-buildings-assembly.jpg" alt="Generated building previews" style="height:100%;width:100%;object-fit:contain">';
    $('hero-motion').hidden=true;
    console.warn('3D hero unavailable:',err.message);
  }
}
function modelPath() {
  const name=selectedCase[method]||`${selectedCase.model}-${method}`;
  return `assets/models/${name}.glb`;
}
function renderWorldCase() {
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
  const pairs={lighthouse:['fig3','037','048'],yates:['fig3','061','062'],ranch:['fig3','060','049'],railroad:['fig5','013','014'],studio:['fig3','025','026'],'railroad-astra':['fig5','038','039']};
  const pair=pairs[selectedCase.id];
  document.querySelector('.render-comparison').hidden=!pair;
  if(pair){
    $('render-base').src=`assets/figimg/${pair[0]}/${pair[1]}.jpg`;
    $('render-ours').src=`assets/figimg/${pair[0]}/${pair[2]}.jpg`;
  }
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
      if(label&&version===loadVersion)label.textContent=progress===null?'Loading real scene geometry…':`Loading geometry · ${Math.round(progress*100)}%`;
    });
    if(!complete||version!==loadVersion)return;
    $('world-canvas').querySelector('.viewer-message')?.remove();
    $('world-status').textContent=`${method==='ours'?'EnRealWorld':'Base Agent'} · ${worldViewer.stats.triangles.toLocaleString()} preview triangles · drag / pinch / arrow keys`;
    worldViewer.setCut(category!=='painting'?$('world-cut').value:100);
  }catch(err){
    if(version!==loadVersion)return;
    showWorldMessage('3D preview could not load. Check WebGL support and serve this page over HTTP.',false);
    $('world-status').textContent='Preview unavailable. Videos and downloadable GLB files remain available.';
    console.warn('World preview unavailable:',err.message);
  }
}
function initWorlds() {
  $('start-world').addEventListener('click',loadWorld);
  $('world-tabs').addEventListener('click',e=>{
    const b=e.target.closest('[data-category]');if(!b)return;
    category=b.dataset.category;selectedCase=worldCases[category][0];
    pressed($('world-tabs'),b);$('world-cut').value=100;$('cut-value').textContent='Full';renderWorldCase();
  });
  $('world-cases').addEventListener('click',e=>{
    const b=e.target.closest('[data-case]');if(!b)return;
    selectedCase=worldCases[category].find(c=>c.id===b.dataset.case);renderWorldCase();
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
  let dragging=false;
  const drag=e=>{if(!dragging)return;const box=$('render-reveal').getBoundingClientRect();reveal((e.clientX-box.left)/box.width*100);};
  $('render-reveal').addEventListener('pointerdown',e=>{dragging=true;e.currentTarget.setPointerCapture(e.pointerId);drag(e);});
  $('render-reveal').addEventListener('pointermove',drag);
  $('render-reveal').addEventListener('pointerup',()=>{dragging=false;});
  $('render-reveal').addEventListener('pointercancel',()=>{dragging=false;});
  renderWorldCase();initHero();
}
function renderProbe(index) {
  const p=probes[index];
  $('probe-detail').innerHTML=`<div><span>QUESTION</span><p>${p[3]}</p></div><div><span>PAIRED INTERVENTION</span><p>${p[1]}</p></div><div><span>OBSERVABLE READOUT</span><p>${p[2]}</p></div>`;
}
function initProbes() {
  $('probe-tabs').innerHTML=probes.map((p,i)=>`<button data-probe="${i}" aria-pressed="${i===0}">${p[0]}</button>`).join('');
  $('probe-tabs').addEventListener('click',e=>{
    const b=e.target.closest('[data-probe]');if(!b)return;pressed($('probe-tabs'),b);renderProbe(Number(b.dataset.probe));
  });
  renderProbe(0);
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
  document.querySelectorAll('.section-heading,.method-principles').forEach(el=>{el.classList.add('reveal');observer.observe(el);});
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
initFigures();initWorlds();initProbes();initCharts();initVideo();initMotion();initCitation();
addEventListener('pagehide',()=>{heroViewer?.dispose();worldViewer?.dispose();stopPair();});
