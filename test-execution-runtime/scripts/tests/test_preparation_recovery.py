"""Unit seams for preparation recovery; synthetic host trace is not forward acceptance."""
import importlib.util
import json
import sys
from pathlib import Path
import pytest

scripts=Path(__file__).parents[1]; sys.path.insert(0,str(scripts))
import runtime_orchestrator as runtime
from reviewer_contract import validate_preparation_recovery_reviews
helper_path=scripts.parents[1]/'test-defect-handling/scripts/tests/test_data_readiness_review.py'
spec=importlib.util.spec_from_file_location('prep_test_samples',helper_path)
samples=importlib.util.module_from_spec(spec); spec.loader.exec_module(samples)

def setup(tmp_path):
    ref,review=samples._review(tmp_path)
    samples._write(tmp_path,'internal/data/manifests/B01-data-manifest.json',{'applicable_version':'v2'})
    task={'batch_id':'B01','case_order':['C1'],'deployment_version':'v2','deployment_event_ref':'internal/execution/deployments/d2.json','deployment_event_sha256':'a'*64,'data_manifest_ref':'internal/data/manifests/B01-data-manifest.json'}
    ledger={'cases':{'C1':{'source_kind':'data_readiness','status':'BLOCKED','deployment_version':'v1','data_readiness_review_ref':ref,'data_readiness_review':review,'bug_ref':'BUG-1'}}}
    return task,ledger

def test_recovery_freezes_real_preparation_review_and_manifest(tmp_path,monkeypatch):
    task,ledger=setup(tmp_path)
    monkeypatch.setattr(runtime,'seal_task',lambda task:None);monkeypatch.setattr(runtime,'validate_task',lambda task:None)
    runtime._bind_preparation_recovery(tmp_path,task,ledger)
    recovery=task['data_readiness_recovery'][0]
    assert recovery['case_ids']==['C1'];assert recovery['bug_ref']=='BUG-1'
    assert recovery['data_manifest_sha256']==runtime._sha256(tmp_path/task['data_manifest_ref'])
    samples._write(tmp_path,runtime.CASE_LEDGER_REL,ledger)
    task['cases']=[{'case_id':'C1'}]
    runtime._commit_results_to_ledger(tmp_path,task,[{'case_id':'C1','status':'PASS'}])
    row=json.loads((tmp_path/runtime.CASE_LEDGER_REL).read_text(encoding='utf8'))['cases']['C1']
    assert row['final_result']=='PASS' and 'source_kind' not in row
    assert row['preparation_history'][0]['status']=='BLOCKED'
    assert 'initial_result' not in row # Never synthesize Runtime FAIL/PASS_AFTER_FIX.

def test_preparation_recovery_rejects_same_deployment(tmp_path):
    task,ledger=setup(tmp_path);task['deployment_version']='v1'
    samples._write(tmp_path,task['data_manifest_ref'],{'applicable_version':'v1'})
    with pytest.raises(AssertionError,match='differ'):
        runtime._bind_preparation_recovery(tmp_path,task,ledger)

def test_preparation_recovery_requires_independent_review():
    task={'data_readiness_recovery':[{'bug_ref':'BUG-1','data_manifest_sha256':'a'*64,'deployment_event_sha256':'b'*64}]}
    with pytest.raises(AssertionError,match='independently verify'):
        validate_preparation_recovery_reviews({},task)
    review={'data_readiness_recovery_reviews':[{'bug_ref':'BUG-1','data_manifest_sha256':'a'*64,'deployment_event_sha256':'b'*64,'preparation_fixed':True,'independent_judgment':'The legitimate creation and readback now succeed'}]}
    validate_preparation_recovery_reviews(review,task)
