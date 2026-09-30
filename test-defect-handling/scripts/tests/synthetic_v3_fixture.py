"""Build current contract test inputs in a temporary copy. This is not host dispatch evidence.

Retain historical raw API/runner artifacts as synthetic samples. Generate new
Task and review contracts; never rewrite the archived Phase 5 fixture itself.
"""
import importlib.util
import json
import shutil
import sys
from pathlib import Path


def build(run_dir):
    repo=Path(__file__).resolve().parents[3]
    runtime_dir=repo/'test-execution-runtime/scripts'
    sys.path.insert(0,str(runtime_dir))
    spec=importlib.util.spec_from_file_location('synthetic_v3_runtime',runtime_dir/'runtime_orchestrator.py')
    runtime=importlib.util.module_from_spec(spec); spec.loader.exec_module(runtime)
    read=runtime._read_json; write=runtime._write_json; sha=runtime._sha256
    plan_path=run_dir/'internal/execution/execution-plan.json'; plan=read(plan_path)
    plan['schema_version']=3
    plan['target_environment']={'env_id':'synthetic-contract','initial_deployment_version':'fixture-v1'}
    write(plan_path,plan)
    ledger_path=run_dir/'internal/execution/results/case-results-ledger.json'; ledger=read(ledger_path)
    dashboard_path=run_dir/'dashboard/dashboard-data.json'; dashboard=read(dashboard_path)
    for state_path in sorted((run_dir/'internal/execution/runtime-state').glob('*-state.json')):
        state=read(state_path); bid=state['batch_id']
        historical_review_task=read(run_dir/state['reviewer_task_ref'])
        for source_ref,snapshot in historical_review_task['artifact_snapshot_manifest'].items():
            dest=run_dir/source_ref; dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(run_dir/snapshot['snapshot_ref'],dest)
        task=read(run_dir/state['task_ref']); task.update(schema_version=3,target_environment='synthetic-contract',deployment_version='fixture-v1')
        runtime.seal_task(task); write(run_dir/state['task_ref'],task)
        results=read(run_dir/state['worker_results_ref']); worker=f'synthetic-v3-{bid}-worker'; reviewer=f'synthetic-v3-{bid}-reviewer'
        for row in results:
            row.update(schema_version=3,target_environment='synthetic-contract',deployment_version='fixture-v1',task_hash=task['task_hash'],agent_session_id=worker)
            ledger['cases'][row['case_id']]['runtime_result']=row
        write(run_dir/state['worker_results_ref'],results)
        self_ref=state['worker_self_review_ref']; self_review=state['worker_self_review']
        self_review.update(input_task_hash=task['task_hash'],agent_session_id=worker,results_sha256=sha(run_dir/state['worker_results_ref']),findings=['Synthetic v3 contract fixture; no actual host dispatch claim'])
        write(run_dir/self_ref,self_review)
        reviewer_task=runtime._build_reviewer_task(run_dir,bid,task,state['task_ref'],state['worker_results_ref'],self_ref,results,self_review)
        write(run_dir/state['reviewer_task_ref'],reviewer_task)
        review=state['reviewer']; review.update(schema_version=3,agent_session_id=reviewer,input_task_hash=reviewer_task['task_hash'],input_results_sha256=sha(run_dir/state['worker_results_ref']),findings=['Synthetic contract test only'])
        output_ref=f'internal/execution/dispatch/{bid}-v3-synthetic-review.json'; write(run_dir/output_ref,review)
        for role,key,session,dispatched_task,outputs,result_status in [
            ('execution_worker','worker_dispatch_receipt',worker,task,{state['worker_results_ref']:sha(run_dir/state['worker_results_ref']),self_ref:sha(run_dir/self_ref)},runtime._result_status_summary(results)),
            ('result_reviewer','reviewer_dispatch_receipt',reviewer,reviewer_task,{output_ref:sha(run_dir/output_ref)},review['status']),
        ]:
            receipt=state[key]
            receipt.update(agent_session_id=session,task_hash=dispatched_task['task_hash'],host_dispatch_ref=f'synthetic-contract-only:{session}',outputs=outputs,result_status=result_status)
            write(run_dir/state['worker_receipt_ref' if role=='execution_worker' else 'reviewer_receipt_ref'],receipt)
        state.update(worker_self_review=self_review,reviewer=review,review_history=[{'type':'initial_or_batch_review','review':review}],retest_history=[],retest_tasks=[],active_retest=None)
        write(state_path,state)
        for row in dashboard['batches']:
            if row['id']==bid: row.update(worker_session_id=worker,reviewer_session_id=reviewer)
    write(ledger_path,ledger); write(dashboard_path,dashboard)
    state_path=run_dir/'internal/state/run-status.json'; state=read(state_path)
    state['confirmation_bindings']['execution-plan'].update(contract_path=str(plan_path.resolve()),contract_sha256=sha(plan_path))
    write(state_path,state)
