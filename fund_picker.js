/* Styled fund suggestions; selection still goes through the existing identity checks. */
(function(){
 const opened=new Set();
 document.addEventListener('pointerdown',e=>{for(const picker of [...opened])if(!picker.root.isConnected||!picker.root.contains(e.target))picker.close();});
 function init(root,input,toggle,list,items){
  let options=[],active=-1,isOpen=false;
  input.setAttribute('role','combobox');input.setAttribute('aria-autocomplete','list');input.setAttribute('aria-controls',list.id);input.setAttribute('autocomplete','off');list.setAttribute('role','listbox');list.setAttribute('aria-label','基金列表');input.setAttribute('aria-label','基金代码');
  const picker={root,close};
  function close(){isOpen=false;list.hidden=true;input.setAttribute('aria-expanded','false');input.removeAttribute('aria-activedescendant');opened.delete(picker);}
  function highlight(index){active=index;[...list.children].forEach((el,i)=>{el.classList.toggle('active',i===active);el.setAttribute('aria-selected',String(i===active));});if(options[active]){input.setAttribute('aria-activedescendant',list.children[active].id);list.children[active].scrollIntoView({block:'nearest'});}}
  function choose(code){input.value=code;input.dispatchEvent(new Event('input',{bubbles:true}));input.dispatchEvent(new Event('change',{bubbles:true}));input.focus();close();}
  function show(query=''){
   for(const other of [...opened])if(other!==picker)other.close();
   options=items.filter(item=>(item.code+' '+item.name).toLowerCase().includes(query.toLowerCase()));active=-1;list.replaceChildren();
   for(const [i,item] of options.entries()){const option=document.createElement('div');option.id=list.id+'-option-'+i;option.className='fund-option';option.setAttribute('role','option');option.setAttribute('aria-selected','false');const name=document.createElement('span'),code=document.createElement('small');name.textContent=item.name;code.textContent=item.code;option.append(name,code);if(item.code===input.value)option.classList.add('chosen');option.onmousedown=e=>e.preventDefault();option.onclick=()=>choose(item.code);list.append(option);}
   if(!options.length){const empty=document.createElement('div');empty.className='fund-picker-empty';empty.textContent='输入完整六位代码可查询其他基金';list.append(empty);}
   isOpen=true;list.hidden=false;input.setAttribute('aria-expanded','true');opened.add(picker);
  }
  input.addEventListener('focus',()=>show());input.addEventListener('input',()=>show(input.value.trim()));
  input.addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();close();}else if(e.key==='Tab')close();else if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();if(!isOpen)show();if(options.length)highlight(active<0?(e.key==='ArrowDown'?0:options.length-1):(active+(e.key==='ArrowDown'?1:-1)+options.length)%options.length);}else if(e.key==='Enter'&&isOpen&&active>=0){e.preventDefault();choose(options[active].code);}});
  root.addEventListener('focusout',e=>{if(!root.contains(e.relatedTarget))close();});
  toggle.onclick=()=>{if(isOpen)close();else{input.focus();show();}};
  close();
 }
 window.FundPicker={init};
 // Shared dropdown presentation; native selects retain values and form events.
 const selects=new Map();let activeSelect=null,serial=0;
 function enhance(select){
  if(selects.has(select)||select.multiple||select.size>1)return;
  const root=document.createElement('div'),button=document.createElement('button'),text=document.createElement('span'),menu=document.createElement('div');
  root.className='unified-select';button.type='button';button.className='select-trigger';button.append(text);
  menu.className='select-menu';menu.id='select-menu-'+(++serial);menu.hidden=true;menu.setAttribute('role','listbox');
  const label=select.getAttribute('aria-label')||[...(select.labels?.[0]?.childNodes||[])].filter(n=>n!==select).map(n=>n.textContent).join('').trim()||'选择选项';
  button.setAttribute('role','combobox');button.setAttribute('aria-label',label);button.setAttribute('aria-haspopup','listbox');button.setAttribute('aria-controls',menu.id);button.setAttribute('aria-expanded','false');menu.setAttribute('aria-label',label);
  select.before(root);root.append(select,button);document.body.append(menu);select.hidden=true;
  let index=-1,search='',lastKey=0;
  function sync(){const value=select.selectedOptions[0]?.textContent||'请选择';if(text.textContent!==value)text.textContent=value;if(button.disabled!==select.disabled)button.disabled=select.disabled;}
  function close(){menu.hidden=true;button.setAttribute('aria-expanded','false');button.removeAttribute('aria-activedescendant');if(activeSelect===entry)activeSelect=null;}
  function highlight(next){index=next;[...menu.children].forEach((el,i)=>el.classList.toggle('is-active',i===index));const item=menu.children[index];if(item){button.setAttribute('aria-activedescendant',item.id);item.scrollIntoView({block:'nearest'});}}
  function choose(next){const option=select.options[next];if(!option||option.disabled||option.parentElement.disabled)return;select.value=option.value;sync();close();button.focus();select.dispatchEvent(new Event('input',{bubbles:true}));select.dispatchEvent(new Event('change',{bubbles:true}));}
  function show(){
   if(select.disabled)return;if(activeSelect)activeSelect.close();for(const picker of [...opened])picker.close();sync();menu.replaceChildren();
   [...select.options].forEach((option,i)=>{const item=document.createElement('div');item.className='select-option';item.id=menu.id+'-'+i;item.textContent=option.textContent;item.setAttribute('role','option');item.setAttribute('aria-selected',String(i===select.selectedIndex));item.setAttribute('aria-disabled',String(option.disabled||!!option.parentElement.disabled));item.onpointerdown=e=>e.preventDefault();item.onclick=()=>choose(i);menu.append(item);});
   const rect=button.getBoundingClientRect(),below=innerHeight-rect.bottom-12,above=rect.top-12,up=below<180&&above>below,height=Math.max(48,Math.min(288,up?above:below));
   menu.style.width=Math.min(rect.width,innerWidth-16)+'px';menu.style.left=Math.max(8,Math.min(rect.left,innerWidth-rect.width-8))+'px';menu.style.maxHeight=height+'px';
   menu.style.top=up?'auto':rect.bottom+5+'px';menu.style.bottom=up?innerHeight-rect.top+5+'px':'auto';menu.hidden=false;button.setAttribute('aria-expanded','true');activeSelect=entry;highlight(select.selectedIndex);
  }
  const entry={root,menu,close,sync,button};selects.set(select,entry);sync();
  button.onclick=()=>menu.hidden?show():close();
  button.onkeydown=e=>{
   if(['ArrowDown','ArrowUp','Home','End'].includes(e.key)){e.preventDefault();if(menu.hidden)show();const enabled=[...select.options].map((o,i)=>!o.disabled&&!o.parentElement.disabled?i:-1).filter(i=>i>=0);if(!enabled.length)return;const pos=enabled.indexOf(index);highlight(e.key==='Home'?enabled[0]:e.key==='End'?enabled.at(-1):enabled[(pos+(e.key==='ArrowDown'?1:-1)+enabled.length)%enabled.length]);}
   else if(e.key==='Escape'){e.preventDefault();close();}
   else if(e.key==='Tab')close();
   else if((e.key==='Enter'||e.key===' ')&&!menu.hidden){e.preventDefault();choose(index);}
   else if(e.key.length===1&&e.key!==' '){e.preventDefault();if(menu.hidden)show();search=Date.now()-lastKey>700?e.key:search+e.key;lastKey=Date.now();const next=[...select.options].findIndex(o=>!o.disabled&&!o.parentElement.disabled&&o.textContent.trim().toLowerCase().startsWith(search.toLowerCase()));if(next>=0)highlight(next);}
  };
  select.addEventListener('change',sync);
 }
 function refreshSelects(){
  for(const [select,entry] of selects){if(!select.isConnected){entry.close();entry.menu.remove();selects.delete(select);}else{entry.sync();if(activeSelect===entry&&!entry.button.getClientRects().length)entry.close();}}
  document.querySelectorAll('.workspace select').forEach(enhance);
 }
 document.addEventListener('pointerdown',e=>{if(activeSelect&&!activeSelect.root.contains(e.target)&&!activeSelect.menu.contains(e.target))activeSelect.close();});
 document.addEventListener('focusin',e=>{if(activeSelect&&!activeSelect.root.contains(e.target))activeSelect.close();});
 window.addEventListener('resize',()=>activeSelect?.close());
 document.addEventListener('scroll',e=>{if(activeSelect&&!activeSelect.menu.contains(e.target))activeSelect.close();},true);
 function start(){refreshSelects();new MutationObserver(refreshSelects).observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['disabled','selected','hidden']});}
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start);else start();
})();
