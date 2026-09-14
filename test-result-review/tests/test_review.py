import pytest
from conftest import load_script
m=load_script(__file__,'scripts/final_review.py','final_review')

def wsr(): return {'status':'passed','checks':{'all_cases_checked':True,'all_expected_checked':True,'execution_method_checked':True,'evidence_binding_checked':True,'failure_classification_checked':True,'file_cleanup_checked':True}}
def rev(): return {'status':'passed','checks':{'completeness_checked':True,'method_consistency_checked':True,'judgement_checked':True,'evidence_checked':True,'abnormal_classification_checked':True}}
def base_result(): return {'case_id':'TC1','status':'PASS','planned_primary_execution':'UI','actual_execution':'UI','planned_evidence':{'recording':False,'files':[]},'core_flow':True}
def base(): return {'formal_case_ids':['TC1'],'planned_case_ids':['TC1'],'planned_batch_ids':['B1'],'batch_results':[{'batch_id':'B1','status':'completed','worker_self_review':wsr(),'reviewer':rev()}],'results':[base_result()]}
def test_final_reconcile_and_assessment():
    out=m.validate(base()); assert out['ok'] and out['final_assessment']['conclusion']=='ready'
def test_needs_review_not_final():
    v=base(); v['results'][0]['status']='NEEDS_REVIEW'
    with pytest.raises(AssertionError): m.validate(v)
def test_method_mismatch_fails():
    v=base(); v['results'][0]['actual_execution']='API'
    with pytest.raises(AssertionError): m.validate(v)
def test_recording_planned_missing_fails():
    v=base(); v['results'][0]['planned_evidence']['recording']={'required':True,'scope':'case'}
    with pytest.raises(AssertionError): m.validate(v)
def test_batch_missing_fails():
    v=base(); v['batch_results']=[]
    with pytest.raises(AssertionError): m.validate(v)
def test_pass_after_fix_requires_history():
    v=base(); v['results'][0]['status']='PASS_AFTER_FIX'
    with pytest.raises(AssertionError): m.validate(v)
def test_pass_after_fix_valid():
    v=base(); r=v['results'][0]; r.update(status='PASS_AFTER_FIX',initial_result='FAIL',bug_ref='BUG1',regressions=[{'regression_id':'R1','result':'PASS','worker_id':'W2','executed_at':'2026-09-14T00:00:00Z'}]); assert m.validate(v)['ok']
def test_fail_fixed_true_is_still_unresolved():
    v=base(); r=v['results'][0]; r.update(status='FAIL',fixed=True,severity='critical',bug_ref='BUG1'); out=m.validate(v); assert out['final_assessment']['conclusion']=='not_recommended' and out['final_assessment']['unresolved_critical_defects']==1
def test_worker_review_checks_required_in_final_reconcile():
    v=base(); v['batch_results'][0]['worker_self_review']['checks']['all_expected_checked']=False
    with pytest.raises(AssertionError): m.validate(v)
def test_reviewer_checks_required_in_final_reconcile():
    v=base(); v['batch_results'][0]['reviewer']['checks']['evidence_checked']=False
    with pytest.raises(AssertionError): m.validate(v)
def test_report_conclusion_must_come_from_final_assessment():
    report=load_script(__file__,'scripts/report.py','report_renderer')
    text=report.render({'scope':'x','final_assessment':{'conclusion':'ready'}}); assert '测试完成，可进入下一阶段' in text
    with pytest.raises(AssertionError): report.render({'scope':'x','conclusion':'随便写个结论'})
