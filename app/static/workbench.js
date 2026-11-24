import {request} from './client.js';
import {snapshot, history, responsibility} from './view.js';
import {visualize} from './plots.js';

const form = document.querySelector('#source');
const file = document.querySelector('#file');
const profile = document.querySelector('#profile');
const operator = document.querySelector('#operator');
const status = document.querySelector('#notice');
const detail = document.querySelector('#review');
const evidence = document.querySelector('#evidence');
const stages = [...document.querySelectorAll('[data-stage]')];
let stage = 'balance';
let report, selected, batch, running = false;

operator.value = localStorage.getItem('operator') || '';

function me() {
  return operator.value.trim();
}

function source() {
  const data = new FormData();
  data.append('actor',me());
  if (file.files.length) data.append('file',file.files[0]);
  else data.append('sample',profile.value);
  return data;
}

function announce(text, failure = false) {
  status.textContent = text;
  status.dataset.failure = String(failure);
}

function draw() {
  if (!report) return;
  snapshot(report, selected, stage);
  visualize(report, selected);
  for (const button of stages) button.setAttribute('aria-pressed',String(button.dataset.stage===stage));
  document.querySelector('#panel-title').textContent = stages.find(button => button.dataset.stage===stage)?.textContent || '运行对账';
  detail.hidden = !batch;
  if (batch) {
    const mine = me() !== '' && batch.owner === me();
    const finalized = batch.status === 'APPROVED';
    document.querySelector('#run-status').textContent = `${batch.id.slice(0,10)} · ${batch.status} · r${batch.revision}`;
    responsibility(batch, report);
    document.querySelector('#claim').hidden = mine || finalized;
    document.querySelector('#release').hidden = !mine || finalized;
    detail.elements.note.disabled = !mine;
    detail.querySelector('[value="APPROVED"]').disabled = !mine || !report.balance.releasable || finalized;
    detail.querySelector('[value="HELD"]').disabled = !mine || finalized;
    evidence.href = `/api/runs/${batch.id}/evidence`;
  }
}

function show(payload, committed = false) {
  batch = committed ? payload : null;
  report = committed ? payload.report : payload;
  detail.elements.note.value = batch?.note || '';
  selected = report.cases?.[0]?.case;
  draw();
}

async function refresh() {
  const data = await request('/api/runs');
  history(data.items, batch?.id);
}

async function perform(action) {
  if (running) return;
  running = true;
  document.body.setAttribute('aria-busy','true');
  announce('处理中…');
  try { await action(); }
  catch (error) { announce(error.message,true); }
  finally { running = false; document.body.removeAttribute('aria-busy'); }
}

function preview(next) {
  return perform(async () => {
    const payload = await request(`/api/stages/${next}`,{method:'POST',body:source()});
    stage = next;
    show(payload);
    announce('阶段预览已更新');
    await refresh();
  });
}

stages.forEach(button => button.addEventListener('click',()=>preview(button.dataset.stage)));
form.addEventListener('submit', event => {
  event.preventDefault();
  perform(async () => {
    const result = await request('/api/runs',{method:'POST',body:source()});
    stage = 'balance'; show(result,true);
    announce('批次已保存'); await refresh();
  });
});
const filename = document.querySelector('#file-name');
profile.addEventListener('change',()=>{file.value=''; filename.textContent=''; preview(stage);});
file.addEventListener('change',()=>{filename.textContent=file.files[0]?.name || ''; preview(stage);});
operator.addEventListener('input',()=>{localStorage.setItem('operator',me()); draw();});
document.querySelector('#rows').addEventListener('click',event=>{
  const button = event.target.closest('[data-case]');
  if (button) { selected = button.dataset.case; draw(); document.querySelector(`[data-case="${CSS.escape(selected)}"]`).focus(); }
});
document.querySelector('#history').addEventListener('click',event=>{
  const button = event.target.closest('[data-run]');
  if (button) perform(async()=>{
    const result = await request(`/api/runs/${button.dataset.run}`);
    stage='balance'; show(result,true); announce('已载入历史批次'); await refresh();
  });
});
document.querySelector('#claim').addEventListener('click',()=>{
  if (!batch) return;
  perform(async()=>{
    const result = await request(`/api/runs/${batch.id}/claim`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({actor:me()})});
    show(result,true); announce('已接办，成为当前责任人'); await refresh();
  });
});
document.querySelector('#release').addEventListener('click',()=>{
  if (!batch) return;
  perform(async()=>{
    const result = await request(`/api/runs/${batch.id}/release`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({actor:me()})});
    show(result,true); announce('已交回批次'); await refresh();
  });
});
detail.addEventListener('submit',event=>{
  event.preventDefault();
  perform(async()=>{
    const payload={status:event.submitter.value,revision:batch.revision,note:detail.elements.note.value,actor:me()};
    const result=await request(`/api/runs/${batch.id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    show(result,true); announce(result.status==='APPROVED'?'批次已签发':'批次已暂缓'); await refresh();
  });
});
preview(stage);
