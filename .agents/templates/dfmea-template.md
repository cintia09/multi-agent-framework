# DFMEA — T-NNN: [Task Title]

> Design Failure Mode and Effects Analysis
> The Implementer must complete this document before submitting for code review.

## Risk Analysis Table

| # | Component/Module | Potential Failure Mode | Failure Effect | S | O | D | RPN | Recommended Action | Status |
|---|-----------------|----------------------|----------------|---|---|---|-----|--------------------|--------|
| 1 | | | | | | | | | pending |
| 2 | | | | | | | | | pending |
| 3 | | | | | | | | | pending |

## Scoring Criteria

**S (Severity)**: 1-10
- 1-3: Minor impact, barely noticeable to user
- 4-6: Moderate impact, degraded but usable
- 7-8: Severe impact, feature unusable
- 9-10: Catastrophic — data loss / security breach / system crash

**O (Occurrence)**: 1-10
- 1-3: Rare (<1% probability)
- 4-6: Occasional (1-10%)
- 7-8: Frequent (10-50%)
- 9-10: Near certain (>50%)

**D (Detection)**: 1-10
- 1-3: High detection rate (automated test coverage)
- 4-6: Medium detection rate (manual testing required)
- 7-8: Low detection rate (triggered only in special scenarios)
- 9-10: Nearly undetectable (only manifests in production)

**RPN = S × O × D**
- RPN ≤ 50: Low risk — document only
- 50 < RPN ≤ 100: Medium risk — action recommended
- RPN > 100: ⛔ High risk — **must take action before submitting for review**

## Status Definitions
- `pending`: Identified, awaiting action
- `mitigated`: Action taken, risk reduced
- `accepted_risk`: Team accepts the risk (reason required)
- `resolved`: Fully eliminated

## Summary

- **High-risk items (RPN>100)**: N items, all mitigated/resolved ✅ / ⛔ unresolved remain
- **Total risk items**: N items
- **Completion date**: [ISO 8601]
- **Owner**: implementer
