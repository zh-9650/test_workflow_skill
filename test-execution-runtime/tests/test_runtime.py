import copy, pytest
from conftest import load_script
m=load_script(__file__,'scripts/execution_control.py','execution_control')

def plan(): return {'case_id':'TC1','primary_execution':'UI','expected_results':[{'id':'E1','expected':'保存成功'}],'evidence_plan':{'screenshots':['E1'],'recording':{'required':True,'scope':'case'},'api':[],'network':[],'files':[]}}
def good(): return {'case_id':'TC1','actual_execution':'UI','status':'PASS','expected_results':[{'id':'E1','actual':'toast 保存成功','result':'pass','evidence_refs':['x.png']}],'recording_ref':'x.mp4'}
def test_pass_valid(): assert m.validate(plan(),good())['ok']
def test_pass_missing_actual_fails():
    r=good(); r['expected_results'][0]['actual']=''
    with pytest.raises(AssertionError): m.validate(plan(),r)
def test_pass_missing_evidence_fails():
    r=good(); r['expected_results'][0]['evidence_refs']=[]
    with pytest.raises(AssertionError): m.validate(plan(),r)
def test_fail_locator_error_fails():
    r=good(); r.update(status='FAIL',reason_type='locator_error',expected='x',actual='y',evidence_refs=['e'],reproduced=True); r['expected_results'][0]['result']='fail'
    with pytest.raises(AssertionError): m.validate(plan(),r)
def test_fail_no_evidence_fails():
    r=good(); r.update(status='FAIL',reason_type='product_issue',expected='x',actual='y',evidence_refs=[],reproduced=True); r['expected_results'][0]['result']='fail'
    with pytest.raises(AssertionError): m.validate(plan(),r)
def test_blocked_reason_required():
    r=good(); r.update(status='BLOCKED');
    with pytest.raises(AssertionError): m.validate(plan(),r)
def test_blocked_script_error_not_allowed():
    r=good(); r.update(status='BLOCKED',blocked_reason_type='script_error',blocked_reason='x',affected_by='tool')
    with pytest.raises(AssertionError): m.validate(plan(),r)
def test_needs_review_requires_action():
    r=good(); r.update(status='NEEDS_REVIEW',review_reason_type='evidence_insufficient',review_reason='missing'); r.pop('required_action',None)
    with pytest.raises(AssertionError): m.validate(plan(),r)
def test_method_switch_fails():
    r=good(); r['actual_execution']='API'
    with pytest.raises(AssertionError): m.validate(plan(),r)
def test_planned_recording_missing_fails():
    r=good(); r.pop('recording_ref')
    with pytest.raises(AssertionError): m.validate(plan(),r)
