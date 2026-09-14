import copy, pytest
from conftest import load_script
m=load_script(__file__,'scripts/design_contract.py','design_contract')

def base(): return {'test_points_confirmed':True,'test_cases_confirmed':True,'test_points':[{'id':'TP1','methods':['边界值'],'technique_analysis':{'边界值':{'source_rule':{'min':1,'max':50},'derived_values':[0,1,2,49,50,51]}}}], 'cases':[{'case_id':'TC1','test_point_ids':['TP1'],'preconditions_applicable':False,'preconditions':[],'test_data_applicable':False,'test_data':[],'steps':['输入 0 并提交'],'expected_results':[{'expected':'页面提示长度不得小于1'}]}], 'self_review':{'status':'passed'}}
def test_valid_design(): assert m.validate(base())['ok']
def test_steps_empty_fails():
    v=base(); v['cases'][0]['steps']=[]
    with pytest.raises(AssertionError): m.validate(v)
def test_vague_expected_fails():
    v=base(); v['cases'][0]['expected_results']=[{'expected':'结果正确'}]
    with pytest.raises(AssertionError): m.validate(v)
def test_unknown_tp_fails():
    v=base(); v['cases'][0]['test_point_ids']=['TP999']
    with pytest.raises(AssertionError): m.validate(v)
def test_boundary_without_derived_values_fails():
    v=base(); v['test_points'][0]['technique_analysis']['边界值'].pop('derived_values')
    with pytest.raises(AssertionError): m.validate(v)
def test_decision_table_without_rules_fails():
    v=base(); p=v['test_points'][0]; p['methods']=['判定表']; p['technique_analysis']={'判定表':{'conditions':['a'],'actions':['x'],'rules':[]}}
    with pytest.raises(AssertionError): m.validate(v)
def test_state_transition_without_transitions_fails():
    v=base(); p=v['test_points'][0]; p['methods']=['状态迁移']; p['technique_analysis']={'状态迁移':{'states':['draft'],'transitions':[],'invalid_transitions':[]}}
    with pytest.raises(AssertionError): m.validate(v)
