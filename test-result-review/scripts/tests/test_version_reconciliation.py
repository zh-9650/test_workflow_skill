import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

SPEC=importlib.util.spec_from_file_location('version_review',Path(__file__).parents[1]/'final_review.py')
review=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(review)


def _run(tmp_path, affected):
    proof=tmp_path/'evidence/deployment.json'
    proof.parent.mkdir()
    proof.write_text('{"version":"v2"}',encoding='utf-8')
    event={
        'event_id':'deploy-2','target_env':'test','deployment_version':'v2',
        'evidence_ref':'evidence/deployment.json',
        'evidence_sha256':hashlib.sha256(proof.read_bytes()).hexdigest(),
        'impact_decision':{'affected_pass_cases':affected,'old_pass_retest_needed':bool(affected),'data_recheck_needed':False,'rationale':'Only create path changed'},
    }
    p=tmp_path/'internal/execution/deployments/deploy-2.json'
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps(event),encoding='utf-8')
    state={'deployment_events':[{**event,'event_ref':p.relative_to(tmp_path).as_posix(),'event_sha256':hashlib.sha256(p.read_bytes()).hexdigest()}],'current_deployment_version':'v2'}
    plan={'target_environment':{'env_id':'test','initial_deployment_version':'v1'}}
    ledger={'C1':{'status':'PASS','runtime_result':{'target_environment':'test','deployment_version':'v1'}}}
    summaries={'C1':{'target_environment':'test','deployment_version':'v1'}}
    return plan,state,ledger,summaries


def test_affected_old_pass_requires_retest(tmp_path):
    with pytest.raises(AssertionError,match='affected old PASS'):
        review._reconcile_versions(tmp_path,*_run(tmp_path,['C1']))


def test_unaffected_old_pass_keeps_version_and_rationale(tmp_path):
    result=review._reconcile_versions(tmp_path,*_run(tmp_path,[]))
    assert result['latest_target_version']=='v2'
    assert result['case_versions'][0]['verified_version']=='v1'
    assert result['case_versions'][0]['not_retested_rationale']==['Only create path changed']


def test_summary_cannot_claim_new_version_for_old_evidence(tmp_path):
    plan,state,ledger,summaries=_run(tmp_path,[])
    summaries['C1']['deployment_version']='v2'
    with pytest.raises(AssertionError,match='preserve actual result'):
        review._reconcile_versions(tmp_path,plan,state,ledger,summaries)
