# Scoring formula

Each hypothesis receives a raw score in ``[0, 1]`` computed deterministically
from the graph, the observations, and the evidence. No LLM is involved, and the
weights are fixed defaults --- they are **not chosen by looking at ground
truth** for any scenario.

## Formula

::

    score =
        w_explained        * frac_explained
      + w_edge_conf        * avg_edge_confidence
      + w_evidence         * avg_verified_evidence_reliability
      - penalty_contradiction  * (contradiction_count / chain_len)
      - penalty_unexplained  * (unexplained / total_observations)
      - penalty_unsupported  * (unsupported_links / chain_links)

The result is clamped to ``[0, 1]``.

## Terms

* ``frac_explained`` -- fraction of observations whose subsystem is named by
  the hypothesis chain (a chain naming ``eps`` explains every ``eps``
  observation).
* ``avg_edge_confidence`` -- mean confidence of the graph edges along the chain
  (missing edges count as 0.0).
* ``avg_verified_evidence_reliability`` -- mean reliability of the
  supporting-cited evidence that verifies as supporting. Auto-filled
  preliminary citations are excluded (see ``docs/evaluation.md``).
* ``contradiction_count`` -- verified contradicting citations cited by the
  hypothesis, normalized by chain length.
* ``unsupported_links`` -- chain links with no supporting graph edge,
  normalized by the number of links.
* ``total_observations`` -- total observations in the run.

## Default weights (``autopsy.analysis.scoring.ScoringConfig``)

| Weight | Default | Meaning |
|---|---|---|
| ``w_explained`` (coverage_weight) | 0.4 | how many observations the chain explains |
| ``w_edge_conf`` (consistency_weight) | 0.3 | average edge confidence along the chain |
| ``w_evidence`` (evidence_weight) | 0.3 | verified supporting-evidence reliability |
| ``penalty_contradiction`` (contradiction_penalty) | 0.15 | per verified contradiction (normalized) |
| ``penalty_unexplained_downstream`` | 0.10 | fraction of observations left unexplained |
| ``penalty_unsupported_link`` | 0.10 | fraction of chain links without a graph edge |

The three positive weights sum to 1.0; penalties are subtracted and can bring
a score below zero before clamping, so a hypothesis with no support and many
contradictions scores 0.0 while a well-supported one can approach 1.0.

## Range

Raw scores are clamped to ``[0, 1]``. Because hypotheses can near-tie (for
example when they reference the same subsystem), raw scores should **not** be
used alone for display or ranking. The UI should use a presentation-level
**relative support share** (see ``docs/evaluation.md`` and
``docs/api-contract.md`` section ``f``).
