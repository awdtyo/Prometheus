"""HTTP interface: routing, request validation, and response serialization.

Routes delegate to ``backend.services``. They must not contain investigation
orchestration, graph work, or SQL.
"""
