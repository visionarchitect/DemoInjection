const output=document.querySelector('#console-output');
let activated=false;
let countdown=86399;

function timestamp(){return new Date().toLocaleTimeString('en-GB',{hour12:false})}
function log(level,message){const line=document.createElement('p');line.className=`log-${level}`;line.innerHTML=`<time>${timestamp()}</time><b>[${level.toUpperCase()}]</b><span></span>`;line.querySelector('span').textContent=message;output.prepend(line);output.scrollTop=0}

function activate(scriptLogs=[]){
  if(activated)return;
  activated=true;
  document.body.classList.add('active');
  document.querySelector('#incident-state').textContent='SCRIPT EXECUTED';
  const levelFor=line=>line.includes('[ALERT]')?'danger':line.includes('[DONE]')?'ok':line.includes('[EXEC]')?'exec':'sys';
  const sequence=[['exec','/bin/sh validation-check.sh'],...scriptLogs.map(line=>[levelFor(line),line]),['danger','Recovery deadline initialized: 23:59:59'],['ok','SHELL PROCESS EXITED 0 — SCRIPT EXECUTION COMPLETE']];
  sequence.forEach(([level,message],index)=>setTimeout(()=>log(level,message),index*430));
}

async function pollStatus(){
  try{
    const response=await fetch('/api/status');
    if(response.ok){const status=await response.json();if(status.payload_active)activate(status.payload_logs||[])}
  }catch(_){log('warn','Telemetry channel unavailable — retrying')}
}

log('sys','Execution monitor attached');
log('wait','Waiting for catalogue helper dispatch');
setInterval(()=>{countdown=Math.max(0,countdown-1);const h=String(Math.floor(countdown/3600)).padStart(2,'0'),m=String(Math.floor(countdown%3600/60)).padStart(2,'0'),s=String(countdown%60).padStart(2,'0');document.querySelector('#countdown').textContent=`${h}:${m}:${s}`},1000);
setInterval(pollStatus,700);
pollStatus();

document.querySelector('#fullscreen-window').onclick=()=>document.documentElement.requestFullscreen?.();
document.querySelector('#close-window').onclick=()=>window.close();
document.querySelector('#restore-system').onclick=async()=>{const response=await fetch('/api/reset',{method:'POST'});if(response.ok){window.opener?.focus();window.close()}};
