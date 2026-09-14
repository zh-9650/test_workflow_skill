from conftest import load_script
ui=load_script(__file__,'scripts/dashboard.py','dashboard')
up=load_script(__file__,'scripts/dashboard_update.py','dashboard_update')

def plan(n=1):
    cases=[{'case_id':f'TC{i:03d}','batch_id':'B1','primary_execution':'UI' if i%2 else 'API','core_flow_id':'FLOW-01' if i<=3 else None,'evidence_plan':{'recording':{'required':i==1,'scope':'case'}}} for i in range(1,n+1)]
    return {'batches':[{'id':'B1','name':'main','case_ids':[c['case_id'] for c in cases]}],'cases':cases,'core_flows':[{'id':'FLOW-01','name':'项目主流程','case_ids':[c['case_id'] for c in cases[:3]]}]}

def test_dashboard_auto_refresh_contract():
    h=ui.render_shell(); assert "fetch('./dashboard-data.json" in h; assert 'setInterval(refresh,3000)' in h; assert '规划执行方式 vs 实际执行方式' in h

def test_planned_cases_initialize_real_total_and_progress():
    d=up.init_dashboard(plan(100)); assert d['metrics']['total_cases']==100 and d['metrics']['completed_cases']==0
    d=up.apply_event(d,{'type':'case_started','batch_id':'B1','case_id':'TC001','worker_id':'W1'}); d=up.apply_event(d,{'type':'case_finished','batch_id':'B1','case_id':'TC001','status':'PASS','actual_execution':'UI'})
    assert d['metrics']['completed_cases']==1 and d['metrics']['total_cases']==100

def test_event_updates_case_bug_review_recording_and_batch_done():
    d=up.init_dashboard(plan(2)); d=up.apply_event(d,{'type':'batch_started','batch_id':'B1','worker_id':'W1'}); d=up.apply_event(d,{'type':'case_started','batch_id':'B1','case_id':'TC001','worker_id':'W1'}); old=d['last_updated']
    d=up.apply_event(d,{'type':'case_finished','batch_id':'B1','case_id':'TC001','status':'PASS','actual_execution':'UI'}); d=up.apply_event(d,{'type':'case_blocked','batch_id':'B1','case_id':'TC002','blocked_reason_type':'upstream_case','actual_execution':'API'})
    assert d['batches'][0]['done']==2 and d['last_updated']>=old
    d=up.apply_event(d,{'type':'review_started','batch_id':'B1','reviewer_id':'R1'}); d=up.apply_event(d,{'type':'review_finished','batch_id':'B1','reviewer_id':'R1','status':'passed','retest_case_ids':[]}); assert d['reviewer_status']['B1']['status']=='passed'
    d=up.apply_event(d,{'type':'bug_submitted','bug_ref':'BUG1','case_ids':['TC1']}); assert d['defects'][0]['id']=='BUG1'
    assert d['recordings']['TC001']['status']=='pending'; d=up.apply_event(d,{'type':'recording_updated','scope_ref':'TC001','status':'completed'}); assert d['recordings']['TC001']['status']=='completed'

def test_core_flow_and_method_metrics():
    d=up.init_dashboard(plan(4)); assert d['core_flows'][0]['total']==3 and d['metrics']['planned_execution']['UI']==2 and d['metrics']['planned_execution']['API']==2
    for i in [1,2,3]: d=up.apply_event(d,{'type':'case_finished','batch_id':'B1','case_id':f'TC{i:03d}','status':'PASS','actual_execution':'UI' if i%2 else 'API'})
    assert d['core_flows'][0]['done']==3 and d['core_flows'][0]['status']=='completed'


def test_planned_100_cases_reaches_50_of_100_without_changing_total():
    d=up.init_dashboard(plan(100))
    for i in range(1,51):
        cid=f'TC{i:03d}'
        d=up.apply_event(d,{'type':'case_finished','batch_id':'B1','case_id':cid,'status':'PASS','actual_execution':'UI' if i%2 else 'API'})
    assert d['metrics']['completed_cases']==50
    assert d['metrics']['total_cases']==100
