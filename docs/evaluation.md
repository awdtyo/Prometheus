# Evaluation metrics

The evaluation harness populates all 12 ``EvaluationMetrics`` fields from
docs/api-contract.md into ``RunResult.evaluation_metrics`` for every
(scenario, seed, variant) run.

## Metric definitions

| Field | Meaning |
|---|---|
| ``root_cause_accuracy`` | 1.0 if the leading hypothesis chain references the ground-truth injected fault's target subsystem, else 0.0. Requires ground truth; 0.0 when unavailable. |
| ``fault_localization_accuracy`` | 1.0 if any hypothesis chain references the target subsystem, else 0.0. Requires ground truth; 0.0 when unavailable. |
| ``causal_chain_accuracy`` | Fraction of expected causal-sequence steps whose subsystem appears in the leading hypothesis chain. Requires ground truth; 0.0 when unavailable. |
| ``evidence_coverage`` | Fraction of observations explained by the leading hypothesis chain (subsystem or observation id referenced in the chain). |
| ``temporal_ordering_accuracy`` | 1.0 if the leading chain's cited node timestamps are non-decreasing, else 0.0. |
| ``contradiction_handling`` | 1.0 minus the share of verified evidence that is contradicted; higher is better. |
| ``unsupported_claim_rate`` | Share of causal-chain links that have no supporting graph edge; lower is better. |
| ``runtime_seconds`` | Wall-clock time for the run. |
| ``evidence_weight`` | Scoring weight on verified supporting evidence reliability. |
| ``consistency_weight`` | Scoring weight on average edge confidence along the chain. |
| ``coverage_weight`` | Scoring weight on the fraction of observations explained. |
| ``contradiction_penalty`` | Score penalty applied per verified contradiction. |

## Baselines

Three baselines run alongside the pipeline:

* ``earliest_anomaly`` — blames the subsystem of the earliest observation.
* ``single_llm`` — one LLM call with a condensed telemetry/event summary, no graph.
* ``no_spec`` — full pipeline with graph spec constraints disabled (ablation).

## Boundary

Ground truth (``fixtures/expected/*_ground_truth.json``) is loaded only by the
evaluation module and is never passed to hypothesis agents.
