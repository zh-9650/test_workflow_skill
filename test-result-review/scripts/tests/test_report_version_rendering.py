import importlib.util
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('version_report',Path(__file__).parents[1]/'report.py')
report=importlib.util.module_from_spec(spec); spec.loader.exec_module(report)

def test_report_requires_reconciliation_not_only_a_conclusion():
    with pytest.raises(AssertionError,match='version_reconciliation'):
        report.render({'final_assessment':{'conclusion':'ready'}})

def test_report_keeps_versions_rounds_and_unexecuted_scope():
    text=report.render({'final_assessment':{'conclusion':'ready_with_risk'},'version_reconciliation':{
        'initial_deployment_version':'v1','latest_target_version':'v3','deployment_events':[],
        'case_versions':[{'case_id':'C1','target_environment':'test','verified_version':'v1','not_retested_rationale':['unchanged read path']}],
        'execution_rounds':[{'case_id':'C2','phase':'product_regression-2','status':'FAIL','review_status':'passed','deployment_version':'v3','results_ref':'internal/results/round2.json'},
                            {'case_id':'C1','phase':'initial','status':'PASS','review_status':'rework_required','deployment_version':'v1','results_ref':'internal/results/initial.json'}],
        'unexecuted_scope':['C3']}})
    for expected in ('v1','v3','unchanged read path','product_regression-2','FAIL','C3'):
        assert expected in text
    assert 'Worker原始结果 PASS，独立复核 rework_required' in text
