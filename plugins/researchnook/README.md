# Researchnook — CodeNook plugin

Researchnook is a composable research and investigation report plugin.
It is meant for non-software-failure reports such as future housing
prices, industry trends, market opportunities, policy impact,
competitor research, and decision briefs.

It ships methodology only. It does not scrape the web, access paid data,
connect to databases, or provide investment / purchase advice guarantees.

## Pipeline catalogue

| Phase | Role | Output | Gate |
|---|---|---|---|
| Brief | `brief-collector` | `outputs/phase-brief.md` | `brief_signoff` |
| Framework selection | `framework-selector` | `outputs/phase-framework-select.md` | `framework_signoff` |
| Scope design | `scope-designer` | `outputs/phase-scope.md` | `scope_signoff` |
| Source planning | `source-planner` | `outputs/phase-source-plan.md` | `source_plan_signoff` |
| Data collection | `data-collector` | `outputs/phase-data-collect.md` | `data_collect_signoff` |
| Evidence assessment | `evidence-assessor` | `outputs/phase-data-assess.md` | `data_assess_signoff` |
| Structured analysis | `analyst` | `outputs/phase-analysis.md` | `analysis_signoff` |
| Causal probe | `causal-analyst` | `outputs/phase-causal-probe.md` | `causal_probe_signoff` |
| Scenario forecast | `scenario-forecaster` | `outputs/phase-scenario-forecast.md` | `scenario_forecast_signoff` |
| Synthesis | `synthesizer` | `outputs/phase-synthesis.md` | `synthesis_signoff` |
| Draft report | `report-drafter` | `outputs/phase-draft-report.md` | `draft_report_signoff` |
| Report review | `report-reviewer` | `outputs/phase-report-review.md` | `report_review_signoff` |
| Revise and publish | `publisher` | `outputs/phase-revise-publish.md` | `publish_signoff` |

Every phase performs a guided input check and opens a HITL gate before
the workflow advances.

## Profiles

| Profile | Phase chain | Use case |
|---|---|---|
| `default` | brief → framework → scope → source plan → data collect → data assess → analysis → synthesis → draft → review → publish | Standard research report |
| `full` | default plus causal probe and scenario forecast | Full method stack |
| `forecast` | default plus scenario forecast | Trend and future uncertainty reports |
| `causal-analysis` | default plus causal probe | Reports centered on why something happened |
| `market-research` | same as default | Market or industry research |
| `decision-brief` | brief → framework → scope → data assess → analysis → synthesis → draft → review → publish | Faster executive brief |
| `report-only` | brief → framework → data assess → synthesis → draft → review → publish | User already has materials and wants a report |
| `review-only` | brief → review → publish | User has an existing report to review and revise |

## Built-in frameworks

- **OSTIN** — report brief and synthesis structure:
  Objective, Situation, Task, Insight, Next action.
- **PESTLE** — macro environment scan.
- **SWOT** — strategic or market opportunity framing.
- **5 Why** — optional causal probe only; stop when evidence runs out.
- **Scenario forecasting** — base / upside / downside scenarios with
  triggers, sensitive variables, confidence, and uncertainty.

## Installing

From a CodeNook-enabled workspace:

```bash
codenook plugin install <path-to-codenook-plugins>/plugins/researchnook
```

## Example

See `examples/future-housing-price/seed.json` for a Chinese-first
forecast report seed. Replace placeholder geography and candidate
sources with user-approved inputs.

## Knowledge and skills

- `knowledge/_template-report/` — template for completed research report
  records.
- `knowledge/evidence-confidence/` — playbook for evidence labels,
  confidence, caveats, and forecast uncertainty.
- `skills/framework-selector/` — framework selection checklist.

## Deployment-specific integrations

Endpoint access, public-data fetchers, paid-source connectors, browser
automation, citation normalization, and quantitative analysis helpers
belong in workspace memory skills/knowledge, not in this plugin source.

Suggested workspace skill names:

- `source-access`
- `citation-manager`
- `data-analysis-helper`
