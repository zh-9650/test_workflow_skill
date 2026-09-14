from pathlib import Path
import tempfile, pytest
from conftest import load_script
ws=load_script(__file__,'scripts/workflow_state.py','workflow_state')
wv=load_script(__file__,'scripts/workspace_validate.py','workspace_validate')
def test_legal_state_flow_and_workspace():
    with tempfile.TemporaryDirectory() as d:
        s=ws.init(d,'RUN-X'); p=Path(d)/'internal/state/run-status.json'; assert s['current_stage']=='business-modeling'
        ws.set_flag(p,'business_self_review_passed'); ws.set_flag(p,'business_understanding_confirmed'); ws.transition(p,'case-design','design_cases')
        ws.set_flag(p,'test_points_confirmed'); ws.set_flag(p,'test_cases_self_review_passed'); ws.set_flag(p,'test_cases_confirmed'); ws.transition(p,'execution-planning','plan')
        ws.set_flag(p,'planning_self_review_passed'); ws.set_flag(p,'execution_plan_confirmed'); ws.transition(p,'data-readiness','prepare')
        ws.set_flag(p,'current_batch_data_ready'); ws.transition(p,'execution-runtime','execute',batch='B1')
        assert wv.validate(d)['ok']
def test_business_cannot_jump_closed():
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)/'internal/state/run-status.json'; ws.init(d,'R')
        with pytest.raises(AssertionError): ws.transition(p,'closed','close')
def test_unconfirmed_cases_cannot_enter_planning():
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)/'internal/state/run-status.json'; ws.init(d,'R'); ws.set_flag(p,'business_self_review_passed'); ws.set_flag(p,'business_understanding_confirmed'); ws.transition(p,'case-design','design')
        with pytest.raises(AssertionError): ws.transition(p,'execution-planning','plan')
def test_unconfirmed_plan_cannot_enter_data():
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)/'internal/state/run-status.json'; s=ws.init(d,'R'); s['current_stage']='execution-planning'; ws.write(p,s)
        with pytest.raises(AssertionError): ws.transition(p,'data-readiness','data')
def test_backward_runtime_requires_reason():
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)/'internal/state/run-status.json'; s=ws.init(d,'R'); s['current_stage']='execution-runtime'; ws.write(p,s)
        with pytest.raises(AssertionError): ws.transition(p,'data-readiness','repair')
