import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db import connection
from apps.infrastructure.models import InfrastructureProject
from apps.non_infrastructure.models import NonInfrastructureProject

def get_db_columns(table_name):
    """Get actual column names from PostgreSQL."""
    c = connection.cursor()
    c.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s
        ORDER BY column_name
    """, [table_name])
    return sorted([r[0] for r in c.fetchall()])

def get_model_columns(model):
    """Get expected columns from Django model."""
    return sorted({
        f.column for f in model._meta.get_fields()
        if getattr(f, 'concrete', False) and not f.many_to_many
    })

# Verify both tables
checks = [
    (InfrastructureProject, 'infrastructure_infrastructureproject'),
    (NonInfrastructureProject, 'non_infrastructure_noninfrastructureproject'),
]

for model, table in checks:
    model_cols = get_model_columns(model)
    db_cols = get_db_columns(table)
    
    print(f"\n{'='*60}")
    print(f"Table: {table}")
    print(f"{'='*60}")
    print(f"Django Model Columns: {len(model_cols)}")
    print(f"Database Columns: {len(db_cols)}")
    
    if set(model_cols) == set(db_cols):
        print("✓ Schema is IN SYNC")
    else:
        print("✗ Schema MISMATCH")
        model_only = set(model_cols) - set(db_cols)
        db_only = set(db_cols) - set(model_cols)
        if model_only:
            print(f"  In model but not DB: {model_only}")
        if db_only:
            print(f"  In DB but not model: {db_only}")
    
    print(f"\nColumns ({len(db_cols)}):")
    for col in db_cols:
        print(f"  - {col}")
