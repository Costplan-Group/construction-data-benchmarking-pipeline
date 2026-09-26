# Numbered SQL migrations applied by database/migrate.py
#
# Naming: NNN_description.sql (zero-padded version prefix).
# Scripts should be idempotent (IF NOT EXISTS / CREATE OR ALTER) so re-runs are safe.
# Applied versions are recorded in dbo.SchemaVersion (checksum + AppliedAt).
#
# Out of band (not auto-migrated — need passwords / optional reporting):
#   database/schema/002_reporting_views.sql
#   database/security/001_ai_readonly_login.sql
#   database/security/002_pbi_readonly_login.sql
