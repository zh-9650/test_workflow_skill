"""Version constants shared by the testing workflow contracts.

Execution artifacts use schema v3.  The existing Router run-state format is
already v3 and is intentionally versioned independently; it must not be
downgraded when the execution contract changes.
"""

WORKFLOW_VERSION = "2.0.0"
EXECUTION_SCHEMA_VERSION = 3
RUN_STATE_SCHEMA_VERSION = 3
