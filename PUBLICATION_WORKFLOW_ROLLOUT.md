# Publication approval workflow

Office Staff create and edit working project records and submit revision snapshots.
The corresponding Engineering or Mayor's Office Head reviews the submission.
Review permission stays scoped to the Head's office and self-review rules.
Approval does not publish a project. A Head explicitly publishes an approved
revision; only the current published snapshot appears on public dashboards,
details, GIS, and photo endpoints.

Editing a working record does not change the submitted or published snapshot.
Publishing a replacement archives the previous public revision. Operational
updates, inspection evidence, image retirement, and cover selection retain their
existing workflow rules. Admin maintenance exceptions are unchanged; superuser
status alone does not make an account an office Head.

## Database setup

Follow [the schema rebuild instructions](SCHEMA_NAMING.md). This branch has a new
migration baseline for empty development databases. The old publication backfill
migration has been removed; new projects are not implicitly published.

## Acceptance checks

- Staff can create, edit, view, and submit projects in their own office.
- Heads can review and update official operational information in their own office.
- Approval alone leaves the project private; explicit publishing makes it public.
- Submitted and published snapshots are stable when working records change.
- A replacement publication archives the old current revision and retains history.
- Inspection evidence and selected cover images remain available in the proper views.
- OTP login and account assignment respect the configured department and role.

Run the complete suite with `python manage.py test --settings=config.test_settings`.
This configuration enables OTP, uses in-memory mail, and creates a fresh test
database through the real migration graph.
