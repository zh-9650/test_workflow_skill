import argparse, hashlib, json, re, runpy
from datetime import datetime
from pathlib import Path

EXECUTION_SCHEMA_VERSION = runpy.run_path(
    str(Path(__file__).resolve().parents[2] / 'clarify-before-testing/scripts/workflow_versions.py')
)['EXECUTION_SCHEMA_VERSION']

FINAL={'PASS','FAIL','BLOCKED','NEEDS_REVIEW'}
BLOCK_TYPES={'product_bug','environment','external_resource','upstream_case','manual_pending','data_unavailable','account_permission'}
REVIEW_TYPES={'case_design_issue','business_rule_uncertain','evidence_insufficient','planning_conflict'}


def fail(path,msg): raise AssertionError(f'{path}: {msg}')
def _main(plan): return plan.get('primary_execution')
def _actual(res): return res.get('actual_execution')


def _resolve_root(evidence_root):
    if evidence_root is None: fail('evidence_root','current Run directory is required for evidence validation')
    return Path(evidence_root).resolve()


def _allowed_case_root(plan_case,evidence_root):
    run=_resolve_root(evidence_root); bid=plan_case.get('batch_id'); cid=plan_case.get('case_id')
    if not bid or not cid: fail('plan_case','batch_id and case_id required for evidence ownership validation')
    return (run/'evidence'/str(bid)/str(cid)).resolve()


def _allowed_batch_root(plan_case,evidence_root):
    run=_resolve_root(evidence_root); bid=plan_case.get('batch_id')
    if not bid: fail('plan_case.batch_id','required for batch evidence ownership validation')
    return (run/'evidence'/str(bid)).resolve()


def _evidence_path(ref,evidence_root):
    if isinstance(ref,dict): ref=ref.get('path') or ref.get('ref')
    if not isinstance(ref,str) or not ref.strip(): fail('evidence_ref','non-empty file path required')
    run=_resolve_root(evidence_root); p=Path(ref)
    p=(p if p.is_absolute() else run/p).resolve()
    return p


def _inside(path,root):
    try: path.relative_to(root); return True
    except ValueError: return False


def _require_evidence(refs,path,evidence_root,allowed_root):
    if not isinstance(refs,list) or not refs: fail(path,'non-empty evidence list required')
    for ref in refs:
        p=_evidence_path(ref,evidence_root)
        if not _inside(p,allowed_root): fail(path,f'evidence must belong to current Run/Batch/Case: {p}')
        if not p.exists() or not p.is_file(): fail(path,f'evidence file does not exist: {p}')


def _require_single_evidence(ref,path,evidence_root,allowed_root):
    p=_evidence_path(ref,evidence_root)
    if not _inside(p,allowed_root): fail(path,f'evidence must belong to current Run/Batch/Case: {p}')
    if not p.exists() or not p.is_file(): fail(path,f'evidence file does not exist: {p}')


def _safe_run_file(ref, label, evidence_root, required_root=None):
    if not isinstance(ref,str) or not ref.strip(): fail(label,'non-empty Run-relative path required')
    root=_resolve_root(evidence_root); raw=Path(ref)
    if raw.is_absolute(): fail(label,'absolute path is forbidden')
    path=(root/raw).resolve()
    if not _inside(path,root): fail(label,'path escapes the current Run')
    if required_root is not None and not _inside(path,required_root): fail(label,f'file must belong to current Case: {path}')
    if not path.is_file(): fail(label,f'file does not exist: {path}')
    return path


def _runner_report_state(report, runner, script_ref, path):
    if not isinstance(report,dict): fail(path,'runner JSON report must be an object')
    if runner=='vitest':
        matches=[r for r in report.get('testResults',[]) if str(r.get('name','')).replace('\\','/').endswith('/'+script_ref)]
        if len(matches)!=1: fail(path,f'Vitest report must contain exactly one result for {script_ref}')
        assertions=matches[0].get('assertionResults',[])
        if not assertions: fail(path,'Vitest report has no assertions for the official Case script')
        return 'passed' if all(a.get('status')=='passed' for a in assertions) else 'failed',report.get('startTime')
    if runner=='playwright-test':
        matches=[s for s in report.get('suites',[]) if str(s.get('file','')).replace('\\','/').endswith(script_ref) or Path(script_ref).name == Path(str(s.get('file',''))).name]
        if len(matches)!=1: fail(path,f'Playwright report must contain exactly one suite for {script_ref}')
        tests=[]
        def collect(suite):
            for spec in suite.get('specs',[]):
                tests.extend(result.get('status') for test in spec.get('tests',[]) for result in test.get('results',[]))
            for child in suite.get('suites',[]): collect(child)
        collect(matches[0])
        if not tests: fail(path,'Playwright report has no executions for the official Case script')
        return ('passed' if all(x=='passed' for x in tests) else 'failed',report.get('stats',{}).get('startTime'))
    fail(path,f'unsupported runner {runner!r}')


def _report_time(value,path):
    try:
        if isinstance(value,(int,float)) and not isinstance(value,bool):
            return datetime.fromtimestamp(value/1000).astimezone()
        return datetime.fromisoformat(str(value).replace('Z','+00:00'))
    except (OverflowError,OSError,TypeError,ValueError): fail(path,'runner report has an invalid start time')


def _assert_secret_keys_redacted(value,path):
    sensitive_tokens={
        'authorization','auth','credential','credentials','cookie','set_cookie','token','password','secret','apikey',
        'session','email','phone','mobile','telephone','national','idcard','passport','ssn',
        'creditcard','cardnumber','bankaccount','accountnumber',
    }
    metadata_tokens={'status','verified','valid','enabled','configured','count','length','type'}
    safe_status_values={'active','absent','closed','expired','failed','invalid','none','open',
                        'present','sent','success','unset','valid','verified'}
    safe_type_values={'access','basic','bearer','business','digest','home','oauth','other',
                      'personal','refresh','work'}
    sensitive_value=re.compile(
        r'\bBearer\s+[A-Za-z0-9._~+/=-]{8,}|'
        r'-----BEGIN ([A-Z0-9 ]*PRIVATE KEY)-----[\s\S]*?(?:-----END \1-----|$)|'
        r'(?:^|[?&;\s])(?:[^=&#;\s]*(?:access[_-]?token|api[_-]?key|authorization|auth|credential|password|secret|session|token)[^=&#;\s]*)=([^&#;\s]+)|'
        r'\b[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b|'
        r'\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b|'
        r'(?<!\d)(?:\+?86[-\s]?)?1[3-9]\d{9}(?!\d)',re.I
    )
    redacted=('[REDACTED]','[REDACTED: present]','***')
    if isinstance(value,dict):
        for key,item in value.items():
            normalized_key=re.sub(r'([a-z0-9])([A-Z])',r'\1_\2',str(key)).lower()
            tokens=set(re.findall(r'[a-z0-9]+',normalized_key))
            joined='_'.join(re.findall(r'[a-z0-9]+',normalized_key))
            sensitive=bool(tokens & sensitive_tokens) or any(
                f'_{field}_' in f'_{joined}_' for field in (
                    'api_key','access_key','private_key','secret_key','credit_card','card_number','bank_account','account_number',
                    'national_id','id_card',
                )
            )
            metadata=bool(tokens & metadata_tokens)
            metadata_value=(item is None or item=='') or (
                metadata and isinstance(item,bool)
            ) or (
                'status' in tokens and isinstance(item,str) and item.lower() in safe_status_values
            ) or (
                bool(tokens & {'count','length'}) and isinstance(item,int) and not isinstance(item,bool)
                and item >= 0
            ) or (
                'type' in tokens and isinstance(item,str) and item.lower() in safe_type_values
            )
            if sensitive and not metadata_value and item not in redacted:
                fail(path,f'sensitive field {key!r} is not redacted')
            _assert_secret_keys_redacted(item,path)
    elif isinstance(value,list):
        for item in value: _assert_secret_keys_redacted(item,path)
    elif isinstance(value,str) and sensitive_value.search(value):
        fail(path,'evidence contains a recognizable credential or personal-data value')


def _blocked_upstream_gate(plan_case,result,evidence_root,rows_by_id,dependency_context):
    """Validate evidence for an upstream gate that prevented any target action."""
    if not (
        result.get('status')=='BLOCKED'
        and result.get('blocked_reason_type')=='upstream_case'
        and result.get('target_action_executed') is False
        and result.get('actual_execution')=='NOT_EXECUTED'
    ):
        return False
    cid=plan_case.get('case_id'); dependencies=plan_case.get('dependencies') or []
    if not dependencies: fail(f'{cid}.dependencies','upstream gate requires confirmed planned dependencies')
    if not isinstance(dependency_context,dict): fail(f'{cid}.dependency_context','trusted Runtime Task dependency context is required')
    unresolved=[]
    for dep in dependencies:
        ctx=dependency_context.get(dep)
        if not isinstance(ctx,dict) or ctx.get('reviewer_confirmed') is not True:
            fail(f'{cid}.dependency_context.{dep}','trusted Reviewer-confirmed dependency result is required')
        state=ctx.get('final_result') or ctx.get('status')
        if ctx.get('case_id') not in (None,dep): fail(f'{cid}.dependency_context.{dep}.case_id','does not match planned dependency')
        if state not in {'PASS','PASS_AFTER_FIX'}:
            if state not in {'FAIL','BLOCKED'}: fail(f'{cid}.dependency_context.{dep}.final_result','must be a terminal unresolved result')
            unresolved.append(dep)
    if not unresolved: fail(f'{cid}.dependency_context','all planned dependencies are resolved; upstream block is invalid')
    affected=result.get('affected_by')
    affected_ids=set(affected if isinstance(affected,list) else str(affected or '').split(','))
    affected_ids={str(x).strip() for x in affected_ids if str(x).strip()}
    if affected_ids!=set(unresolved): fail(f'{cid}.affected_by','must exactly identify every unresolved planned dependency')

    gate_ref=None
    for row in rows_by_id.values():
        for ref in row.get('evidence_refs',row.get('evidence',[])):
            path=_evidence_path(ref,evidence_root)
            if path.suffix.lower()=='.json' and path.name!='vitest-report.json':
                try: payload=json.loads(path.read_text(encoding='utf-8'))
                except (OSError,ValueError): continue
                if isinstance(payload,dict) and payload.get('evidence_type')=='blocked_dependency':
                    if gate_ref is not None: fail(f'{cid}.blocked_dependency_evidence','exactly one gate evidence file is allowed')
                    gate_ref=path
    if gate_ref is None: fail(f'{cid}.blocked_dependency_evidence','current Case must attach blocked_dependency gate evidence')
    for eid,row in rows_by_id.items():
        if row.get('result')=='blocked':
            refs=row.get('evidence_refs',row.get('evidence',[]))
            if not any(_evidence_path(ref,evidence_root).resolve()==gate_ref.resolve() for ref in refs):
                fail(f'{cid}.expected_results[{eid}].evidence_refs','blocked Expected must directly attach the dependency gate evidence')
    try: gate=json.loads(gate_ref.read_text(encoding='utf-8'))
    except (OSError,ValueError) as exc: fail(f'{cid}.blocked_dependency_evidence',f'invalid JSON: {exc}')
    if gate.get('case_id')!=cid or gate.get('blocked_reason_type')!='upstream_case': fail(f'{cid}.blocked_dependency_evidence','case and block type must match')
    if gate.get('target_action_executed') is not False or gate.get('request_made') is not False: fail(f'{cid}.blocked_dependency_evidence','must prove no target action or request was made')
    def has_request_response_payload(value):
        if isinstance(value,dict):
            for key,item in value.items():
                normalized=re.sub(r'([a-z0-9])([A-Z])',r'\1_\2',str(key)).lower()
                compact=normalized.replace('_','')
                if (('request' in compact and compact!='requestmade') or 'response' in compact
                    or compact in {'url','headers','body','statuscode'}):
                    return True
                if has_request_response_payload(item): return True
        elif isinstance(value,list):
            return any(has_request_response_payload(item) for item in value)
        return False
    if has_request_response_payload(gate): fail(f'{cid}.blocked_dependency_evidence','gate evidence must not contain request/response payload fields')
    rows=gate.get('dependency_results')
    if not isinstance(rows,list): fail(f'{cid}.blocked_dependency_evidence.dependency_results','list required')
    observed={}
    for item in rows:
        if not isinstance(item,dict) or not item.get('case_id') or item['case_id'] in observed: fail(f'{cid}.blocked_dependency_evidence.dependency_results','unique dependency case rows required')
        observed[item['case_id']]=item
    if set(observed)!=set(unresolved): fail(f'{cid}.blocked_dependency_evidence.dependency_results','must cover exactly all unresolved dependencies')
    for dep in unresolved:
        ctx=dependency_context[dep]; item=observed[dep]
        if item.get('status')!=(ctx.get('final_result') or ctx.get('status')) or item.get('reviewer_confirmed') is not True:
            fail(f'{cid}.blocked_dependency_evidence.{dep}','does not match trusted Reviewer-confirmed Runtime Task context')
    if gate.get('affected_by')!=result.get('affected_by'): fail(f'{cid}.blocked_dependency_evidence.affected_by','must match Case result')
    _assert_secret_keys_redacted(gate,str(gate_ref))
    all_refs=[]
    for row in rows_by_id.values():
        all_refs.extend(row.get('evidence_refs',row.get('evidence',[])))
    for field in ('evidence_refs','file_evidence_refs'):
        refs=result.get(field,[]) or []
        if not isinstance(refs,list): fail(f'{cid}.{field}','must be a list of current-Case evidence refs')
        all_refs.extend(refs)
    checked=set()
    for ref in all_refs:
        path=_evidence_path(ref,evidence_root)
        _require_single_evidence(ref,f'{cid}.blocked_dependency_evidence',evidence_root,_allowed_case_root(plan_case,evidence_root))
        if path.suffix.lower()!='.json' or path.resolve() in checked: continue
        checked.add(path.resolve())
        try: payload=json.loads(path.read_text(encoding='utf-8'))
        except (OSError,ValueError) as exc: fail(f'{cid}.blocked_dependency_evidence',f'JSON evidence must be readable: {exc}')
        if has_request_response_payload(payload):
            fail(f'{cid}.blocked_dependency_evidence','Case JSON evidence must not contain request/response payload fields when the target action was not executed')
    return True


def _validate_automation_run(plan_case,result,evidence_root,rows_by_id,dependency_context=None):
    cid=plan_case.get('case_id'); planned=plan_case.get('automation',{}); main=_main(plan_case)
    if main=='人工' or planned.get('required') is False:
        if result.get('automation_run') is not None: fail(f'{cid}.automation_run','manual Case cannot claim an automated run')
        return
    case_root=_allowed_case_root(plan_case,evidence_root)
    record=result.get('automation_run')
    if not isinstance(record,dict): fail(f'{cid}.automation_run','official script provenance is required')
    script_ref=record.get('script_ref'); target=planned.get('script_target')
    if script_ref!=target: fail(f'{cid}.automation_run.script_ref','must equal the confirmed Planning script_target')
    script=_safe_run_file(script_ref,f'{cid}.automation_run.script_ref',evidence_root)
    suffix='.test.ts' if planned.get('runner')=='vitest' else '.spec.ts' if planned.get('runner')=='playwright-test' else None
    if suffix is None or not script_ref.endswith(suffix): fail(f'{cid}.automation_run.script_ref','extension does not match planned runner')
    actual_hash=hashlib.sha256(script.read_bytes()).hexdigest()
    if record.get('script_sha256')!=actual_hash: fail(f'{cid}.automation_run.script_sha256','does not match current final script')
    if record.get('runner')!=planned.get('runner') or record.get('driver')!=planned.get('driver'):
        fail(f'{cid}.automation_run','runner/driver differs from Planning')
    if record.get('static_check')!='passed': fail(f'{cid}.automation_run.static_check','must pass before official run')
    if not isinstance(record.get('debug_attempts'),list): fail(f'{cid}.automation_run.debug_attempts','list required')
    official=record.get('official_run')
    if not isinstance(official,dict): fail(f'{cid}.automation_run.official_run','required after script creation and debugging')
    if not isinstance(official.get('run_id'),str) or not official['run_id'].strip(): fail(f'{cid}.automation_run.official_run.run_id','required')
    if type(official.get('exit_code')) is not int: fail(f'{cid}.automation_run.official_run.exit_code','integer required')
    if official.get('script_sha256')!=actual_hash: fail(f'{cid}.automation_run.official_run.script_sha256','must match the final script hash')
    try:
        started=datetime.fromisoformat(official['started_at'].replace('Z','+00:00'))
        finished=datetime.fromisoformat(official['finished_at'].replace('Z','+00:00'))
    except (KeyError,AttributeError,TypeError,ValueError): fail(f'{cid}.automation_run.official_run','valid started_at/finished_at timestamps required')
    if finished<started: fail(f'{cid}.automation_run.official_run','finished_at precedes started_at')
    report_path=_safe_run_file(official.get('report_ref'),f'{cid}.automation_run.official_run.report_ref',evidence_root,case_root)
    if official['exit_code']!=0 and result.get('status')=='PASS': fail(f'{cid}.automation_run.official_run.exit_code','nonzero runner exit cannot produce PASS')
    try: report=json.loads(report_path.read_text(encoding='utf-8'))
    except (OSError,ValueError) as exc: fail(f'{cid}.automation_run.official_run.report_ref',f'invalid JSON runner report: {exc}')
    report_state,report_started=_runner_report_state(report,planned['runner'],script_ref,official['report_ref'])
    report_time=_report_time(report_started,f'{cid}.automation_run.official_run.report_ref')
    if started.tzinfo is None: started=started.astimezone()
    if finished.tzinfo is None: finished=finished.astimezone()
    if report_time<started.astimezone() or report_time>finished.astimezone():
        fail(f'{cid}.automation_run.official_run.report_ref','runner report timestamp is outside the official run window')
    if result.get('status')=='PASS' and report_state!='passed': fail(f'{cid}.status','PASS requires this Case to pass in the official runner report')
    if result.get('status')=='FAIL' and report_state!='failed': fail(f'{cid}.status','product FAIL requires a failed official assertion for this Case')

    ep=plan_case.get('evidence_plan',{})
    blocked_gate=_blocked_upstream_gate(plan_case,result,evidence_root,rows_by_id,dependency_context)
    official_report=report_path.resolve()
    for item in ep.get('screenshots',[]):
        for eid in item.get('expected_ids',[]):
            refs=rows_by_id[eid].get('evidence_refs',rows_by_id[eid].get('evidence',[]))
            if not any(Path(str(ref.get('path') or ref.get('ref') if isinstance(ref,dict) else ref)).suffix.lower() in {'.png','.jpg','.jpeg','.webp'} for ref in refs):
                fail(f'{cid}.evidence_plan.screenshots',f'expected a screenshot for Expected {eid}')
    for item in ep.get('api',[]):
        if item.get('kind') not in {'request_response','read_back'}: continue
        if blocked_gate and item.get('kind')=='request_response': continue
        for eid in item.get('expected_ids',[]):
            refs=rows_by_id[eid].get('evidence_refs',rows_by_id[eid].get('evidence',[]))
            json_refs=[ref for ref in refs if Path(str(ref.get('path') or ref.get('ref') if isinstance(ref,dict) else ref)).suffix.lower()=='.json']
            api_refs=[]
            for ref in json_refs:
                path=_evidence_path(ref,evidence_root)
                if path.resolve()!=official_report:
                    api_refs.append((ref,path))
            if not api_refs: fail(f'{cid}.evidence_plan.api',f'Expected {eid} needs JSON {item["kind"]} evidence separate from the official Runner report')
            for ref,path in api_refs:
                try: payload=json.loads(path.read_text(encoding='utf-8'))
                except (OSError,ValueError) as exc: fail(f'{cid}.evidence_plan.api',f'invalid JSON evidence: {exc}')
                if item.get('kind')=='request_response' and (
                    not isinstance(payload,dict) or payload.get('redacted') is not True
                ):
                    fail(f'{cid}.evidence_plan.api','request/response Evidence must assert redacted=true')
                _assert_secret_keys_redacted(payload,str(path))
    for item in ep.get('files',[]):
        if item.get('kind')!='runner_report': continue
        for eid in item.get('expected_ids',[]):
            refs=rows_by_id[eid].get('evidence_refs',rows_by_id[eid].get('evidence',[]))
            attached={_evidence_path(ref,evidence_root).resolve() for ref in refs}
            if official_report not in attached:
                fail(f'{cid}.evidence_plan.files',f'Expected {eid} must attach the official Runner report declared by automation_run.official_run.report_ref')
    if ep.get('recording') is True:
        video=result.get('recording_ref') or result.get('video_ref')
        video_path=_safe_run_file(video,f'{cid}.recording_ref',evidence_root,case_root)
        if video_path.suffix.lower() not in {'.webm','.mp4'}: fail(f'{cid}.recording_ref','case recording must be a video file')


def _validate_jev_execution(plan_case, result, evidence_root):
    cid = plan_case.get('case_id')
    jev = plan_case.get('jev_policy')
    if not isinstance(jev, dict):
        return
    mode = jev.get('mode', 'none')
    invocations = result.get('jev_invocations')
    if 'jev_invocation' in result:
        fail(f'{cid}.jev_invocation','legacy singular field is forbidden; use jev_invocations')

    if mode == 'none':
        if invocations:
            fail(f'{cid}.jev', 'Case jev_policy mode is none but runtime result contains Jev invocation records')
        return

    if mode == 'required':
        if result.get('status')=='BLOCKED' and result.get('target_action_executed') is False and _actual(result) in (None,'NOT_EXECUTED') and not invocations:
            if not result.get('jev_skipped_reason'): fail(f'{cid}.jev_skipped_reason','unexecuted BLOCKED must explain why planned Jev steps were not reached')
            return
        if not isinstance(invocations, list) or len(invocations) == 0:
            if result.get('status') == 'PASS':
                fail(f'{cid}.status', 'PASS forbidden: planned required Jev invocation was not performed')
            fail(f'{cid}.jev_invocations', 'required Jev invocation records missing in runtime result')

    if mode == 'conditional':
        if not invocations:
            skipped_reason = result.get('jev_skipped_reason') or result.get('jev_not_called_reason')
            if not skipped_reason or not str(skipped_reason).strip():
                fail(f'{cid}.jev_skipped_reason', 'conditional Jev invocation was not performed; non-empty jev_skipped_reason required')
            return

    total_cost = 0.0
    planned_tt = jev.get('target_type')
    planned_eids = set(jev.get('expected_ids', []))
    if len(invocations or [])>jev.get('max_calls',0):
        fail(f'{cid}.jev_invocations',f'call count exceeds planned max_calls={jev.get("max_calls")}')
    policy_hash=hashlib.sha256(json.dumps(jev,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest()
    case_root=_allowed_case_root(plan_case,evidence_root) if invocations else None
    for idx, inv in enumerate(invocations or []):
        p = f'{cid}.jev_invocations[{idx}]'
        if not isinstance(inv, dict):
            fail(p, 'invocation record must be an object')
        tt = inv.get('target_type')
        if planned_tt and tt and tt != planned_tt:
            fail(f'{p}.target_type', f'mismatch with planned target_type {planned_tt}, got {tt}')
        if inv.get('provider')!=jev.get('provider') or inv.get('model')!=jev.get('model') or inv.get('model_version')!=jev.get('model_version'):
            fail(p+'.provider/model','must match the confirmed Planning provider, model, and model_version')
        if inv.get('policy_sha256')!=policy_hash: fail(p+'.policy_sha256','must bind the exact confirmed Jev policy')
        cost = inv.get('cost_usd')
        if type(cost) not in (int, float) or not __import__('math').isfinite(cost) or cost < 0:
            fail(f'{p}.cost_usd', 'non-negative number required')
        total_cost += float(cost)
        if total_cost>jev.get('max_cost_usd',0):
            fail(f'{cid}.jev_invocations',f'total Jev cost exceeds planned max_cost_usd ${jev.get("max_cost_usd"):.4f}')
        if cost>jev.get('max_cost_per_call_usd',0): fail(p+'.cost_usd','exceeds planned per-call cost cap')
        conf = inv.get('confidence')
        if type(conf) not in (int, float) or not (0.0 <= conf <= 1.0):
            fail(f'{p}.confidence', f'confidence must be a number between 0.0 and 1.0, got {conf}')
        eid = inv.get('expected_id')
        if eid not in planned_eids:
            fail(f'{p}.expected_id', f'must map to planned expected_ids {sorted(planned_eids)}, got {eid}')
        selected=inv.get('selected_option') if planned_tt=='api_semantic_judgment' else inv.get('selected_id')
        if selected not in jev.get('bounded_options',[]): fail(p+'.selected_option','must be one of the bounded Planning options')
        required=('request','response','usage','source_response') if planned_tt=='api_semantic_judgment' else ('request','response','usage','candidate_snapshot','post_selection_revalidation')
        for name in required:
            ref=inv.get(name+'_ref'); digest=inv.get(name+'_sha256')
            file_path=_safe_run_file(ref,p+'.'+name+'_ref',evidence_root,case_root)
            actual=hashlib.sha256(file_path.read_bytes()).hexdigest()
            if not isinstance(digest,str) or not re.fullmatch(r'[0-9a-f]{64}',digest) or digest!=actual:
                fail(p+'.'+name+'_sha256',f'must match {name} evidence file')
            if file_path.suffix.lower()=='.json':
                try: payload=json.loads(file_path.read_text(encoding='utf-8'))
                except (OSError,ValueError) as exc: fail(p+'.'+name+'_ref',f'invalid JSON evidence: {exc}')
                _assert_secret_keys_redacted(payload,str(file_path))
        request=json.loads(_safe_run_file(inv['request_ref'],p+'.request_ref',evidence_root,case_root).read_text(encoding='utf-8'))
        if request.get('case_id')!=cid or request.get('expected_id')!=eid or request.get('target_type')!=planned_tt or request.get('policy_sha256')!=policy_hash:
            fail(p+'.request_ref','request audit must bind Case, Expected, and target_type')
        response=json.loads(_safe_run_file(inv['response_ref'],p+'.response_ref',evidence_root,case_root).read_text(encoding='utf-8'))
        answer=(response.get('answers') or {}).get('judgment') or {}
        if response.get('model')!=jev['model'] or answer.get('choice')!=selected or answer.get('confidence')!=conf:
            fail(p+'.response_ref','saved official response must match pinned model, selected option and confidence')
        usage=json.loads(_safe_run_file(inv['usage_ref'],p+'.usage_ref',evidence_root,case_root).read_text(encoding='utf-8'))
        reported_cost=usage.get('costUsd',usage.get('cost_usd'))
        if reported_cost!=cost: fail(p+'.usage_ref','invocation cost must match saved usage evidence')
    max_cost = jev.get('max_cost_usd')
    if mode=='required' and {i.get('expected_id') for i in (invocations or []) if isinstance(i,dict)}!=planned_eids:
        fail(f'{cid}.jev_invocations','required calls must cover every planned Expected ID')
    if total_cost > max_cost:
        fail(f'{cid}.jev_invocations', f'total Jev cost ${total_cost:.4f} exceeds planned max_cost_usd ${max_cost:.4f}')


def validate(plan_case,result,evidence_root=None,*,dependency_context=None):
    cid=plan_case.get('case_id'); status=result.get('status')
    schema_version=result.get('schema_version')
    if type(schema_version) is not int or schema_version != EXECUTION_SCHEMA_VERSION:
        fail(f'{cid}.schema_version',f'must be integer {EXECUTION_SCHEMA_VERSION}')
    if result.get('case_id')!=cid: fail('case_id',f'mismatch, expected {cid}')
    if status not in FINAL: fail(f'{cid}.status',f'invalid {status}')
    actual_execution=_actual(result); planned_execution=_main(plan_case)
    not_executed=(status=='BLOCKED' and result.get('target_action_executed') is False and actual_execution in (None,'NOT_EXECUTED'))
    if not not_executed and actual_execution!=planned_execution:
        fail(f'{cid}.actual_execution',f'planned {planned_execution}, actual {actual_execution}')

    case_evidence_root=_allowed_case_root(plan_case,evidence_root)
    expected=plan_case.get('expected_results',[]); rows=result.get('expected_results',[])
    if not expected: fail(f'{cid}.expected_results','plan has none')
    if len(expected)!=len(rows): fail(f'{cid}.expected_results','mapping incomplete')
    exp_by={e.get('id'):e for e in expected}; row_by={e.get('id'):e for e in rows}
    if None in exp_by or len(exp_by)!=len(expected) or None in row_by or len(row_by)!=len(rows) or set(exp_by)!=set(row_by): fail(f'{cid}.expected_results','IDs missing/duplicate/mismatch')
    for eid,r in row_by.items():
        p=f'{cid}.expected_results[{eid}]'
        if r.get('actual') in (None,''): fail(p+'.actual','required')
        if r.get('result') not in {'pass','fail','blocked','needs_review'}: fail(p+'.result','invalid')
        refs=r.get('evidence_refs',r.get('evidence',[]))
        if not refs: fail(p+'.evidence_refs','every Expected requires current-run evidence')
        _require_evidence(refs,p+'.evidence_refs',evidence_root,case_evidence_root)

    _validate_automation_run(plan_case,result,evidence_root,row_by,dependency_context)
    _validate_jev_execution(plan_case,result,evidence_root)

    if status=='PASS':
        bad=[eid for eid,r in row_by.items() if r.get('result')!='pass']
        if bad: fail(f'{cid}.status',f'PASS but expected results not pass: {bad}')
    elif status=='FAIL':
        if result.get('reason_type')!='product_issue': fail(f'{cid}.reason_type','FAIL requires product_issue; technical/data/design errors are not product FAIL')
        if result.get('expected') in (None,'') or result.get('actual') in (None,''): fail(f'{cid}.FAIL','expected and actual required')
        _require_evidence(result.get('evidence_refs',[]),f'{cid}.evidence_refs',evidence_root,case_evidence_root)
        if result.get('reproduced') is not True:
            if result.get('reproduction_applicable') is not False or not result.get('reproduction_reason'): fail(f'{cid}.reproduced','must be true or explicitly not applicable with reason')
        if not any(r.get('result')=='fail' for r in rows): fail(f'{cid}.expected_results','FAIL requires at least one failed expected')
    elif status=='BLOCKED':
        if result.get('blocked_reason_type') not in BLOCK_TYPES: fail(f'{cid}.blocked_reason_type',f'must be one of {sorted(BLOCK_TYPES)}')
        if not result.get('blocked_reason'): fail(f'{cid}.blocked_reason','required')
        if result.get('affected_by') in (None,''): fail(f'{cid}.affected_by','required')
        if all(r.get('result')=='pass' for r in rows): fail(f'{cid}.expected_results','BLOCKED cannot have every Expected marked pass')
        if not any(r.get('result')=='blocked' for r in rows): fail(f'{cid}.expected_results','BLOCKED requires at least one blocked Expected')
    elif status=='NEEDS_REVIEW':
        if result.get('review_reason_type') not in REVIEW_TYPES: fail(f'{cid}.review_reason_type',f'must be one of {sorted(REVIEW_TYPES)}')
        if not result.get('review_reason'): fail(f'{cid}.review_reason','required')
        if not result.get('required_action'): fail(f'{cid}.required_action','required')
        if not any(r.get('result')=='needs_review' for r in rows): fail(f'{cid}.expected_results','NEEDS_REVIEW requires at least one Expected needing review')

    ep=plan_case.get('evidence_plan',{}); rec=ep.get('recording')
    if isinstance(rec,dict): fail(f'{cid}.evidence_plan.recording','legacy recording object is unsupported')
    if rec is True:
        rr=result.get('recording_ref',result.get('video_ref'))
        if not rr: fail(f'{cid}.recording_ref','planned recording missing')
        _require_single_evidence(rr,f'{cid}.recording_ref',evidence_root,case_evidence_root)
    for ref in result.get('file_evidence_refs',[]) or []:
        _require_single_evidence(ref,f'{cid}.file_evidence_refs',evidence_root,case_evidence_root)
    return {'ok':True,'case_id':cid,'status':status}


if __name__=='__main__':
    a=argparse.ArgumentParser(); a.add_argument('--plan-case',required=True); a.add_argument('--result',required=True); a.add_argument('--evidence-root',required=True); x=a.parse_args()
    print(json.dumps(validate(json.loads(Path(x.plan_case).read_text(encoding='utf-8')),json.loads(Path(x.result).read_text(encoding='utf-8')),x.evidence_root),ensure_ascii=False))
