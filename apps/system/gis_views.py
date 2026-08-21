import json
import os
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.http import HttpResponseNotFound, JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_GET

from .publication_public import current_public_revisions, public_projects

STATIC_GIS_DIR = os.path.join(settings.BASE_DIR, "static", "gis")
ALLOWED_STATIC_LAYERS = {
    "barangays": "barangays.geojson",
    "roads": "roads.geojson",
    "bridges": "bridges.geojson",
    "waterways": "waterways.geojson",
    "facilities": "facilities.geojson",
}


@require_GET
def static_layer_geojson(request, layer_name):
    filename = ALLOWED_STATIC_LAYERS.get(layer_name)
    if not filename:
        return HttpResponseNotFound("Unknown GIS layer.")

    path = os.path.join(STATIC_GIS_DIR, filename)
    if not os.path.exists(path):
        return JsonResponse({"type": "FeatureCollection", "features": [], "_placeholder": True})

    with open(path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return JsonResponse(
                {"type": "FeatureCollection", "features": [], "_error": "Invalid GeoJSON on disk."},
                status=500,
            )

    return JsonResponse(data, safe=False)


def _status_color_key(status):
    value = (status or "").strip().lower()
    if value in ("completed", "done"):
        return "completed"
    if value in ("ongoing", "in progress", "in_progress", "ongoing_bidding", "awarded"):
        return "ongoing"
    if value in ("planned", "proposed", "pending", "planning"):
        return "planned"
    if value in ("delayed", "suspended", "on hold", "on_hold", "rebid", "cancelled"):
        return "delayed"
    return "unknown"


@require_GET
def projects_geojson(request):
    project_type = request.GET.get("type")
    status_filter = (request.GET.get("status") or "").strip().lower()
    barangay_filter = (request.GET.get("barangay") or "").strip().lower()
    office_filter = (request.GET.get("office") or "").strip().lower()
    funding_filter = (request.GET.get("funding") or "").strip().lower()
    year_filter = (request.GET.get("year") or "").strip()
    query_filter = (request.GET.get("q") or "").strip().lower()

    features = []

    infrastructure, non_infrastructure = public_projects()
    for infra in infrastructure:
        if project_type and project_type != "infrastructure":
            continue

        address = infra["address"]
        if not address or address.get("latitude") is None or address.get("longitude") is None:
            continue

        status_label = infra["award_status_label"] or "Planned"
        status_key = _status_color_key(status_label)
        office_name = infra["implementing_office"].get("name") or ""
        financial = infra["financial"]
        funding_source = (financial.get("fund_source") or {}).get("name") or ""
        budget = financial.get("approved_budget") or financial.get("contract_price")
        project_name = infra["title"] or "Infrastructure Project"
        project_code = infra["code"]
        project_year = infra["planned_start_date"].year if infra["planned_start_date"] else ""

        if status_filter and status_key != status_filter:
            continue
        if barangay_filter and (address.get("barangay") or "").strip().lower() != barangay_filter:
            continue
        if office_filter and office_filter not in office_name.lower():
            continue
        if funding_filter and funding_filter not in funding_source.lower():
            continue
        if year_filter and str(project_year) != year_filter:
            continue
        if query_filter and query_filter not in project_name.lower() and query_filter not in project_code.lower():
            continue

        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(address["longitude"]), float(address["latitude"])],
                },
                "properties": {
                    "project_id": infra["project_id"],
                    "location_id": address.get("id"),
                    "name": project_name,
                    "code": project_code,
                    "type": "infrastructure",
                    "status": status_label,
                    "status_key": status_key,
                    "progress": infra["physical_progress_percentage"],
                    "budget": budget,
                    "funding_source": funding_source,
                    "implementing_office": office_name,
                    "barangay": address.get("barangay") or "",
                    "address": address.get("street") or "",
                    "detail_url": reverse("public_infrastructure_project_detail", kwargs={"pk": infra["record_id"]}),
                },
            }
        )

    for noninfra in non_infrastructure:
        if project_type and project_type != "non_infrastructure":
            continue

        address = noninfra["address"]
        if not address or address.get("latitude") is None or address.get("longitude") is None:
            continue

        status_key = _status_color_key(noninfra["status"])
        status_label = noninfra["status_label"]
        project_name = noninfra["title"] or "Non-Infrastructure Project"
        project_code = noninfra["code"]
        project_year = noninfra["event_date"].year if noninfra["event_date"] else ""
        office_name = noninfra["proponent"]

        if status_filter and status_key != status_filter:
            continue
        if barangay_filter and (address.get("barangay") or "").strip().lower() != barangay_filter:
            continue
        if office_filter and office_filter not in office_name.lower():
            continue
        if year_filter and str(project_year) != year_filter:
            continue
        if query_filter and query_filter not in project_name.lower() and query_filter not in project_code.lower():
            continue

        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(address["longitude"]), float(address["latitude"])],
                },
                "properties": {
                    "project_id": noninfra["project_id"],
                    "location_id": address.get("id"),
                    "name": project_name,
                    "code": project_code,
                    "type": "non_infrastructure",
                    "status": status_label,
                    "status_key": status_key,
                    "progress": None,
                    "budget": None,
                    "funding_source": "",
                    "implementing_office": office_name,
                    "barangay": address.get("barangay") or "",
                    "address": address.get("street") or noninfra["venue_name"],
                    "detail_url": reverse("public_non_infrastructure_project_detail", kwargs={"pk": noninfra["record_id"]}),
                },
            }
        )

    return JsonResponse(
        {"type": "FeatureCollection", "features": features},
        encoder=DjangoJSONEncoder,
        safe=False,
    )


@require_GET
def project_photos(request, project_id):
    revision = current_public_revisions().filter(project_id=project_id).first()
    photos = (revision.snapshot_data or {}).get("images", []) if revision else []
    data = [{
        "id": photo.get("id"),
        "url": photo.get("url") or "",
        "caption": "",
        "is_cover": bool(photo.get("is_cover")),
    } for photo in photos if photo.get("url")]

    return JsonResponse({"project_id": project_id, "photos": data})
