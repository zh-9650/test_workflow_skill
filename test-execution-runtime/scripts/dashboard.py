from pathlib import Path
import argparse

HTML='''<!doctype html>
<html><head><meta charset="utf-8"><title>Test Run Dashboard</title>
<style>
body{font-family:Arial,sans-serif;max-width:1200px;margin:24px auto;padding:0 18px}.cards{display:flex;gap:10px;flex-wrap:wrap}.card{border:1px solid #ddd;border-radius:10px;padding:12px 16px;min-width:125px}table{border-collapse:collapse;width:100%;margin:8px 0}td,th{border:1px solid #ddd;padding:8px;text-align:left}.muted{color:#666}pre{white-space:pre-wrap;background:#f6f6f6;padding:10px;border-radius:8px}.ok{font-weight:700}
</style></head><body>
<h1>测试执行进度</h1><div id="summary" class="cards"></div>
<p id="current"></p><p class="muted" id="updated"></p>
<h2>Batch 进度</h2><div id="batches"></div>
<h2>Case 脚本与证据</h2><div id="cases"></div>
<h2>核心流程</h2><div id="core"></div>
<h2>规划执行方式 vs 实际执行方式</h2><div id="methods"></div>
<h2>录屏状态</h2><div id="recordings"></div>
<h2>BLOCKED 原因</h2><pre id="blocked"></pre>
<h2>缺陷</h2><pre id="defects"></pre>
<h2>Reviewer</h2><pre id="review"></pre>
<h2>最近动态</h2><ul id="recent"></ul>
<script>
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function table(headers,rows){return `<table><thead><tr>${headers.map(x=>`<th>${esc(x)}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr>${r.map(x=>`<td>${esc(x)}</td>`).join('')}</tr>`).join('')}</tbody></table>`}
function render(d){
 const done=d.metrics?.completed_cases||0,total=d.metrics?.total_cases||0;
 const bd=d.metrics?.completed_batches||0,bt=d.metrics?.total_batches||0;
 document.getElementById('summary').innerHTML=`<div class="card"><b>Case 完成率</b><br>${done}/${total} (${total?Math.round(done*100/total):0}%)</div><div class="card"><b>Batch</b><br>${bd}/${bt}</div><div class="card"><b>PASS</b><br>${d.metrics?.PASS||0}</div><div class="card"><b>FAIL</b><br>${d.metrics?.FAIL||0}</div><div class="card"><b>BLOCKED</b><br>${d.metrics?.BLOCKED||0}</div>`;
 document.getElementById('current').innerHTML=`当前 Stage: <b>${esc(d.current_stage||'-')}</b> ｜ Batch: <b>${esc(d.current_batch||'-')}</b> ｜ Case: <b>${esc(d.current_case||'-')}</b> ｜ Worker: <b>${esc(d.current_worker||'-')}</b> ｜ Reviewer: <b>${esc(d.current_reviewer||'-')}</b> ｜ 动作: <b>${esc(d.current_action||'-')}</b>`;
 document.getElementById('updated').textContent='Last Updated: '+(d.last_updated||'-');
 document.getElementById('batches').innerHTML=table(['Batch','名称','状态','已处理/总数','Worker session / 回执 / 结果','Reviewer session / 回执 / 结果'],(d.batches||[]).map(b=>[b.id,b.name||'',b.status,`${b.done||0}/${b.total||0}`,`${b.worker_session_id||'-'} / ${b.worker_receipt_status||'-'} / ${b.worker_result_status?.overall||'-'}`,`${b.reviewer_session_id||'-'} / ${b.reviewer_receipt_status||'-'} / ${b.reviewer_result_status||'-'}`]));
 document.getElementById('cases').innerHTML=table(['Case','Batch','状态','runner','脚本状态 / Hash','正式运行','证据数','录屏'],(d.cases||[]).map(c=>[c.id,c.batch_id,c.status,c.runner||c.planned_execution,`${c.script_status||'-'} / ${c.script_sha256||'-'}`,c.official_run_status||'-',c.evidence_count||0,c.recording_status||'not_required']));
 document.getElementById('core').innerHTML=table(['流程','名称','状态','进度'],(d.core_flows||[]).map(f=>[f.id||'',f.name||'',f.status||'',`${f.done||0}/${f.total||0}`]));
 const pm=d.metrics?.planned_execution||{}, am=d.metrics?.actual_execution||{};
 document.getElementById('methods').innerHTML=table(['方式','规划','实际已完成'],['UI','API','人工'].map(k=>[k,pm[k]||0,am[k]||0]));
 document.getElementById('recordings').innerHTML=table(['范围','类型','状态'],Object.entries(d.recordings||{}).map(([k,v])=>[k,v?.scope||'',v?.status||v||'']));
 document.getElementById('blocked').textContent=JSON.stringify(d.blocked_reason_stats||{},null,2);
 document.getElementById('defects').textContent=JSON.stringify(d.defects||[],null,2);
 document.getElementById('review').textContent=JSON.stringify(d.reviewer_status||{},null,2);
 document.getElementById('recent').innerHTML=(d.recent||[]).slice(0,20).map(x=>`<li>${esc(x.at)} ${esc(x.type)} ${esc(x.batch_id||'')} ${esc(x.case_id||'')}</li>`).join('');
}
async function refresh(){try{const r=await fetch('./dashboard-data.json?ts='+Date.now(),{cache:'no-store'}); if(!r.ok) throw new Error(r.status); render(await r.json());}catch(e){document.getElementById('updated').textContent='Dashboard 数据读取失败: '+e;}}
refresh(); setInterval(refresh,3000);
</script></body></html>'''

def render_shell(): return HTML

def write_dashboard(output):
    p=Path(output); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(HTML,encoding='utf-8'); return p

if __name__=='__main__':
    a=argparse.ArgumentParser(); a.add_argument('--output',required=True); x=a.parse_args(); print(write_dashboard(x.output))
