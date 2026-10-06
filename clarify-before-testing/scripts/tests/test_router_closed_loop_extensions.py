import json
import hashlib
import importlib.util
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = REPO_ROOT / "clarify-before-testing" / "scripts" / "workflow_state.py"


def load_workflow():
    spec = importlib.util.spec_from_file_location("workflow_state_closed_loop_test", WORKFLOW)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_record_waiting_state(tmp_path):
    workflow_state = load_workflow()
    run_dir = tmp_path / "work" / "test-runs" / "RUN-TEST-001"
    run_dir.mkdir(parents=True)
    state = workflow_state.init(run_dir, "RUN-TEST-001")
    state_file = run_dir / "internal/state/run-status.json"

    # Valid waiting state
    updated = workflow_state.record_waiting_state(
        state_file,
        "waiting_for_worker_slot",
        reason="Host subagent concurrency limit reached"
    )
    assert updated["next_action"]["type"] == "waiting_for_worker_slot"
    assert updated["next_action"]["reason"] == "Host subagent concurrency limit reached"

    # Another valid waiting state
    updated2 = workflow_state.record_waiting_state(
        state_file,
        "waiting_for_fix_deployment",
        reason="Bug #101 fixed on git, awaiting staging deployment"
    )
    assert updated2["next_action"]["type"] == "waiting_for_fix_deployment"

    # Invalid waiting state rejected
    with pytest.raises(AssertionError, match="unsupported waiting type"):
        workflow_state.record_waiting_state(state_file, "invalid_waiting_state")


def test_snapshot_rejects_unbound_legacy_plan(tmp_path):
    workflow_state = load_workflow()
    run_dir = tmp_path / "work" / "test-runs" / "RUN-SNAPSHOT-001"
    run_dir.mkdir(parents=True)
    state = workflow_state.init(run_dir, "RUN-SNAPSHOT-001")
    state_file = run_dir / "internal/state/run-status.json"

    # Add mock execution plan
    plan_path = run_dir / "internal/execution/execution-plan.json"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps({
        "schema_version": 2,
        "cases": [
            {"case_id": "TC-001", "batch_id": "B01", "primary_execution": "API"},
            {"case_id": "TC-002", "batch_id": "B01", "primary_execution": "UI"}
        ]
    }), encoding="utf-8")

    # Add mock ledger with reviewer-confirmed cases
    ledger_path = run_dir / "internal/execution/results/case-results-ledger.json"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps({
        "cases": {
            "TC-001": {"status": "PASS", "final_result": "PASS", "reviewer_confirmed": True},
            "TC-002": {"status": "BLOCKED", "final_result": "BLOCKED", "reviewer_confirmed": True, "blocked_reason": "Waiting on prerequisite data"}
        }
    }), encoding="utf-8")

    before = state_file.read_bytes()
    with pytest.raises(AssertionError):
        workflow_state.create_stage_snapshot(state_file)
    assert state_file.read_bytes() == before
    assert not list((run_dir / 'deliverables').glob('stage-snapshot-*.json'))


def _deployment_run(workflow_state, tmp_path):
    run_dir = tmp_path / "work" / "test-runs" / "RUN-DEPLOY-001"
    run_dir.mkdir(parents=True)
    workflow_state.init(run_dir, "RUN-DEPLOY-001")
    state_file = run_dir / "internal/state/run-status.json"
    plan_path = run_dir / "internal/execution/execution-plan.json"
    plan = {
        "schema_version": 3,
        "target_environment": {"env_id": "staging", "version": "v1.0.0"},
        "cases": [{"case_id": "TC-001", "batch_id": "B01", "primary_execution": "API"}],
    }
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    state = json.loads(state_file.read_text(encoding="utf-8"))
    state["confirmation_bindings"]["execution-plan"] = {
        "contract_path": str(plan_path.resolve()),
        "contract_sha256": hashlib.sha256(plan_path.read_bytes()).hexdigest(),
    }
    state_file.write_text(json.dumps(state), encoding="utf-8")
    evidence = run_dir / "evidence/deployment/staging-v1.0.1.json"
    evidence.parent.mkdir(parents=True)
    evidence.write_text(json.dumps({"version": "v1.0.1", "env": "staging"}), encoding="utf-8")
    impact = {
        "old_pass_retest_needed": False,
        "affected_pass_cases": [],
        "data_recheck_needed": True,
        "rationale": "Fix changes authentication data",
    }
    return run_dir, state_file, evidence, impact


def test_record_deployment_requires_impact_analysis(tmp_path):
    workflow_state = load_workflow()
    _, state_file, evidence, _ = _deployment_run(workflow_state, tmp_path)
    with pytest.raises(AssertionError, match="impact_decision"):
        workflow_state.record_deployment_verified(
            state_file, "staging", "v1.0.1", "http_health_endpoint", evidence
        )


def test_record_deployment_binds_plan_and_writes_immutable_event(tmp_path):
    workflow_state = load_workflow()
    run_dir, state_file, evidence, impact = _deployment_run(workflow_state, tmp_path)
    with pytest.raises(AssertionError, match="planned env"):
        workflow_state.record_deployment_verified(
            state_file, "production", "v1.0.1", "http_health_endpoint", evidence, impact
        )
    event = workflow_state.record_deployment_verified(
        state_file, "staging", "v1.0.1", "http_health_endpoint", evidence, impact
    )
    event_path = run_dir / event["event_ref"]
    assert event_path.is_file()
    assert hashlib.sha256(event_path.read_bytes()).hexdigest() == event["event_sha256"]
    assert event["impact_decision"] == impact


@pytest.mark.parametrize('action', ['waiting', 'snapshot'])
def test_closed_run_is_immutable(tmp_path, action):
    workflow = load_workflow()
    run, state_file, _, _ = _deployment_run(workflow, tmp_path)
    state = workflow.read(state_file)
    state['current_stage'] = 'closed'
    workflow.write(state_file, state)
    workflow.write(run / 'internal/execution/results/case-results-ledger.json', {
        'cases': {'TC-001': {'status': 'PASS', 'reviewer_confirmed': True}}})
    before = {p.relative_to(run): p.read_bytes() for p in run.rglob('*') if p.is_file()}
    with pytest.raises(AssertionError, match='closed Run is immutable'):
        if action == 'waiting':
            workflow.record_waiting_state(state_file, 'waiting_for_worker_slot')
        else:
            workflow.create_stage_snapshot(state_file)
    assert {p.relative_to(run): p.read_bytes() for p in run.rglob('*') if p.is_file()} == before


@pytest.mark.parametrize('contract_rejects', [False, True])
def test_close_reopens_final_contract_with_the_actual_run_path(tmp_path, monkeypatch, contract_rejects):
    # Contract spy verifies propagation; actual Final Review is tested separately.
    from types import SimpleNamespace
    w = load_workflow()
    run = tmp_path / 'run'
    w.init(run, 'close-path')
    sf = run / 'internal/state/run-status.json'
    review = run / 'internal/review/final.json'
    report = run / 'deliverables/test-report.md'
    w.write(review, {'test_marker': 'bound-artifact'})
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text('bound report', encoding='utf8')
    state = w.read(sf)
    state.update(current_stage='result-review', final_review_status='passed',
                 final_review_source={'path': str(review), 'sha256': w.sha256(review),
                                      'report': {'path': str(report), 'sha256': w.sha256(report)}})
    w.write(sf, state)
    calls = []
    def validate(payload, run_dir):
        calls.append((payload, Path(run_dir)))
        if contract_rejects:
            raise AssertionError('unresolved formal work')
        return {'ok': True}
    monkeypatch.setattr(w, '_load_module', lambda *args: SimpleNamespace(validate=validate))
    if contract_rejects:
        with pytest.raises(AssertionError, match='unresolved formal work'):
            w.transition(sf, 'closed', 'none')
        assert w.read(sf)['current_stage'] == 'result-review'
    else:
        assert w.transition(sf, 'closed', 'none')['current_stage'] == 'closed'
    assert calls == [({'test_marker': 'bound-artifact'}, run.resolve())]


def _load_test_helper(relative, name):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _snapshot_run(tmp_path):
    """Synthetic file-backed contracts only; no real host dispatch claim."""
    w = load_workflow()
    run = tmp_path / 'run'
    w.init(run, 'snapshot-contract')
    state_file = run / 'internal/state/run-status.json'
    state = w.read(state_file)
    business = {'model_version': 'b1'}
    points = {'design_version': 'p1', 'business_model_version': 'b1',
              'test_points': [{'tp_id': 'TP1', 'priority': 'P1'}]}
    case = {'case_id': 'C1', 'case_type': 'ordinary', 'priority': 'P1',
            'title': 'Inspect isolated fixture', 'target_action': 'Read fixture',
            'test_point_ids': ['TP1'], 'preconditions_applicable': False,
            'steps': [{'step_id': 'S1', 'action': 'Read fixture'}],
            'assertions': [{'assertion_id': 'E1', 'checkpoint': 'final',
                            'expected': 'The fixture value equals 1', 'test_point_ids': ['TP1']}],
            'evidence_policy': {'level': 'standard', 'recording_required': False, 'required': []}}
    design = {'schema_version': '2.0.0', 'case_design_version': 'c1',
              'business_model_version': 'b1', 'test_point_version': 'p1',
              'expansion_records': [{'tp_id': 'TP1', 'strategy': 'direct', 'rationale': 'One observation', 'execution_instance_ids': ['I1']}],
              'case_templates': [case],
              'execution_instances': [{'instance_id': 'I1', 'case_id': 'C1', 'test_point_ids': ['TP1'], 'variation': 'one fixture',
                                       'test_data': {}, 'expected_assertion_ids': ['E1'], 'result_tracking': {'independent': True}}],
              'test_cases_self_review': {'status': 'passed', **{key: True for key in ['point_coverage_complete', 'instance_coverage_complete', 'assertion_mapping_complete', 'failure_masking_checked', 'parameterization_checked', 'complex_cases_checked', 'no_unresolved_expected']}},
              'presentation_sync': {'status': 'passed', 'checks': {key: True for key in ['main_document_updated', 'review_document_updated', 'pending_questions_reflected', 'model_consistency_checked']}}}
    for kind, payload in [('business-understanding', business), ('test-points', points), ('test-cases', design)]:
        cp = run / f'internal/design/{kind}.json'
        ap = run / f'deliverables/{kind}.md'
        rp = run / f'deliverables/{kind}-review.md'
        w.write(cp, payload); ap.write_text('Synthetic fixture', encoding='utf8'); rp.write_text('Synthetic review', encoding='utf8')
        record = {'path': str(ap), 'sha256': w.sha256(ap), 'contract_path': str(cp), 'contract_sha256': w.sha256(cp),
                  'review_path': str(rp), 'review_sha256': w.sha256(rp), 'self_review_status': 'passed'}
        state['artifacts'][kind] = record
        state['confirmation_bindings'][kind] = dict(record)
        sf, cf = w.ARTIFACT_FLAGS[kind]; state['confirmations'][sf] = state['confirmations'][cf] = True
    cases_mod = w._load_module(REPO_ROOT / 'test-case-design/scripts/case_contract.py', 'snapshot_design')
    cases_mod.validate(design, points, business)
    pc = cases_mod.project_execution_cases(design)[0]
    pc.update(primary_execution='人工', batch_id='B01', dependencies=[], automation={'required': False},
              manual_execution={'reason': 'Synthetic manual observation contract', 'steps': ['Read fixture'], 'result_entry': 'File-backed result'},
              evidence_plan={'level': 'standard', 'screenshots': [], 'recording': False, 'api': [], 'network': [], 'files': []},
              jev_policy={'mode': 'none'})
    planning = _load_test_helper('test-execution-planning/scripts/tests/test_execution_planning_v2.py', 'snapshot_plan_samples')
    plan = planning._sample_valid_plan({})
    plan.update(cases=[pc], batches=[{'id': 'B01', 'case_ids': ['C1'], 'parallel_safe': False}], confirmed_case_ids=['C1'],
                confirmed_cases_sha256=state['confirmation_bindings']['test-cases']['contract_sha256'])
    plan['data_requirements'][0]['case_ids'] = ['C1']
    pp = run / 'internal/execution/execution-plan.json'; w.write(pp, plan)
    state['current_stage'] = 'execution-planning'; w.write(state_file, state)
    doc = run / 'deliverables/04-execution-plan.md'; doc.write_text('Synthetic plan', encoding='utf8')
    w.register_artifact(state_file, 'execution-plan', doc, 'passed', pp)
    w.confirm_artifact(state_file, 'execution-plan', doc)
    ledger = run / 'internal/execution/results/case-results-ledger.json'
    w.write(ledger, {'cases': {'C1': {'status': 'PASS', 'reviewer_confirmed': True}}})
    return w, run, state_file, pp, ledger


@pytest.mark.parametrize('mutation', ['unbound', 'changed', 'upstream', 'legacy', 'runtime', 'preparation'])
def test_snapshot_requires_current_contracts_and_real_review_sources(tmp_path, mutation):
    w, run, sf, pp, ledger = _snapshot_run(tmp_path)
    if mutation == 'unbound':
        state = w.read(sf); state['confirmation_bindings'].pop('execution-plan'); w.write(sf, state)
    elif mutation == 'changed':
        pp.write_text(pp.read_text(encoding='utf8') + ' ', encoding='utf8')
    elif mutation == 'upstream':
        (run / 'deliverables/test-points.md').write_text('Changed', encoding='utf8')
    elif mutation == 'legacy':
        plan = w.read(pp); plan['schema_version'] = 2; w.write(pp, plan)
        state = w.read(sf)
        for key in ['artifacts', 'confirmation_bindings']:
            state[key]['execution-plan']['contract_sha256'] = w.sha256(pp)
        w.write(sf, state)
    elif mutation == 'preparation':
        w.write(ledger, {'cases': {'C1': {'status': 'BLOCKED', 'reviewer_confirmed': True, 'source_kind': 'data_readiness',
                                        'data_readiness_review': {'status': 'passed', 'affected_case_ids': ['C1']}}}})
    before = {p.relative_to(run): p.read_bytes() for p in run.rglob('*') if p.is_file()}
    with pytest.raises(AssertionError):
        w.create_stage_snapshot(sf)
    assert {p.relative_to(run): p.read_bytes() for p in run.rglob('*') if p.is_file()} == before


def _preparation_snapshot(tmp_path):
    w, run, sf, pp, ledger = _snapshot_run(tmp_path)
    helper = _load_test_helper('test-defect-handling/scripts/tests/test_data_readiness_review.py', 'snapshot_preparation_samples')
    ref, review = helper._review(run)
    w.write(ledger, {'cases': {'C1': {'status': 'BLOCKED', 'reviewer_confirmed': True, 'source_kind': 'data_readiness',
                                    'data_readiness_review_ref': ref, 'data_readiness_review': review}}})
    state = w.read(sf); state['open_defects'] = ['pending-preparation-bug']; w.write(sf, state)
    return w, run, sf


def test_snapshot_accepts_independent_preparation_block_without_fake_runtime(tmp_path):
    w, run, sf = _preparation_snapshot(tmp_path)
    result = w.create_stage_snapshot(sf)
    assert result['cases_summary'] == {'C1': 'BLOCKED'}
    assert result['is_final_review'] is False
    assert result['open_defects'] == ['pending-preparation-bug']
    assert w.read(sf)['current_stage'] != 'closed'
    assert w.read(sf)['final_review_status'] is None


@pytest.mark.parametrize('target', ['existing', 'ancestor', 'escape'])
def test_snapshot_output_path_rejection_preserves_files(tmp_path, target):
    w, run, sf = _preparation_snapshot(tmp_path)
    out = run / 'deliverables/existing.json'
    out.write_bytes(b'keep me')
    path = out if target == 'existing' else run / 'deliverables' if target == 'ancestor' else tmp_path / 'outside.json'
    before = {p.relative_to(run): p.read_bytes() for p in run.rglob('*') if p.is_file()}
    with pytest.raises(AssertionError, match='output_path'):
        w.create_stage_snapshot(sf, path)
    assert {p.relative_to(run): p.read_bytes() for p in run.rglob('*') if p.is_file()} == before


def _runtime_snapshot(tmp_path):
    w, run, sf, pp, ledger = _snapshot_run(tmp_path)
    import sys
    sys.path.insert(0, str(REPO_ROOT / 'test-execution-runtime/scripts'))
    runtime = w._load_module(REPO_ROOT / 'test-execution-runtime/scripts/runtime_orchestrator.py', 'snapshot_fixture_runtime')
    plan = w.read(pp)
    task = runtime.build_task(plan, 'B01', 'internal/execution/context.json', 'internal/data/manifests/B01.json')
    task_ref = 'internal/execution/tasks/B01.json'; w.write(run / task_ref, task)
    ev_ref = 'evidence/B01/C1/value.json'; w.write(run / ev_ref, {'value': 1})
    result = {'schema_version': 3, 'case_id': 'C1', 'status': 'PASS', 'actual_execution': '人工',
              'task_id': task['task_id'], 'task_hash': task['task_hash'], 'agent_session_id': 'synthetic-worker',
              'target_environment': task['target_environment'], 'deployment_version': task['deployment_version'],
              'expected_results': [{'id': 'E1', 'actual': 'value=1', 'result': 'pass', 'evidence_refs': [ev_ref]}]}
    results_ref = 'internal/execution/results/B01.json'; w.write(run / results_ref, [result])
    self_ref = 'internal/execution/reviews/B01-self.json'
    self_review = {'task_id': task['task_id'], 'input_task_hash': task['task_hash'], 'agent_session_id': 'synthetic-worker',
                  'results_sha256': w.sha256(run / results_ref), 'status': 'passed', 'checked_case_ids': ['C1'],
                  'checks': {key: True for key in runtime._load_module(REPO_ROOT / 'test-execution-runtime/scripts/worker_review.py', 'fixture_worker').MANDATORY},
                  'findings': ['Synthetic contract only']}
    w.write(run / self_ref, self_review)
    review_task = runtime._build_reviewer_task(run, 'B01', task, task_ref, results_ref, self_ref, [result], self_review)
    review_task_ref = 'internal/execution/tasks/B01-reviewer.json'; w.write(run / review_task_ref, review_task)
    reviewer = runtime._load_module(REPO_ROOT / 'test-execution-runtime/scripts/reviewer_contract.py', 'fixture_reviewer')
    review = {'schema_version': 3, 'reviewer_task_id': review_task['task_id'], 'input_task_hash': review_task['task_hash'],
              'input_results_sha256': w.sha256(run / results_ref), 'agent_session_id': 'synthetic-reviewer',
              'status': 'passed', 'checked_case_ids': ['C1'], 'checks': {key: True for key in reviewer.MANDATORY},
              'findings': ['Synthetic contract only'], 'retest_case_ids': [], 'return_stage': None}
    review_ref = 'internal/execution/reviews/B01-review.json'; w.write(run / review_ref, review)
    def receipt(role, frozen, session, outputs, status):
        return {'agent_role': role, 'receipt_status': 'completed', 'task_id': frozen['task_id'], 'task_hash': frozen['task_hash'],
                'agent_session_id': session, 'dispatch_source': 'codex_subagent_tool', 'host_dispatch_ref': 'synthetic-contract',
                'started_at': '2026-10-04T00:00:00Z', 'finished_at': '2026-10-04T00:01:00Z',
                'outputs': {ref: w.sha256(run / ref) for ref in outputs}, 'result_status': status}
    state = {'batch_id': 'B01', 'status': 'completed', 'task_ref': task_ref, 'worker_results_ref': results_ref,
             'worker_self_review_ref': self_ref, 'reviewer_task_ref': review_task_ref,
             'review_history': [{'type': 'initial_or_batch_review', 'review': review}], 'reviewer': review,
             'worker_dispatch_receipt': receipt('execution_worker', task, 'synthetic-worker', [results_ref, self_ref], runtime._result_status_summary([result])),
             'reviewer_dispatch_receipt': receipt('result_reviewer', review_task, 'synthetic-reviewer', [review_ref], 'passed')}
    w.write(run / 'internal/execution/runtime-state/B01-state.json', state)
    w.write(ledger, {'cases': {'C1': {'status': 'PASS', 'reviewer_confirmed': True, 'runtime_result': result}}})
    return w, run, sf


def test_snapshot_accepts_frozen_runtime_chain(tmp_path):
    w, run, sf = _runtime_snapshot(tmp_path)
    assert w.create_stage_snapshot(sf)['cases_summary'] == {'C1': 'PASS'}


def test_snapshot_accepts_native_windows_receipt_output_separators(tmp_path):
    if __import__('os').name != 'nt':
        pytest.skip('Native Windows receipt path semantics')
    w, run, sf = _runtime_snapshot(tmp_path)
    path = run / 'internal/execution/runtime-state/B01-state.json'
    state = w.read(path)
    receipt = state['worker_dispatch_receipt']
    receipt['outputs'] = {ref.replace('/', '\\'): digest for ref, digest in receipt['outputs'].items()}
    w.write(path, state)
    assert w.create_stage_snapshot(sf)['cases_summary'] == {'C1': 'PASS'}


@pytest.mark.parametrize('artifact', ['result', 'self', 'review', 'snapshot', 'receipt'])
def test_snapshot_rejects_tampered_runtime_sources_without_writing(tmp_path, artifact):
    w, run, sf = _runtime_snapshot(tmp_path)
    state_path = run / 'internal/execution/runtime-state/B01-state.json'
    state = w.read(state_path)
    if artifact == 'receipt':
        state['reviewer_dispatch_receipt']['agent_session_id'] = 'synthetic-worker'; w.write(state_path, state)
    elif artifact == 'snapshot':
        task = w.read(run / state['reviewer_task_ref'])
        ref = next(iter(task['artifact_snapshot_manifest'].values()))['snapshot_ref']
        (run / ref).write_text('tampered', encoding='utf8')
    else:
        ref = {'result': state['worker_results_ref'], 'self': state['worker_self_review_ref'], 'review': 'internal/execution/reviews/B01-review.json'}[artifact]
        (run / ref).write_text('{}', encoding='utf8')
    before = {p.relative_to(run): p.read_bytes() for p in run.rglob('*') if p.is_file()}
    with pytest.raises(AssertionError):
        w.create_stage_snapshot(sf)
    assert {p.relative_to(run): p.read_bytes() for p in run.rglob('*') if p.is_file()} == before


@pytest.mark.parametrize('link_kind', ['file', 'ancestor', 'deliverables'])
def test_snapshot_rejects_junction_or_symlink_outputs(tmp_path, link_kind):
    w, run, sf = _preparation_snapshot(tmp_path)
    target = run / 'deliverables/target' if link_kind == 'ancestor' else run / 'target'
    target.mkdir()
    before_state = sf.read_bytes()
    if link_kind == 'file':
        original = run / 'deliverables/original.json'; original.write_bytes(b'preserve')
        link = run / 'deliverables/link.json'
        try: link.symlink_to(original)
        except OSError: pytest.skip('Host does not allow file symlinks')
        output = link
    else:
        link = run / 'deliverables' if link_kind == 'deliverables' else run / 'deliverables/linked'
        if link_kind == 'deliverables':
            # Preserve fixture documents while replacing only the temporary directory entry.
            link.rename(run / 'saved-deliverables')
            import shutil
            for document in (run / 'saved-deliverables').iterdir():
                shutil.copy2(document, target / document.name)
        import subprocess
        if __import__('os').name == 'nt':
            completed = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(target)], capture_output=True)
            assert completed.returncode == 0, completed.stderr
        else:
            link.symlink_to(target, target_is_directory=True)
        output = link / 'snapshot.json'
    with pytest.raises(AssertionError):
        w.create_stage_snapshot(sf, output)
    assert sf.read_bytes() == before_state
    assert not (target / 'snapshot.json').exists()
    if link_kind == 'file': assert original.read_bytes() == b'preserve'
