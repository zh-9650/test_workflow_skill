from copy import deepcopy

def fail(path,msg): raise AssertionError(f'{path}: {msg}')

def _status_of(v):
    if isinstance(v,dict): return v.get('final_result') or v.get('status')
    return None

def build(plan,batch_id,execution_context_ref,data_manifest_ref,output_root='internal/execution/results',case_result_ledger=None):
    batches={b['id']:b for b in plan.get('batches',[])}
    cases={c['case_id']:c for c in plan.get('cases',[])}
    if batch_id not in batches: fail('batch_id',f'unknown {batch_id}')
    b=batches[batch_id]; local_ids=set(b.get('case_ids',[])); case_result_ledger=case_result_ledger or {}
    ordered=[]; dependency_context={}
    for cid in b['case_ids']:
        if cid not in cases: fail(f'{batch_id}.case_ids',f'unknown case {cid}')
        c=deepcopy(cases[cid]); ordered.append(c)
        for dep in c.get('dependencies',[]) or []:
            if dep in local_ids: continue
            if dep not in cases: fail(f'{cid}.dependencies',f'unknown dependency {dep}')
            if dep not in case_result_ledger: fail(f'{cid}.dependencies[{dep}]','cross-batch dependency final result is missing from case result ledger')
            item=case_result_ledger[dep]
            if isinstance(item,dict) and item.get('reviewer_confirmed') is False:
                fail(f'{cid}.dependencies[{dep}]','upstream result is not reviewer-confirmed')
            st=_status_of(item)
            if st not in {'PASS','FAIL','BLOCKED','PASS_AFTER_FIX'}:
                fail(f'{cid}.dependencies[{dep}].status',f'non-final upstream status {st!r}')
            dependency_context[dep]={
                'batch_id':cases[dep].get('batch_id'),
                'status':item.get('status') if isinstance(item,dict) else None,
                'final_result':item.get('final_result') if isinstance(item,dict) else None,
                'reviewer_confirmed':item.get('reviewer_confirmed') if isinstance(item,dict) else None,
            }
    return {
        'batch_id':batch_id,
        'goal':b.get('goal') or b.get('name') or batch_id,
        'case_order':list(b['case_ids']),
        'cases':ordered,
        'dependency_context':dependency_context,
        'execution_context_ref':execution_context_ref,
        'data_manifest_ref':data_manifest_ref,
        'evidence_plan':{c['case_id']:deepcopy(c.get('evidence_plan',{})) for c in ordered},
        'allowed_adjustments':['locator','wait_strategy','scroll','popup','non_validation_navigation','browser_recovery','script_bug','supporting_query'],
        'forbidden_adjustments':['primary_execution','expected','case_goal','critical_steps','case_scope','batch_scope','test_data_meaning'],
        'output_paths':{'results':f'{output_root}/{batch_id}','evidence':f'evidence/{batch_id}'},
        'status':'pending'
    }
