import copy, pytest
from conftest import load_script
m=load_script(__file__,'scripts/data_manifest.py','data_manifest')

def builder(): return {'builder_id':'PB1','object_type':'project','business_entry':'api','script_ref':'scripts/data/project_builder.py','verified':True,'verified_environment':'test','verified_at':'2026-09-14T00:00:00Z'}
def valid(): return {'batch_id':'B1','data_required':True,'builders':[builder()],'objects':[{'object_type':'project','object_ref':'P1','creation':{'business_entry':'api','implementation':'script','builder_ref':'scripts/data/project_builder.py','builder_id':'PB1'},'state_applicable':True,'target_state':'approved','current_state':'approved','verified':True,'read_back_verified':True,'relations_verified':True,'case_ids':['TC1']}]}

def test_valid_manifest(): assert m.validate(valid())['ok']
def test_no_data_requires_reason(): assert m.validate({'batch_id':'B1','data_required':False,'reason':'pure read query','objects':[]})['ok']
def test_required_empty_objects_fails():
    v=valid(); v['objects']=[]
    with pytest.raises(AssertionError): m.validate(v)
def test_missing_object_ref_fails():
    v=valid(); v['objects'][0]['object_ref']=''
    with pytest.raises(AssertionError): m.validate(v)
def test_state_applicable_target_missing_fails():
    v=valid(); v['objects'][0]['target_state']=None
    with pytest.raises(AssertionError): m.validate(v)
def test_current_state_missing_fails():
    v=valid(); v['objects'][0]['current_state']=None
    with pytest.raises(AssertionError): m.validate(v)
def test_sql_business_entry_fails():
    v=valid(); v['objects'][0]['creation']['business_entry']='sql'
    with pytest.raises(AssertionError): m.validate(v)
def test_unverified_builder_fails():
    v=valid(); v['builders'][0]['verified']=False
    with pytest.raises(AssertionError): m.validate(v)
def test_state_not_applicable_explicit():
    v=valid(); o=v['objects'][0]; o['state_applicable']=False; o['target_state']=None; o['current_state']=None
    assert m.validate(v)['ok']
def test_none_none_cannot_fake_state_ready():
    v=valid(); v['objects'][0]['target_state']=None; v['objects'][0]['current_state']=None
    with pytest.raises(AssertionError): m.validate(v)

def test_readiness_is_computed_not_hand_filled():
    v=valid(); out=m.validate(v); assert out['readiness']['ready'] is True and v['readiness']['ready'] is True
    bad=valid(); bad['ready']=True
    with pytest.raises(AssertionError): m.validate(bad)
