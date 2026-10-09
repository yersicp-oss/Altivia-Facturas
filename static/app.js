'use strict';
(function(){
 const $=id=>document.getElementById(id);
 const menu=$('mobileMenu');if(menu)menu.addEventListener('click',()=> $('sidebar')?.classList.toggle('open'));
 document.querySelectorAll('[data-confirm]').forEach(btn=>btn.addEventListener('click',ev=>{if(!confirm(btn.dataset.confirm))ev.preventDefault()}));
 const createUser=document.querySelector('form[action="/users/create"]');
 if(createUser){
   const role=createUser.querySelector('select[name="role"]'),pwd=createUser.querySelector('input[name="password"]');
   const update=()=>{if(!role||!pwd)return;pwd.required=(role.value!=='miembro');pwd.placeholder=(role.value==='miembro'?'Sin contraseña para miembros':'Mínimo 10 caracteres');};
   role?.addEventListener('change',update);update();
 }
 const inputs=document.querySelectorAll('.invoiceUpload');if(!inputs.length)return;
 const status=$('analysisStatus'),screen=$('reviewScreen'),capture=$('captureScreen'),form=$('invoiceForm');
 const owner=$('publicOwner');const selection=$('selectMember');const chosen=$('selectedOwner');
 const fileLabels={camera:'foto de cámara',photo:'fotografía',pdf:'PDF'};
 function msg(text,warning=false){status.innerHTML='';const p=document.createElement('div');p.className=warning?'warnbox':'notice';p.textContent=text;status.appendChild(p)}
 function reset(){screen.classList.add('hidden');capture.classList.remove('hidden');inputs.forEach(x=>x.value='');status.innerHTML='';window.scrollTo({top:0,behavior:'smooth'})}
 $('cancelReview')?.addEventListener('click',reset);$('changeFile')?.addEventListener('click',reset);
 $('memberNext')?.addEventListener('click',()=>{if(!owner.value){owner.reportValidity();return}chosen.value=owner.value;selection.classList.add('hidden');capture.classList.remove('hidden');capture.scrollIntoView({behavior:'smooth'})});
 $('changeMember')?.addEventListener('click',()=>{reset();capture.classList.add('hidden');selection.classList.remove('hidden');selection.scrollIntoView({behavior:'smooth'})});
 inputs.forEach(input=>input.addEventListener('change',async()=>{
   const file=input.files&&input.files[0];if(!file)return;
   if(file.size>15*1024*1024){msg('El archivo supera 15 MB. Comprime el documento o escanea con menor resolución.',true);return}
   msg('Analizando '+fileLabels[input.dataset.mode]+'… Esto puede tardar unos segundos.');
   const data=new FormData();data.append('file',file);data.append('csrf',form.querySelector('[name=csrf]').value);
   if(chosen)data.append('owner_id',chosen.value);
   try{
     const resp=await fetch('/api/analyze',{method:'POST',body:data,headers:{'X-CSRF-Token':form.querySelector('[name=csrf]').value}});
     const result=await resp.json();if(!resp.ok)throw new Error(result.error||'No se pudo analizar el documento.');
     $('draft_token').value=result.draft_token;
     const fields=result.fields||{};
     for(const key of ['receipt_type','series','number','issued_on','provider','ruc','total','currency']){
        const element=form.elements.namedItem(key);const value=fields[key];
        if(element && value!==undefined && value!==null && value!=='')element.value=String(value);
     }
     const warn=$('ocrWarnings');warn.innerHTML='';
     if(result.warnings?.length){result.warnings.forEach(w=>{const div=document.createElement('div');div.className='warnbox';div.textContent=w;warn.appendChild(div)})}
     if(result.uncertain?.length){const labels={receipt_type:'tipo de comprobante',series:'serie',number:'número',issued_on:'fecha de emisión',provider:'proveedor',ruc:'RUC',total:'importe total'};
        const items=result.uncertain.filter(x=>labels[x]).map(x=>labels[x]);if(items.length){const div=document.createElement('div');div.className='warnbox';div.textContent='Completar o verificar: '+items.join(', ')+'.';warn.appendChild(div)}
     }
     capture.classList.add('hidden');screen.classList.remove('hidden');screen.scrollIntoView({behavior:'smooth'});
   }catch(err){msg(err.message||'Error de conexión. Inténtalo de nuevo.',true)}
 }));
})();
