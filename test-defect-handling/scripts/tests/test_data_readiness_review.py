import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

SPEC=importlib.util.spec_from_file_location('data_defect_review',Path(__file__).parents[1]/'defect_contract.py')
contract=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(contract)


def _write(root,ref,payload):
    path=root/ref; path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(payload),encoding='utf-8')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _review(root):
    failure_ref='evidence/B01/failure.json'
    failure_sha=_write(root,failure_ref,{'batch_id':'B01','affected_case_ids':['C1'],'preparer_session_id':'preparer','legal_reproduction':True,'completed_at':'2026-09-30T00:00:00Z'})
    task_ref='internal/data/reviews/task.json'
    task_sha=_write(root,task_ref,{'task_id':'DR-review-1','batch_id':'B01','case_ids':['C1'],'preparation_failure_sha256':failure_sha})
    receipt_ref='internal/data/reviews/receipt.json'
    receipt_sha=_write(root,receipt_ref,{'agent_role':'result_reviewer','receipt_status':'completed','agent_session_id':'reviewer','dispatch_source':'codex_subagent_tool','host_dispatch_ref':'synthetic-test-event-1','task_id':'DR-review-1','task_hash':task_sha})
    host_ref='internal/data/reviews/host-events.json'
    host_sha=_write(root,host_ref,{'events':[
        {'event_type':'agent_dispatched','call_id':'synthetic-test-event-1','agent_session_id':'reviewer','task_sha256':task_sha,'at':'2026-09-30T00:00:01Z'},
        {'event_type':'agent_completed','call_id':'synthetic-test-event-1','agent_session_id':'reviewer','task_sha256':task_sha,'at':'2026-09-30T00:00:02Z'}]})
    ref='internal/data/reviews/review.json'
    payload={'schema_version':3,'source_kind':'data_readiness','status':'passed','batch_id':'B01','affected_case_ids':['C1'],
             'reviewer_session_id':'reviewer','blocked_reason':'Legal fixture creation failed','legal_reproduction_verified':True,
             'reviewer_task_ref':task_ref,'reviewer_task_sha256':task_sha,'reviewer_receipt_ref':receipt_ref,'reviewer_receipt_sha256':receipt_sha,
             'preparation_failure_ref':failure_ref,'preparation_failure_sha256':failure_sha}
    payload.update(host_events_ref=host_ref,host_events_sha256=host_sha)
    _write(root,ref,payload)
    return ref,payload


def test_data_review_requires_real_artifacts_and_scope(tmp_path):
    ref,_=_review(tmp_path)
    assert contract.validate_data_readiness_review(tmp_path,ref,'B01',['C1'])['status']=='passed'
    with pytest.raises(AssertionError,match='scope'):
        contract.validate_data_readiness_review(tmp_path,ref,'B01',['C2'])


def test_data_review_rejects_same_preparer_session(tmp_path):
    ref,payload=_review(tmp_path); payload['reviewer_session_id']='preparer'; _write(tmp_path,ref,payload)
    with pytest.raises(AssertionError,match='differ from data preparer'):
        contract.validate_data_readiness_review(tmp_path,ref,'B01',['C1'])


def test_data_review_path_cannot_escape_run(tmp_path):
    ref,_=_review(tmp_path)
    with pytest.raises(AssertionError,match='internal/data/reviews'):
        contract.validate_data_readiness_review(tmp_path,'../outside.json','B01',['C1'])
