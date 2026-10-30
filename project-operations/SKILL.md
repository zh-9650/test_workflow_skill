---
name: project-operations
description: Search, create, validate, degrade, and retire reusable project operation assets for testing stages. Use when a routed test stage needs login, navigation, dynamic configuration, component, mutation, verification, data, or cleanup know-how, or after a semantic operation reaches a verified business checkpoint.
---

# Project Operations

Instruction version: `vnext-2`.

Manage DOM, semantic operation, data-recipe, automation, regression, and shared
learning assets without turning old selectors or one successful click into
trusted automation.

Read [operation-asset-contract.md](references/operation-asset-contract.md).
Read [knowledge-settlement.md](references/knowledge-settlement.md) when
creating/updating/degrading/retiring any non-operation asset or shared learning.

## Search before rediscovery

Search by semantic intent plus current environment, page/container, component,
role, business state, dynamic input type, and required proof:

```text
python <skill-root>/scripts/operation_assets.py search --project-root <project-root> --intent "<semantic intent>" --environment "<environment>" --role "<role>"
```

For a resumed Run, use assets already bound in `runtime-state.json` before a
broad search. For a new Run, search summaries/index first and open only relevant
Markdown assets.

Completion criterion: every selected asset has current applicability evidence;
otherwise return “no reliable asset” and enter controlled exploration.

## Apply dynamically

Resolve configuration, IDs, entities, page state, and values from the current
environment. Reconfirm preconditions and business object identity. Never replay
temporary DOM refs, fixed row indexes, tab numbers, or one-run entity IDs.

An asset's proof scope limits what it can establish. A navigation asset cannot
prove persistence; a successful API setup asset cannot prove an equivalent UI
entry.

## Decide immediately at a checkpoint

After each successful or informative failed semantic operation, record exactly
one decision:

- `created`: a new candidate semantic method;
- `updated`: changed conditions, strategy, postcondition, or failure knowledge;
- `validated`: an existing asset worked under current conditions;
- `degraded(branch,reason)`: a named applicability branch failed while other
  proven branches remain reusable;
- `not-reusable(reason)`: one-off, unsafe, underproven, or no transferable
  method.

Write new/changed candidates to the Run staging area first. Merge them
atomically into `project-context/operation-assets/<asset-id>.md` after review.
Unchanged reuse appends a validation event rather than rewriting the asset.

## Manage lifecycle by independent evidence

Use:

- `candidate`: one verified checkpoint or observed human action;
- `verified`: replayed in a newly observed session with postconditions;
- `stable`: survived relevant variations/challenges;
- `degraded`: evidence shows one applicability branch is unreliable;
- `retired`: capability removed, proof obsolete, or superseded.

Do not promote by a mechanical success count. Human-performed operations remain
candidate until AI independently verifies the result and successfully replays
them in a new context.

Degrade only the evidenced environment/page/component/role/state branch.
Never translate a single changed component into whole-asset
`not-reusable`; preserve and revalidate unaffected branches.
Deduplicate negative knowledge by failure signature and applicability; redact
secrets and one-off identifiers and give transient facts an expiry.

## Rebuild and validate the projection

Markdown assets are authoritative. Rebuild the search index:

```text
python <skill-root>/scripts/operation_assets.py rebuild --project-root <project-root>
```

Validate:

```text
python <skill-root>/scripts/operation_assets.py validate --project-root <project-root>
```

The index is disposable. Never manually maintain competing manifest,
procedure, and guided-plan authorities.

Validate/search all YAML assets with `asset_registry.py`. Stage new or changed
automation under the Run, then use `promote`; this enforces three clean
independent contexts, effect/cleanup/secret gates, and base-version conflict
checks. Use `transition` to update/degrade/retire. Hard delete only an
unreferenced candidate; referenced assets remain as tombstones.

Ingest each transferable, evidence-backed learning event immediately with
`shared_learning.py ingest`. `observed` knowledge is a strategy hint, never
current product truth or authorization. Search the shared library after bound
project assets and before rediscovery. Never edit a core Skill from a normal
Run. After learning is `generalized`, use `scripts/skill_improvement.py regress`
to capture a digest-bound full Skill-group baseline and `propose` to create a
`pending-human-confirmation` improvement proposal. This tool intentionally has
no publication command: implementation and publication require a separate
active `core-skill-change` decision with `decision_effect=grant`.

## Asset completion

An asset is usable only when it identifies the semantic intent, supported
inputs, applicability/non-applicability, dynamic resolution, preconditions,
preferred and alternative user-level strategies, component/business
postconditions, proof scope, safe failure/recovery, compatibility fingerprint,
source evidence, lifecycle, and protected secret references.

Never store plaintext passwords, tokens, cookies, authorization values, or full
browser storage state.
