from copy import deepcopy
from pathlib import Path
from pathlib import PurePosixPath
import hashlib
import json
import runpy


_VERSIONS = runpy.run_path(
    str(
        Path(__file__).resolve().parents[2]
        / 'clarify-before-testing/scripts/workflow_versions.py'
    )
)
EXECUTION_SCHEMA_VERSION = _VERSIONS['EXECUTION_SCHEMA_VERSION']
WORKFLOW_VERSION = _VERSIONS['WORKFLOW_VERSION']

def fail(path,msg): raise AssertionError(f'{path}: {msg}')


def _canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')


def task_hash(task):
    payload={key:value for key,value in task.items() if key!='task_hash'}
    return hashlib.sha256(_canonical(payload)).hexdigest()


def seal_task(task):
    task.pop('task_hash',None)
    task['task_hash']=task_hash(task)
    return task


def _validate_automation(case, batch_id, seen_targets):
    cid=case.get('case_id'); main=case.get('primary_execution'); auto=case.get('automation')
    if not isinstance(auto,dict): fail(f'{cid}.automation','required by the v2 Worker Task')
    if main=='人工':
        if set(auto)!={'required'} or type(auto.get('required')) is not bool or auto['required'] is not False:
            fail(f'{cid}.automation','manual Case must set boolean required=false')
        return
    stacks={
        'API':('typescript','vitest','node-native-fetch','scripts/api','.test.ts'),
        'UI':('typescript','playwright-test','playwright-page','scripts/ui','.spec.ts'),
    }
    if main not in stacks: fail(f'{cid}.primary_execution',f'unsupported {main!r}')
    language,runner,driver,prefix,suffix=stacks[main]
    expected={'required':True,'language':language,'runner':runner,'driver':driver,'script_strategy':'create_or_update'}
    if type(auto.get('required')) is not bool: fail(f'{cid}.automation.required','boolean required')
    for key,value in expected.items():
        if auto.get(key)!=value: fail(f'{cid}.automation.{key}',f'must be {value!r}')
    target=auto.get('script_target')
    if not isinstance(target,str) or '\\' in target: fail(f'{cid}.automation.script_target','Run-relative POSIX path required')
    parts=target.split('/'); parsed=PurePosixPath(target)
    if parsed.is_absolute() or any(x in {'','..','.'} for x in parts) or len(parts)!=4 or parts[:3]!=[ *prefix.split('/'), batch_id ] or not parts[3].startswith(cid) or not parts[3].endswith(suffix):
        fail(f'{cid}.automation.script_target','must be a safe scripts/<api|ui>/<Batch>/<Case>*.ts path')
    if target in seen_targets: fail(f'{cid}.automation.script_target',f'duplicate with {seen_targets[target]}')
    seen_targets[target]=cid


def validate(task):
    if not isinstance(task,dict): fail('worker_task','object required')
    if type(task.get('schema_version')) is not int or task['schema_version'] != EXECUTION_SCHEMA_VERSION:
        fail('schema_version',f'worker task requires schema_version={EXECUTION_SCHEMA_VERSION}')
    if task.get('workflow_version') != WORKFLOW_VERSION:
        fail('workflow_version',f'worker task requires workflow_version={WORKFLOW_VERSION}')
    if not isinstance(task.get('task_id'),str) or not task['task_id']:
        fail('task_id','required')
    if task.get('task_hash')!=task_hash(task):
        fail('task_hash','does not match the canonical Worker Task payload')
    if not isinstance(task.get('batch_id'),str) or not task['batch_id']:
        fail('batch_id','non-empty string required')
    order=task.get('case_order')
    cases=task.get('cases')
    if not isinstance(order,list) or not order or any(not isinstance(cid,str) or not cid for cid in order):
        fail('case_order','non-empty Case ID list required')
    if len(order)!=len(set(order)):
        fail('case_order','duplicate Case IDs are forbidden')
    if not isinstance(cases,list) or len(cases)!=len(order) or [c.get('case_id') for c in cases if isinstance(c,dict)]!=order:
        fail('cases','must contain the ordered Case objects exactly once')
    targets={}
    for case in cases:
        if not isinstance(case,dict): fail('cases','object required')
        _validate_automation(case,task['batch_id'],targets)
    return {
        'ok':True,
        'schema_version':EXECUTION_SCHEMA_VERSION,
        'workflow_version':WORKFLOW_VERSION,
    }

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
    task={
        'schema_version':EXECUTION_SCHEMA_VERSION,
        'workflow_version':WORKFLOW_VERSION,
        'batch_id':batch_id,
        'goal':b.get('goal') or b.get('name') or batch_id,
        'case_order':list(b['case_ids']),
        'cases':ordered,
        'project_testing_index_ref':'.test-workflow/PROJECT_TESTING_INDEX.md',
        'source_refs':{c['case_id']:deepcopy(c.get('source_refs',[])) for c in ordered},
        'dependency_context':dependency_context,
        'execution_context_ref':execution_context_ref,
        'data_manifest_ref':data_manifest_ref,
        'evidence_plan':{c['case_id']:deepcopy(c.get('evidence_plan',{})) for c in ordered},
        'allowed_adjustments':['locator','wait_strategy','scroll','popup','non_validation_navigation','browser_recovery','script_bug','supporting_query'],
        'forbidden_adjustments':['primary_execution','expected','case_goal','critical_steps','case_scope','batch_scope','test_data_meaning'],
        'output_paths':{'results':f'{output_root}/{batch_id}','evidence':f'evidence/{batch_id}'},
        'status':'pending'
    }
    task['task_id']=f"{batch_id}-{hashlib.sha256(_canonical(task)).hexdigest()[:12]}"
    seal_task(task)
    validate(task)
    return task
