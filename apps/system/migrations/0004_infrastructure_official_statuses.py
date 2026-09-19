# Generated as a compatibility migration for the infrastructure official-status vocabulary.
from copy import deepcopy

from django.db import migrations, models


# Legacy values are mapped without removing records. Any unrecognised non-empty
# value is deliberately preserved and printed during migration for manual review.
STATUS_MAP = {
    "awarded": "pre_construction",
    "ongoing_bidding": "pre_construction",
    "rebid": "not_yet_started",
    "ongoing": "ongoing",
    "completed": "completed",
    "cancelled": "cancelled",
}

STATUS_LABELS = {
    "not_yet_started": "Not Yet Started",
    "pre_construction": "Pre-Construction",
    "ongoing": "Ongoing",
    "on_hold": "On Hold",
    "suspended": "Suspended",
    "completed": "Completed",
    "for_inspection": "For Inspection",
    "for_turnover": "For Turnover",
    "turned_over": "Turned Over",
    "cancelled": "Cancelled",
}


def _normalise(value, unknown_values):
    if value in (None, ""):
        return value, False
    if value in STATUS_MAP:
        return STATUS_MAP[value], STATUS_MAP[value] != value
    if value in STATUS_LABELS:
        return value, False
    unknown_values.add(str(value))
    return value, False


def _normalise_snapshot(snapshot, unknown_values):
    if not isinstance(snapshot, dict):
        return snapshot, False

    snapshot = deepcopy(snapshot)
    changed = False

    infrastructure = snapshot.get("infrastructure")
    if isinstance(infrastructure, dict):
        value = infrastructure.get("award_status")
        mapped, value_changed = _normalise(value, unknown_values)
        if value_changed:
            infrastructure["award_status"] = mapped
            changed = True
        if mapped in STATUS_LABELS and infrastructure.get("award_status_label") != STATUS_LABELS[mapped]:
            infrastructure["award_status_label"] = STATUS_LABELS[mapped]
            changed = True

    progress_update = snapshot.get("progress_update")
    if isinstance(progress_update, dict):
        for field_name in (
            "official_status",
            "previous_official_status",
            "new_official_status",
        ):
            value = progress_update.get(field_name)
            mapped, value_changed = _normalise(value, unknown_values)
            if value_changed:
                progress_update[field_name] = mapped
                changed = True
            if (
                field_name == "official_status"
                and mapped in STATUS_LABELS
                and progress_update.get("official_status_label") != STATUS_LABELS[mapped]
            ):
                progress_update["official_status_label"] = STATUS_LABELS[mapped]
                changed = True

    return snapshot, changed


def forwards(apps, schema_editor):
    InfrastructureProject = apps.get_model("system", "InfrastructureProject")
    InfrastructureProgressUpdate = apps.get_model(
        "system", "InfrastructureProgressUpdate"
    )
    ProjectRevision = apps.get_model("system", "ProjectRevision")

    # Update database-backed project and operational-history values first.
    for legacy, replacement in STATUS_MAP.items():
        if legacy != replacement:
            InfrastructureProject.objects.filter(award_status=legacy).update(
                award_status=replacement
            )
            InfrastructureProgressUpdate.objects.filter(
                previous_official_status=legacy
            ).update(previous_official_status=replacement)
            InfrastructureProgressUpdate.objects.filter(
                new_official_status=legacy
            ).update(new_official_status=replacement)

    unknown_values = set()
    for value in InfrastructureProject.objects.exclude(
        award_status__isnull=True
    ).exclude(award_status="").values_list("award_status", flat=True):
        _normalise(value, unknown_values)
    for field_name in ("previous_official_status", "new_official_status"):
        for value in InfrastructureProgressUpdate.objects.exclude(
            **{field_name: ""}
        ).values_list(field_name, flat=True):
            _normalise(value, unknown_values)

    # Current and historical public-review snapshots contain copied status data.
    for revision in ProjectRevision.objects.iterator():
        snapshot, changed = _normalise_snapshot(revision.snapshot, unknown_values)
        if changed:
            revision.snapshot = snapshot
            revision.save(update_fields=["snapshot"])

    if unknown_values:
        print(
            "Official-status migration preserved unmapped values for manual review: "
            + ", ".join(sorted(unknown_values))
        )


class Migration(migrations.Migration):

    dependencies = [
        ("system", "0003_alter_projectreport_project_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="infrastructureproject",
            name="award_status",
            field=models.CharField(
                blank=True,
                choices=[
                    ("not_yet_started", "Not Yet Started"),
                    ("pre_construction", "Pre-Construction"),
                    ("ongoing", "Ongoing"),
                    ("on_hold", "On Hold"),
                    ("suspended", "Suspended"),
                    ("completed", "Completed"),
                    ("for_inspection", "For Inspection"),
                    ("for_turnover", "For Turnover"),
                    ("turned_over", "Turned Over"),
                    ("cancelled", "Cancelled"),
                ],
                max_length=50,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="infrastructureprogressupdate",
            name="previous_official_status",
            field=models.CharField(
                blank=True,
                choices=[
                    ("not_yet_started", "Not Yet Started"),
                    ("pre_construction", "Pre-Construction"),
                    ("ongoing", "Ongoing"),
                    ("on_hold", "On Hold"),
                    ("suspended", "Suspended"),
                    ("completed", "Completed"),
                    ("for_inspection", "For Inspection"),
                    ("for_turnover", "For Turnover"),
                    ("turned_over", "Turned Over"),
                    ("cancelled", "Cancelled"),
                ],
                default="",
                max_length=50,
            ),
        ),
        migrations.AlterField(
            model_name="infrastructureprogressupdate",
            name="new_official_status",
            field=models.CharField(
                blank=True,
                choices=[
                    ("not_yet_started", "Not Yet Started"),
                    ("pre_construction", "Pre-Construction"),
                    ("ongoing", "Ongoing"),
                    ("on_hold", "On Hold"),
                    ("suspended", "Suspended"),
                    ("completed", "Completed"),
                    ("for_inspection", "For Inspection"),
                    ("for_turnover", "For Turnover"),
                    ("turned_over", "Turned Over"),
                    ("cancelled", "Cancelled"),
                ],
                default="",
                max_length=50,
            ),
        ),
    ]
