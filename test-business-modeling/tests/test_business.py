import pytest
from conftest import load_script
m=load_script(__file__,'scripts/business_contract.py','business_contract')
def base(): return {'scope':'x','modules':[{'name':'m','purpose':'p','functions':['f'],'rules':[],'data_impacts':[],'linkages':[],'open_questions':[]}],'cross_module_flows':[],'confirmed_rules':[],'open_questions':[],'self_review':{'status':'passed'},'user_confirmation':{'status':'confirmed'}}
def test_business_contract(): assert m.validate(base())['ok']
def test_self_review_required():
    v=base(); v['self_review']['status']='failed'
    with pytest.raises(AssertionError): m.validate(v)
def test_user_confirmation_required_for_downstream():
    v=base(); v['user_confirmation']['status']='pending'
    with pytest.raises(AssertionError): m.validate(v)
