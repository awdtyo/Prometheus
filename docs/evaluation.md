# Evaluation metrics

The evaluation harness computes the twelve ``EvaluationMetrics`` fields
documented in ``docs/api-contract.md`` for every completed
``(scenario, seed, variant)`` run and writes them into
``RunResult.evaluation_metrics``.

Ground truth (``fixtures/expected/*_ground_truth.json``) is read *only* by the
evaluation module and is never passed to hypothesis agents. When ground truth is
unavailable for a scenario, the metrics that require it
(``root_cause_accuracy``, ``fault_localization_accuracy``,
``causal_chain_accuracy``) are reported as ``0.0`` rather than fabricated.

## The twelve metrics

| Field | Inputs | Formula | Range | 0.0 means | 1.0 means |
|---|---|---|---|---|---|
| ``root_cause_accuracy`` | leading hypothesis chain; ground-truth injected fault target subsystem | 1.0 if any chain node's subsystem equals the target subsystem, else 0.0 | {0, 1} | leading chain does not name the root-cause subsystem | leading chain names the root-cause subsystem |
| ``fault_localization_accuracy`` | all hypothesis chains; ground-truth injected fault target subsystem | 1.0 if any hypothesis chain names the target subsystem, else 0.0 | {0, 1} | no hypothesis names the root-cause subsystem | at least one hypothesis names it |
| ``causal_chain_accuracy`` | leading hypothesis chain; ground-truth ``expected_causal_sequence`` | fraction of expected steps whose subsystem appears in the leading chain | [0, 1] | none of the expected steps are recovered | every expected step is recovered |
| ``evidence_coverage`` | leading hypothesis chain; observations | fraction of observations whose subsystem is referenced by the leading chain | [0, 1] | no observation's subsystem is named by the chain | every observation's subsystem is named |
| ``temporal_ordering_accuracy`` | leading hypothesis chain node timestamps | 1.0 if cited node timestamps are non-decreasing, else 0.0 | {0, 1} | chain cites timestamps out of order | chain cites timestamps in order (or < 2 nodes) |
| ``contradiction_handling`` | supporting evidence; contradicting citations | 1.0 - (contradicted supporting evidence count / supporting evidence count) | [0, 1] | every supporting evidence item is contradicted | no supporting evidence is contradicted |
| ``unsupported_claim_rate`` | leading hypothesis chain; graph edges | share of causal-chain links with no supporting graph edge | [0, 1] | every chain link is unsupported | every chain link is supported |
| ``runtime_seconds`` | wall clock around the run | seconds elapsed | [0, inf) | — | — |
| ``evidence_weight`` | scoring config weight | ``ScoringConfig.w_evidence`` | [0, 1] | — | — |
| ``consistency_weight`` | scoring config weight | ``ScoringConfig.w_edge_conf`` | [0, 1] | — | — |
| ``coverage_weight`` | scoring config weight | ``ScoringConfig.w_explained`` | [0, 1] | — | — |
| ``contradiction_penalty`` | scoring config weight | ``ScoringConfig.penalty_contradiction`` | [0, 1] | — | — |

## Notes on interpretation

* ``evidence_coverage`` is subsystem-scoped: a hypothesis chain that names the
  ``eps`` subsystem counts every ``eps`` observation as explained, even if the
  chain does not cite that observation's exact id. This is intentional --- the
  metric measures whether the hypothesis identifies the right *subsystem*, not
  whether it cites every individual observation.
* ``unsupported_claim_rate`` is graph-grounded: it measures whether each
  consecutive link in the leading chain is backed by a graph edge. A chain can
  name the right subsystems (high ``evidence_coverage``) while its links are not
  grounded in the graph (high ``unsupported_claim_rate``). That combination is a
  red flag: the hypothesis names the right area but its causal ordering is not
  supported by the graph.
* ``contradiction_handling`` treats an evidence item as contradicted only when
  the same evidence id is cited as *supporting* somewhere and as
  *contradicting* somewhere else. Uncited evidence is neither supporting nor
  contradicted.
* The four weight/penalty fields (``evidence_weight``, ``consistency_weight``,
  ``coverage_weight``, ``contradiction_penalty``) are the scoring-config values
  used to compute each hypothesis's raw score; they are reported for
  reproducibility and are not themselves performance scores.

## Presentation vs. raw scores

Hypothesis raw scores (``Hypothesis.score``) are the weighted scoring-model
output. Because several hypotheses can tie or near-tie (for example when they
reference the same subsystem), the UI should not rank by raw score alone. A
presentation-level **relative support share** --- each hypothesis's verified
supporting-evidence reliability divided by the total verified reliability ---
spreads tied scores apart and is what should be displayed and used for ranking.
Raw scores are retained in ``RunResult``; the relative support share is a
derived display value. See ``docs/api-contract.md`` section ``g``.

## Invalidated results

``data/eval/results.real.json.invalid`` holds a pre-audit recording for
``decoy_sensor_bias`` that is **not** a current result. It was produced before
this scoring/metrics audit and is internally inconsistent
(``root_cause_accuracy=1.0`` and ``evidence_coverage=1.0`` while
``unsupported_claim_rate=1.0``: every claim unsupported yet full coverage).
It is kept only as a record and must not be quoted. Current results are
produced by ``python -m autopsy evaluate`` and written to
``data/eval/results.<mode>.json`` (fake-LLM numbers test the plumbing only;
see above).
