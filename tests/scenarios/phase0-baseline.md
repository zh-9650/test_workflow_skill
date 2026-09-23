# Phase 0 baseline (2026-09-23)

- Starting branch and commit: `main` at `14636d59cab9723a98a09c7f5ba81c36e972ad2f`, equal to `origin/main` at the start of this phase.
- Starting worktree: no tracked changes; `新版测试Skill改造计划.md` was the user's untracked source plan and remains protected.
- Repository shape: nine Run skills, 20 Python scripts, no `tests/` or TypeScript automation project before this phase.
- Existing Router Run State used `schema_version=3`; execution contracts had no schema version gate. New execution contracts use version 2 independently of Run State.
- Baseline Contract probes: Execution Plan accepted an API Case without runner, driver or script target and a UI recording with `scope=batch`; Worker Task had no schema version or task hash; Reviewer accepted no agent session ID; Case Result required Expected/Evidence but no script hash or official runner report.
- Phase 0 red evidence: `tests/test_execution_plan_v2.py` rejected three old/unknown schema samples only after the version gate was added; before the gate all three unexpectedly passed validation. The version constant test initially failed because the shared version module did not yet exist.

The full behavior acceptance remains in Phases 1–6. These probes do not establish real Worker/Reviewer dispatch or API/UI smoke.
