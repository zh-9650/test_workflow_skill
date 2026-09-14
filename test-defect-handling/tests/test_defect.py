import pytest
from conftest import load_script
m=load_script(__file__,'scripts/defect_contract.py','defect_contract')

def ep(): return {'screenshots':['E1'],'recording':False,'api':[],'network':[],'files':[]}
def pc(cid='TC1'): return {'case_id':cid,'primary_execution':'UI','expected_results':[{'id':'E1','expected':'saved'}],'evidence_plan':ep()}
def rr(cid='TC1',execution='UI',evidence=True,actual='saved'): return {'case_id':cid,'actual_execution':execution,'status':'PASS','expected_results':[{'id':'E1','actual':actual,'result':'pass','evidence_refs':['r.png'] if evidence else []}]}
def bug(): return {'defect_id':'D1','source_cases':['TC1'],'source_batch':'B1','reviewer_confirmed':True,'duplicate_check':{'performed':True,'result':'new','existing_bug_ref':None},'root_cause_group':'save','payload':{'title':'save fails','project':'P','module':'M','developer':'dev','severity':'major','environment':'test','preconditions':['login'],'steps':['save'],'actual':'not saved','expected':'saved','reproduction_rate':'3/3','evidence_refs':['x.png']},'self_review':{'status':'passed'},'submission':{'status':'submitted','bug_ref':'BUG1'}}
def reg(): return {'regression_id':'R1','bug_ref':'BUG1','original_case_ids':['TC1'],'impact_case_ids':[],'worker_is_new':True,'preserve_primary_execution':True,'cases':[pc()],'status':'completed','results':[rr()]}

def test_valid_bug_and_regression(): assert m.validate(bug())['ok'] and m.validate_reg(reg())['regression_passed']
def test_reviewer_false_blocks_bug():
    v=bug(); v['reviewer_confirmed']=False
    with pytest.raises(AssertionError): m.validate(v)
def test_duplicate_check_required():
    v=bug(); v['duplicate_check']['performed']=False
    with pytest.raises(AssertionError): m.validate(v)
def test_existing_requires_ref():
    v=bug(); v['duplicate_check']={'performed':True,'result':'existing','existing_bug_ref':None}; v['submission']={'status':'not_submitted_existing','bug_ref':None}
    with pytest.raises(AssertionError): m.validate(v)
def test_existing_bug_uses_explicit_not_submitted_status():
    v=bug(); v['duplicate_check']={'performed':True,'result':'existing','existing_bug_ref':'BUG-OLD'}; v['submission']={'status':'not_submitted_existing','bug_ref':'BUG-OLD'}; assert m.validate(v)['bug_ref']=='BUG-OLD'
def test_existing_bug_cannot_look_like_submission_failure():
    v=bug(); v['duplicate_check']={'performed':True,'result':'existing','existing_bug_ref':'BUG-OLD'}; v['submission']={'status':'failed','bug_ref':'BUG-OLD'}
    with pytest.raises(AssertionError): m.validate(v)
def test_self_review_required():
    v=bug(); v['self_review']['status']='failed'
    with pytest.raises(AssertionError): m.validate(v)
def test_submitted_requires_bug_ref():
    v=bug(); v['submission']['bug_ref']=None
    with pytest.raises(AssertionError): m.validate(v)
def test_existing_bug_not_resubmitted():
    v=bug(); v['duplicate_check']={'performed':True,'result':'existing','existing_bug_ref':'BUG-OLD'}
    with pytest.raises(AssertionError): m.validate(v)
def test_regression_new_worker_required():
    v=reg(); v['worker_is_new']=False
    with pytest.raises(AssertionError): m.validate_reg(v)
def test_regression_preserve_execution_required():
    v=reg(); v['preserve_primary_execution']=False
    with pytest.raises(AssertionError): m.validate_reg(v)
def test_regression_original_case_must_exist():
    v=reg(); v['cases']=[pc('TC2')]; v['results']=[rr('TC2')]
    with pytest.raises(AssertionError): m.validate_reg(v)
def test_regression_completed_needs_results():
    v=reg(); v['results']=[]
    with pytest.raises(AssertionError): m.validate_reg(v)
def test_regression_ui_to_api_fails():
    v=reg(); v['results'][0]['actual_execution']='API'
    with pytest.raises(AssertionError): m.validate_reg(v)
def test_regression_missing_evidence_fails():
    v=reg(); v['results'][0]=rr(evidence=False)
    with pytest.raises(AssertionError): m.validate_reg(v)
def test_regression_missing_actual_fails():
    v=reg(); v['results'][0]=rr(actual='')
    with pytest.raises(AssertionError): m.validate_reg(v)
