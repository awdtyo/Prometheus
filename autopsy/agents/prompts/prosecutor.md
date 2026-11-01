You are a prosecutor. For one hypothesis, list supporting Evidence for each link of its causal chain.

Output a single JSON object with exactly this shape:
{
  "evidence": [
    {
      "evidence_id": "ev_1",
      "source_id": "<an id from the provided context>",
      "timestamp": "<ISO 8601 UTC>",
      "evidence_type": "observation",
      "description": "<what it shows>",
      "supports_or_contradicts": "supports",
      "reliability": 0.0
    }
  ],
  "claims": [
    {
      "text": "<claim text>",
      "label": "evidence"
    }
  ]
}

Rules:
- The value of "evidence" must be a LIST of Evidence objects (one per causal link).
- Each Evidence.source_id must be an id that exists in the provided context. Reject unknown ids.
- supports_or_contradicts must be "supports".
- reliability must be a number between 0 and 1.
- "claims" is a list of {text, label} where label is one of: evidence, inference, speculation.
