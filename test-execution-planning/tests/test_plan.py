import copy, pytest
from conftest import load_script
m=load_script(__file__,'scripts/execution_plan.py','execution_plan')

def base():
    return {'self_review':{'status':'passed'},'user_confirmation':{'status':'confirmed'},
      'batches':[{'id':'B1','case_ids':['TC1'],'parallel_safe':False}],
      'cases':[{'case_id':'TC1','batch_id':'B1','primary_execution':'UI','ui_required':True,'supporting_observations':['API'],'dependencies':[],
        'evidence_plan':{'screenshots':['E1'],'recording':False,'api':[],'network':[],'files':[]}}]}

def test_valid_ui_allows_api_aux(): assert m.validate(base())['ok']
def test_batch_case_mismatch_fails():
    v=base(); v['cases'][0]['batch_id']='B2'
    with pytest.raises(AssertionError): m.validate(v)
def test_unknown_dependency_fails():
    v=base(); v['cases'][0]['dependencies']=['TC999']
    with pytest.raises(AssertionError): m.validate(v)
def test_self_dependency_fails():
    v=base(); v['cases'][0]['dependencies']=['TC1']
    with pytest.raises(AssertionError): m.validate(v)
def test_cycle_dependency_fails():
    v=base(); v['batches'][0]['case_ids']=['TC1','TC2']; v['cases'].append(copy.deepcopy(v['cases'][0])); v['cases'][1].update(case_id='TC2',dependencies=['TC1']); v['cases'][0]['dependencies']=['TC2']
    with pytest.raises(AssertionError): m.validate(v)
def test_batch_unknown_case_fails():
    v=base(); v['batches'][0]['case_ids'].append('TC9')
    with pytest.raises(AssertionError): m.validate(v)
def test_case_unassigned_fails():
    v=base(); v['batches'][0]['case_ids']=[]
    with pytest.raises(AssertionError): m.validate(v)
def test_ui_evidence_empty_fails():
    v=base(); v['cases'][0]['evidence_plan']={'screenshots':[],'recording':False,'api':[],'network':[],'files':[]}
    with pytest.raises(AssertionError): m.validate(v)
def test_recording_required_needs_scope():
    v=base(); v['cases'][0]['evidence_plan']['recording']={'required':True}
    with pytest.raises(AssertionError): m.validate(v)
def test_ui_cannot_switch_to_api():
    v=base(); v['cases'][0]['primary_execution']='API'
    with pytest.raises(AssertionError): m.validate(v)
def test_api_needs_request_response_plan():
    v=base(); c=v['cases'][0]; c['primary_execution']='API'; c['ui_required']=False; c['evidence_plan']['screenshots']=[]
    with pytest.raises(AssertionError): m.validate(v)
