/* KISA bulk studio: secure browser-to-Bunny resumable MP4 transfers.
   No Stream API key is shipped here. Tickets are issued by authenticated FastAPI. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  if (!$('dropzone')) return;
  const csrf = document.body.dataset.csrf;
  const MAX_BYTES = 1024 * 1024 * 1024;
  const MAX_FILES = 100;
  const CHUNK_BYTES = 8 * 1024 * 1024;
  const state = { files: [], tasks: [], uploading: false, checking: false, timer: null };
  const toMessage = error => error instanceof Error ? error.message : String(error);

  async function api(url, options = {}) {
    const response = await fetch(url, { credentials: 'same-origin', cache: 'no-store', ...options });
    if (!response.ok) {
      let detail = `Request failed (${response.status})`;
      try { const problem = await response.json(); if (problem.detail) detail = String(problem.detail); } catch (_) {}
      if (response.status === 401) detail = 'Admin session expired. Sign in again, then restart the upload.';
      throw new Error(detail);
    }
    return response.json();
  }
  function mutation(url, body) {
    return api(url, { method:'POST', headers:{'Content-Type':'application/json','X-CSRF-Token':csrf}, body:JSON.stringify(body) });
  }
  function notify(message, error=false) {
    const node = $('batch-status'); node.hidden = false; node.classList.toggle('error',error); node.textContent = message;
  }
  function fileNumber(name) {
    const base = name.replace(/\.mp4$/i,'').split('/').pop();
    const match = base.match(/(?:episode|ep|part|chapter|e)?[\s._-]*(\d+)(?=\D*$)/i);
    return match ? Number(match[1]) : null;
  }
  function filenameTitle(name, position) {
    let candidate = name.replace(/\.mp4$/i,'').replace(/^[\s._\-]*(?:episode|ep|part|chapter)[\s._\-]*\d+[\s._\-]*/i,'')
      .replace(/^[\s._\-]*\d+[\s._\-]*/,'').replace(/[_\-.]+/g,' ').replace(/\s+/g,' ').trim();
    if (!candidate || /^episode\s*\d+$/i.test(candidate)) return `Episode ${position}`;
    return candidate.replace(/\b\w/g, m=>m.toUpperCase()).slice(0,120);
  }
  async function durationOf(file) {
    // Native browser metadata read, no upload. Revoke to avoid memory buildup.
    return new Promise(resolve => {
      const objectUrl = URL.createObjectURL(file);
      const video = document.createElement('video');
      video.preload = 'metadata';
      let done = false;
      const finish = seconds => {
        if (done) return; done = true; video.removeAttribute('src'); video.load(); URL.revokeObjectURL(objectUrl);
        resolve(Number.isFinite(seconds) && seconds >= 1 && seconds <= 900 ? Math.round(seconds) : 75);
      };
      video.onloadedmetadata = () => finish(video.duration);
      video.onerror = () => finish(75);
      video.src = objectUrl;
      setTimeout(() => finish(75), 8000);
    });
  }
  function addFiles(files) {
    if (state.uploading) return notify('Wait for the current transfer to finish.',true);
    const candidates = [...files].filter(f => f instanceof File && f.name.toLowerCase().endsWith('.mp4'));
    const errors = [];
    const known = new Set(state.files.map(x=>`${x.file.name}:${x.file.size}:${x.file.lastModified}`));
    for (const f of candidates) {
      if (f.size < 1 || f.size > MAX_BYTES) { errors.push(`${f.name} exceeds the 1 GiB limit or is empty`); continue; }
      const key = `${f.name}:${f.size}:${f.lastModified}`;
      if (known.has(key)) continue;
      if (state.files.length >= MAX_FILES) {errors.push('Maximum 100 files per batch');break;}
      known.add(key);
      state.files.push({file:f, title:'', duration:75, progress:0, status:'Ready', episode_id:null, error:null});
    }
    // Natural filename ordering: 01.mp4, 02.mp4, 10.mp4.
    state.files.sort((a,b)=>a.file.name.localeCompare(b.file.name,undefined,{numeric:true,sensitivity:'base'}));
    state.files.forEach((item,i) => {if (!item.title) item.title = filenameTitle(item.file.name,i+1);});
    renderFiles();
    if (errors.length) notify(errors.slice(0,3).join('. '),true);
    if (candidates.length === 0) notify('Select MP4 files. Other formats were skipped.',true);
    // Metadata processing in series avoids opening 100 decoder instances.
    (async () => {
      for (const item of state.files) {
        if (item.metadataChecked) continue;
        item.metadataChecked = true;
        item.duration = await durationOf(item.file);
      }
      renderFiles();
    })();
  }
  function renderFiles() {
    $('batch-review').hidden = !state.files.length;
    $('batch-count').textContent = `${state.files.length} episode${state.files.length === 1?'':'s'} selected`;
    const start = Number($('start-number').value) || 1;
    const list = $('batch-list'); list.replaceChildren();
    for (let i = 0; i < state.files.length; i++) {
      const item = state.files[i];
      const row = document.createElement('div');row.className='batch-row';
      const num = document.createElement('span');num.className='number';num.textContent=String(start+i).padStart(2,'0');
      const file = document.createElement('div');file.className='file-name';file.textContent=item.file.name;
      const meta = document.createElement('small');meta.textContent=`${(item.file.size/1024/1024).toFixed(1)} MB · ${item.duration}s`;file.append(meta);
      const title = document.createElement('input');title.value=item.title; title.maxLength=120;title.setAttribute('aria-label',`Title for ${item.file.name}`);
      title.disabled=state.uploading;title.addEventListener('input',()=>{item.title=title.value;});
      const arrows = document.createElement('div');arrows.className='order-btns';
      for (const [symbol,delta] of [['↑',-1],['↓',1]]) {
        const btn=document.createElement('button');btn.type='button';btn.textContent=symbol;
        btn.disabled=state.uploading || i+delta<0 || i+delta>=state.files.length;
        btn.setAttribute('aria-label',`Move ${item.file.name} ${delta<0?'up':'down'}`);
        btn.onclick=()=>{const other=i+delta;[state.files[i],state.files[other]]=[state.files[other],state.files[i]];renderFiles();};
        arrows.append(btn);
      }
      const progress=document.createElement('span');progress.className='status-indicator';progress.textContent=item.progress?`${item.status} ${item.progress}%`:item.status;
      row.append(num,file,title,arrows,progress);list.append(row);
    }
    const finished=state.files.filter(x=>['Published','Ready to publish','Waiting for encoding','Encoding'].includes(x.status) && x.progress===100).length;
    $('overall-progress').textContent=state.uploading?`${finished}/${state.files.length} sent to Bunny. Keep this tab open.`:'Review the list, then start uploads.';
  }
  const series=$('series');
  series.addEventListener('change',()=>{
    const newSeries=series.value==='__new__'; $('new-series').hidden=!newSeries;
    const selected=series.selectedOptions[0];
    $('start-number').value=newSeries ? 1 : Number(selected?.dataset.next || 1);
    $('series-help').textContent=newSeries?'Provide the title and description below.':'For replacing sample episodes, tick the placeholder option and start at Episode 1.';
    renderFiles();
  });
  $('new-title').addEventListener('input',e=>{
    if ($('new-slug').dataset.manuallyEdited==='yes') return;
    $('new-slug').value=e.target.value.toLowerCase().normalize('NFKD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'').slice(0,48);
  });
  $('new-slug').addEventListener('input',()=>{$('new-slug').dataset.manuallyEdited='yes';});
  $('start-number').addEventListener('input',renderFiles);
  const drop = $('dropzone');
  drop.addEventListener('dragover',e=>{e.preventDefault();drop.classList.add('dragover');});
  drop.addEventListener('dragleave',()=>drop.classList.remove('dragover'));
  drop.addEventListener('drop',e=>{e.preventDefault();drop.classList.remove('dragover');addFiles(e.dataTransfer.files);});
  drop.addEventListener('keydown',e=>{if (e.key==='Enter'||e.key===' '){e.preventDefault();$('file-input').click();}});
  $('file-input').addEventListener('change',e=>{addFiles(e.target.files);e.target.value='';});
  $('folder-input').addEventListener('change',e=>{addFiles(e.target.files);e.target.value='';});
  $('clear-files').onclick=()=>{if(state.uploading)return;state.files=[];state.tasks=[];renderFiles();$('batch-status').hidden=true;};
  $('refresh-library').onclick=()=>location.reload();
  $('publish-ready').onclick=async()=>{
    const button=$('publish-ready');button.disabled=true;
    const filter=$('filter-series').value;
    try{
      const out=await mutation('/admin/bulk/publish-ready',{slug:filter});
      notify(`${out.published.length} episodes published; ${out.waiting.length} still encoding; ${out.errors.length} status checks unavailable. Reloading…`);
      setTimeout(()=>location.reload(),1100);
    }catch(error){notify(toMessage(error),true);}finally{button.disabled=false;}
  };
  const updateFilters=()=>{
    const search=$('search-episodes').value.toLowerCase().trim();
    const show=$('filter-series').value, filter=$('filter-status').value;
    let visible=0;
    for(const row of $('episodes-table').rows){
      const hit=(!search||row.dataset.search.includes(search))&&(!show||row.dataset.series===show)&&(!filter||row.dataset.status===filter);
      row.hidden=!hit;if(hit)visible++;
    }
    $('no-rows').hidden=!!visible;
  };
  for (const id of ['search-episodes','filter-series','filter-status']) $(id).addEventListener('input',updateFilters);

  function ticketHeaders(ticket) {
    return {'Tus-Resumable':'1.0.0', 'AuthorizationSignature':ticket.signature,'AuthorizationExpire':String(ticket.expires),
      'VideoId':ticket.video_id,'LibraryId':String(ticket.library_id)};
  }
  function encode64(s) {
    const data=new TextEncoder().encode(s);let result='';for(const byte of data)result+=String.fromCharCode(byte);return btoa(result);
  }
  async function checkOffset(url, headers) {
    const res=await fetch(url,{method:'HEAD',headers,mode:'cors',cache:'no-store'});
    if(!res.ok)throw new Error(`Resume check failed: HTTP ${res.status}`);
    const header=res.headers.get('Upload-Offset');const value=Number(header);
    if(header===null||!Number.isSafeInteger(value)||value<0)throw new Error('Bunny missing Upload-Offset; check library CORS');
    return value;
  }
  const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  async function tusUpload(task,ticket) {
    const file=task.file;
    if(ticket.tus_endpoint!=='https://video.bunnycdn.com/tusupload')throw new Error('Unexpected Bunny upload endpoint');
    const headers=ticketHeaders(ticket);
    const key=`kisa:tus:${task.episode_id}:${ticket.video_id}:${file.name}:${file.size}:${file.lastModified}`;
    let location=sessionStorage.getItem(key);let offset=0;
    if(location){
      try{if(new URL(location).origin!=='https://video.bunnycdn.com')throw Error('Unexpected URL');offset=await checkOffset(location,headers);}
      catch(_){location=null;sessionStorage.removeItem(key);}
    }
    if(!location){
      const fields=[`filename ${encode64(file.name)}`,`filetype ${encode64(file.type||'video/mp4')}`].join(',');
      const res=await fetch(ticket.tus_endpoint,{method:'POST',mode:'cors',cache:'no-store',
        headers:{...headers,'Upload-Length':String(file.size),'Upload-Metadata':fields}});
      if(!res.ok)throw new Error(`Bunny refused upload (HTTP ${res.status})`);
      const loc=res.headers.get('Location');if(!loc)throw new Error('Bunny did not return upload location');
      location=new URL(loc,ticket.tus_endpoint).href;
      if(new URL(location).origin!=='https://video.bunnycdn.com')throw new Error('Unexpected Bunny upload URL');
      sessionStorage.setItem(key,location);
    }
    if(offset>file.size)throw new Error('Remote upload is longer than local file');
    while(offset<file.size){
      let attempts=0;
      while(true){
        const end=Math.min(file.size,offset+CHUNK_BYTES);
        try{
          const res=await fetch(location,{method:'PATCH',mode:'cors',cache:'no-store',headers:{...headers,
            'Content-Type':'application/offset+octet-stream','Upload-Offset':String(offset)},body:file.slice(offset,end)});
          if(!res.ok)throw new Error(`Bunny upload failed (HTTP ${res.status})`);
          const raw=res.headers.get('Upload-Offset');const next=Number(raw);
          if(raw===null||!Number.isSafeInteger(next)||next<=offset||next>end)throw new Error('Invalid Bunny upload offset');
          offset=next;break;
        }catch(error){
          attempts++;if(attempts>5)throw error;
          await pause(Math.min(1500*2**attempts,15000));
          try{
            const authoritative=await checkOffset(location,headers);
            if(authoritative>file.size)throw new Error('Bunny offset exceeds file size');
            if(authoritative>offset){offset=authoritative;break;}
          }catch(_){/* Next retry checks the same range. */}
        }
      }
      task.progress=Math.round(offset/file.size*100);task.status='Uploading';renderFiles();
    }
    sessionStorage.removeItem(key);
  }
  async function publishEpisode(episode_id) {
    const data=new FormData();data.set('csrf',csrf);data.set('episode',episode_id);data.set('publish','1');
    const res=await fetch('/admin/episodes/publish',{method:'POST',body:data,credentials:'same-origin'});
    if(!res.ok){let detail=`HTTP ${res.status}`;try{const body=await res.json();detail=body.detail||detail;}catch(_){}throw new Error(String(detail));}
  }
  async function processEncoding() {
    if(state.checking)return;state.checking=true;
    try{
      const waiting=state.tasks.filter(t=>t.episode_id&&['Encoding','Uploaded','Publish pending'].includes(t.status));
      for(const task of waiting){
        try{
          const result=await api('/admin/videos/bunny/status/'+encodeURIComponent(task.episode_id));
          if(result.ready){
            if($('auto-publish').checked){
              try{await publishEpisode(task.episode_id);task.status='Published';}
              catch(err){task.status='Ready to publish';task.error=toMessage(err);}
            }else{task.status='Ready to publish';}
          }else if(result.state==='failed'){
            task.status='Failed';task.error='Bunny reported a processing failure. Please retry or replace the video.';
          }else{
            task.status='Encoding'; task.error=null;
          }
        }catch(error){task.error=toMessage(error);/* retry on next poll */}
      }
      renderFiles();
      if(!state.tasks.some(t=>['Encoding','Uploaded','Publish pending'].includes(t.status)) && state.timer){clearInterval(state.timer);state.timer=null;}
    }finally{state.checking=false;}
  }
  async function transfer(task) {
    task.status='Preparing';renderFiles();
    try{
      // An earlier attempt may have finished transferring while the browser
      // lost the response. Do not start a second transfer in that case.
      if (task.episode_id) {
        try {
          const existing = await api('/admin/videos/bunny/status/'+encodeURIComponent(task.episode_id));
          if (existing.ready || [1,2,3,4,9,10].includes(existing.status)) {
            task.status='Encoding';task.progress=100;renderFiles();return;
          }
        } catch (_) { /* No linked asset yet: proceed with upload ticket. */ }
      }
      const ticket=await mutation('/admin/videos/bunny/start',{episode_id:task.episode_id,filename:task.file.name,size_bytes:task.file.size});
      if(ticket.state === 'processing') {
        task.progress=100; task.status='Encoding'; renderFiles(); return;
      }
      await tusUpload(task,ticket);
      task.progress=100;task.status='Encoding';renderFiles();
    }catch(error){
      task.status='Failed';task.error=toMessage(error);renderFiles();
      notify(`Upload of ${task.file.name} needs attention: ${task.error}`, true);
    }
  }
  async function startBatch() {
    if(state.uploading||!state.files.length)return;
    const isNew=series.value==='__new__';
    const slug=isNew?$('new-slug').value.trim():series.value;
    if(!/^[a-z0-9-]{3,48}$/.test(slug))return notify('Select a movie or enter a valid new movie slug.',true);
    const start=Number($('start-number').value);
    if(!Number.isInteger(start)||start<1||start+state.files.length>10001)return notify('Invalid starting episode number.',true);
    const files=state.files.map(t=>({filename:t.file.name,size_bytes:t.file.size,title:t.title.trim(),duration_seconds:t.duration}));
    if(files.some(f=>!f.title))return notify('All episodes need a title.',true);
    const body={slug,start_number:start,files,replace_unlinked:$('replace-existing').checked,
      create_series:isNew,auto_publish:$('auto-publish').checked};
    if(isNew){body.series_title=$('new-title').value.trim();body.synopsis=$('new-description').value.trim();body.genre=$('new-genre').value.trim();}
    const btn=$('start-batch');btn.disabled=true;
    state.uploading=true;renderFiles();
    try{
      notify('Creating the episode slots safely…');
      const prepared=await mutation('/admin/bulk/prepare',body);
      state.tasks=state.files;
      for(let i=0;i<state.tasks.length;i++){
        state.tasks[i].episode_id=prepared.items[i].episode_id;
        state.tasks[i].status='Queued';state.tasks[i].progress=0;state.tasks[i].error=null;
      }
      notify(`Created or reused ${prepared.count} episode slots. Uploads started in the background of this tab.`);
      // Limit concurrent transfers to avoid overwhelming phones and small uplinks.
      let cursor=0;
      const worker=async()=>{while(cursor<state.tasks.length){const task=state.tasks[cursor++];await transfer(task);}};
      state.timer=setInterval(processEncoding,15000);
      await Promise.all([worker(),worker()]);
      await processEncoding();
      const failed=state.tasks.filter(t=>t.status==='Failed');
      $('retry-failed').hidden=!failed.length;
      notify(`${state.tasks.length-failed.length} file(s) sent to Bunny. ${failed.length} need retry. ${$('auto-publish').checked?'Success! Bunny is processing your video(s). They will go live automatically when ready, even if you close this tab after transfers finish.':'Bunny is processing your video(s). You can publish them later from the library.'}`, failed.length>0);
    }catch(error){notify(toMessage(error),true);}
    finally{state.uploading=false;btn.disabled=false;renderFiles();}
  }
  $('retry-failed').addEventListener('click', async () => {
    if(state.uploading)return;
    const retry=state.tasks.filter(task=>task.status==='Failed'&&task.episode_id);
    if(!retry.length)return;
    state.uploading=true;$('retry-failed').disabled=true;
    try {
      for(const task of retry)await transfer(task);
      if(!state.timer)state.timer=setInterval(processEncoding,15000);
      await processEncoding();
      const failed=retry.filter(task=>task.status==='Failed');
      $('retry-failed').hidden=!failed.length;
      notify(`${retry.length-failed.length} uploads recovered; ${failed.length} still need attention.`,!!failed.length);
    } finally {state.uploading=false;$('retry-failed').disabled=false;renderFiles();}
  });
  $('start-batch').addEventListener('click',startBatch);
})();
