import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.contrib.auth import get_user_model
from apps.infrastructure.forms import InfrastructureProjectForm
from apps.system.models import Contractor, FundSource, ImplementingOffice, InfrastructureCategory

u = get_user_model().objects.create_user(username='u1', email='u1@example.com', password='Testpass123!')
cat = InfrastructureCategory.objects.create(category_code='roads', category_name='Roads')
off = ImplementingOffice.objects.create(office_name='Engineering Office')
con = Contractor.objects.create(contractor_name='Sample Contractor')
fs = FundSource.objects.create(fund_source_code='local', fund_source_name='Local Funds')
form = InfrastructureProjectForm(data={
    'title': 'Road Improvement Project',
    'description': 'desc',
    'category': str(cat.infrastructure_category_id),
    'implementing_office': str(off.office_id),
    'contractor': str(con.contractor_id),
    'procurement_method': 'competitive_bidding',
    'award_status': 'awarded',
    'street': 'Main Street',
    'barangay': 'San Jose',
    'municipality': 'Gabaldon',
    'province': 'Nueva Ecija',
    'latitude': '15.1234567',
    'longitude': '120.9876543',
    'planned_start_date': '2026-01-01',
    'planned_end_date': '2026-12-31',
    'cost_progress_percentage': '25.00',
    'physical_progress_percentage': '40.00',
    'abc_amount': '1500000.00',
    'contract_price': '1400000.00',
    'fund_source': str(fs.fund_source_id),
    'actual_expenditure': '500000.00',
    'duration_days': '365',
})
print('is_valid', form.is_valid(), form.errors)
infra = form.save(user=u)
print('saved address', infra.address, infra.address.latitude, infra.address.longitude)
print('raw rows', list(__import__('apps.system.models', fromlist=['Infrastructure_Project']).Infrastructure_Project.objects.all().values_list('infrastructure_id', 'project_id', 'infrastructure_title')))
print('filtered rows', list(__import__('apps.system.models', fromlist=['Infrastructure_Project']).Infrastructure_Project.objects.filter(project_id=infra.project_id).values_list('infrastructure_id', 'project_id', 'infrastructure_title')))
print('project id', infra.project_id, infra.project.project_id)
print('project lookup count', type(infra.project), infra.project)
edit_form = InfrastructureProjectForm(instance=infra.project)
print('edit form initial keys', sorted(edit_form.initial.keys()))
print('lat', edit_form.initial.get('latitude'))
print('lon', edit_form.initial.get('longitude'))
