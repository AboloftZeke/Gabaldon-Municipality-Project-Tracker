# Clean application schema

This branch uses a fresh migration baseline. Existing development records do not
need to be preserved. Use a **new, empty database**, not an existing database with
the previous migration history. No existing database is dropped by this change.

## Model and table map

All application models live in `apps.system.models`. Every table has an explicit
`system_` prefix and snake_case name.

| Previous model | Current model | Current table |
| --- | --- | --- |
| `Infrastructure_Project` | `InfrastructureProject` | `system_infrastructure_project` |
| `Non_Infrastructure_Project` | `NonInfrastructureProject` | `system_non_infrastructure_project` |
| `Infrastructure_Schedule` | `InfrastructureSchedule` | `system_infrastructure_schedule` |
| `Project_Inspection` | `ProjectInspection` | `system_project_inspection` |
| `Project_Image` | `ProjectImage` | `system_project_image` |
| `ProjectPublicationRevision` | `ProjectRevision` | `system_project_revision` |
| `Financial` | `FinancialRecord` | `system_financial_record` |
| `UserFlag` | `UserRole` | `system_user_role` |
| `Reports` | `ProjectReport` | `system_project_report` |
| `Reports_Template` | `ReportTemplate` | `system_report_template` |

Unchanged model names with newly explicit readable table names:
`InfrastructureCategory` → `system_infrastructure_category`,
`NonInfrastructureCategory` → `system_non_infrastructure_category`,
`ImplementingOffice` → `system_implementing_office`,
`FundSource` → `system_fund_source`,
`InfrastructureProgressUpdate` → `system_infrastructure_progress_update`,
`InspectionEvidence` → `system_inspection_evidence`, and
`LoginOTPChallenge` → `system_login_otp_challenge`.
The progress-update/inspection join table is
`system_infrastructure_progress_update_supporting_inspections`.
`Project`, `Address`, and `Contractor` retain their existing table names.

## Fields and relations

| Previous | Current |
| --- | --- |
| `infrastructure_title`, `non_infra_name` | `title` |
| `infrastructure_description` | `description` |
| Non-infrastructure `non_infra_category` | `category` (`category_id` in SQL) |
| `snapshot_data` | `snapshot` |
| `supersedes_revision` | `previous_revision` (`previous_revision_id` in SQL) |
| `is_current_public_revision` | `is_current_public` |
| Project `publication_revisions` | `revisions` |
| User `flags` | `role_assignment` |
| User submitted/reviewed/published `*_project_publication_revisions` | `*_project_revisions` |

Existing descriptive project, image, inspection, schedule, and revision primary
keys are retained. Forms, ORM lookups, services, admin, templates, management
commands, and tests use the new names. Snapshot content retains its public data
structure; the JSON model field is now named `snapshot`.

## Removed and retained models

Removed the legacy models in `apps.infrastructure` and `apps.non_infrastructure`
and their tables `infrastructure_infrastructureproject` and
`non_infrastructure_noninfrastructureproject`. Their remaining runtime use was
location choices, now held in `apps.system.choices.BARANGAY_CHOICES`.

Removed both unmanaged project compatibility models that mapped onto normalized
tables. Views and forms now use the normalized models directly. Removed all
project compatibility properties and migrated template callers to real fields
and relationships. Cover selection still prioritizes the selected active image.

Removed unmanaged `UserProfile`, `system_legacy_userprofile_archive`, and the
runtime `User.profile` monkey patch. Permissions continue to read persisted office
and role assignments; missing assignments do not grant office access. Superuser
administration remains explicit.

Replaced the three apps' old schema/data-copy/archive migrations with
`system.0001_initial` and `system.0002_seed_categories`. The other two apps no longer
own database models. Removed migration-only backfill tests and the obsolete manual
dashboard fixture script; current workflow tests and fresh-schema regression
tests cover the supported schema. Fresh databases do not automatically publish
projects or reconstruct obsolete password/profile tables.

Retained report metadata and report-template models, renamed as requested. They
have no current report-generation callers, but belong to the intended normalized
design rather than the replaced legacy schema; absence of a caller alone does
not establish that the planned reporting entities should be deleted. All active
financial, schedule, image, inspection, progress, revision, OTP, and role models
remain. Django authentication, permissions/groups, content types, sessions, admin
log, and migration tables are unchanged.

## Rebuild and verify

Create an empty PostgreSQL development database and set `DB_NAME`, `DB_USER`,
`DB_PASSWORD`, `DB_HOST`, and `DB_PORT` to that database. Stop application workers
while switching databases. Do not use `--fake` or reuse old migration records.

```sh
python manage.py migrate
python manage.py makemigrations --check --dry-run
python manage.py check
python verify_schema.py
python manage.py createsuperuser
```

Recreate office Staff/Head accounts through the application's account forms.
Set `LOGIN_OTP_ENABLED=True` and configure email delivery when testing OTP.
Approved remains distinct from Published; an office Head must explicitly publish
an approved revision. History and published snapshots remain independent of edits
to working records.

Portable local checks use a separate SQLite database and enable OTP for tests:

```sh
python manage.py migrate --settings=config.test_settings
python manage.py makemigrations --check --dry-run --settings=config.test_settings
python manage.py check --settings=config.test_settings
python manage.py test --settings=config.test_settings
```

`TEST_DATABASE_PATH` can select the SQLite verification file. The test settings
use a fast password hasher and in-memory email; they are for tests only. The full
suite was also run against an isolated PostgreSQL 18 database with real migrations.

Validation: 212 tests passed on PostgreSQL 18 and 212 on SQLite. Fresh migrations, migration drift checks, Django system checks, and the PostgreSQL table/column audit passed.
