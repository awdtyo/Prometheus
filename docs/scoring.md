# Scoring formula

score = w_explained * frac_explained
      + w_edge_conf * avg_edge_confidence
      + w_evidence * avg_verified_evidence_reliability
      - penalty_contradiction * contradiction_count
      - penalty_unexplained_downstream * (unexplained / total_obs)
      - penalty_unsupported_link * unsupported_links

Weights in ScoringConfig. Deterministic, no LLM.
