let workflowProject=null,workflowCaption=null,workflowComfy='unknown';
const $=s=>document.querySelector(s);
const historyLogOpen=new Map();
let state={},selected=null,preparedView=false,pendingJob=null,lastProjects='',lastJobs='';
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(path,method='GET',data){const opts={method,headers:{'X-Studio-Request':'1'}};if(data instanceof FormData)opts.body=data;else if(data!==undefined){opts.headers['Content-Type']='application/json';opts.body=JSON.stringify(data)}const r=await fetch(path,opts);const v=await r.json();if(!r.ok)throw Error(typeof v.detail==='string'?v.detail:JSON.stringify(v.detail));return v}
function message(text,error=false){const el=$(error?'#error':'#notice');el.textContent=text;el.hidden=false;$(error?'#notice':'#error').hidden=true}
async function busy(el,fn){el.disabled=true;$('#error').hidden=true;try{await fn()}catch(e){message(e.message,true)}finally{el.disabled=false}}
function tab(name){document.querySelectorAll('.tab').forEach(e=>e.hidden=e.id!==name);document.querySelectorAll('.nav').forEach(e=>e.classList.toggle('active',e.dataset.tab===name));$('#page-title').textContent={dataset:'Build a better dataset.',training:'Bring your character to life.',library:'Find your best checkpoint.',settings:'Make this server your own.'}[name];$('#subtitle').textContent={dataset:'Keep the identity. Give the details room to change.',training:'Choose a model, check its requirements, and follow training progress.',library:'Compare, download, and create with ComfyUI.',settings:'Choose where your trained LoRAs are copied.'}[name];renderNextStep()}
document.querySelectorAll('.nav').forEach(b=>b.onclick=()=>tab(b.dataset.tab));
function renderProjects(){const signature=JSON.stringify([state.projects,state.sources,selected]);if(signature===lastProjects)return;lastProjects=signature;const src=$('#source').value;$('#source').innerHTML=(state.sources||[]).map(x=>`<option value="${esc(x)}">${esc(x)}</option>`).join('');if((state.sources||[]).includes(src))$('#source').value=src;$('#import').disabled=!(state.sources||[]).length;const projects=(state.projects||[]).filter(p=>!p.removed);$('#project-list').innerHTML=projects.length?projects.map(p=>`<div class="project-item"><div><strong>${esc(p.name)}</strong><small>${p.image_count} images · ${esc(p.trigger)} · ${p.prepared?'Prepared':'Needs preparation'}</small></div><div class="actions"><button class="secondary" data-project="${p.id}">Review</button><button class="secondary" data-remove-project="${p.id}">Remove</button></div></div>`).join(''):'<div class="empty">No projects yet. Import a dataset to begin.</div>';const prior=$('#train-project').value;$('#train-project').innerHTML='<option value="">Choose a prepared dataset</option>'+projects.filter(p=>p.prepared).map(p=>`<option value="${p.id}">${esc(p.name)}</option>`).join('');$('#train-project').value=selected&&projects.some(p=>p.id===selected&&p.prepared)?selected:prior;document.querySelectorAll('[data-project]').forEach(b=>b.onclick=()=>busy(b,()=>loadProject(b.dataset.project,false)))}
async function refresh(){state=await api('/api/state');$('#gpu-name').textContent=state.gpu.name;$('#gpu-memory').textContent=state.gpu.used===null?'Unavailable':`${(state.gpu.used/1024).toFixed(1)} / ${(state.gpu.total/1024).toFixed(1)} GB`;$('#disk').textContent=state.disk_free_gb+' GB';$('#run-status').textContent=state.jobs.some(j=>['queued','loading','running','stopping'].includes(j.status))?'Active':'Idle';renderProjects();renderMonitor();renderJobs();renderLibrary();renderHistoryTools();renderNextStep()}
async function loadProject(id,prepared=false){const d=await api(`/api/projects/${id}?prepared=${prepared}`);showProject(d)}
function showProject(d){workflowProject=d;selected=d.project.id;preparedView=d.view==='prepared';$('#review').hidden=false;$('#project-heading').textContent=d.project.name+(preparedView?' · prepared preview':' · source captions');$('#audit-summary').textContent=`${d.audit.count} images · ${d.audit.warnings} with review notes · trigger: ${d.project.trigger}`;$('#revision-status').textContent=d.project.prepared?'Prepared revision ready. Existing jobs keep their own revision.':'Prepare a revision after reviewing captions.';$('#to-training').disabled=!d.project.prepared;$('#gallery').innerHTML=d.audit.images.map(r=>`<article class="image-card"><img loading="lazy" src="/api/projects/${selected}/images/${encodeURIComponent(r.name)}?prepared=${preparedView}" alt="Dataset image ${esc(r.name)}"><div class="image-body"><div class="filename">${esc(r.name)}</div><button class="danger" data-remove-image="${esc(r.name)}">Remove photo</button><div class="dimensions">${r.width} × ${r.height} · ${r.words} words</div>${r.warnings.map(w=>`<div class="warning">${esc(w)}</div>`).join('')}<label>Caption<textarea data-name="${esc(r.name)}" ${preparedView?'readonly':''}>${esc(r.caption)}</textarea></label>${preparedView?'<small class="muted">Edit the source, then prepare a new revision.</small>':`<button class="secondary" data-save="${esc(r.name)}">Save caption</button>`}</div></article>`).join('');document.querySelectorAll('[data-save]').forEach(b=>b.onclick=()=>busy(b,async()=>{const area=b.parentElement.querySelector('textarea');await api(`/api/projects/${selected}/captions/${encodeURIComponent(b.dataset.save)}`,'PUT',{text:area.value});message('Caption saved with a backup. Prepare a new revision when your edits are complete.');await refresh();$('#to-training').disabled=true;$('#revision-status').textContent='Caption changed. Prepare a fresh revision.'}));renderImageRemoval(d);renderProjects();renderHistoryTools();renderNextStep()}
$('#import').onclick=e=>busy(e.currentTarget,async()=>{const d=await api('/api/projects','POST',{name:$('#project-name').value,trigger:$('#trigger').value,source:$('#source').value});await refresh();await loadProject(d.id);message('Working copy imported. The original server dataset is unchanged.')});
$('#upload').onclick=e=>busy(e.currentTarget,async()=>{const files=$('#files').files;if(!files.length)throw Error('Select images and caption files first');const form=new FormData();form.append('name',$('#project-name').value);form.append('trigger',$('#trigger').value);for(const f of files)form.append('files',f);$('#upload-status').textContent='Uploading to the server… Keep this page open until it finishes.';let d;try{d=await api('/api/upload','POST',form)}catch(e){$('#upload-status').textContent='Upload failed. Your local files are unchanged. '+e.message;throw e}await refresh();await loadProject(d.id);$('#upload-status').textContent='Upload complete — saved to a separate Raw Images batch on the server.';$('#files').value='';message('Uploaded to Raw Images and opened a working project. Generate captions, review them, then prepare a revision at the bottom.')});
$('#prepare').onclick=e=>busy(e.currentTarget,async()=>{const d=await api(`/api/projects/${selected}/prepare`,'POST',{mode:$('#crop-mode').value,max_size:Number($('#max-size').value),clean:$('#clean').checked});await refresh();showProject(d);message('Prepared a new revision. Review the resulting framing and captions below.')});
$('#source-view').onclick=e=>busy(e.currentTarget,()=>loadProject(selected,false));
$('#to-training').onclick=()=>{tab('training');$('#train-project').value=selected;window.scrollTo({top:0,behavior:'smooth'})};
$('#create-job').onclick=e=>busy(e.currentTarget,async()=>{if(!$('#train-project').value)throw Error('Select a prepared dataset first');await api('/api/jobs','POST',{project:$('#train-project').value,profile_id:$('#training-profile').value,steps:Number($('#steps').value),label:$('#job-label').value});await refresh();message('Config created. Review it, then use Start training when ready.')});
function renderJobs(){const signature=JSON.stringify(state.jobs);if(signature===lastJobs)return;lastJobs=signature;const positions=new Map([...document.querySelectorAll('[data-log]')].map(x=>[x.dataset.log,{top:x.querySelector('pre').scrollTop,left:x.querySelector('pre').scrollLeft}]));const open=new Set([...document.querySelectorAll('[data-log][open]')].map(x=>x.dataset.log));$('#jobs').innerHTML=state.jobs.some(j=>!j.removed)?state.jobs.filter(j=>!j.removed).map(j=>`<article class="job"><div class="row"><div><h3>${esc(j.name)}</h3><small class="muted">${esc(j.profile_label)} · ${esc(j.project_name)} · ${j.steps.toLocaleString()} steps · ${esc(j.trigger)}</small></div><span class="status ${esc(j.status)}">${esc(j.status)}</span></div><progress max="${j.steps}" value="${j.step}"></progress><div class="row"><span class="muted">${j.step} / ${j.steps} ${j.loss?'· loss '+esc(j.loss):''}</span><span class="muted">${j.status==='ready'?'Config ready':esc(j.stage)}</span></div>${j.error?`<div class="warning">${esc(j.error)}</div>`:''}<div class="actions">${!['queued','loading','running','stopping'].includes(j.status)?`<button class="secondary" data-remove-job="${j.id}">Remove from history</button>`:''}<a href="/api/jobs/${j.id}/config" target="_blank">View YAML ↗</a>${j.status==='ready'?`<button class="primary" data-start="${j.id}">Start training</button>`:''}${['queued','loading','running','stopping'].includes(j.status)?`<button class="danger" data-stop="${j.id}" ${j.status==='stopping'?'disabled':''}>${j.status==='stopping'?'Stopping…':'Request stop'}</button>`:''}${j.checkpoints.map(c=>`<a href="${c.url}">${esc(c.name)}</a>`).join(' ')}</div><details data-log="${j.id}" ${(historyLogOpen.has(j.id)?historyLogOpen.get(j.id):(open.has(j.id)||['queued','loading','running','stopping'].includes(j.status)))?'open':''}><summary>Live log</summary><pre>${esc(j.log||'No log yet. Training has not started.')}</pre></details></article>`).join(''):'<div class="empty">No jobs yet. Create a configuration from a prepared dataset.</div>';document.querySelectorAll('[data-log]').forEach(x=>{x.ontoggle=()=>historyLogOpen.set(x.dataset.log,x.open);const p=positions.get(x.dataset.log);if(p){x.querySelector('pre').scrollTop=p.top;x.querySelector('pre').scrollLeft=p.left}});document.querySelectorAll('[data-start]').forEach(b=>b.onclick=()=>{pendingJob=b.dataset.start;const j=state.jobs.find(x=>x.id===pendingJob);$('#confirm-text').textContent=`${j.name} · ${j.steps} steps · ${j.project_name}`;$('#confirm-dialog').showModal()});document.querySelectorAll('[data-stop]').forEach(b=>b.onclick=()=>busy(b,async()=>{await api(`/api/jobs/${b.dataset.stop}/stop`,'POST',{});message('Stop requested. Wait for the runner to exit; last saved checkpoints remain available.');await refresh()}))}
$('#cancel-start').onclick=()=>$('#confirm-dialog').close();$('#confirm-start').onclick=e=>busy(e.currentTarget,async()=>{await api(`/api/jobs/${pendingJob}/start`,'POST',{});$('#confirm-dialog').close();message('Training started. You can close the browser; the job runs on the server.');await refresh()});
let librarySignature='';
function renderLibrary(){
 const removed=new Set(state.removed_adapters||[]);
 const files=[...state.existing.map(x=>({...x,url:'/api/existing/'+encodeURIComponent(x.name),label:'Existing training output · ohwx woman'})),...state.jobs.flatMap(j=>j.checkpoints.map(c=>({...c,label:j.profile_label+' · '+j.project_name+' · '+j.trigger+' · '+j.inference})))].sort((a,b)=>(b.modified||0)-(a.modified||0)||a.name.localeCompare(b.name));
 const signature=JSON.stringify([files,[...removed]]);if(signature===librarySignature)return;librarySignature=signature;
 const visible=files.filter(f=>!removed.has(f.url)),hidden=files.filter(f=>removed.has(f.url));
 const row=(f,restore=false)=>`<div class="file-row"><div><strong>${esc(f.name)}</strong><small>${esc(f.label)} · ${(f.bytes/1024/1024).toFixed(1)} MB · Saved ${esc(f.modified?new Date(f.modified*1000).toLocaleString():'date unavailable')}</small></div><div class="actions"><button class="primary" data-copy-comfy="${esc(f.url)}">Copy to ComfyUI</button><button class="secondary" data-download-adapter="${esc(f.url)}">Download to computer ↓</button><button class="secondary" data-adapter="${esc(f.url)}" data-restore-adapter="${restore}">${restore?'Restore':'Remove from history'}</button></div></div>`;
 $('#library-files').innerHTML=visible.length?visible.map(f=>row(f)).join(''):'<div class="empty">No adapters in the current history. Removed entries can be restored below.</div>';
 $('#removed-adapters-content').innerHTML=hidden.map(f=>row(f,true)).join('')||'<p>No removed adapters.</p>';
 $('#removed-adapters-summary').textContent=`Removed adapters (${hidden.length}) · restore`;
 document.querySelectorAll('[data-download-adapter]').forEach(b=>b.onclick=()=>{window.location.href=b.dataset.downloadAdapter});
 document.querySelectorAll('[data-copy-comfy]').forEach(b=>b.onclick=()=>busy(b,async()=>{const d=await api('/api/library/copy-to-comfyui','POST',{url:b.dataset.copyComfy});b.textContent='In ComfyUI ✓';message(`${d.name}: ${d.status==='already_present'?'already in':'copied to'} ComfyUI’s LoRA folder on the server. Refresh ComfyUI’s model list, then select it in your LoRA loader.`)}));
 document.querySelectorAll('[data-adapter]').forEach(b=>b.onclick=()=>busy(b,async()=>{const restore=b.dataset.restoreAdapter==='true';await api('/api/library/history','POST',{url:b.dataset.adapter,removed:!restore});await refresh();message(restore?'Adapter restored to the library.':'Adapter removed from history. The model file is preserved; restore it below anytime.')}));
}

refresh().catch(e=>message('Could not connect: '+e.message,true));setInterval(()=>refresh().catch(e=>message('Connection interrupted: '+e.message,true)),6000);
// Florence captions stay in a separate draft panel until explicitly applied.
const captionPanel=document.createElement('section');captionPanel.className='panel caption-panel';captionPanel.hidden=true;$('#review').prepend(captionPanel);
let captionSignature='';
const autoFillAttempted=new Set();
async function refreshCaptions(){
 if(!selected)return;captionPanel.hidden=false;
 const data=await api('/api/captioning');const runs=data.runs.filter(r=>r.project===selected);
 const latest=runs[0];workflowCaption=latest;renderWorkflowGlow();
 if(latest?.status==='completed'&&latest.results.some(r=>!r.applied)&&!autoFillAttempted.has(latest.id)){
  autoFillAttempted.add(latest.id);
  try{const result=await api(`/api/captioning/${latest.id}/apply-all`,'POST',{});await loadProject(selected,false);await refresh();message(`Filled ${result.saved} caption boxes automatically. Review the captions, then prepare a new revision at the bottom.`);return}
  catch(e){message(e.message,true)}
 }

 const signature=JSON.stringify([selected,runs]);if(signature===captionSignature)return;captionSignature=signature;
 const priorMode=captionPanel.querySelector('#caption-mode')?.value,priorFile=captionPanel.querySelector('#caption-file')?.value;
 const openDrafts=new Set([...captionPanel.querySelectorAll('details[open]')].map(e=>e.querySelector('textarea').dataset.draft));
 const saved=new Map([...captionPanel.querySelectorAll('textarea')].map(e=>[e.dataset.draft,e.value]));
 captionPanel.innerHTML=`<h3>Automatic photo captions</h3><p>Florence-2 PromptGen describes your photos locally in ComfyUI. When the latest batch completes, all image caption boxes fill automatically. Existing captions are backed up. Review the filled captions before preparing a revision.</p><div class="actions"><select id="caption-mode" aria-label="Images to caption"><option value="missing">Images missing captions</option><option value="all">All images</option><option value="one">One image preview</option></select><input id="caption-file" aria-label="Preview image filename" placeholder="Filename for one-image preview"><button id="caption-start" class="primary">Generate drafts</button></div><div>${runs.map(r=>`<article class="job"><div class="caption-progress-row"><strong>${esc(r.status)} · ${r.results.length} / ${r.total} drafts</strong><div class="caption-next-note"><strong>When this finishes, scroll to the bottom of the page to continue.</strong><p>The caption boxes fill automatically when the batch completes. Review them, then choose Prepare a new revision, followed by Continue to training.</p><a href="#prepare">Go to preparation ↓</a></div></div>${r.current?`<small>${esc(r.current)}</small>`:''}${r.error?`<p class="warning">${esc(r.error)}</p>`:''}${['queued','running'].includes(r.status)?`<button data-caption-stop="${r.id}">Stop after current image</button>`:''}${r.status==='needs_attention'?`<button data-caption-resolve="${r.id}">Resolve once ComfyUI is idle</button>`:''}${r.results.map((v,i)=>`<details><summary>${esc(v.name)} ${v.applied?'· applied':''}</summary><label>Generated draft<textarea data-draft="${r.id}-${i}">${esc(saved.get(r.id+'-'+i)??v.text)}</textarea></label><button data-caption-apply="${r.id}" data-caption-index="${i}" ${v.applied||['queued','running','needs_attention'].includes(r.status)?'disabled':''}>Apply caption with backup</button></details>`).join('')}</article>`).join('')}</div>`;
 if(priorMode)$('#caption-mode').value=priorMode;if(priorFile)$('#caption-file').value=priorFile;
 captionPanel.querySelectorAll('details').forEach(e=>{e.open=openDrafts.has(e.querySelector('textarea').dataset.draft)});
 $('#caption-start').onclick=e=>busy(e.currentTarget,async()=>{await api(`/api/projects/${selected}/captioning`,'POST',{mode:$('#caption-mode').value,filename:$('#caption-file').value});await refreshCaptions()});
 captionPanel.querySelectorAll('[data-caption-stop]').forEach(b=>b.onclick=()=>busy(b,async()=>{await api(`/api/captioning/${b.dataset.captionStop}/stop`,'POST',{});message('Will stop after the current image. Finished drafts are kept.')}));
 captionPanel.querySelectorAll('[data-caption-resolve]').forEach(b=>b.onclick=()=>busy(b,async()=>{await api(`/api/captioning/${b.dataset.captionResolve}/resolve`,'POST',{});await refreshCaptions()}));
 captionPanel.querySelectorAll('[data-caption-apply]').forEach(b=>b.onclick=()=>busy(b,async()=>{const r=runs.find(x=>x.id===b.dataset.captionApply),v=r.results[Number(b.dataset.captionIndex)];await api(`/api/captioning/${r.id}/apply`,'POST',{filename:v.name,text:b.parentElement.querySelector('textarea').value});await loadProject(selected,false);await refresh();await refreshCaptions();message('Caption applied. Review the source, then prepare a fresh revision.')}));
}
const originalShowProject=showProject;showProject=function(d){originalShowProject(d);refreshCaptions().catch(e=>message(e.message,true))};
setInterval(()=>refreshCaptions().catch(e=>message(e.message,true)),4000);

function renderHistoryTools(){
 document.querySelectorAll('[data-remove-project]').forEach(b=>b.onclick=()=>busy(b,async()=>{await api(`/api/projects/${b.dataset.removeProject}/history`,'POST',{removed:true});if(selected===b.dataset.removeProject){selected=null;$('#review').hidden=true}await refresh();message('Project removed from history. Restore it below whenever you need it. Files are preserved.')}));
 document.querySelectorAll('[data-remove-job]').forEach(b=>b.onclick=()=>busy(b,async()=>{await api(`/api/jobs/${b.dataset.removeJob}/history`,'POST',{removed:true});await refresh();message('Job removed from history. Its checkpoints remain in the LoRA library.')}));
 for(const kind of ['projects','jobs']){
  const el=$('#removed-'+kind),rows=(state[kind]||[]).filter(x=>x.removed);
  const signature=JSON.stringify(rows.map(x=>[x.id,x.name]));if(el.dataset.signature===signature)continue;el.dataset.signature=signature;
  el.innerHTML=rows.length?`<summary>Removed ${kind} (${rows.length}) · restore</summary>`+rows.map(x=>`<div class="file-row"><span>${esc(x.name)}</span><button class="secondary" data-restore="${x.id}">Restore</button></div>`).join(''):'<summary>No removed '+kind+'</summary>';
  el.querySelectorAll('[data-restore]').forEach(b=>b.onclick=()=>busy(b,async()=>{await api(`/api/${kind}/${b.dataset.restore}/history`,'POST',{removed:false});await refresh()}));
 }
}
function renderNextStep(){
 const view=document.querySelector('.nav.active')?.dataset.tab||'dataset',p=(state.projects||[]).find(x=>x.id===selected&&!x.removed);
 let text,action;
 if(view==='dataset'){
  if(!p){text='Step 1 · Upload photos into a working project, or choose Review on an existing project. My Dataset is updated only when you publish.';action=null}
  else if(!p.prepared){text='Step 2 · Start ComfyUI and generate captions. The boxes fill automatically when finished. Review them, then prepare a new revision below.';action=null}
  else if(p.published_revision!==p.prepared){text='Step 3 · Inspect the prepared images and captions, then publish the finished set to My Dataset.';action='publish'}
  else {text='Step 4 · Your finished dataset is published. Continue to Training to create a configuration.';action='training'}
 }else if(view==='training'){
  if((state.jobs||[]).some(j=>['queued','loading','running','stopping'].includes(j.status))){text='Training is active · Follow its progress below. When it finishes, open the LoRA library.'}
  else if((state.jobs||[]).some(j=>!j.removed&&j.status==='ready')){text='Next · Review the ready job’s YAML in Run History, then click Start training when the GPU is available.'}
  else {text='Next · Choose a prepared dataset and create a configuration. A 20-step test is a useful first check.'}
 }else if(view==='settings'){text='Settings apply to future copies. Existing models stay where they are.'}else {text='Next · Copy a checkpoint to ComfyUI, load it with its matching base model, and compare results using the same prompt and seed.'}
 $('#next-step-text').textContent=text;$('#publish-dataset').hidden=action!=='publish';$('#next-training').hidden=action!=='training';renderWorkflowGlow();
}
$('#next-training').onclick=()=>{$('#to-training').click();renderNextStep()};
$('#publish-dataset').onclick=()=>{$('#publish-dialog').showModal()};
$('#cancel-publish').onclick=()=>$('#publish-dialog').close();
$('#confirm-publish').onclick=e=>busy(e.currentTarget,async()=>{const d=await api(`/api/projects/${selected}/publish`,'POST',{});$('#publish-dialog').close();await refresh();message(`Published ${d.images} image/caption pairs to My Dataset. Previous contents were backed up.`)});

$('#files').onchange=()=>{$('#upload-status').textContent=$('#files').files.length+' files selected. Click Upload to send them to Raw Images on the server.'};

async function refreshComfy(){const d=await api('/api/comfyui');workflowComfy=d.status;renderWorkflowGlow();$('#comfy-status').textContent='ComfyUI: '+d.status;for(const action of ['start','stop'])$('#comfy-'+action).disabled=!d.managed;}
for(const action of ['start','stop'])$('#comfy-'+action).onclick=e=>busy(e.currentTarget,async()=>{await api('/api/comfyui/'+action,'POST',{});await refreshComfy();message(action==='start'?'ComfyUI start requested. Give it a moment to load, then generate caption drafts.':'ComfyUI stopped. You can now prepare or start training.');await refresh()});
refreshComfy().catch(e=>{$('#comfy-status').textContent=e.message});setInterval(()=>refreshComfy().catch(()=>{}),6000);

let monitoredRun=null,followRunLog=true,monitorLatest='',monitorChangedAt=null;
function cleanLogLines(text){return String(text||'').replace(/\x1b\[[0-9;?]*[ -/]*[@-~]/g,'').split(/[\r\n]+/).map(x=>x.trimEnd()).filter(x=>x.trim());}
function updateMonitorLog(){
 const pre=$('#monitor-log');
 if(followRunLog&&pre.textContent!==monitorLatest){pre.textContent=monitorLatest;pre.scrollTop=0;pre.scrollLeft=0}
 $('#monitor-follow').textContent=followRunLog?'Pause log to read':'Resume latest activity';
 $('#monitor-follow').setAttribute('aria-pressed',String(followRunLog));
 $('#monitor-update').textContent=(followRunLog?'Live log':'Log paused for reading · status still updates')+(monitorChangedAt?' · Latest change seen '+monitorChangedAt:'');
}
function renderMonitor(){
 const jobs=state.jobs||[],active=jobs.find(j=>['queued','loading','running','stopping'].includes(j.status));
 const job=active||jobs.find(j=>j.id===monitoredRun)||jobs.find(j=>!j.removed&&j.status!=='ready');
 $('#run-monitor').hidden=!job;if(!job)return;
 if(monitoredRun!==job.id){monitoredRun=job.id;followRunLog=true;monitorLatest='';monitorChangedAt=null}
 const lines=cleanLogLines(job.log),latest=lines.at(-1)||'';
 const stage=['queued','loading','running','stopping'].includes(job.status)?(latest||job.stage):job.status==='completed'?'Training finished. Saved adapters are available in the LoRA library.':(job.error||job.status);
 $('#monitor-title').textContent=job.project_name;
 $('#monitor-status').textContent=job.status;$('#monitor-status').className='status '+job.status;
 const eta=trainingETA(job);$('#monitor-eta-value').textContent=eta.value;$('#monitor-eta-note').textContent=eta.note;
 $('#monitor-stage').textContent=stage;
 $('#monitor-progress').max=job.steps;$('#monitor-progress').value=job.step;
 $('#monitor-steps').textContent=`${job.step.toLocaleString()} / ${job.steps.toLocaleString()} training steps · ${(100*job.step/job.steps).toFixed(1)}%`;
 $('#monitor-loss').textContent=job.loss?'Latest loss: '+job.loss:'Loss: available once training starts';
 $('#monitor-gpu').textContent=state.gpu.used===null?'GPU memory unavailable':`GPU memory: ${(state.gpu.used/1024).toFixed(1)} / ${(state.gpu.total/1024).toFixed(1)} GB`;
 $('#monitor-checkpoints').textContent=`${job.checkpoints.length} saved checkpoints`;
 const next=lines.slice(-100).reverse().join('\n')||'Waiting for the training process to write output…';
 if(next!==monitorLatest){monitorLatest=next;monitorChangedAt=new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}
 updateMonitorLog();
}
$('#monitor-follow').onclick=()=>{followRunLog=!followRunLog;updateMonitorLog()};
$('#monitor-log').addEventListener('scroll',()=>{if(followRunLog&&$('#monitor-log').scrollTop>8){followRunLog=false;updateMonitorLog()}});

function renderImageRemoval(d){
 let panel=$('#removed-photos');if(!panel){panel=document.createElement('details');panel.id='removed-photos';$('#gallery').after(panel)}
 const removed=d.removed_images||[];
 panel.hidden=!removed.length;
 panel.innerHTML=`<summary>Removed photos (${removed.length}) · restore</summary>${removed.map(r=>`<div class="actions"><span>${esc(r.name)}</span><button class="secondary" data-restore-image="${esc(r.id)}">Restore photo</button></div>`).join('')}`;
 const retainEdits=async()=>{if(preparedView)return;for(const area of document.querySelectorAll('#gallery textarea')){if(area.value!==area.defaultValue)await api(`/api/projects/${selected}/captions/${encodeURIComponent(area.dataset.name)}`,'PUT',{text:area.value})}};
 document.querySelectorAll('[data-remove-image]').forEach(b=>b.onclick=()=>busy(b,async()=>{
  await retainEdits();await api(`/api/projects/${selected}/images/${encodeURIComponent(b.dataset.removeImage)}/remove`,'POST',{prepared:preparedView});
  await refresh();await loadProject(selected,false);message('Photo removed from this working dataset. You can restore it below the photos. Prepare a new revision, then publish again if needed.');
 }));
 panel.querySelectorAll('[data-restore-image]').forEach(b=>b.onclick=()=>busy(b,async()=>{
  await retainEdits();await api(`/api/projects/${selected}/removed-images/${b.dataset.restoreImage}/restore`,'POST',{});
  await refresh();await loadProject(selected,false);message('Photo and caption restored. Prepare a new revision before training or publishing.');
 }));
}

let defaultLoraDestination='';
async function loadDestinations(){const d=await api('/api/settings/destinations');$('#lora-destination').value=d.lora_destination;defaultLoraDestination=d.default_lora_destination;$('#destination-status').textContent='Saved destination: '+d.lora_destination}
$('#save-destinations').onclick=e=>busy(e.currentTarget,async()=>{const d=await api('/api/settings/destinations','PUT',{lora_destination:$('#lora-destination').value});$('#lora-destination').value=d.lora_destination;$('#destination-status').textContent='Saved destination: '+d.lora_destination;message('Destination saved. Future Copy to ComfyUI actions use this server folder.')});
$('#default-destination').onclick=()=>{$('#lora-destination').value=defaultLoraDestination;$('#destination-status').textContent='Standard folder selected. Click Save destination to apply.'};
loadDestinations().catch(e=>message(e.message,true));

function renderWorkflowGlow(){
 const view=document.querySelector('.nav.active')?.dataset.tab||'dataset';
 const project=(state.projects||[]).find(p=>p.id===selected&&!p.removed);
 const jobs=(state.jobs||[]).filter(j=>!j.removed);
 let target=null,nav=view,label='Work here next';
 if(view==='settings'){target=$('#settings .panel');label='Server preferences'}
 else if(view==='library'){target=$('#library .panel');label='Choose a checkpoint to copy'}
 else if(view==='training'){
  const active=jobs.find(j=>['queued','loading','running','stopping'].includes(j.status));
  const ready=jobs.find(j=>j.status==='ready');
  if(active){target=$('#run-monitor');label='Training in progress'}
  else if(ready){target=workflowComfy==='active'?$('.comfy-controls'):$('#jobs')?.closest('.panel');label=workflowComfy==='active'?'Free GPU memory before starting':'Review and start your ready job'}
  else if(jobs[0]?.status==='completed'){target=$('.next-step');nav='library';label='Training complete — open LoRA library';$('#next-step-text').textContent='Next · Open LoRA library to copy your completed checkpoint to ComfyUI. You can also create another training job below.'}
  else {target=$('#create-job')?.closest('.panel');label='Prepare your training configuration'}
 }else if(!project){target=$('#upload')?.closest('.panel');label='Start here — import your photos'}
 else if(workflowCaption?.project===selected&&['queued','running','needs_attention'].includes(workflowCaption.status)){target=$('.caption-panel');label=workflowCaption.status==='needs_attention'?'Captioning needs attention':'Captioning in progress'}
 else if(project.prepared){target=preparedView?$('#gallery'):$('#review');label='Review prepared photos';if(project.published_revision===project.prepared){target=$('.next-step');nav='training';label='Ready to continue to training'}else{target=$('.next-step');label='Review your prepared photos, then publish'}}
 else {
  const missing=workflowProject?.project.id===selected&&workflowProject.audit.images.some(r=>!r.caption.trim());
  if(missing){target=workflowComfy==='active'?$('.caption-panel'):$('.comfy-controls');label=workflowComfy==='active'?'Generate or write missing captions':'Start ComfyUI for automatic captions'}
  else {target=$('#gallery');label='Review photos and captions, then prepare a revision'}
 }
 const next=new Set([target,document.querySelector(`.nav[data-tab="${nav}"]`)].filter(Boolean));
 document.querySelectorAll('.workflow-focus').forEach(el=>{if(!next.has(el)){el.classList.remove('workflow-focus');el.removeAttribute('data-workflow-hint')}});
 next.forEach(el=>el.classList.add('workflow-focus'));
 if(target){target.dataset.workflowHint=label;target.classList.add('workflow-section')}
}

let trainingProfiles=[];
function updateTrainingProfile(){
 const p=trainingProfiles.find(p=>p.id===$('#training-profile').value);
 $('#create-job').disabled=!p?.ready;
 for(const option of $('#steps').options)option.disabled=!!p?.max_test_steps&&Number(option.value)>p.max_test_steps;
 if(p?.max_test_steps)$('#steps').value='20';
 $('#profile-status').textContent=p?`${p.validation}. ${p.requirement}. ${p.id==='flux1-dev'?'Dev requires acceptance of its gated, non-commercial model license.':''}`:'No training profile selected';
 if(p){$('#profile-license').href=p.license_url;$('#profile-preset').innerHTML=Object.entries(p.preset).map(([label,value])=>`<span>${esc(label)} <b>${esc(value)}</b></span>`).join('')}
}
function updateTrainingFamily(){
 $('#training-profile').innerHTML=trainingProfiles.filter(p=>p.family===$('#model-family').value).map(p=>`<option value="${esc(p.id)}">${esc(p.label)}${p.ready?'':' · setup required'}</option>`).join('');$('#steps').value='20';updateTrainingProfile();
}
$('#model-family').onchange=updateTrainingFamily;
$('#training-profile').onchange=()=>{$('#steps').value='20';updateTrainingProfile()};
$('#create-job').disabled=true;
api('/api/training-profiles').then(rows=>{trainingProfiles=rows;const families=[...new Map(rows.map(p=>[p.family,p.family_label])).entries()];$('#model-family').innerHTML=families.map(([id,label])=>`<option value="${esc(id)}">${esc(label)}</option>`).join('');updateTrainingFamily()}).catch(e=>{$('#profile-status').textContent=e.message});
