"""Load telemetry, event logs, and YAML configuration into typed models.

Planned responsibilities: telemetry readers, event-log readers, and
subsystem/scenario YAML loaders. Validation failures should surface as typed
domain errors rather than leaking pandas or PyYAML exceptions.
"""
