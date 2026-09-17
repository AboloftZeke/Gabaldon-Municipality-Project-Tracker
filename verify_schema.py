"""Verify application tables and columns against Django's active model registry."""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.apps import apps
from django.db import connection

def verify_schema():
    models = [model for model in apps.get_models(include_auto_created=True)
              if model._meta.app_label in {'system', 'infrastructure', 'non_infrastructure'}
              and model._meta.managed]
    expected = {model._meta.db_table for model in models}
    with connection.cursor() as cursor:
        tables = set(connection.introspection.table_names(cursor))
        actual = {name for name in tables if name.startswith(('system_', 'infrastructure_', 'non_infrastructure_'))}
        if actual != expected:
            raise AssertionError(f'Unexpected tables: {actual - expected}; missing: {expected - actual}')
        for model in models:
            columns = {column.name for column in connection.introspection.get_table_description(cursor, model._meta.db_table)}
            expected_columns = {field.column for field in model._meta.local_fields}
            if columns != expected_columns:
                raise AssertionError(f'{model._meta.db_table}: {columns ^ expected_columns}')
    return sorted(expected)

if __name__ == '__main__':
    for table in verify_schema():
        print(table)
    print('All application tables and columns match the active models.')
