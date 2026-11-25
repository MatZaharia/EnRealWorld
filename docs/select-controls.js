export function initSelectControls() {
  let opened=null;
  document.querySelectorAll('select').forEach(select=>{
    const label=select.closest('label');
    const name=select.getAttribute('aria-label')||[...label?.childNodes||[]].filter(n=>n.nodeType===3).map(n=>n.textContent).join(' ').trim()||'Choose an option';
    const button=document.createElement('button');
    button.type='button';button.className='select-trigger';button.id=select.id+'-trigger';
    button.setAttribute('role','combobox');button.setAttribute('aria-haspopup','listbox');button.setAttribute('aria-expanded','false');button.setAttribute('aria-label',name);
    const text=document.createElement('span');text.className='select-value';
    const arrow=document.createElement('span');arrow.className='select-chevron';arrow.setAttribute('aria-hidden','true');
    button.append(text,arrow);
    const menu=document.createElement('div');menu.className='select-menu';menu.id=select.id+'-listbox';menu.hidden=true;
    menu.setAttribute('role','listbox');menu.setAttribute('aria-label',name);button.setAttribute('aria-controls',menu.id);
    const portal=document.createElement('div');portal.className='select-portal';portal.append(menu);document.body.append(portal);
    select.after(button);select.hidden=true;
    let active=0,options=[],typeahead='',typedAt=0;
    const close=()=>{
      menu.hidden=true;button.setAttribute('aria-expanded','false');button.removeAttribute('aria-activedescendant');
      if(opened?.button===button)opened=null;
    };
    const position=()=>{
      if(menu.hidden)return;
      const r=button.getBoundingClientRect(),vh=document.documentElement.clientHeight,vw=document.documentElement.clientWidth;
      if(!button.getClientRects().length||r.bottom<0||r.top>vh){close();return;}
      const width=Math.min(Math.max(r.width,170),vw-24);
      menu.style.width=width+'px';menu.style.maxHeight='260px';
      const below=vh-r.bottom-16,above=r.top-16,up=below<Math.min(menu.scrollHeight,200)&&above>below;
      menu.style.maxHeight=Math.max(60,Math.min(260,up?above:below))+'px';
      menu.style.left=Math.max(12,Math.min(r.left,vw-width-12))+'px';
      menu.style.top=(up?Math.max(12,r.top-menu.offsetHeight-6):r.bottom+6)+'px';
    };
    const highlight=index=>{
      active=index;
      options.forEach((option,i)=>option.classList.toggle('highlighted',i===active));
      const option=options[active];
      if(option){button.setAttribute('aria-activedescendant',option.id);option.scrollIntoView({block:'nearest'});}
    };
    const choose=index=>{
      if(select.options[index]?.disabled)return;
      select.selectedIndex=index;select.dispatchEvent(new Event('input',{bubbles:true}));select.dispatchEvent(new Event('change',{bubbles:true}));
      close();button.focus({preventScroll:true});
    };
    const sync=()=>{
      text.textContent=select.selectedOptions[0]?.textContent||'Choose';button.disabled=select.disabled;
      button.title=text.textContent;button.setAttribute('aria-label',`${name}: ${text.textContent}`);
      options=[...select.options].map((item,i)=>{
        const row=document.createElement('div');row.className='select-option';row.id=menu.id+'-'+i;
        row.setAttribute('role','option');row.setAttribute('aria-selected',String(item.selected));row.setAttribute('aria-disabled',String(item.disabled));row.textContent=item.textContent;
        row.addEventListener('pointerdown',e=>e.preventDefault());row.addEventListener('click',()=>choose(i));
        return row;
      });
      menu.replaceChildren(...options);
      if(!menu.hidden){position();highlight(select.selectedIndex);}
    };
    const open=()=>{
      if(button.disabled)return;
      opened?.close();menu.hidden=false;button.setAttribute('aria-expanded','true');
      opened={button,menu,close,position};position();highlight(Math.max(0,select.selectedIndex));
    };
    button.addEventListener('click',()=>{if(menu.hidden)open();else close();});
    button.addEventListener('keydown',e=>{
      const keys=['ArrowDown','ArrowUp','Home','End','Enter',' ','Escape'];
      if(e.key==='Tab'){close();return;}
      if(keys.includes(e.key))e.preventDefault();
      if(e.key==='Escape'){close();return;}
      if(e.key==='Enter'||e.key===' '){if(menu.hidden)open();else choose(active);return;}
      if(['ArrowDown','ArrowUp','Home','End'].includes(e.key)){
        if(menu.hidden)open();
        const valid=[...select.options].map((o,i)=>o.disabled?-1:i).filter(i=>i>=0);
        const current=valid.indexOf(active),next=e.key==='Home'?0:e.key==='End'?valid.length-1:Math.max(0,Math.min(valid.length-1,current+(e.key==='ArrowDown'?1:-1)));
        if(valid[next]!=null)highlight(valid[next]);return;
      }
      if(e.key.length===1&&!e.ctrlKey&&!e.metaKey&&!e.altKey){
        e.preventDefault();const now=performance.now();typeahead=now-typedAt>700?e.key:typeahead+e.key;typedAt=now;
        if(menu.hidden)open();const index=[...select.options].findIndex(o=>!o.disabled&&o.textContent.toLowerCase().startsWith(typeahead.toLowerCase()));if(index>=0)highlight(index);
      }
    });
    button.addEventListener('blur',()=>queueMicrotask(()=>{if(document.activeElement!==button)close();}));
    select.addEventListener('change',sync);
    new MutationObserver(sync).observe(select,{childList:true,subtree:true,attributes:true,attributeFilter:['disabled','selected','label']});
    sync();
  });
  document.addEventListener('pointerdown',e=>{if(opened&&!opened.button.contains(e.target)&&!opened.menu.contains(e.target))opened.close();});
  document.addEventListener('scroll',e=>{if(opened&&!opened.menu.contains(e.target))opened.position();},{capture:true,passive:true});
  addEventListener('resize',()=>opened?.position());
  window.visualViewport?.addEventListener('resize',()=>opened?.position());
  document.addEventListener('fullscreenchange',()=>opened?.close());
}
