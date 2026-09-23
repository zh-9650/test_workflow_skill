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
        matches=[s for s in report.get('suites',[]) if str(s.get('file','')).replace('\\','/').endswith(script_ref)]
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
        'authorization','cookie','set_cookie','token','password','secret','apikey',
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
                    'api_key','credit_card','card_number','bank_account','account_number',
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


def _validate_automation_run(plan_case,result,evidence_root,rows_by_id):
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
    for item in ep.get('screenshots',[]):
        eid=item.get('expected_ids',[])
        refs=rows_by_id[eid[0]].get('evidence_refs',rows_by_id[eid[0]].get('evidence',[])) if eid else []
        if not any(Path(str(ref.get('path') or ref.get('ref') if isinstance(ref,dict) else ref)).suffix.lower() in {'.png','.jpg','.jpeg','.webp'} for ref in refs):
            fail(f'{cid}.evidence_plan.screenshots',f'expected a screenshot for Expected {eid}')
    for item in ep.get('api',[]):
        if item.get('kind') not in {'request_response','read_back'}: continue
        for eid in item.get('expected_ids',[]):
            refs=rows_by_id[eid].get('evidence_refs',rows_by_id[eid].get('evidence',[]))
            json_refs=[ref for ref in refs if Path(str(ref.get('path') or ref.get('ref') if isinstance(ref,dict) else ref)).suffix.lower()=='.json']
            if not json_refs: fail(f'{cid}.evidence_plan.api',f'Expected {eid} needs JSON {item["kind"]} evidence')
            for ref in json_refs:
                path=_evidence_path(ref,evidence_root)
                try: payload=json.loads(path.read_text(encoding='utf-8'))
                except (OSError,ValueError) as exc: fail(f'{cid}.evidence_plan.api',f'invalid JSON evidence: {exc}')
                _assert_secret_keys_redacted(payload,str(path))
    if ep.get('recording') is True:
        video=result.get('recording_ref') or result.get('video_ref')
        video_path=_safe_run_file(video,f'{cid}.recording_ref',evidence_root,case_root)
        if video_path.suffix.lower() not in {'.webm','.mp4'}: fail(f'{cid}.recording_ref','case recording must be a video file')


def validate(plan_case,result,evidence_root=None):
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

    _validate_automation_run(plan_case,result,evidence_root,row_by)

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
