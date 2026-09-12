# Publication review comparison

## Existing architecture

- `ProjectPublicationRevision.snapshot_data` stores JSON-safe content, captured by
  `publication_snapshots.py` at draft creation and refreshed on submission or
  resubmission. Later working-copy edits do not change the submitted snapshot.
- Both project types have `project` and `images` sections. Infrastructure also
  captures `infrastructure`, latest `financial`, `schedule`, and `inspection`
  sections; Non-Infrastructure captures `non_infrastructure`. Related addresses,
  categories, offices, contractors, users, and funding sources are nested values.
- Public reads use `current_public_revisions()`: status `published` and
  `is_current_public_revision=True`. Database constraints permit one current
  public revision per project. `supersedes_revision` records the baseline at
  draft creation and is not necessarily the current public baseline later.
- Submission moves draft/needs-revision to pending review. Admin review approves,
  rejects, or requests revision; publishing is a separate action that archives
  the previous current revision. Archiving removes the public version. Review
  and publication actions are restricted to superusers.
- Snapshot images contain ID, URL, cover flag, and capture metadata. Working-copy
  removal retains referenced image records/files, allowing old images to remain
  visible in a comparison.

## Comparison behavior

`publication_diff.compare_snapshots` is a read-only, reusable helper. It returns
sections and fields with submitted/previous display values, change states and
badges, plus image comparisons. No new history storage or migrations are needed.

`revision_comparison` selects the current public revision using the public read
selector. It never uses live project fields, the latest revision, or the
`supersedes_revision` link as the comparison baseline. Both detail GET and invalid
review POST responses receive the same comparison context.

Missing/null/empty values are treated as cleared; zero is retained. Numeric
formatting differences do not create changes. Record IDs and capture timestamps
are ignored. Named relationships display their names and relevant code/percentage
details; nested address fields are compared individually. Images match by ID or
URL and report additions, removals, URL changes, and cover-flag changes. Image
ordering and creation timestamps alone do not count as changes.

Never-published projects show **Initial Publication Submission**, including
resubmissions after rejection. Previously published but now archived projects
show **No Current Published Revision**, without invented differences. Viewing
the current public revision identifies it as such. Historical revisions compare
against the public version at the time the review page is opened.

The template renders the server-prepared fields with escaped values, text badges,
and colored borders; unchanged fields use the existing neutral review style.
Approval, rejection, needs-revision, publishing, archiving, and permission logic
remain unchanged.

## Focused verification

Run `manage.py test` with these labels using the normal PostgreSQL test settings:

```
apps.system.test_publication_diff
apps.system.tests.PublicationWorkflowTests
apps.system.tests.ProjectPublicationRevisionModelTests
apps.system.tests.PublicationServiceTests
apps.system.tests.EmployeePublicationWorkflowViewTests
apps.system.tests.AdminPublicationReviewViewTests
apps.system.tests.ProjectPublicationSnapshotTests
apps.system.tests.ProjectPublicationImageRetentionTests
```

Development verification used Django 6.0.4 with an isolated SQLite test database
and application migrations disabled in an external test-settings module. The
existing migrations include PostgreSQL-specific SQL; PostgreSQL migration and
locking behavior were not validated by that local run. No production settings
were changed. The full project test suite was not run.
