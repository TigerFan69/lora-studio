// Estimate only from this run's training progress, never preprocessing counters.
function trainingETA(job){
 const waiting={value:'Waiting for training to begin',note:'An estimate appears once a measured training pace is available.'};
 if(job.status==='completed')return {value:'Finished',note:'Training completed.'};
 if(job.status==='stopping')return {value:'Stop requested',note:'Waiting for the training process to exit.'};
 if(!['queued','loading','running'].includes(job.status))return {value:'Not running',note:'No remaining-time estimate.'};
 if(!job.step)return waiting;
 if(job.step>=job.steps)return {value:'Finishing up',note:'Saving the final output; duration varies.'};
 if(job.step<5)return {value:'Estimating training pace…',note:'Waiting for a few completed training steps.'};
 const lines=String(job.log||'').replace(/\x1b\[[0-9;?]*[ -/]*[@-~]/g,'').split(/[\r\n]+/).reverse();
 for(const line of lines){
  if(!line.startsWith(job.name+':'))continue;
  const count=line.match(/(\d+)\/(\d+)\s*\[/),rate=line.match(/,\s*([\d.]+)\s*(s\/it|it\/s)\b/);
  if(!count||!rate||Number(count[1])!==job.step||Number(count[2])!==job.steps)continue;
  const pace=Number(rate[1]);if(!Number.isFinite(pace)||pace<=0)continue;
  const seconds=(job.steps-job.step)*(rate[2]==='s/it'?pace:1/pace);
  const minutes=Math.ceil(seconds/60),hours=Math.floor(minutes/60),remainder=minutes%60;
  const duration=seconds<60?'Less than 1 min':hours?`${hours} hr${remainder?' '+remainder+' min':''}`:`${minutes} min`;
  return {value:'About '+duration.replace(/^Less/,'less'),note:'At the latest measured pace. Saving checkpoints and other pauses can add time.'};
 }
 return {value:'Estimating training pace…',note:'Waiting for a valid rate in the latest training output.'};
}
