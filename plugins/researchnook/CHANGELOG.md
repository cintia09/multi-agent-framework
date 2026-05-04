# Researchnook plugin changelog

## 0.1.0 — initial general research report workflow

Added:

- New `researchnook` plugin identity for general research,
  investigation, market-analysis, trend-analysis, scenario-forecasting,
  and decision-brief workflows.
- Thirteen HITL-gated phases covering brief, framework selection, scope,
  source planning, data collection, evidence assessment, analysis,
  optional causal probe, optional scenario forecast, synthesis, drafting,
  review, and publish.
- Profiles: `default`, `full`, `forecast`, `causal-analysis`,
  `market-research`, `decision-brief`, `report-only`, and `review-only`.
- Built-in framework semantics for OSTIN, PESTLE, SWOT, 5 Why, and
  scenario forecasting.
- Evidence and confidence labeling playbook.
- Framework selector skill.
- Future housing price example seed.

Notes:

- v0.1.0 does not implement web scraping, paid data access, database
  connectors, or investment / purchase advice guarantees.
- 5 Why is optional and scoped to causal analysis; forecast reports use
  scenarios rather than single-point predictions.
