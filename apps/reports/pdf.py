"""A4 PDF documents built only from disclosed report data."""

from datetime import date, datetime, time
from decimal import Decimal
from html import escape
from io import BytesIO

from django.conf import settings
from django.core.files.storage import default_storage
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


GREEN = colors.HexColor('#1A5A3A')
DARK_GREEN = colors.HexColor('#173D2A')
SOFT_GREEN = colors.HexColor('#EDF6F0')
TEXT = colors.HexColor('#17251D')
MUTED = colors.HexColor('#66766D')
BORDER = colors.HexColor('#D9E2DC')
ROW_ALT = colors.HexColor('#F7FAF8')


def _styles():
    base = getSampleStyleSheet()
    return {
        'title': ParagraphStyle(
            'ReportTitle', parent=base['Title'], fontName='Helvetica-Bold',
            fontSize=22, leading=26, textColor=DARK_GREEN, spaceAfter=5 * mm,
        ),
        'subtitle': ParagraphStyle(
            'ReportSubtitle', parent=base['Normal'], fontSize=9.5,
            leading=14, textColor=MUTED, spaceAfter=6 * mm,
        ),
        'section': ParagraphStyle(
            'ReportSection', parent=base['Heading2'], fontName='Helvetica-Bold',
            fontSize=12, leading=15, textColor=DARK_GREEN,
            spaceBefore=4 * mm, spaceAfter=2.5 * mm, keepWithNext=True,
        ),
        'body': ParagraphStyle(
            'ReportBody', parent=base['BodyText'], fontSize=9,
            leading=13, textColor=TEXT,
        ),
        'small': ParagraphStyle(
            'ReportSmall', parent=base['BodyText'], fontSize=7.5,
            leading=10, textColor=TEXT,
        ),
        'small_header': ParagraphStyle(
            'ReportSmallHeader', parent=base['BodyText'],
            fontName='Helvetica-Bold', fontSize=7.2, leading=9,
            textColor=colors.white,
        ),
        'small_right': ParagraphStyle(
            'ReportSmallRight', parent=base['BodyText'], fontSize=7.5,
            leading=10, textColor=TEXT, alignment=TA_RIGHT,
        ),
        'metric_label': ParagraphStyle(
            'MetricLabel', parent=base['Normal'], fontName='Helvetica-Bold',
            fontSize=7, leading=9, textColor=MUTED,
        ),
        'metric_value': ParagraphStyle(
            'MetricValue', parent=base['Normal'], fontName='Helvetica-Bold',
            fontSize=15, leading=18, textColor=GREEN,
        ),
        'empty': ParagraphStyle(
            'Empty', parent=base['Normal'], fontSize=9, leading=13,
            textColor=MUTED, alignment=TA_CENTER,
        ),
    }


def _text(value, fallback='N/A'):
    if value is None or value == '':
        value = fallback
    if isinstance(value, datetime):
        value = value.strftime('%B %d, %Y')
    elif isinstance(value, date):
        value = value.strftime('%B %d, %Y')
    elif isinstance(value, time):
        value = value.strftime('%I:%M %p').lstrip('0')
    return escape(str(value))


def _currency(value):
    if value is None:
        return 'N/A'
    return f'PHP {Decimal(value):,.2f}'


def _percent(value):
    if value is None:
        return 'N/A'
    return f'{Decimal(value):,.1f}%'


def _document(buffer, *, summary=False):
    pagesize = landscape(A4) if summary else A4
    return SimpleDocTemplate(
        buffer,
        pagesize=pagesize,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=22 * mm,
        bottomMargin=18 * mm,
        title='Gabaldon Municipality Project Report',
        author='Gabaldon Municipality Project Tracker',
        pageCompression=0,
    )


def _page_frame(canvas, doc):
    width, height = doc.pagesize
    canvas.saveState()
    canvas.setFillColor(GREEN)
    canvas.rect(0, height - 11 * mm, width, 11 * mm, stroke=0, fill=1)
    canvas.setFillColor(colors.white)
    canvas.setFont('Helvetica-Bold', 8)
    canvas.drawString(15 * mm, height - 7 * mm, 'GABALDON MUNICIPALITY PROJECT TRACKER')
    canvas.setStrokeColor(BORDER)
    canvas.line(15 * mm, 12 * mm, width - 15 * mm, 12 * mm)
    canvas.setFillColor(MUTED)
    canvas.setFont('Helvetica', 7)
    canvas.drawString(15 * mm, 7.5 * mm, 'Generated from current public project information')
    canvas.drawRightString(width - 15 * mm, 7.5 * mm, f'Page {doc.page}')
    canvas.restoreState()


def _title_block(story, title, subtitle, styles):
    story.append(Paragraph(escape(title), styles['title']))
    story.append(Paragraph(escape(subtitle), styles['subtitle']))


def _details_table(rows, styles, *, columns=2):
    cells = []
    for label, value in rows:
        cells.append([
            Paragraph(escape(label.upper()), styles['metric_label']),
            Paragraph(_text(value), styles['body']),
        ])
    paired = []
    if columns == 2:
        for index in range(0, len(cells), 2):
            row = cells[index:index + 2]
            if len(row) == 1:
                row.append(['', ''])
            paired.append([*row[0], *row[1]])
        widths = [35 * mm, 51 * mm, 35 * mm, 51 * mm]
    else:
        paired = cells
        widths = [42 * mm, 130 * mm]
    table = Table(paired, colWidths=widths, hAlign='LEFT')
    table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BACKGROUND', (0, 0), (-1, -1), ROW_ALT),
        ('BOX', (0, 0), (-1, -1), 0.5, BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.4, BORDER),
        ('LEFTPADDING', (0, 0), (-1, -1), 7),
        ('RIGHTPADDING', (0, 0), (-1, -1), 7),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
    ]))
    return table


def _section(story, heading, rows, styles, *, columns=2):
    content = [
        Paragraph(escape(heading), styles['section']),
        _details_table(rows, styles, columns=columns),
    ]
    story.append(KeepTogether(content))


def _local_image(image_url, max_width=170 * mm, max_height=85 * mm):
    if not image_url:
        return None
    media_url = settings.MEDIA_URL or '/media/'
    if not image_url.startswith(media_url):
        return None
    storage_name = image_url[len(media_url):].lstrip('/')
    if not storage_name or not default_storage.exists(storage_name):
        return None
    try:
        with default_storage.open(storage_name, 'rb') as source:
            image = Image(BytesIO(source.read()))
        scale = min(
            max_width / image.imageWidth,
            max_height / image.imageHeight,
            1,
        )
        image.drawWidth = image.imageWidth * scale
        image.drawHeight = image.imageHeight * scale
        image.hAlign = 'LEFT'
        return image
    except Exception:
        # A stale or malformed disclosed image should not block the report.
        return None


def _append_images(story, images, styles):
    available = []
    for image_data in images:
        image = _local_image(image_data.get('image_url'))
        if image:
            available.append(image)
    if not available:
        return
    story.extend([
        PageBreak(),
        Paragraph('Disclosed Project Images', styles['section']),
    ])
    for index, image in enumerate(available, 1):
        story.extend([
            KeepTogether([
                image,
                Spacer(1, 1.5 * mm),
                Paragraph(f'Project image {index}', styles['small']),
            ]),
            Spacer(1, 4 * mm),
        ])


def build_individual_report_pdf(report_type, report):
    """Return a portrait A4 individual-project PDF as bytes."""
    styles = _styles()
    buffer = BytesIO()
    doc = _document(buffer)
    scope_label = (
        'Infrastructure' if report_type == 'infrastructure'
        else 'Non-Infrastructure'
    )
    story = []
    _title_block(
        story,
        report['title'],
        f"Individual {scope_label} Project Report | {report['code']} | "
        f"Published revision {report['revision'].revision_number}",
        styles,
    )

    if report_type == 'infrastructure':
        _section(story, 'Project Information', [
            ('Category', report['category'].get('name')),
            ('Status', report['award_status_label']),
            ('Implementing Office', report['implementing_office'].get('name')),
            ('Published By', report['created_by_name']),
            ('Last Updated', report['updated_at']),
        ], styles)
        _section(story, 'Location', [
            ('Street', report['address'].get('street')),
            ('Barangay', report['address'].get('barangay')),
            ('Municipality', report['address'].get('municipality')),
            ('Province', report['address'].get('province')),
        ], styles)
        _section(story, 'Procurement and Financial Information', [
            ('Contractor', report['contractor'].get('name')),
            ('Procurement Method', report['procurement_method_label']),
            ('Source of Fund', report['financial'].get('fund_source', {}).get('name')),
            ('Approved Budget for the Contract', _currency(report['financial'].get('approved_budget'))),
            ('Contract Price', _currency(report['financial'].get('contract_price'))),
        ], styles)
        _section(story, 'Schedule and Progress', [
            ('Planned Start', report['planned_start_date']),
            ('Planned End', report['planned_end_date']),
            ('Actual Start', report['schedule'].get('actual_start_date')),
            ('Actual Completion', report['schedule'].get('actual_completion_date')),
            ('Cost Progress', _percent(report['cost_progress_percentage'])),
            ('Physical Progress', _percent(report['physical_progress_percentage'])),
        ], styles)
        inspection = report.get('inspection') or {}
    else:
        inspection = None
        _section(story, 'Project Information', [
            ('Category', report['category'].get('name')),
            ('Status', report['status_label']),
            ('Proponent', report['proponent']),
            ('Beneficiaries', report['beneficiaries']),
            ('Published By', report['created_by_name']),
            ('Last Updated', report['updated_at']),
        ], styles)
        _section(story, 'Location and Venue', [
            ('Venue', report['venue_name']),
            ('Street', report['address'].get('street')),
            ('Barangay', report['address'].get('barangay')),
            ('Municipality', report['address'].get('municipality')),
            ('Province', report['address'].get('province')),
        ], styles)
        _section(story, 'Schedule', [
            ('Event or Service Date', report['event_date']),
            ('Start Time', report['start_time']),
            ('End Time', report['end_time']),
        ], styles)

    story.extend([
        Paragraph('Description', styles['section']),
        Paragraph(_text(report['description'], 'No description provided.'), styles['body']),
        Spacer(1, 3 * mm),
    ])
    if inspection:
        _section(story, 'Latest Disclosed Inspection', [
            ('Inspection Date', inspection.get('inspection_date')),
            ('Completion', _percent(inspection.get('completion_percentage'))),
            ('Inspected By', (inspection.get('inspected_by') or {}).get('display_name')),
            ('Findings', inspection.get('findings')),
            ('Remarks', inspection.get('remarks')),
        ], styles)
    _append_images(story, report.get('images') or [], styles)
    doc.build(story, onFirstPage=_page_frame, onLaterPages=_page_frame)
    return buffer.getvalue()


def _metric_card(label, value, styles):
    return [
        Paragraph(escape(label.upper()), styles['metric_label']),
        Paragraph(_text(value), styles['metric_value']),
    ]


def _summary_table(report_type, rows, styles):
    if report_type == 'infrastructure':
        headings = [
            'Code', 'Title', 'Barangay', 'Category', 'Status',
            'Progress', 'Planned Start', 'Planned End', 'Contract Price',
        ]
        widths = [25, 42, 26, 26, 23, 20, 26, 26, 32]
        body = [[
            project['code'], project['title'],
            project['address'].get('barangay') or 'N/A',
            project['category'].get('name') or 'N/A',
            project['award_status_label'] or 'N/A',
            _percent(project['physical_progress_percentage']),
            _text(project['planned_start_date']),
            _text(project['planned_end_date']),
            _currency(project['financial'].get('contract_price')),
        ] for project in rows]
    else:
        headings = [
            'Code', 'Title', 'Category', 'Status', 'Barangay / Venue',
            'Event / Service Date', 'Proponent', 'Beneficiaries',
        ]
        widths = [22, 48, 30, 23, 38, 31, 38, 22]
        body = [[
            project['code'], project['title'],
            project['category'].get('name') or 'N/A',
            project['status_label'] or 'N/A',
            project['address'].get('barangay') or project['venue_name'] or 'N/A',
            _text(project['event_date']), project['proponent'] or 'N/A',
            _text(project['beneficiaries']),
        ] for project in rows]
    data = [[
        Paragraph(escape(item), styles['small_header'])
        for item in headings
    ]]
    for row in body:
        data.append([Paragraph(_text(item), styles['small']) for item in row])
    table = Table(
        data,
        colWidths=[width * mm for width in widths],
        repeatRows=1,
        hAlign='LEFT',
    )
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), GREEN),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0.35, BORDER),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, ROW_ALT]),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    return table


def build_summary_report_pdf(report_type, summary, active_filters):
    """Return a landscape A4 summary PDF as bytes."""
    styles = _styles()
    buffer = BytesIO()
    doc = _document(buffer, summary=True)
    scope_label = (
        'Infrastructure' if report_type == 'infrastructure'
        else 'Non-Infrastructure'
    )
    story = []
    _title_block(
        story,
        f'{scope_label} Project Summary',
        'Compiled from current published project revisions only. '
        f"Generated {timezone.localtime():%B %d, %Y at %I:%M %p}.",
        styles,
    )
    if active_filters:
        filter_text = ' | '.join(
            f'{label}: {value}' for label, value in active_filters
        )
        story.extend([
            Paragraph('Applied Filters', styles['section']),
            Paragraph(escape(filter_text), styles['body']),
            Spacer(1, 3 * mm),
        ])

    if report_type == 'infrastructure':
        metrics = [[
            _metric_card('Total Projects', summary['total_projects'], styles),
            _metric_card('Disclosed Contract Value', _currency(summary['total_contract_value']), styles),
            _metric_card('Average Physical Progress', _percent(summary['average_physical_progress']), styles),
        ]]
        breakdowns = [('Status', summary['status_counts'])]
    else:
        metrics = [[
            _metric_card('Total Programs / Projects', summary['total_projects'], styles),
            _metric_card('Total Beneficiaries', summary['total_beneficiaries'], styles),
        ]]
        breakdowns = [
            ('Status', summary['status_counts']),
            ('Category', summary['category_counts']),
        ]
    metric_table = Table(
        metrics,
        colWidths=[246 * mm / len(metrics[0])] * len(metrics[0]),
    )
    metric_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BACKGROUND', (0, 0), (-1, -1), SOFT_GREEN),
        ('BOX', (0, 0), (-1, -1), 0.5, BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, BORDER),
        ('LEFTPADDING', (0, 0), (-1, -1), 9),
        ('RIGHTPADDING', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.extend([metric_table, Spacer(1, 4 * mm)])

    for label, counts in breakdowns:
        values = ', '.join(
            f'{name}: {count}' for name, count in counts.items()
        ) or 'None'
        story.append(Paragraph(
            f'<b>Counts by {escape(label.lower())}:</b> {escape(values)}',
            styles['body'],
        ))
    story.extend([
        Spacer(1, 3 * mm),
        Paragraph('Published Projects', styles['section']),
    ])
    if summary['rows']:
        story.append(_summary_table(report_type, summary['rows'], styles))
    else:
        story.append(Paragraph(
            'No disclosed projects match the selected filters.',
            styles['empty'],
        ))
    doc.build(story, onFirstPage=_page_frame, onLaterPages=_page_frame)
    return buffer.getvalue()
