import argparse, json, importlib.util, hashlib
from pathlib import Path
from datetime import datetime, timezone


def fail(path,msg): raise AssertionError(f'{path}: {msg}')
def _load(path,name):
    spec=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
def _load_execution_control(): return _load(Path(__file__).resolve().parents[2]/'test-execution-runtime/scripts/execution_control.py','shared_execution_control')
def _sha256(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def _now(): return datetime.now(timezone.utc).isoformat()

def _dashboard(run_dir,event):
    p=Path(__file__).resolve().parents[2]/'test-execution-runtime/scripts/dashboard_update.py'; m=_load(p,'defect_dashboard_update'); base=Path(run_dir); state=base/'internal/state/run-status.json'; data=base/'dashboard/dashboard-data.json'
    if not event.get('stage'): event['stage']='defect-handling'
    if data.exists(): return m.apply_event_files(state,data,event)
    return None

def _inside(path,root):
    try: path.resolve().relative_to(root.resolve()); return True
    except ValueError: return False

def _run_evidence_file(run_dir,ref,allowed_roots,path):
    base=Path(run_dir).resolve(); p=Path(ref); p=(p if p.is_absolute() else base/p).resolve()
    if not any(_inside(p,r) for r in allowed_roots): fail(path,f'evidence must belong to one of the source Case evidence directories: {p}')
    if not p.exists() or not p.is_file(): fail(path,f'evidence file does not exist: {p}')
    return p

def _load_confirmed_plan(run_dir):
    base=Path(run_dir).resolve(); plan_path=base/'internal/execution/execution-plan.json'; state_path=base/'internal/state/run-status.json'
    if not plan_path.exists(): fail('execution_plan','missing current execution plan')
    if not state_path.exists(): fail('execution_plan','run-status.json missing')
    state=json.loads(state_path.read_text(encoding='utf-8')); binding=state.get('confirmation_bindings',{}).get('execution-plan')
    if not binding: fail('execution_plan','execution plan is not user-confirmed/bound')
    if Path(binding.get('contract_path','')).resolve()!=plan_path.resolve() or _sha256(plan_path)!=binding.get('contract_sha256'):
        fail('execution_plan','confirmed execution plan changed or binding does not match')
    plan=json.loads(plan_path.read_text(encoding='utf-8'))
    return plan_path,plan

def validate(v):
    for k in ['defect_id','source_cases','source_batch','reviewer_confirmed','duplicate_check','root_cause_group','payload','self_review','submission']:
        if k not in v: fail(k,'required')
    if not v['source_cases']: fail('source_cases','non-empty required')
    if not v['source_batch']: fail('source_batch','required')
    if v['reviewer_confirmed'] is not True: fail('reviewer_confirmed','must be true before formal bug handling')
    dc=v['duplicate_check']
    if dc.get('performed') is not True: fail('duplicate_check.performed','must be true')
    if dc.get('result') not in {'new','existing'}: fail('duplicate_check.result','new|existing required')
    if dc['result']=='existing' and not dc.get('existing_bug_ref'): fail('duplicate_check.existing_bug_ref','required for existing bug')
    payload=v['payload']; req=['title','project','module','developer','severity','environment','preconditions','steps','actual','expected','reproduction_rate','evidence_refs']
    for k in req:
        if k not in payload or payload[k] in (None,'',[]): fail(f'payload.{k}','required')
    if v['self_review'].get('status')!='passed': fail('self_review.status','must be passed before submission')
    sub=v['submission']
    if sub.get('status') not in {'submitted','failed','not_submitted_existing'}: fail('submission.status','invalid')
    if dc['result']=='new':
        if sub.get('status')=='not_submitted_existing': fail('submission.status','new bug cannot use not_submitted_existing')
        if sub.get('status')=='submitted' and not sub.get('bug_ref'): fail('submission.bug_ref','required after submitted')
    else:
        if sub.get('status')!='not_submitted_existing': fail('submission.status','existing bug must use not_submitted_existing')
        if sub.get('bug_ref')!=dc.get('existing_bug_ref'): fail('submission.bug_ref','must equal existing_bug_ref')
    return {'ok':True,'defect_id':v['defect_id'],'bug_ref':dc.get('existing_bug_ref') or sub.get('bug_ref')}

def _baseline_case_map(plan):
    rows={c.get('case_id'):c for c in plan.get('cases',[])}
    if None in rows: fail('execution_plan.cases','case_id required')
    return rows

def validate_reg(v,baseline_plan,evidence_root=None):
    for k in ['regression_id','bug_ref','original_case_ids','impact_case_ids','worker_is_new','cases','status']:
        if k not in v: fail(k,'required')
    if not v['original_case_ids']: fail('original_case_ids','non-empty required')
    if v['worker_is_new'] is not True: fail('worker_is_new','must be true')
    cases=v['cases']
    if not isinstance(cases,list) or not cases: fail('cases','regression task cases required')
    ids=[c.get('case_id') for c in cases]
    if any(not x for x in ids) or len(ids)!=len(set(ids)): fail('cases','unique case_ids required')
    required_ids=set(v['original_case_ids'])|set(v.get('impact_case_ids',[]))
    if set(ids)!=required_ids: fail('cases',f'must equal original + impact scope; missing={sorted(required_ids-set(ids))}, extra={sorted(set(ids)-required_ids)}')
    baseline=_baseline_case_map(baseline_plan)
    unknown=required_ids-set(baseline)
    if unknown: fail('cases',f'regression scope must come from confirmed execution plan: {sorted(unknown)}')
    # Regression is not allowed to redefine the original Case or primary execution method.
    for c in cases:
        cid=c['case_id']; base=baseline[cid]
        if 'primary_execution' in c and c.get('primary_execution')!=base.get('primary_execution'):
            fail(f'cases[{cid}].primary_execution',f'must preserve original Planning method {base.get("primary_execution")}')
        for field in ['steps','expected_results','target_action']:
            if field in c and c.get(field)!=base.get(field): fail(f'cases[{cid}].{field}','Regression cannot change the confirmed/planned Case')
    if v['status']=='completed':
        results=v.get('results')
        if not isinstance(results,list) or not results: fail('results','completed regression requires real results')
        rids=[r.get('case_id') for r in results]
        if len(rids)!=len(set(rids)) or set(rids)!=required_ids: fail('results','must match regression scope exactly')
        ctl=_load_execution_control(); result_by={r['case_id']:r for r in results}
        for cid in required_ids: ctl.validate(baseline[cid],result_by[cid],evidence_root=evidence_root)
        failed_scope=sorted(cid for cid in required_ids if result_by[cid].get('status')!='PASS'); passed=not failed_scope
    else:
        failed_scope=[]; passed=False
    return {'ok':True,'regression_id':v['regression_id'],'regression_passed':passed,'failed_scope_case_ids':failed_scope}

CASE_LEDGER_REL='internal/execution/results/case-results-ledger.json'
def _load_ledger(run_dir):
    path=Path(run_dir)/CASE_LEDGER_REL
    if not path.exists(): fail('case_result_ledger',f'missing {CASE_LEDGER_REL}')
    return path,json.loads(path.read_text(encoding='utf-8'))
def _write_ledger(path,ledger):
    tmp=path.with_suffix(path.suffix+'.tmp'); tmp.write_text(json.dumps(ledger,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); tmp.replace(path)

def apply_defect_to_ledger(run_dir,v):
    out=validate(v); bug=out['bug_ref']; path,ledger=_load_ledger(run_dir); rows=ledger.setdefault('cases',{})
    roots=[]
    for cid in v['source_cases']:
        if cid not in rows: fail(f'case_result_ledger.{cid}','defect source case is not initialized in ledger')
        item=rows[cid]
        if item.get('reviewer_confirmed') is not True or (item.get('final_result') or item.get('status'))!='FAIL':
            fail(f'case_result_ledger.{cid}','formal defect source must be a reviewer-confirmed FAIL')
        if item.get('batch_id')!=v['source_batch']: fail(f'case_result_ledger.{cid}.batch_id','does not match defect source_batch')
        if not isinstance(item.get('runtime_result'),dict) or item['runtime_result'].get('status')!='FAIL': fail(f'case_result_ledger.{cid}.runtime_result','real initial FAIL runtime result required')
        roots.append((Path(run_dir)/'evidence'/v['source_batch']/cid).resolve())
    for ref in v['payload'].get('evidence_refs',[]): _run_evidence_file(run_dir,ref,roots,'payload.evidence_refs')
    ts=_now()
    for cid in v['source_cases']:
        rows[cid]['bug_ref']=bug; rows[cid]['defect_id']=v['defect_id']; rows[cid]['updated_at']=ts
    ledger['updated_at']=ts; _write_ledger(path,ledger)
    _dashboard(run_dir,{'type':'bug_submitted','batch_id':v['source_batch'],'bug_ref':bug,'case_ids':v['source_cases'],'blocked_case_ids':v.get('blocked_case_ids',[]),'stage':'defect-handling'})
    return {'ok':True,'defect_id':v['defect_id'],'bug_ref':bug,'updated_case_ids':v['source_cases']}

def apply_regression_to_ledger(run_dir,v):
    _,plan=_load_confirmed_plan(run_dir)
    out=validate_reg(v,baseline_plan=plan,evidence_root=run_dir)
    if out.get('regression_passed') is not True: fail('regression_passed',f'regression task scope not fully passed: {out.get("failed_scope_case_ids",[])}')
    path,ledger=_load_ledger(run_dir); rows=ledger.setdefault('cases',{}); result_by={r['case_id']:r for r in v['results']}; original=set(v['original_case_ids']); impact=set(v.get('impact_case_ids',[])); ts=_now()
    # Historical FAIL and Bug link are facts from Runtime/Defect; Regression cannot manufacture them.
    for cid in original:
        if cid not in rows: fail(f'case_result_ledger.{cid}','case is not initialized in ledger')
        item=rows[cid]
        if item.get('reviewer_confirmed') is not True: fail(f'case_result_ledger.{cid}','original failed Case is not reviewer-confirmed')
        if item.get('initial_result')!='FAIL' or not isinstance(item.get('runtime_result'),dict) or item['runtime_result'].get('status')!='FAIL':
            fail(f'case_result_ledger.{cid}.initial_result','Regression requires a real preserved initial FAIL; it cannot create one')
        if item.get('bug_ref')!=v['bug_ref'] and item.get('existing_bug_ref')!=v['bug_ref']:
            fail(f'case_result_ledger.{cid}.bug_ref','Regression bug_ref must match the Bug already linked to the original FAIL')
        if (item.get('final_result') or item.get('status'))!='FAIL': fail(f'case_result_ledger.{cid}.final_result','original Case must still be FAIL before successful regression')
    for cid in impact:
        if cid not in rows: fail(f'case_result_ledger.{cid}','impact Case must already exist in the global Case ledger')
    source_batches=set();
    for cid in original|impact:
        item=rows[cid]; source_batches.add(item.get('batch_id'))
        hist=item.setdefault('regression_history',[]); hist.append({'regression_id':v['regression_id'],'bug_ref':v['bug_ref'],'result':result_by[cid],'at':ts,'scope':'original' if cid in original else 'impact'})
        item['regression_id']=v['regression_id']; item['regression_result']=result_by[cid]; item['reviewer_confirmed']=True; item['updated_at']=ts
        if cid in original:
            item['status']='PASS_AFTER_FIX'; item['final_result']='PASS_AFTER_FIX'; item['source']='regression_passed'
            dash_status='PASS_AFTER_FIX'
        else:
            # Preserve the original runtime_result/history; only final state changes after impact regression.
            item['status']='PASS'; item['final_result']='PASS'; item['source']='regression_impact_passed'
            dash_status='PASS'
        _dashboard(run_dir,{'type':'case_finished','batch_id':item.get('batch_id'),'case_id':cid,'status':dash_status,'actual_execution':result_by[cid].get('actual_execution'),'stage':'defect-handling'})
    ledger['updated_at']=ts; _write_ledger(path,ledger)
    _dashboard(run_dir,{'type':'regression_finished','bug_ref':v['bug_ref'],'status':'PASS','source_batch_ids':sorted(x for x in source_batches if x),'case_ids':sorted(original|impact),'stage':'defect-handling'})
    return {'ok':True,'regression_id':v['regression_id'],'updated_case_ids':sorted(original|impact)}


if __name__=='__main__':
    a=argparse.ArgumentParser(); a.add_argument('--input',required=True); a.add_argument('--type',choices=['bug','regression'],default='bug'); a.add_argument('--apply-run-dir'); a.add_argument('--execution-plan'); x=a.parse_args(); v=json.loads(Path(x.input).read_text(encoding='utf-8'))
    if x.type=='bug': out=apply_defect_to_ledger(x.apply_run_dir,v) if x.apply_run_dir else validate(v)
    else:
        if x.apply_run_dir: out=apply_regression_to_ledger(x.apply_run_dir,v)
        else:
            if not x.execution_plan: fail('execution_plan','standalone regression validation requires --execution-plan')
            out=validate_reg(v,json.loads(Path(x.execution_plan).read_text(encoding='utf-8')),evidence_root=Path(x.execution_plan).resolve().parents[2] if x.execution_plan else None)
    print(json.dumps(out,ensure_ascii=False))
