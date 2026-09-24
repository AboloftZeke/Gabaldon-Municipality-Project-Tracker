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

## Mayor's Office progress evidence

Mayor's Office Staff open a published non-infrastructure project and save a
progress update with remarks, a proposed status, and at least one evidence file.
The saved update is a Draft and does not change the official project status.
Staff explicitly submit it for Mayor Head review. The Head may return it with
a reason or approve it; approval alone still does not change the status.

The Head separately applies an approved update. This changes the working
status and creates an approved operational `ProjectRevision` with a frozen
record of the update and its evidence metadata. The Head must publish that
revision before the public project status or evidence history changes.
Previous published revisions retain their own evidence; pending, returned,
and unpublished revisions are not displayed in the public history. Internal
review notes are not shown publicly. Existing evidence files must remain
available through configured media storage for public links to work.

Before proposing a merge, run the full test suite and resolve any unrelated
baseline failures as well as Mayor evidence failures. A passing feature-only
suite does not by itself establish that the whole repository is release ready.

### Phase 9 validation gate (2026-09-24)

The Mayor evidence and shared publication regression selection passed 173
tests. The complete repository run executed 330 tests and finished with 11
failures and 4 errors. The same 15 cases failed on the Phase 8B starting
branch before the Phase 9 changes. The errors involve old non-infrastructure
operational-form fixtures attempting to validate an excluded `event_date`;
the failures include infrastructure report status expectations, existing
operational/dashboard assertions, and older template assertions. No Phase 9
Mayor evidence integration test failed. **Do not mark the whole repository as
merge-ready until the complete suite is green or those failures are resolved
and explicitly accepted by the maintainers.**
