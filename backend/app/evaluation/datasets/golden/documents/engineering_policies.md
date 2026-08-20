# Engineering Operating Procedures & Reliability Policies

## Section 1: Service Level Agreements (SLAs) and SLOs
The platform commits to a standard availability Service Level Objective (SLO) of 99.95% uptime for standard tier tenants and 99.99% (four nines) for enterprise tier tenants, calculated on a rolling 30-day window.
- **P95 Latency Target**: Hybrid RAG query processing and candidate retrieval must return within 250 milliseconds.
- **P99 Latency Target**: Complete end-to-end multi-agent answer synthesis must complete within 2500 milliseconds.

## Section 2: Incident Classification & Severity Levels
1. **SEV-1 (Critical Outage)**: Total service degradation or data loss impacting >10% of active users. Initial response time: ≤ 15 minutes. Incident commander assigned, status page updated every 30 minutes.
2. **SEV-2 (Major Incident)**: Core capability failure (e.g., reranker offline or vector search failing) affecting a subset of users with no immediate workaround. Initial response time: ≤ 30 minutes. Status updates every 60 minutes.
3. **SEV-3 (Minor Incident)**: Non-critical feature disruption or localized degraded performance. Initial response time: ≤ 4 hours during standard business hours.
4. **SEV-4 (Low Impact)**: Minor cosmetic bugs, documentation inaccuracies, or administrative tooling defects. Initial response time: ≤ 24 hours.

## Section 3: Code Quality, Review & Testing Standards
- All production pull requests require a minimum of two peer review approvals, including at least one designated Code Owner for the affected module.
- Automated test coverage must remain at or above 85% line coverage across backend services.
- Pull requests that introduce quality regressions in RAG retrieval (e.g., MRR drop > 0.03 or precision drop > 0.02) are automatically blocked by the CI evaluation gate.
- Direct commits to `main` branch are strictly prohibited via GitHub branch protection rules.

## Section 4: Release Management & Change Freezes
- Deployments occur automatically via CI/CD pipelines utilizing blue-green deployment strategies with automatic canary rollback if error rates exceed 0.05%.
- Annual end-of-year change freeze is enforced from December 15 through January 5, permitting only critical security patches and SEV-1 emergency fixes.
