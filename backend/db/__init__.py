"""SQLite persistence for backend-owned records.

Schema and queries live here. This package must not import FastAPI or ``autopsy``;
services translate between domain models and stored records.
"""
