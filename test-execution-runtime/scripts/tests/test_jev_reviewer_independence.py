import importlib.util
from pathlib import Path

import pytest

SPEC=importlib.util.spec_from_file_location('jev_reviewer',Path(__file__).parents[1]/'reviewer_contract.py')
reviewer=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reviewer)
RESULTS=[{'case_id':'C1','jev_invocations':[{'expected_id':'E1','source_response_sha256':'a'*64}]}]


def _judgment():
    return {'case_id':'C1','expected_id':'E1','source_evidence_sha256':'a'*64,
            'independent_judgment':'The response contradicts the planned constraint',
            'independent_judgment_at':'2026-09-30T00:00:00Z','jev_record_reviewed_at':'2026-09-30T00:00:01Z'}


def test_jev_case_cannot_pass_review_without_independent_source_judgment():
    with pytest.raises(AssertionError,match='cover exactly'):
        reviewer.validate_jev_independent_judgments({},RESULTS)


def test_jev_judgment_must_follow_independent_source_judgment():
    row=_judgment(); row['jev_record_reviewed_at']=row['independent_judgment_at']
    with pytest.raises(AssertionError,match='must precede'):
        reviewer.validate_jev_independent_judgments({'jev_independent_judgments':[row]},RESULTS)


def test_independent_judgment_binds_actual_source_evidence():
    reviewer.validate_jev_independent_judgments({'jev_independent_judgments':[_judgment()]},RESULTS)
