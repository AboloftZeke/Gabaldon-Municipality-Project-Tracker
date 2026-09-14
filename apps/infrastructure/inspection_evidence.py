import os

from django.core.files.storage import default_storage
from django.db import transaction

from apps.system.models import InspectionEvidence


@transaction.atomic
def update_inspection_evidence(
    inspection,
    actor,
    *,
    photos=(),
    documents=(),
    remove_ids=(),
):
    """Add and remove files belonging only to the selected inspection."""
    evidence_to_remove = list(
        inspection.evidence.select_for_update().filter(pk__in=remove_ids)
    )
    for evidence in evidence_to_remove:
        default_storage.delete(evidence.storage_name)
        evidence.delete()

    created = []
    for evidence_type, uploads in (
        ('image', photos),
        ('document', documents),
    ):
        for upload in uploads or ():
            original_name = os.path.basename(upload.name)
            folder = os.path.join(
                'inspections',
                str(inspection.pk),
                'photos' if evidence_type == 'image' else 'documents',
            )
            storage_name = default_storage.save(
                os.path.join(folder, original_name),
                upload,
            )
            created.append(InspectionEvidence.objects.create(
                inspection=inspection,
                evidence_type=evidence_type,
                original_name=original_name,
                storage_name=storage_name,
                file_url=default_storage.url(storage_name),
                content_type=getattr(upload, 'content_type', '') or '',
                uploaded_by_user=actor,
            ))
    return created
