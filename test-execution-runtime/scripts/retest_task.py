from copy import deepcopy
from batch_task_builder import EXECUTION_SCHEMA_VERSION, WORKFLOW_VERSION, seal_task, task_hash, validate

def build(original_task,retest_case_ids,sequence=1,result_context=None):
    wanted=set(retest_case_ids)
    cases=[deepcopy(c) for c in original_task.get('cases',[]) if c.get('case_id') in wanted]
    found={c['case_id'] for c in cases}
    if found != wanted: raise AssertionError(f'retest_case_ids: unknown cases {sorted(wanted-found)}')
    bid=original_task['batch_id']; result_context=result_context or []
    if isinstance(result_context,list): result_context={r.get('case_id'):r for r in result_context}
    dep_ctx=deepcopy(original_task.get('dependency_context',{}))
    for c in cases:
        for dep in c.get('dependencies',[]) or []:
            if dep in wanted or dep in dep_ctx: continue
            if dep not in result_context: raise AssertionError(f'{c["case_id"]}.dependencies[{dep}]: retest dependency result missing')
            r=result_context[dep]; dep_ctx[dep]={'batch_id':original_task.get('batch_id'),'status':r.get('status'),'final_result':r.get('final_result')}
    task = {
        'schema_version': EXECUTION_SCHEMA_VERSION,
        'workflow_version': WORKFLOW_VERSION,
        'task_id':f'{bid}-retest-{sequence:03d}','batch_id':bid,'retest_of':bid,
        'parent_task_hash':original_task.get('task_hash') or task_hash(original_task),
        'case_order':[cid for cid in original_task['case_order'] if cid in wanted],'cases':cases,'dependency_context':dep_ctx,
        'execution_context_ref':original_task.get('execution_context_ref'),'data_manifest_ref':original_task.get('data_manifest_ref'),
        'evidence_plan':{cid:original_task.get('evidence_plan',{}).get(cid,{}) for cid in wanted},
        'allowed_adjustments':original_task.get('allowed_adjustments',[]),'forbidden_adjustments':original_task.get('forbidden_adjustments',[]),
        'output_paths':original_task.get('output_paths',{}),'status':'pending'
    }
    seal_task(task)
    validate(task)
    return task
