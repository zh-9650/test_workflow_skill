# Project assets and shared learning

## Authorities

```text
project-context/dom-maps/<page-id>.yaml
project-context/operation-assets/<asset-id>.md
project-context/automation-assets/<asset-id>.yaml
project-context/data-recipes/<asset-id>.yaml
project-context/regression-assets/<asset-id>.yaml
~/.claude/test-learning/records/<learning-id>.yaml
```

DOM maps describe what exists, stable locators, containers, readiness,
dependencies, page fingerprint, evidence, and lifecycle. Operation assets
describe how to act/wait/prove/recover. Automation assets bind code digests to
Case, Oracle, Actor, data, DOM, and operation versions. Data recipes implement
provision/verify/cleanup/reconcile. Regression assets preserve failure and fix
verification obligations.

Use:

```text
asset_registry.py validate|rebuild|search|promote|transition|delete
operation_assets.py validate|rebuild|search|transition
shared_learning.py ingest|feedback|search|transition|rebuild
skill_improvement.py regress|propose
```

Technical assets progress through candidate → verified → stable → degraded →
retired. AI may manage this lifecycle automatically behind validation gates.
Referenced assets are retired/superseded, not physically erased. Staging and
unreferenced candidates may be deleted; secrets are removed immediately with a
redacted tombstone.

Shared learning progresses observed → corroborated → generalized → degraded →
retired. One evidence-backed event is immediately searchable as `observed`.
Generalize after two projects, or three independent Runs plus a counterexample
challenge. Strip URLs/IPs, credentials, real data, one-run IDs, temporary DOM
refs, and project-only business conclusions.

Different strategies for the same mechanism, applicability, and failure
signature are recorded as a conflict and both are degraded until the
contradiction is resolved. A manual transition cannot bypass the independent-
observation threshold.

After a shared strategy is used, submit one `feedback` event with
`supported|contradicted|not-applicable`, a generalized applicability note and
evidence references. Delivery is idempotent. Contradiction or a newly observed
non-applicable condition automatically degrades the record; evidence and
project/Run identities are stored only as anonymous references.

At every checkpoint append a learning event or a reason the discovery is not
transferable. At result review, `asset-settlement.json` must settle every asset
and learning event as promoted/ingested, deferred, rejected, or degraded.

For generalized learning, first run a full digest-stable Skill-group regression
with `skill_improvement.py regress`, then create the proposal with `propose`.
The generated proposal remains `pending-human-confirmation`; the tool cannot
publish or edit the core Skill group. Publication is a separate change that
requires an active granted `core-skill-change` decision.
