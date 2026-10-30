# Operation asset contract

Store one authoritative Markdown file per asset:

```text
project-context/operation-assets/<asset-id>.md
```

## Frontmatter

```yaml
---
schema_version: vnext-2
asset_id: auth.login.standard
semantic_name: Login and verify identity
asset_type: authentication
intent: login
status: candidate
environments: [test]
roles: [admin]
components: [form]
business_states: [logged-out]
proof_scope: [identity, role, refresh-persistence]
compatibility_fingerprint:
  app: hr-system
  version: unknown
  framework: vue
  component_library: element-plus
source_runs: [RUN-...]
last_verified_at: null
---
```

Allowed asset types:

- authentication and identity verification;
- navigation/page reachability;
- dynamic configuration/reference resolution;
- component interaction;
- business mutation;
- persistence/impact verification;
- data preparation and cleanup.

## Body

```markdown
# Semantic name

## Purpose and supported inputs
## Applicability
## Non-applicability
## Dynamic-value resolution
## Preconditions
## Preferred user-level strategy
## Alternative strategies
## Component checkpoint
## Business postconditions
## Proof scope and evidence
## Failure signatures and recovery
## Sensitive references
## Validation and lifecycle history
```

Type-specific assets omit irrelevant sections and add fields their operation
needs. Do not mechanically copy a universal form.

Authentication assets store only credential-source references and human-action
boundaries. Missing plaintext credentials is a required safety property, not
an applicability failure or retirement reason.

## Promotion review

Select relevant challenges rather than success counts:

- newly observed session;
- compatible/different fingerprint;
- role variation;
- page/business-state variation;
- dynamic parameter variation;
- business postcondition proof;
- failure branch and safe return.

Record which challenges were applied and their evidence.
