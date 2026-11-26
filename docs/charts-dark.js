import {families,modelNames,scores,ablations} from './data-dark.js';
const $=id=>document.getElementById(id);
const COLORS={base:'#536b7c',ours:'#a9f6d8',coral:'#fc9d90',cyan:'#60ddf4'};
const metricNames=['Score S','Functionality F','Geometry G','Dynamics D'];
const metricDecimals=[2,1,1,1];
let benchmark='video';
const fmt=(n,d=2)=>Number(n).toFixed(d);
const escape=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

export function bindTooltips(container) {
  container.querySelectorAll('[data-tip]').forEach(el=>{
    const show=e=>{
      const tip=$('chart-tooltip');
      tip.textContent=el.dataset.tip;
      tip.style.display='block';
      const b=el.getBoundingClientRect();
      const x=e.clientX??b.left+b.width/2,y=e.clientY??b.top;
      tip.style.left=`${Math.max(8,Math.min(x+12,innerWidth-tip.offsetWidth-12))}px`;
      tip.style.top=`${Math.max(8,Math.min(y+14,innerHeight-tip.offsetHeight-12))}px`;
    };
    const hide=()=>{$('chart-tooltip').style.display='none';};
    el.addEventListener('pointerenter',show);el.addEventListener('pointermove',show);el.addEventListener('focus',show);
    el.addEventListener('pointerleave',hide);el.addEventListener('blur',hide);
  });
}

function csv(rows) {
  return rows.map(r=>r.map(v=>`"${String(v).replace(/"/g,'""')}"`).join(',')).join('\r\n');
}
export function allBenchmarkCSV() {
  const rows=[['model','family','method','S','F','G','D','source_note']];
  Object.keys(scores).forEach(model=>families.forEach((family,i)=>['base','ours'].forEach(method=>rows.push([
    modelNames[model],family,method==='base'?'Base Agent':'EnRealWorld',...scores[model][method][i],
    model==='kimi'&&family==='HOT3D'&&method==='ours'?'Reported S and components inconsistent; confirm with authors':'Manuscript reported values'
  ]))));
  return csv(rows)+'\r\n';
}
function legend(items) {
  $('chart-legend').innerHTML=items.map(([title,color])=>`<span><i style="--swatch:${color}"></i>${title}</span>`).join('');
}
function groupedBars(labels,series,{max=100,height=345,decimals=2}={}) {
  const W=1080,H=height,L=48,R=20,T=28,B=52,CW=W-L-R,CH=H-T-B;
  let html=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${escape($('chart-title').textContent)}">`;
  for(let i=0;i<=5;i++){
    const v=max*i/5,y=T+CH*(1-i/5);
    html+=`<line class="chart-grid" x1="${L}" x2="${W-R}" y1="${y}" y2="${y}"/><text class="chart-tick" x="${L-12}" y="${y+4}" text-anchor="end">${max===1?v.toFixed(1):Math.round(v)}</text>`;
  }
  const step=CW/labels.length,barWidth=Math.min(42,(step-24)/series.length);
  labels.forEach((name,i)=>{
    const x=L+step*(i+.5);
    html+=`<text class="chart-label" x="${x}" y="${H-23}" text-anchor="middle">${escape(name)}</text>`;
    series.forEach((s,j)=>{
      const value=s.values[i],bh=CH*value/max,bx=x+(j-series.length/2)*(barWidth+5)+2.5;
      const tip=`${name}\n${s.name}: ${fmt(value,decimals)}\n${s.note||''}`;
      html+=`<g class="chart-bar" tabindex="0" role="img" aria-label="${escape(tip)}" data-tip="${escape(tip)}"><title>${escape(tip)}</title><rect x="${bx}" y="${T+CH-bh}" width="${barWidth}" height="${bh}" rx="2" fill="${s.color}"/><text class="chart-value" x="${bx+barWidth/2}" y="${T+CH-bh-8}" text-anchor="middle">${fmt(value,decimals)}</text></g>`;
    });
  });
  return html+'</svg>';
}
function renderVideo() {
  const model=$('chart-model').value,m=Number($('chart-metric').value),data=scores[model];
  $('chart-title').textContent=`${modelNames[model]} · ${metricNames[m]}`;
  $('chart-description').textContent='39 tasks · 100-point scale · higher is better. Overall is the reported task-level aggregate, not the unweighted average of the seven family bars.';
  legend([['Base Agent',COLORS.base],['EnRealWorld',COLORS.ours]]);
  $('benchmark-chart').innerHTML=groupedBars(families,[{name:'Base Agent',color:COLORS.base,values:data.base.map(v=>v[m])},{name:'EnRealWorld',color:COLORS.ours,values:data.ours.map(v=>v[m])}],{decimals:metricDecimals[m]});
  $('chart-note').textContent='Bars start at zero. S and F/G/D retain the manuscript’s reported precision; S is not recomputed from rounded components.'+(model==='kimi'?' Data caution: Kimi HOT3D EnRealWorld reports S = 32.48 with F/G/D = 18.8/78.4/43.6, which are internally inconsistent. Values are preserved, not silently corrected.':'');
}
function renderAblation() {
  $('chart-title').textContent='What changes when coordination is removed?';
  $('chart-description').textContent='GPT-6.1 Sol · 39 Video2World tasks · score S on a 100-point scale. Single-session variants separate role prompts, utilities, and coordination.';
  legend([['Shared-session variants',COLORS.base],['Full EnRealWorld',COLORS.ours]]);
  const series={name:'Execution score S',color:COLORS.cyan,values:ablations.map(r=>r[1])};
  $('benchmark-chart').innerHTML=groupedBars(ablations.map(r=>r[0]),[series]);
  $('chart-note').textContent='Prompts: role duties only. Utils: tools only. NoCoord: prompts and tools in a shared session. Full EnRealWorld adds isolated role contexts, information boundaries, and Manager-led deliberation.';
  const bars=$('benchmark-chart').querySelectorAll('.chart-bar rect');
  bars.forEach((r,i)=>r.setAttribute('fill',i===4?COLORS.ours:COLORS.base));
}
function renderPhysics() {
  $('chart-title').textContent='Counterfactual physics, not just appearance.';
  $('chart-description').textContent='GPT-6.1 Sol · medium reasoning · 43 counterfactual tasks. Visual and physics scores are on a 0–1 scale; failed candidates count as zero.';
  legend([['Base Agent',COLORS.base],['EnRealWorld',COLORS.ours]]);
  $('benchmark-chart').innerHTML=groupedBars(['Visual score ↑','Physics score ↑'],[{name:'Base Agent',color:COLORS.base,values:[.336,.321]},{name:'EnRealWorld',color:COLORS.ours,values:[.491,.416]}],{max:1,decimals:3,height:310})+`<div class="metric-cards"><div class="metric-card"><h4>FAILED CANDIDATES / LOWER IS BETTER</h4><strong>19 → 6</strong><p>Base Agent → EnRealWorld · out of 43</p></div><div class="metric-card"><h4>VISUAL SCORE GAIN</h4><strong>+0.155</strong><p>0.336 → 0.491</p></div><div class="metric-card"><h4>PHYSICS SCORE GAIN</h4><strong>+0.095</strong><p>0.321 → 0.416</p></div></div>`;
  $('chart-note').textContent='These results concern the 43 counterfactual tasks, not the entire 156-task suite. All means include failed candidates as zero. Source: supplementary PhysCodeGym evaluation.';
}
function renderCost() {
  $('chart-title').textContent='Better execution comes with additional work.';
  $('chart-description').textContent='Reported extra time per task relative to the strongest comparison method. These are approximate overheads, not absolute runtimes or a cross-model efficiency ranking.';
  legend([['Extra time / approximate minutes',COLORS.cyan]]);
  $('benchmark-chart').innerHTML=groupedBars(['GPT-6.1 Sol','DeepSeek V4.1','Kimi-3.1 Pro'],[{name:'Extra time (minutes)',color:COLORS.cyan,values:[25,75,76],note:'Approximate per-task overhead'}],{max:100,decimals:0,height:300})+`<div class="metric-cards"><div class="metric-card"><h4>COMPUTE / PER TASK</h4><strong style="font-size:24px">RTX 4090</strong><p>16 CPU cores · 128 GB RAM</p></div><div class="metric-card"><h4>CACHED INPUT TOKEN SHARE</h4><strong>97.4–98.6%</strong><p>Reported range across models; not assigned per model.</p></div><div class="metric-card"><h4>NEW INPUT TOKEN SHARE</h4><strong>1.4–2.6%</strong><p>No absolute token counts or dollar cost inferred.</p></div></div>`;
  $('chart-note').textContent='GPT compares 53.55 vs VIGA 51.21. DeepSeek reports +13.72 and Kimi +8.63 vs strongest comparisons. Cache statistics cover 38 GPT tasks and 39 tasks for each other model. Missing absolute runtimes, token totals, and dollar costs are not estimated.';
}
function render() {
  $('chart-tooltip').style.display='none';
  $('chart-model').parentElement.hidden=benchmark!=='video';
  $('chart-metric').parentElement.hidden=benchmark!=='video';
  ({video:renderVideo,ablation:renderAblation,physics:renderPhysics,cost:renderCost})[benchmark]();
  bindTooltips($('benchmark-chart'));
}
function delta() {
  let html='<div class="heat-grid"><span></span>'+families.map(f=>`<span class="heat-label">${f}</span>`).join('');
  Object.keys(scores).forEach(model=>{
    html+=`<span class="heat-label heat-row-label">${model==='gpt'?'GPT-6.1 Sol':model==='deepseek'?'DeepSeek V4.1':'Kimi-3.1 Pro'}</span>`;
    families.forEach((family,i)=>{
      const d=scores[model].ours[i][0]-scores[model].base[i][0],positive=d>=0,color=positive?'169,246,216':'252,157,144';
      const alpha=.08+Math.min(Math.abs(d)/35,1)*.28;
      const label=`${modelNames[model]} · ${family}\nBase ${fmt(scores[model].base[i][0])} → EnRealWorld ${fmt(scores[model].ours[i][0])}\nΔ S ${d>=0?'+':''}${fmt(d)}`+(model==='kimi'&&family==='HOT3D'?'\nReported S/component inconsistency; see data caution.':'');
      html+=`<span class="heat-cell" role="img" tabindex="0" aria-label="${escape(label)}" data-tip="${escape(label)}" style="background:rgba(${color},${alpha});color:${positive?COLORS.ours:COLORS.coral}">${d>=0?'+':''}${fmt(d)}</span>`;
    });
  });
  $('delta-matrix').innerHTML=html+'</div>';
  bindTooltips($('delta-matrix'));
}
export function initCharts() {
  $('benchmark-tabs').addEventListener('click',e=>{
    const b=e.target.closest('[data-benchmark]');if(!b)return;
    benchmark=b.dataset.benchmark;
    $('benchmark-tabs').querySelectorAll('button').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));
    render();
  });
  $('chart-model').addEventListener('change',render);$('chart-metric').addEventListener('change',render);
  render();delta();
}
