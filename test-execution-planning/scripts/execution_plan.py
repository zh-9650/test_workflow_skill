import argparse, hashlib, importlib.util, json, runpy
from pathlib import Path
import re
from pathlib import PurePosixPath

EXECUTION_SCHEMA_VERSION = runpy.run_path(
    str(Path(__file__).resolve().parents[2] / 'clarify-before-testing/scripts/workflow_versions.py')
)['EXECUTION_SCHEMA_VERSION']

MAIN={'UI','API','人工'}
AUX={'UI','API','数据库只读','Network','日志','文件','其他系统'}
AUTOMATION_STACKS={
    'API': {'language':'typescript','runner':'vitest','driver':'node-native-fetch','prefix':'scripts/api/','suffix':'.test.ts'},
    'UI': {'language':'typescript','runner':'playwright-test','driver':'playwright-page','prefix':'scripts/ui/','suffix':'.spec.ts'},
}
IMMUTABLE_CASE_FIELDS=('title','steps','expected_results','target_action','test_point_ids','preconditions','test_data','complex_flow','intermediate_assertions')


def fail(path,msg): raise AssertionError(f'{path}: {msg}')
def sha256(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def _canon(v): return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def _validate_evidence_items(cid, field, items, expected_ids):
    if not isinstance(items,list): fail(f'{cid}.evidence_plan.{field}','list required')
    for i,item in enumerate(items):
        p=f'{cid}.evidence_plan.{field}[{i}]'
        if not isinstance(item,dict): fail(p,'evidence object with kind and expected_ids required')
        if not isinstance(item.get('kind'),str) or not item['kind'].strip(): fail(p+'.kind','non-empty kind required')
        if field=='screenshots' and item['kind']!='screenshot': fail(p+'.kind','screenshots entries must use kind=screenshot')
        ids=item.get('expected_ids')
        if not isinstance(ids,list) or not ids or any(not isinstance(x,str) for x in ids): fail(p+'.expected_ids','non-empty Expected ID list required')
        if len(ids)!=len(set(ids)) or not set(ids)<=expected_ids: fail(p+'.expected_ids','must uniquely reference Expected IDs in this Case')
        if field=='api' and item['kind']=='request_response' and item.get('redacted') is not True:
            fail(p+'.redacted','request/response evidence must be explicitly redacted')


def _validate_automation(c, main, batch_id, script_targets):
    cid=c['case_id']; auto=c.get('automation')
    if not isinstance(auto,dict): fail(f'{cid}.automation','required object')
    if main=='人工':
        if set(auto)!={'required'} or type(auto.get('required')) is not bool or auto['required'] is not False:
            fail(f'{cid}.automation','manual Case requires only boolean required=false')
        manual=c.get('manual_execution')
        if not isinstance(manual,dict) or not isinstance(manual.get('reason'),str) or not manual['reason'].strip(): fail(f'{cid}.manual_execution.reason','manual reason required')
        if not isinstance(manual.get('steps'),list) or not manual['steps'] or any(not isinstance(x,str) or not x.strip() for x in manual['steps']): fail(f'{cid}.manual_execution.steps','non-empty explicit steps required')
        if not isinstance(manual.get('result_entry'),str) or not manual['result_entry'].strip(): fail(f'{cid}.manual_execution.result_entry','result entry method required')
        if 'script_target' in auto: fail(f'{cid}.automation.script_target','manual Case cannot have script_target')
        return
    expected=AUTOMATION_STACKS[main]
    required={'required':True,'language':expected['language'],'runner':expected['runner'],'driver':expected['driver'],'script_strategy':'create_or_update'}
    for key,value in required.items():
        if key=='required' and type(auto.get(key)) is not bool:
            fail(f'{cid}.automation.required','must be a boolean')
        if auto.get(key)!=value: fail(f'{cid}.automation.{key}',f'must be {value!r} for {main}')
    target=auto.get('script_target')
    if not isinstance(target,str) or not target or '\\' in target: fail(f'{cid}.automation.script_target','safe Run-relative POSIX path required')
    path=PurePosixPath(target)
    if path.is_absolute() or any(part in {'','..','.'} for part in target.split('/')) or re.match(r'^[A-Za-z]:',target): fail(f'{cid}.automation.script_target','absolute paths and traversal are forbidden')
    parts=target.split('/')
    if len(parts)!=4 or '/'.join(parts[:2])!=expected['prefix'].rstrip('/') or parts[2]!=batch_id or not parts[3].startswith(cid) or not parts[3].endswith(expected['suffix']):
        fail(f'{cid}.automation.script_target',f'must be {expected["prefix"]}{batch_id}/{cid}*{expected["suffix"]}')
    if target in script_targets: fail(f'{cid}.automation.script_target',f'duplicate target already assigned to {script_targets[target]}')
    script_targets[target]=cid


def _validate_jev_policy(c, main, exp_ids):
    import math
    cid = c['case_id']
    jev = c.get('jev_policy')
    if not isinstance(jev, dict):
        fail(f'{cid}.jev_policy', 'explicit jev_policy object (required|conditional|none) is required')
    mode = jev.get('mode')
    if mode not in {'required', 'conditional', 'none'}:
        fail(f'{cid}.jev_policy.mode', 'must be required, conditional, or none')
    if mode == 'none':
        return
    if main == '人工':
        fail(f'{cid}.jev_policy', 'manual Case cannot plan Jev invocation')
    tt = jev.get('target_type')
    if main == 'UI' and tt != 'ui_candidate_selection':
        fail(f'{cid}.jev_policy.target_type', 'UI Case must use target_type=ui_candidate_selection')
    if main == 'API' and tt != 'api_semantic_judgment':
        fail(f'{cid}.jev_policy.target_type', 'API Case must use target_type=api_semantic_judgment')
    purpose = jev.get('purpose')
    if not isinstance(purpose, str) or not purpose.strip():
        fail(f'{cid}.jev_policy.purpose', 'non-empty purpose is required')
    trigger = jev.get('trigger_condition')
    if not isinstance(trigger, str) or not trigger.strip():
        fail(f'{cid}.jev_policy.trigger_condition', 'non-empty trigger_condition is required')
    options = jev.get('bounded_options')
    if not isinstance(options, list) or not 2 <= len(options) <= 255 or any(not isinstance(x, str) or not x.strip() for x in options) or len(set(options)) != len(options):
        fail(f'{cid}.jev_policy.bounded_options', '2..255 unique non-empty string options required')
    fallback = jev.get('failure_fallback')
    if not isinstance(fallback, str) or not fallback.strip():
        fail(f'{cid}.jev_policy.failure_fallback', 'failure_fallback is required')
    if 'switch_provider' in fallback.lower() or 'laya' in fallback.lower():
        fail(f'{cid}.jev_policy.failure_fallback', 'switching provider is forbidden')
    for key in ('max_cost_usd','max_cost_per_call_usd'):
        value=jev.get(key)
        if type(value) not in (int,float) or not math.isfinite(value) or value<=0:
            fail(f'{cid}.jev_policy.{key}',f'{key} must be a positive number')
    if jev['max_cost_per_call_usd']>jev['max_cost_usd']:
        fail(f'{cid}.jev_policy.max_cost_per_call_usd','cannot exceed max_cost_usd')
    for key in ('max_calls','max_input_chars'):
        value=jev.get(key)
        if type(value) is not int or value<=0:
            fail(f'{cid}.jev_policy.{key}',f'{key} must be a positive integer')
    if jev.get('provider')!='typesafe-official':
        fail(f'{cid}.jev_policy.provider','must be typesafe-official')
    for key in ('model','model_version'):
        if not isinstance(jev.get(key),str) or not jev[key].strip():
            fail(f'{cid}.jev_policy.{key}',f'non-empty {key} required')
    if jev['model']!=f'jev-{jev["model_version"]}':
        fail(f'{cid}.jev_policy.model','must match pinned official model_version as jev-<version>')
    required_evidence=jev.get('required_evidence')
    expected_evidence={'request','response','usage','reviewer_independent_judgment'}
    if main=='API': expected_evidence.add('source_response')
    else: expected_evidence.update({'candidate_snapshot','post_selection_revalidation'})
    if not isinstance(required_evidence,list) or set(required_evidence)!=expected_evidence or len(required_evidence)!=len(expected_evidence):
        fail(f'{cid}.jev_policy.required_evidence',f'must contain exactly {sorted(expected_evidence)}')
    e_ids = jev.get('expected_ids', [])
    if not isinstance(e_ids, list) or not e_ids or any(eid not in exp_ids for eid in e_ids):
        fail(f'{cid}.jev_policy.expected_ids', 'must map to valid Expected IDs in this Case')


def _validate_run_context(plan, cases, require_context=False):
    env = plan.get('target_environment')
    if env is None and require_context:
        fail('target_environment', 'target_environment object required in Execution Plan')
    if env is not None:
        if not isinstance(env, dict):
            fail('target_environment', 'object required')
        if not isinstance(env.get('env_id'), str) or not env['env_id'].strip():
            fail('target_environment.env_id', 'non-empty env_id required')
        if not isinstance(env.get('initial_deployment_version'), str) or not env['initial_deployment_version'].strip():
            fail('target_environment.initial_deployment_version', 'initial_deployment_version required')
        if any(c.get('primary_execution') == 'API' for c in cases):
            url = env.get('api_base_url')
            if not isinstance(url, str) or not url.startswith(('http://', 'https://')):
                fail('target_environment.api_base_url', 'valid HTTP(S) URL required for API execution')
        if any(c.get('primary_execution') == 'UI' for c in cases):
            url = env.get('web_base_url')
            if not isinstance(url, str) or not url.startswith(('http://', 'https://')):
                fail('target_environment.web_base_url', 'valid HTTP(S) URL required for UI execution')

    dp = plan.get('defect_platform')
    if dp is None and require_context:
        fail('defect_platform', 'defect_platform object required in Execution Plan')
    if dp is not None:
        if not isinstance(dp, dict):
            fail('defect_platform', 'object required')
        if not isinstance(dp.get('platform_type'), str) or not dp['platform_type'].strip():
            fail('defect_platform.platform_type', 'platform_type required')
        if not isinstance(dp.get('project_key') or dp.get('project_id'), str):
            fail('defect_platform.project_key', 'project_key or project_id required')
        cred = dp.get('credential_ref', '')
        if isinstance(cred, str) and any(bad in cred.lower() for bad in ('password123', 'secret123', 'admin123')):
            fail('defect_platform.credential_ref', 'must be a reference, not a plain secret value')

    dr = plan.get('data_requirements')
    if not isinstance(dr,list) or not dr:
        fail('data_requirements','non-empty list required; every Case must declare prerequisite or runtime-generated data')
    case_ids = {c['case_id'] for c in cases}
    mapped=set()
    timing_by_scope={'base_resource':'before_run','batch_dedicated':'before_batch','runtime_generated':'runtime'}
    isolation_values={'project','run','batch','case'}
    for i, item in enumerate(dr):
        p = f'data_requirements[{i}]'
        if not isinstance(item, dict): fail(p, 'object required')
        scope=item.get('scope')
        if scope not in timing_by_scope:
            fail(p + '.scope', 'must be base_resource, batch_dedicated, or runtime_generated')
        if not isinstance(item.get('object_type'), str) or not item['object_type'].strip():
            fail(p + '.object_type', 'non-empty object_type required')
        cids = item.get('case_ids', [])
        if not isinstance(cids, list) or not cids or any(cid not in case_ids for cid in cids):
            fail(p + '.case_ids', 'non-empty list mapping only to cases in this plan required')
        if not isinstance(item.get('actor_role'),str) or not item['actor_role'].strip(): fail(p+'.actor_role','non-empty actor_role required')
        perms=item.get('permission_requirements')
        if not isinstance(perms,list) or any(not isinstance(x,str) or not x.strip() for x in perms): fail(p+'.permission_requirements','list of permission names required')
        if item.get('creation_timing')!=timing_by_scope[scope]: fail(p+'.creation_timing',f'must be {timing_by_scope[scope]} for {scope}')
        if item.get('isolation_scope') not in isolation_values: fail(p+'.isolation_scope',f'must be one of {sorted(isolation_values)}')
        if not isinstance(item.get('source'),str) or not item['source'].strip(): fail(p+'.source','non-empty source required')
        mapped.update(cids)
    if mapped!=case_ids: fail('data_requirements.case_ids',f'every Case must be covered; missing={sorted(case_ids-mapped)}')


def _confirmed_case_map(confirmed_cases):
    cases=confirmed_cases.get('cases',[]) if isinstance(confirmed_cases,dict) else []
    ids=[c.get('case_id') for c in cases]
    if not ids or any(not x for x in ids) or len(ids)!=len(set(ids)): fail('confirmed_cases','confirmed test-case payload must contain unique case_ids')
    return {c['case_id']:c for c in cases}


def _assert_case_source(plan_case,confirmed):
    cid=plan_case['case_id']
    for field in IMMUTABLE_CASE_FIELDS:
        if field in plan_case and _canon(plan_case.get(field)) != _canon(confirmed.get(field)):
            fail(f'{cid}.{field}',f'Planning cannot modify confirmed Case field {field}')
    # These are required in the plan because Runtime task needs them, but must be exact copies.
    for field in ('title','steps','expected_results','target_action','preconditions','test_data'):
        if field not in plan_case: fail(f'{cid}.{field}','must carry the exact confirmed Case value into Runtime planning')
        if _canon(plan_case[field]) != _canon(confirmed.get(field)):
            fail(f'{cid}.{field}','must exactly equal the confirmed Case')


def validate(plan,require_confirmed=True,confirmed_cases=None,confirmed_cases_sha256=None,require_context=True):
    if type(plan.get('schema_version')) is not int or plan['schema_version'] != EXECUTION_SCHEMA_VERSION:
        fail('schema_version',f'execution plan requires schema_version={EXECUTION_SCHEMA_VERSION}')
    cases=plan.get('cases'); batches=plan.get('batches')
    if not isinstance(cases,list) or not cases: fail('cases','required and non-empty')
    if not isinstance(batches,list) or not batches: fail('batches','required and non-empty')
    if confirmed_cases is None: fail('confirmed_cases','real confirmed test-case payload is required for planning validation')
    confirmed_by=_confirmed_case_map(confirmed_cases); confirmed_ids=list(confirmed_by)
    plan_ids=[c.get('case_id') for c in cases]
    if set(plan_ids)!=set(confirmed_ids) or len(plan_ids)!=len(confirmed_ids):
        fail('case_set',f'planning cases must exactly equal confirmed cases; missing={sorted(set(confirmed_ids)-set(plan_ids))}, extra={sorted(set(plan_ids)-set(confirmed_ids))}')
    declared=plan.get('confirmed_case_ids')
    if not isinstance(declared,list) or set(declared)!=set(confirmed_ids) or len(declared)!=len(confirmed_ids): fail('confirmed_case_ids','must exactly match confirmed test cases')
    if confirmed_cases_sha256 is not None and plan.get('confirmed_cases_sha256')!=confirmed_cases_sha256: fail('confirmed_cases_sha256','must bind to the confirmed test-case contract version')

    sr=plan.get('self_review',{})
    if sr.get('status')!='passed': fail('self_review.status','must be passed')
    for k in ['all_cases_assigned','execution_method_checked','batch_logic_checked','dependency_checked','evidence_checked','data_strategy_checked']:
        if sr.get('checks',{}).get(k) is not True: fail(f'self_review.checks.{k}','must be true')
    if require_confirmed and plan.get('user_confirmation',{}).get('status')!='confirmed': fail('user_confirmation.status','execution plan must be confirmed')

    batch_ids=[]; batch_by_id={}; case_membership={}
    for i,b in enumerate(batches):
        p=f'batches[{i}]'; bid=b.get('id')
        if not bid: fail(p+'.id','required')
        if bid in batch_by_id: fail(p+'.id',f'duplicate {bid}')
        batch_ids.append(bid); batch_by_id[bid]=b
        if not isinstance(b.get('parallel_safe'),bool): fail(p+'.parallel_safe','boolean required')
        if not isinstance(b.get('case_ids'),list) or not b['case_ids']: fail(p+'.case_ids','non-empty list required')
        if len(set(b['case_ids']))!=len(b['case_ids']): fail(p+'.case_ids','duplicate case id in batch')
        for cid in b['case_ids']: case_membership.setdefault(cid,[]).append(bid)
    batch_order={bid:i for i,bid in enumerate(batch_ids)}

    case_by_id={}; script_targets={}
    for i,c in enumerate(cases):
        p=f'cases[{i}]'; cid=c.get('case_id')
        if not cid: fail(p+'.case_id','required')
        if cid in case_by_id: fail(p+'.case_id',f'duplicate {cid}')
        case_by_id[cid]=c; _assert_case_source(c,confirmed_by[cid])
        bid=c.get('batch_id')
        if bid not in batch_by_id: fail(f'{cid}.batch_id',f'unknown batch {bid}')
        if case_membership.get(cid)!=[bid]: fail(f'{cid}.batch_id',f'must appear exactly once in {bid}.case_ids; actual={case_membership.get(cid)}')
        main=c.get('primary_execution')
        if main not in MAIN: fail(f'{cid}.primary_execution',f'invalid {main}')
        exp=c['expected_results']; exp_ids=[]
        for j,e in enumerate(exp):
            if not isinstance(e,dict): fail(f'{cid}.expected_results[{j}]','object with stable id and expected text required')
            eid=e.get('id'); expected=e.get('expected')
            if not eid or not isinstance(expected,str) or not expected.strip(): fail(f'{cid}.expected_results[{j}]','id and observable expected text required')
            exp_ids.append(eid)
        if len(exp_ids)!=len(set(exp_ids)): fail(f'{cid}.expected_results','duplicate expected id')
        if c.get('ui_required') is True and main!='UI': fail(f'{cid}.primary_execution','UI-required case cannot use API/manual')
        if 'aux_validation' in c: fail(f'{cid}.aux_validation','legacy field is not supported; use supporting_observations')
        supporting=c.get('supporting_observations',[])
        if not isinstance(supporting,list) or any(not isinstance(x,str) or x not in AUX for x in supporting): fail(f'{cid}.supporting_observations','contains unsupported value')
        if 'depends_on' in c: fail(f'{cid}.depends_on','legacy field is not supported; use dependencies')
        _validate_automation(c,main,bid,script_targets)
        ep=c.get('evidence_plan')
        if not isinstance(ep,dict) or not ep: fail(f'{cid}.evidence_plan','must be explicit, not empty shell')
        if 'waiver_reason' in ep: fail(f'{cid}.evidence_plan.waiver_reason','waivers are not supported; plan concrete evidence')
        level=ep.get('level')
        if level not in {'standard','critical'}: fail(f'{cid}.evidence_plan.level','must be standard or critical')
        for k in ['screenshots','api','network','files']:
            if k not in ep: fail(f'{cid}.evidence_plan.{k}','required')
            _validate_evidence_items(cid,k,ep[k],set(exp_ids))
        if 'recording' not in ep or not isinstance(ep['recording'],bool): fail(f'{cid}.evidence_plan.recording','case-level boolean required; Batch recording is not supported')
        if main=='UI' and not ep['screenshots']: fail(f'{cid}.evidence_plan.screenshots','UI Case requires a key assertion screenshot mapped to an Expected')
        if main=='UI' and level=='critical' and ep['recording'] is not True: fail(f'{cid}.evidence_plan.recording','critical UI Case requires case-level recording')
        policy=confirmed_by[cid].get('evidence_policy')
        if not isinstance(policy,dict): fail(f'{cid}.evidence_policy','confirmed machine-readable policy required')
        if main=='人工' and any(item.get('kind')=='runner_report' for item in policy.get('required',[])):
            fail(f'{cid}.evidence_policy','manual Case cannot require an automated runner_report')
        if level!=policy.get('level'): fail(f'{cid}.evidence_plan.level','must preserve the confirmed Case evidence level')
        if ep['recording'] is not policy.get('recording_required'):
            fail(f'{cid}.evidence_plan.recording','must preserve the confirmed Case recording requirement')
        evidence_fields={'screenshot':'screenshots','request_response':'api','read_back':'api','network':'network','file':'files','runner_report':'files'}
        for required in policy.get('required',[]):
            field=evidence_fields.get(required.get('kind'))
            if not field: fail(f'{cid}.evidence_policy.required','unsupported required evidence kind '+str(required.get('kind')))
            matched=[item for item in ep[field] if item.get('kind')==required['kind']]
            required_ids=set(required['assertion_ids'])
            if not any(required_ids<=set(item.get('expected_ids',[])) for item in matched):
                fail(f'{cid}.evidence_plan.{field}',f"missing confirmed {required['kind']} evidence for {sorted(required_ids)}")
            if required.get('redacted') is True and not any(item.get('redacted') is True and required_ids<=set(item.get('expected_ids',[])) for item in matched):
                fail(f'{cid}.evidence_plan.{field}','confirmed redaction requirement is not preserved')
        if main=='API':
            api_kinds={item['kind'] for item in ep['api']}
            if 'request_response' not in api_kinds: fail(f'{cid}.evidence_plan.api','API Case requires redacted request_response evidence')
            if 'read_back_required' not in ep or not isinstance(ep['read_back_required'],bool): fail(f'{cid}.evidence_plan.read_back_required','explicit boolean decision required')
            if any(item.get('kind')=='read_back' for item in policy.get('required',[])) and ep['read_back_required'] is not True:
                fail(f'{cid}.evidence_plan.read_back_required','confirmed Case evidence policy requires read_back')
            if ep['read_back_required'] and 'read_back' not in api_kinds: fail(f'{cid}.evidence_plan.api','required read_back evidence is missing')
        if c.get('downloads_file') is True and not ep['files']: fail(f'{cid}.evidence_plan.files','download case requires files evidence')
        if c.get('jev_policy') is not None or require_context:
            _validate_jev_policy(c, main, set(exp_ids))

    for bid,b in batch_by_id.items():
        for cid in b['case_ids']:
            if cid not in case_by_id: fail(f'{bid}.case_ids',f'contains unknown case {cid}')
            if case_by_id[cid].get('batch_id')!=bid: fail(f'{bid}.case_ids',f'{cid}.batch_id disagrees')
    for cid in case_by_id:
        if len(case_membership.get(cid,[]))!=1: fail(f'{cid}.batch_id','case must be assigned exactly once')

    graph={cid:[] for cid in case_by_id}
    for cid,c in case_by_id.items():
        deps=c.get('dependencies',[]) or []
        if not isinstance(deps,list): fail(f'{cid}.dependencies','list required')
        for d in deps:
            if d not in case_by_id: fail(f'{cid}.dependencies',f'unknown case {d}')
            if d==cid: fail(f'{cid}.dependencies','self dependency forbidden')
            graph[cid].append(d)
            if batch_order[case_by_id[d]['batch_id']]>batch_order[c['batch_id']]: fail(f'{cid}.dependencies',f'dependency {d} is scheduled in a later batch')
    color={cid:0 for cid in graph}
    def dfs(n,stack):
        color[n]=1
        for d in graph[n]:
            if color[d]==1: fail(f'{n}.dependencies',f'cycle detected: {" -> ".join(stack+[n,d])}')
            if color[d]==0: dfs(d,stack+[n])
        color[n]=2
    for cid in graph:
        if color[cid]==0: dfs(cid,[])

    _validate_run_context(plan, cases, require_context=require_context)
    return {'ok':True,'cases':len(case_by_id),'batches':len(batch_by_id),'confirmed_cases_bound':True}


if __name__=='__main__':
    a=argparse.ArgumentParser()
    a.add_argument('--input',required=True)
    a.add_argument('--confirmed-cases',required=True)
    a.add_argument('--allow-waiting-confirmation',action='store_true')
    a.add_argument('--require-context',action='store_true',default=True,help='require run_context and jev_policy (default True)')
    x=a.parse_args()
    cp=Path(x.confirmed_cases).resolve(); confirmed_design=json.loads(cp.read_text(encoding='utf-8'))
    run_dir=cp.parents[2]
    business_path=run_dir/'internal/business/business-model.json'; points_path=run_dir/'internal/design/test-points.json'
    if not business_path.is_file() or not points_path.is_file():
        fail('confirmed_cases','Run-bound business model and test-point contracts are required for Case projection')
    root=Path(__file__).resolve().parents[2]
    spec=importlib.util.spec_from_file_location('planning_case_contract',root/'test-case-design/scripts/case_contract.py')
    case_contract=importlib.util.module_from_spec(spec); spec.loader.exec_module(case_contract)
    case_contract.validate(confirmed_design,json.loads(points_path.read_text(encoding='utf-8')),json.loads(business_path.read_text(encoding='utf-8')),require_confirmed=not x.allow_waiting_confirmation)
    confirmed={'cases':case_contract.project_execution_cases(confirmed_design)}
    print(json.dumps(validate(json.loads(Path(x.input).read_text(encoding='utf-8')),not x.allow_waiting_confirmation,confirmed,sha256(cp),require_context=x.require_context),ensure_ascii=False))
