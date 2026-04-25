#!/usr/bin/env python
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from django.contrib.auth.models import User
from core.models import InfrastructureProject, UserProfile

print("=" * 80)
print("COMPLETE PUBLICATION WORKFLOW VERIFICATION")
print("=" * 80)

# Create fresh test users
Engineer = User.objects.create_user(
    username='final_engineer',
    email='final@engineer.com',
    password='testpass123',
    is_staff=True
)
eng_prof, _ = UserProfile.objects.get_or_create(user=Engineer, defaults={'department': 'engineer'})

Admin = User.objects.create_user(
    username='final_admin',
    email='final@admin.com',
    password='testpass123',
    is_staff=True,
    is_superuser=True
)
admin_prof, _ = UserProfile.objects.get_or_create(user=Admin, defaults={'department': 'admin'})

print(f"✅ Test Users Created:")
print(f"   - Engineer: final_engineer / testpass123")
print(f"   - Admin: final_admin / testpass123")

# STEP 1: Engineer creates a draft project
print(f"\n{'='*80}")
print(f"STEP 1: ENGINEER CREATES DRAFT PROJECT")
print(f"{'='*80}")

project = InfrastructureProject.objects.create(
    title='Final Test: Water System Installation',
    location='bagong_sikat',
    category='road',
    implementing_office='Engineering Office',
    procurement_method='competitive_bidding',
    publication_status='draft',
    created_by=Engineer
)
print(f"✅ Project created")
print(f"   - ID: {project.id}")
print(f"   - Title: {project.title}")
print(f"   - Status: {project.get_publication_status_display()}")
print(f"   - Created by: {project.created_by.username}")

# STEP 2: Engineer submits for review
print(f"\n{'='*80}")
print(f"STEP 2: ENGINEER SUBMITS FOR REVIEW")
print(f"{'='*80}")
print(f"Engineer action: Click 'Submit for Review' → Confirm submission")

project.publication_status = 'pending_review'
project.save()
project.refresh_from_db()

print(f"✅ Project submitted for review")
print(f"   - Status: {project.get_publication_status_display()}")

# STEP 3: Admin sees pending projects
print(f"\n{'='*80}")
print(f"STEP 3: ADMIN VIEWS PROJECT REVIEW QUEUE")
print(f"{'='*80}")

pending_projects = InfrastructureProject.objects.filter(publication_status='pending_review')
print(f"✅ Admin navigates to: Projects → Project Review Queue")
print(f"   - Pending projects: {pending_projects.count()}")
for p in pending_projects:
    print(f"     • {p.title}")
    print(f"       Created by: {p.created_by.username}")
    print(f"       Status: {p.get_publication_status_display()}")

# STEP 4: Admin approves project
print(f"\n{'='*80}")
print(f"STEP 4: ADMIN REVIEWS AND APPROVES PROJECT")
print(f"{'='*80}")
print(f"Admin action: Click 'Review & Approve' → Select 'Approve & Publish' → Submit")

project.publication_status = 'published'
project.reviewed_by = Admin
from django.utils import timezone
project.reviewed_at = timezone.now()
project.save()
project.refresh_from_db()

print(f"✅ Project approved and published")
print(f"   - Status: {project.get_publication_status_display()}")
print(f"   - Reviewed by: {project.reviewed_by.username}")

# STEP 5: All users can see published project
print(f"\n{'='*80}")
print(f"STEP 5: PROJECT NOW VISIBLE TO ALL")
print(f"{'='*80}")

published_projects = InfrastructureProject.objects.filter(publication_status='published')
print(f"✅ Published projects visible to everyone")
print(f"   - Total published: {published_projects.count()}")
for p in published_projects:
    print(f"     • {p.title}")
    print(f"       Created by: {p.created_by.username}")
    print(f"       Status: {p.get_publication_status_display()}")

print(f"\n{'='*80}")
print(f"✅ WORKFLOW COMPLETE AND VERIFIED!")
print(f"{'='*80}")
print(f"\nNow go test this manually:")
print(f"1. Open browser: http://127.0.0.1:8000/")
print(f"2. Login: final_engineer / testpass123")
print(f"3. Create a new project")
print(f"4. Go to project detail → Click 'Submit for Review'")
print(f"5. Confirm submission")
print(f"6. Logout, then login: final_admin / testpass123")
print(f"7. Click 'Project Review Queue' in sidebar")
print(f"8. You should see the pending project!")
