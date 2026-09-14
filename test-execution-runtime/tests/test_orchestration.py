import json, pytest
from conftest import load_script
orc=load_script(__file__,'scripts/runtime_orchestrator.py','runtime_orchestrator')
br=load_script(__file__,'scripts/batch_result.py','batch_result')

def ep(): return {'screenshots':['E1'],'recording':False,'api':[],'network':[],'files':[]}
def c(cid,deps=None,batch='B01'): return {'case_id':cid,'batch_id':batch,'primary_execution':'UI','dependencies':deps or [],'expected_results':[{'id':'E1','expected':'expected'}],'evidence_plan':ep()}
def plan(): return {'batches':[{'id':'B01','name':'main','case_ids':['TC001','TC002','TC003']}], 'cases':[c('TC001'),c('TC002'),c('TC003',['TC002'])]}
def manifest(b='B01'): return {'batch_id':b,'data_required':False,'reason':'no setup','objects':[]}
def passr(cid): return {'case_id':cid,'actual_execution':'UI','status':'PASS','expected_results':[{'id':'E1','actual':'ok','result':'pass','evidence_refs':['x.png']}]}
def failr(cid): return {'case_id':cid,'actual_execution':'UI','status':'FAIL','reason_type':'product_issue','expected':'expected','actual':'bad','evidence_refs':['f.png'],'reproduced':True,'expected_results':[{'id':'E1','actual':'bad','result':'fail','evidence_refs':['f.png']}]}
def blockedr(cid,dep='TC002'): return {'case_id':cid,'actual_execution':'UI','status':'BLOCKED','blocked_reason_type':'upstream_case','blocked_reason':'dependency failed','affected_by':dep,'expected_results':[{'id':'E1','actual':'not executed','result':'blocked','evidence_refs':['f.png']}]}
def results(): return [passr('TC001'),failr('TC002'),blockedr('TC003')]
def wsr(ids): return {'status':'passed','findings':[],'checked_case_ids':ids,'checks':{'all_cases_checked':True,'all_expected_checked':True,'execution_method_checked':True,'evidence_binding_checked':True,'failure_classification_checked':True,'file_cleanup_checked':True}}
def reviewer(status='passed',retest=None,return_stage=None,findings=None): return {'status':status,'findings':findings or [],'retest_case_ids':retest or [],'return_stage':return_stage,'checks':{'completeness_checked':True,'method_consistency_checked':True,'judgement_checked':True,'evidence_checked':True,'abnormal_classification_checked':True}}
def make(): return orc.RuntimeOrchestrator(plan(),'B01',manifest(),{'environment_ready':True})

def test_main_worker_review_reviewer_flow():
    x=make(); t=x.create_task(); assert t['case_order']==['TC001','TC002','TC003']; x.start_worker(); x.submit_worker_results(results()); x.submit_worker_self_review(wsr(t['case_order'])); out=x.submit_reviewer(reviewer()); assert out['status']=='completed'; assert x.snapshot()['status']=='completed'
def test_reviewer_rework_generates_local_retest():
    x=make(); t=x.create_task(); x.start_worker(); x.submit_worker_results(results()); x.submit_worker_self_review(wsr(t['case_order'])); out=x.submit_reviewer(reviewer('rework_required',['TC001'],findings=['evidence weak'])); assert out['retest_task']['case_order']==['TC001']; x.apply_retest([passr('TC001')],wsr(['TC001']),reviewer()); assert x.snapshot()['status']=='completed'
def test_precheck_returns_data_readiness():
    bad={'batch_id':'B01','data_required':True,'objects':[{'object_type':'project','object_ref':'P1','creation':{'business_entry':'api','implementation':'direct'},'state_applicable':True,'target_state':'approved','current_state':'draft','verified':True,'read_back_verified':True,'relations_verified':True,'case_ids':['TC001']}]}
    p=orc.batch_precheck(plan(),'B01',bad,{'environment_ready':True}); assert p['status']=='return_to_data' and 'target state not reached' in p['reason']
def test_reviewer_can_return_upstream():
    x=make(); t=x.create_task(); x.start_worker(); x.submit_worker_results(results()); x.submit_worker_self_review(wsr(t['case_order'])); out=x.submit_reviewer(reviewer('return_upstream',return_stage='execution_planning',findings=['plan conflicts with UI'])); assert out['return_stage']=='execution_planning'
def test_batch_cannot_complete_without_reviewer_passed():
    v={'case_ids':['TC001'],'case_results':[{'case_id':'TC001'}],'worker_self_review':wsr(['TC001']),'reviewer':reviewer('rework_required',['TC001'],findings=['x']),'status':'completed'}
    with pytest.raises(AssertionError): br.validate(v)
def test_worker_self_review_must_pass_before_reviewer():
    x=make(); x.create_task(); x.start_worker(); x.submit_worker_results(results())
    with pytest.raises(AssertionError): x.submit_worker_self_review({'status':'failed','findings':['x']})
def test_worker_passed_requires_structured_checks():
    x=make(); t=x.create_task(); x.start_worker(); x.submit_worker_results(results()); bad=wsr(t['case_order']); bad['checks']['evidence_binding_checked']=False
    with pytest.raises(AssertionError): x.submit_worker_self_review(bad)
def test_reviewer_passed_requires_structured_checks():
    x=make(); t=x.create_task(); x.start_worker(); x.submit_worker_results(results()); x.submit_worker_self_review(wsr(t['case_order'])); bad=reviewer(); bad['checks']['evidence_checked']=False
    with pytest.raises(AssertionError): x.submit_reviewer(bad)
def test_orchestrator_rejects_invalid_case_result_before_review():
    x=make(); x.create_task(); x.start_worker(); bad=results(); bad[0]['expected_results'][0]['evidence_refs']=[]
    with pytest.raises(AssertionError): x.submit_worker_results(bad)
def test_dependency_failure_requires_upstream_block():
    x=make(); x.create_task(); x.start_worker(); bad=results(); bad[2]=passr('TC003')
    with pytest.raises(AssertionError): x.submit_worker_results(bad)
def test_duplicate_worker_result_rejected_before_dict_conversion():
    x=make(); x.create_task(); x.start_worker(); bad=results()+[passr('TC001')]
    with pytest.raises(AssertionError,match='duplicate result for case_id=TC001'): x.submit_worker_results(bad)

def test_cross_batch_dependency_context_pass_and_block():
    p={'batches':[{'id':'B01','case_ids':['TC001']},{'id':'B02','case_ids':['TC020']}],'cases':[c('TC001',batch='B01'),c('TC020',['TC001'],batch='B02')]}
    x=orc.RuntimeOrchestrator(p,'B02',manifest('B02'),{'environment_ready':True},{'TC001':{'status':'PASS'}}); t=x.create_task(); assert t['dependency_context']['TC001']['status']=='PASS'; x.start_worker(); x.submit_worker_results([passr('TC020')])
    y=orc.RuntimeOrchestrator(p,'B02',manifest('B02'),{'environment_ready':True},{'TC001':{'status':'FAIL'}}); y.create_task(); y.start_worker(); y.submit_worker_results([blockedr('TC020','TC001')]); assert y.case_results[0]['status']=='BLOCKED'

def test_retest_uses_full_case_contract():
    x=make(); t=x.create_task(); x.start_worker(); x.submit_worker_results(results()); x.submit_worker_self_review(wsr(t['case_order'])); x.submit_reviewer(reviewer('rework_required',['TC001'],findings=['redo']))
    bad={'case_id':'TC001'}
    with pytest.raises(AssertionError): x.apply_retest([bad],wsr(['TC001']),reviewer())

def test_file_backed_orchestrator_writes_task_and_full_retest(tmp_path):
    p=plan(); pp=tmp_path/'plan.json'; mp=tmp_path/'manifest.json'; cp=tmp_path/'context.json'
    pp.write_text(json.dumps(p),encoding='utf-8'); mp.write_text(json.dumps(manifest()),encoding='utf-8'); cp.write_text(json.dumps({'environment_ready':True}),encoding='utf-8')
    st=orc.prepare_run_files(pp,'B01',mp,cp,tmp_path); assert (tmp_path/'internal/execution/tasks/B01-task.json').exists() and st['status']=='pending'
    rp=tmp_path/'results.json'; rp.write_text(json.dumps(results()),encoding='utf-8'); orc.accept_worker_results_files(tmp_path,'B01',rp)
    sr=tmp_path/'self.json'; sr.write_text(json.dumps(wsr(['TC001','TC002','TC003'])),encoding='utf-8'); orc.accept_self_review_files(tmp_path,'B01',sr)
    rr=tmp_path/'review.json'; rr.write_text(json.dumps(reviewer('rework_required',['TC001'],findings=['redo'])),encoding='utf-8'); out=orc.accept_reviewer_files(tmp_path,'B01',rr); assert out['state']['status']=='needs_rework'
    rres=tmp_path/'retest-results.json'; rres.write_text(json.dumps([passr('TC001')]),encoding='utf-8'); orc.accept_retest_results_files(tmp_path,'B01',rres)
    rs=tmp_path/'retest-self.json'; rs.write_text(json.dumps(wsr(['TC001'])),encoding='utf-8'); orc.accept_retest_self_review_files(tmp_path,'B01',rs)
    rv=tmp_path/'retest-review.json'; rv.write_text(json.dumps(reviewer()),encoding='utf-8'); done=orc.accept_retest_reviewer_files(tmp_path,'B01',rv); assert done['status']=='completed'

def test_retest_carries_dependency_context_for_non_retested_case():
    p={'batches':[{'id':'B1','case_ids':['TA','TB']}],'cases':[c('TA',batch='B1'),c('TB',['TA'],batch='B1')]}
    x=orc.RuntimeOrchestrator(p,'B1',manifest('B1'),{'environment_ready':True}); t=x.create_task(); x.start_worker(); x.submit_worker_results([passr('TA'),passr('TB')]); x.submit_worker_self_review(wsr(t['case_order'])); out=x.submit_reviewer(reviewer('rework_required',['TB'],findings=['redo dependent case']))
    assert out['retest_task']['case_order']==['TB'] and out['retest_task']['dependency_context']['TA']['status']=='PASS'
    x.apply_retest([passr('TB')],wsr(['TB']),reviewer()); assert x.status=='completed'

def test_precheck_revalidates_manifest_instead_of_trusting_forged_readiness():
    bad={'batch_id':'B01','data_required':True,'readiness':{'ready':True,'checked_at':'fake'},'objects':[{'object_type':'project','object_ref':'P1','creation':{'business_entry':'api','implementation':'direct'},'state_applicable':True,'target_state':'approved','current_state':'draft','verified':True,'read_back_verified':True,'relations_verified':True,'case_ids':['TC001']}]}
    out=orc.batch_precheck(plan(),'B01',bad,{'environment_ready':True}); assert out['status']=='return_to_data' and 'target state not reached' in out['reason']


def test_cross_batch_blocked_dependency_requires_downstream_blocked():
    p={'batches':[{'id':'B01','case_ids':['TC001']},{'id':'B02','case_ids':['TC020']}],'cases':[c('TC001',batch='B01'),c('TC020',['TC001'],batch='B02')]}
    x=orc.RuntimeOrchestrator(p,'B02',manifest('B02'),{'environment_ready':True},{'TC001':{'status':'BLOCKED'}})
    t=x.create_task(); assert t['dependency_context']['TC001']['status']=='BLOCKED'
    x.start_worker(); x.submit_worker_results([blockedr('TC020','TC001')])
    assert x.case_results[0]['status']=='BLOCKED'
