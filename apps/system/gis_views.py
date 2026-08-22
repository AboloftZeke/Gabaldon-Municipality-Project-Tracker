import json
import os
from datetime import date
from functools import lru_cache
from urllib.parse import urlencode
from urllib.request import urlopen

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.http import HttpResponseNotFound, JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_GET

from .models import Infrastructure_Project, Non_Infrastructure_Project, Project_Image

STATIC_GIS_DIR = os.path.join(settings.BASE_DIR, "static", "gis")
AUTHORITATIVE_BARANGAY_SERVICE = (
    "https://ulap-nga.georisk.gov.ph/arcgis/rest/services/"
    "PSA/BarangayPopMF/MapServer/0/query"
)

ALLOWED_STATIC_LAYERS = {
    "barangays": "barangays.geojson",
    "roads": "roads.geojson",
    "bridges": "bridges.geojson",
    "waterways": "waterways.geojson",
    "facilities": "facilities.geojson",
}


@lru_cache(maxsize=1)
def authoritative_gabaldon_barangays():
    """Return real Gabaldon barangay polygons from the GeoRisk/PSA service."""
    params = urlencode(
        {
            "where": "prov_name = 'Nueva Ecija' AND city_name LIKE '%Gabaldon%'",
            "outFields": "brgy_name,brgy_code,psgc_10d,city_name,prov_name",
            "returnGeometry": "true",
            "f": "geojson",
        }
    )

    try:
        with urlopen(f"{AUTHORITATIVE_BARANGAY_SERVICE}?{params}", timeout=20) as response:
            data = json.load(response)
    except (OSError, json.JSONDecodeError):
        return None

    if data.get("type") != "FeatureCollection":
        return None

    for feature in data.get("features", []):
        properties = feature.setdefault("properties", {})
        properties["name"] = (
            properties.get("brgy_name")
            or properties.get("name")
            or "Unnamed barangay"
        )
        properties["is_placeholder"] = False

    data["_source"] = "GeoRisk Philippines / Philippine Statistics Authority"
    return data


@require_GET
def static_layer_geojson(request, layer_name):
    if layer_name == "barangays":
        data = authoritative_gabaldon_barangays()
        if data is not None:
            return JsonResponse(data, safe=False)
        return JsonResponse(
            {
                "type": "FeatureCollection",
                "features": [],
                "_error": "Authoritative Gabaldon barangay boundaries are unavailable.",
            },
            status=503,
        )

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


def _infer_noninfra_status(noninfra):
    event_dt = getattr(noninfra, "event_date", None)
    if event_dt is None:
        return "planned", "Planned"
    if event_dt < date.today():
        return "completed", "Completed"
    return "planned", "Planned"


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

    infra_qs = (
        Infrastructure_Project.objects.select_related(
            "project", "address", "implementing_office"
        )
        .prefetch_related("financial_records__fund_source")
        .all()
    )

    for infra in infra_qs:
        if project_type and project_type != "infrastructure":
            continue

        address = infra.address
        if not address or address.latitude is None or address.longitude is None:
            continue

        status_label = infra.get_award_status_display() or "Planned"
        status_key = _status_color_key(status_label)
        office_name = infra.implementing_office or ""

        financial = infra.financial_records.first()
        funding_source = ""
        budget = None
        if financial:
            budget = financial.approved_budget or financial.bid_amount
            if financial.fund_source:
                funding_source = financial.fund_source.fund_source_name or ""

        project_name = infra.infrastructure_title or "Infrastructure Project"
        project_code = infra.infrastructure_code or f"INF-{infra.infrastructure_id}"
        project_year = infra.planned_start_date.year if infra.planned_start_date else ""

        if status_filter and status_key != status_filter:
            continue
        if barangay_filter and (address.barangay or "").strip().lower() != barangay_filter:
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
                    "coordinates": [float(address.longitude), float(address.latitude)],
                },
                "properties": {
                    "project_id": infra.project.project_id,
                    "location_id": address.address_id,
                    "name": project_name,
                    "code": project_code,
                    "type": "infrastructure",
                    "status": status_label,
                    "status_key": status_key,
                    "progress": infra.physical_progress_percentage,
                    "budget": budget,
                    "funding_source": funding_source,
                    "implementing_office": office_name,
                    "barangay": address.barangay,
                    "address": address.street or "",
                    "detail_url": reverse("engineering_projects:project_detail", kwargs={"pk": infra.infrastructure_id}),
                },
            }
        )

    noninfra_qs = Non_Infrastructure_Project.objects.select_related("project", "address").all()

    for noninfra in noninfra_qs:
        if project_type and project_type != "non_infrastructure":
            continue

        address = noninfra.address
        if not address or address.latitude is None or address.longitude is None:
            continue

        status_key, status_label = _infer_noninfra_status(noninfra)
        project_name = noninfra.non_infra_name or "Non-Infrastructure Project"
        project_code = f"NINF-{noninfra.non_infra_id}"
        project_year = noninfra.event_date.year if noninfra.event_date else ""
        office_name = noninfra.proponent or ""

        if status_filter and status_key != status_filter:
            continue
        if barangay_filter and (address.barangay or "").strip().lower() != barangay_filter:
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
                    "coordinates": [float(address.longitude), float(address.latitude)],
                },
                "properties": {
                    "project_id": noninfra.project.project_id,
                    "location_id": address.address_id,
                    "name": project_name,
                    "code": project_code,
                    "type": "non_infrastructure",
                    "status": status_label,
                    "status_key": status_key,
                    "progress": None,
                    "budget": None,
                    "funding_source": "",
                    "implementing_office": office_name,
                    "barangay": address.barangay,
                    "address": address.street or noninfra.venue_name or "",
                    "detail_url": reverse(
                        "mayor_projects:non_infrastructure_project_detail",
                        kwargs={"pk": noninfra.non_infra_id},
                    ),
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
    photos = Project_Image.objects.filter(project_id=project_id).order_by(
        "-is_cover",
        "-created_at",
    )

    data = [
        {
            "id": p.project_image_id,
            "url": p.image_url,
            "caption": "",
            "is_cover": p.is_cover,
        }
        for p in photos
        if p.image_url
    ]

    return JsonResponse({"project_id": project_id, "photos": data})
