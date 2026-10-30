"""Application services that orchestrate investigations.

Routes call services; services call ``autopsy`` and ``backend.db``. No FastAPI
imports belong in this package, and business logic stays out of API routes.
"""
