---
id: framework-selector
name: framework-selector
title: "Research framework selector"
summary: "Choose a fit-for-purpose mix of OSTIN, PESTLE, SWOT, 5 Why, and scenario forecasting for Researchnook reports."
tags:
  - researchnook
  - skill
  - framework
  - research
---

# Research framework selector

Use this skill during `framework_select` or when a role needs to justify
why a framework belongs in the report.

## Inputs

- Research topic.
- Audience and decision goal.
- Output type: decision brief, full report, market research, forecast, causal analysis, review.
- Time horizon and geography.
- Available evidence and constraints.

## Selection rules

| If the report needs... | Prefer | Avoid |
|------------------------|--------|-------|
| A compact decision brief | OSTIN + evidence labels | Full PESTLE/SWOT unless the brief asks for it |
| Macro environment scan | PESTLE | 5 Why unless a causal problem is explicit |
| Strategic position / opportunity | SWOT + evidence labels | SWOT without external evidence |
| Cause of an observed outcome | 5 Why or driver tree | Forcing exactly five layers |
| Future uncertainty | Scenario forecasting | Single-point predictions |
| Final report structure | OSTIN + report template | Framework jargon in executive summary |

## Output shape

```markdown
## Framework recommendation
| Framework | Use | Phase | Reason | Caveat |
|---|---|---|---|---|

## Rejected frameworks
| Framework | Reason rejected |
|---|---|
```

## Safety checks

- 5 Why is optional and should stop when evidence runs out.
- Scenario forecasting must include base/upside/downside, triggers,
  confidence, and uncertainty.
- Do not imply that framework selection gives access to data sources.
