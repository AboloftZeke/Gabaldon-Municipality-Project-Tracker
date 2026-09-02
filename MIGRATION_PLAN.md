# Gabaldon Municipality Project Tracker — Migration Plan

## Status

- Audit complete
- No destructive schema changes have been applied in this branch
- No `--fake` migrations are planned
- The plan below preserves the current Django auth data and the existing project records

## Scope and constraints

This migration plan is designed to move the project from the current flat legacy schema to the normalized ERD while respecting these rules:

- Do not drop the PostgreSQL database
- Do not delete active project records
- Do not run destructive migrations automatically
- Do not invent or fabricate missing source data
- Preserve Django `auth_user` password hashes and authentication behavior
- Create real Django migrations for every structural change
- Keep backup and recovery safety in place
- Verify row counts, foreign keys, and field mapping after each migration step

## Current project audit summary

### Active models today

The codebase currently contains legacy models in:

- `apps/infrastructure/models.py` — `InfrastructureProject`
- `apps/non_infrastructure/models.py` — `NonInfrastructureProject`
- `apps/system/models.py` — `UserProfile`, `PasswordChangeHistory`

The app still depends on Django's built-in `User` model for authentication and password hashing.

### Legacy references still in use

The legacy models remain wired into application behavior:

- `UserProfile` is still used for login role checks and password-change enforcement
- `PasswordChangeHistory` is still used by password tracking signals
- `InfrastructureProject` is still used across forms, views, dashboards, and templates
- `NonInfrastructureProject` is still used across forms, views, dashboards, and templates

### Data and schema realities

Confirmed by the existing codebase and migrations:

- The app is still operating on flat project tables rather than a normalized base `Project` model.
- `location` is a barangay-choice string, not yet a normalized `Address` relationship.
- `contractor`, `implementing_office`, and `source_of_fund` are currently plain strings.
- There is no active normalized `Project`, `Address`, `Contractor`, `Implementing_Office`, `Fund_Source`, `Financial`, `Project_Inspection`, or `Infrastructure_Schedule` model in the active code.
- `Project_Image`, `Reports`, and `Reports_Template` are not present in the active project or migrations.
- The project already contains a prior cleanup migration history, and the branch must be treated carefully because the schema has already been modified once before.

## Target normalized architecture

The migration moves toward the following design:

- `User` remains the system-of-record for auth credentials
- `Project` becomes the base project entity
- `Infrastructure_Project` and `Non_Infrastructure_Project` reference `Project`
- `Address` stores barangay/coordinate data
- `Infrastructure_Category`, `Non_Infrastructure_Category`, `Contractor`, `Implementing_Office`, and `Fund_Source` are normalized lookup entities
- `Financial` stores budget and bid amounts
- `Infrastructure_Schedule` preserves infrastructure timeline data
- `Project_Inspection` handles progress/inspection data
- `Project_Image`, `Reports`, and `Reports_Template` are optional and should only be created if explicitly approved as part of the agreed architecture

## Migration phases

### Phase 1: Backup and baseline verification

1. Confirm a PostgreSQL backup exists for the production/development database.
2. Record row counts for the relevant tables before migration.
3. Capture the current schema for:
   - `auth_user`
   - `system_userprofile`
   - `system_passwordchangehistory`
   - `infrastructure_infrastructureproject`
   - `non_infrastructure_noninfrastructureproject`
4. Save a migration baseline in the branch so it is recoverable.

### Phase 2: Create lookup tables and address model

Create the following tables first and keep them non-destructive:

- `Infrastructure_Category`
- `Non_Infrastructure_Category`
- `Contractor`
- `Implementing_Office`
- `Fund_Source`
- `Address`

Rules:

- Use unique constraints only where the existing data can safely support them.
- Keep required address fields nullable until migration has populated them or the project approves explicit defaults.
- Populate category/office/contractor/fund records from existing strings without creating duplicates.
- For the current Gabaldon/Nueva Ecija context, do not fabricate municipality/province/country values unless the project explicitly approves a default.

### Phase 3: Add the base project model

Create:

- `Project`

Fields to preserve:

- `project_type`
- `created_by_user_id`
- `updated_by_user_id`
- `is_published`
- `is_visible_to_public`
- `created_at`
- `updated_at`

Important:

- Keep the Django `User` model as the source of truth for authentication.
- Do not create a separate credentials table.
- Do not change the password hash field or the password hashing algorithm.
- Preserve the historical `created_by` and `updated_by` relationships where they exist.

### Phase 4: Create the normalized project submodels

Create:

- `Infrastructure_Project`
- `Non_Infrastructure_Project`

Rules:

- `Infrastructure_Project.project_id` must be unique and reference `Project.project_id`
- `Non_Infrastructure_Project.project_id` must be unique and reference `Project.project_id`
- Map legacy titles and descriptions to their normalized names
- Map `location` to `Address.barangay`
- Move coordinates to `Address.latitude` and `Address.longitude`
- Preserve public visibility by mapping `is_public` to `Project.is_visible_to_public`

### Phase 5: Preserve all explicit keep-fields

Before deleting any old column or legacy field, ensure each of the following has a migration target:

Infrastructure keep-fields:

- `procurement_method`
- `award_status`
- `planned_start_date`
- `planned_end_date`
- `cost_progress_percentage`
- `physical_progress_percentage`

Non-infrastructure keep-fields:

- `service_description`
- `beneficiaries_description`
- `service_location_details`
- `service_period`
- `service_time`
- `budget_cost`
- `results_achieved`
- `planned_start_date`
- `planned_end_date`
- `actual_start_date`
- `revised_completion_date`
- `overall_progress_percentage`

These values must be carried into the new schema or deliberately left `NULL` if no destination exists. Do not silently discard them.

### Phase 6: Add schedule, financial, and inspection models

Create:

- `Infrastructure_Schedule`
- `Financial`
- `Project_Inspection`

Rules:

- Preserve all historical finance values: `abc_amount` -> `approved_budget`, `contract_price` -> `bid_amount`
- Preserve `source_of_fund` through `Fund_Source` and `Financial.fund_source_id`
- Preserve `cost_progress_percentage` and `physical_progress_percentage` with no forced averaging or arbitrary selection
- If there is no clear destination for both percentages, stop and document the mismatch before deleting either field

### Phase 7: Data migration execution

Run an explicit data migration only after the new tables exist.

Required migration actions:

1. Create lookup table entries from legacy category strings
2. Map contractor strings into `Contractor`
3. Map implementing-office strings into `Implementing_Office`
4. Map fund-source strings into `Fund_Source`
5. Create `Project` records for each migrated legacy project
6. Create `Address` rows where values can be safely extracted
7. Create `Infrastructure_Project` and `Non_Infrastructure_Project` records linked to `Project`
8. Copy `created_by` / `updated_by` references to the new project base model
9. Copy public visibility state
10. Copy `abc_amount` and `contract_price` into `Financial`
11. Copy dates and progress values where a real destination exists
12. Keep fields with no destination as `NULL` rather than inventing them

### Phase 8: Application compatibility updates

After migration, update the codebase to reflect the normalized schema:

- `views`
- `forms`
- `templates`
- `admin`
- `urls`
- `signals`
- dashboards and filters
- any queryset logic tied to legacy fields

The legacy field references in the project must be migrated to the new models before removing the old tables.

### Phase 9: Remove obsolete user/system models only when safe

Only after the app no longer depends on them:

- Remove `UserProfile`
- Remove `PasswordChangeHistory`

This must be done with a dedicated migration after the code has been updated and verified.

### Phase 10: Verification and quality gates

After each migration step, run:

- `python manage.py check`
- `python manage.py makemigrations`
- `python manage.py migrate`
- `python manage.py check`

Then validate:

- project counts match source and target rows
- FK relationships are valid
- `created_by_user_id` points to a real `auth_user`
- `Address.barangay` matches the original `location` data
- `latitude` and `longitude` preserved correctly
- financial values preserved without unexplained change
- user password hashes remain in `auth_user`

## Explicit decisions needed before code implementation

The following items must be decided explicitly before full migration implementation:

1. `infrastructure_code` generation format
2. Whether `is_published` has a real source or should get an approved default
3. Whether `Project_Inspection.inspected_by_user_id` should allow `NULL` in migration
4. Whether `Project_Image`, `Reports`, and `Reports_Template` are included in the agreed scope
5. How to handle ambiguous fields where no destination in target ERD exists

## Recommended implementation order

The migration should be implemented in this order:

1. Backup and baseline verification
2. Lookup tables
3. Address
4. Project
5. Infrastructure and Non-Infrastructure project tables
6. Infrastructure schedule and financial tables
7. Project inspection table
8. Data migration
9. Code compatibility updates
10. Safe removal of legacy `UserProfile` / `PasswordChangeHistory`
11. Final cleanup migration

## Risk note

Because the repo already contains a prior schema cleanup and because the project relies on legacy auth/user logic, this migration should be executed incrementally in a feature branch and validated after each migration step. The code should not be treated as safe for one-shot destructive migration.

## Implementation status for this branch

This branch is currently at the safe planning stage. The next execution step is to add the first normalized migration scaffold and model layer in a non-destructive sequence, but only after the plan above is followed exactly.
