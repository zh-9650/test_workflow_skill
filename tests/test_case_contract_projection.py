from __future__ import annotations

from conftest import load_script


def test_parameterized_projection_keeps_step_checkpoints_and_scopes_evidence() -> None:
    contract = load_script(
        "test-case-design/scripts/case_contract.py",
        "case_contract_instance_projection",
    )
    source = {
        "case_templates": [
            {
                "case_id": "TC-PARAM-001",
                "title": "parameterized case",
                "target_action": "submit",
                "steps": [
                    {"step_id": "STEP-1", "action": "submit first variation"},
                    {"step_id": "STEP-2", "action": "submit second variation"},
                ],
                "assertions": [
                    {
                        "assertion_id": "ASSERT-A",
                        "checkpoint": "intermediate",
                        "step_id": "STEP-1",
                        "expected": "first variation is accepted",
                    },
                    {
                        "assertion_id": "ASSERT-B",
                        "checkpoint": "step",
                        "step_id": "STEP-2",
                        "expected": "second variation is accepted",
                    },
                ],
                "evidence_policy": {
                    "level": "standard",
                    "recording_required": False,
                    "required": [
                        {"kind": "runner_report", "assertion_ids": ["ASSERT-A", "ASSERT-B"]}
                    ],
                },
            }
        ],
        "execution_instances": [
            {
                "instance_id": "INSTANCE-A",
                "case_id": "TC-PARAM-001",
                "expected_assertion_ids": ["ASSERT-A"],
                "test_point_ids": ["TP-1"],
                "test_data": {"value": "a"},
            },
            {
                "instance_id": "INSTANCE-B",
                "case_id": "TC-PARAM-001",
                "expected_assertion_ids": ["ASSERT-B"],
                "test_point_ids": ["TP-1"],
                "test_data": {"value": "b"},
            },
        ],
    }

    projected = contract.project_execution_cases(source)

    assert [case["case_id"] for case in projected] == [
        "TC-PARAM-001--INSTANCE-A",
        "TC-PARAM-001--INSTANCE-B",
    ]
    assert projected[0]["expected_results"][0]["step_id"] == "STEP-1"
    assert projected[0]["expected_results"][0]["checkpoint"] == "intermediate"
    assert projected[1]["expected_results"][0]["step_id"] == "STEP-2"
    assert projected[1]["evidence_policy"]["required"][0]["assertion_ids"] == ["ASSERT-B"]
    assert projected[0]["evidence_policy"]["required"][0]["assertion_ids"] == ["ASSERT-A"]
