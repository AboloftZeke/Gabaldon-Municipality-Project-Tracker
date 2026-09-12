# Publication Approval Workflow Rollout

## What changes for employees and administrators

New and edited projects remain working records until an employee submits a
revision for review. An administrator can inspect the submitted snapshot,
request revisions, reject it, or approve it. Approval and publication are
separate actions. Only the revision explicitly published by an administrator
is shown on the public dashboard, project detail pages, GIS layer, and photo
endpoints.

Editing a project after submission does not silently change the submitted or
published version. Publishing a later approved revision archives the previous
public revision. Archiving the current revision removes the project from all
public surfaces without deleting the employee's working record.

## Pre-deployment checklist

1. Confirm the deployment is using the
   `feature/publication-approval-workflow` branch or its reviewed merge commit.
2. Take and verify a restorable database backup.
3. Confirm the production environment provides a long, random `SECRET_KEY`.
4. Set `DEBUG=False` and configure the production host names in
   `ALLOWED_HOSTS`.
5. When HTTPS is terminated by Django, enable secure session and CSRF cookies,
   HTTPS redirection, and an appropriate HSTS policy. When TLS is terminated by
   a reverse proxy, configure the proxy and Django's forwarded-protocol setting
   consistently before enabling redirects or HSTS.
6. Ensure uploaded project images referenced by published revisions remain
   available at their stored URLs.

## Deployment sequence

Run these commands from the application directory with the production virtual
environment and configuration loaded:

```text
python manage.py check --deploy
python manage.py migrate --plan
python manage.py migrate
python manage.py collectstatic --noinput
```

Migration `system.0027_backfill_published_revisions` creates one current
published revision for each existing normalized infrastructure or
non-infrastructure project that has no publication history. This preserves the
projects that residents could see before the approval workflow was introduced.
Projects that already have a workflow revision are not changed.

Do not mark migration `0027` as fake. Its data operation is required for the
public dashboard to retain existing projects.

## Post-deployment acceptance check

Use one test project for each department and confirm:

- A newly created project is absent from the public dashboard.
- The responsible employee can submit it for review.
- A different department cannot use that submission endpoint.
- Only an administrator can open the review queue and record a decision.
- Returning or rejecting a revision requires review notes.
- Approval alone does not make the project public.
- Publishing the approved revision makes that exact snapshot public.
- Editing the working record does not change the public version.
- Publishing a later approved revision replaces and archives the old public
  revision.
- Archiving the current revision removes it from the dashboard, detail pages,
  GIS output, and project-photo output.

## Focused verification command

The following test groups cover the final workflow without running unrelated
application tests:

```text
python manage.py test \
  apps.system.tests.PublicationServiceTests \
  apps.system.tests.EmployeePublicationWorkflowViewTests \
  apps.system.tests.AdminPublicationReviewViewTests \
  apps.system.tests.ProjectPublicationBackfillMigrationTests \
  apps.system.tests.PublicDashboardInfrastructureDataSourceTests \
  apps.system.tests.PublicDashboardNonInfrastructureStatusTests
```

## Rollback note

Prefer restoring the verified pre-deployment database backup if the deployment
must be fully rolled back. Reversing migration `0027` removes only revisions
that carry its migration marker, but later review activity may have changed
publication history after deployment. Review that history before attempting a
database migration rollback on an active system.
