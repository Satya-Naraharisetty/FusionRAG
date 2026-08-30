"""Single source of truth for the integration-test Postgres URL.

The pytest integration suite (test_auth, test_search, ...) creates and
truncates tables (users, refresh_sessions, ...), so it MUST run against a
dedicated database — never the dev DB (fusion_rag on port 5432).

The default below points at the dedicated `postgres-test` compose service
(port 5433). Override with TEST_DATABASE_URL to use any other Postgres —
for example CI spins up its own ephemeral instance and sets this env var.
"""

import os

DEFAULT_TEST_DATABASE_URL = (
    "postgresql://postgres:postgres@localhost:5433/fusion_rag_test"
)

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)
