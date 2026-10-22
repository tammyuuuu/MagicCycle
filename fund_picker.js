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
})();
