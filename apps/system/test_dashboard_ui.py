"""Shared dashboard navigation and message presentation contracts."""

import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.messages import constants
from django.contrib.messages.storage.base import Message
from django.contrib.messages.storage.cookie import CookieStorage
from django.test import RequestFactory, TestCase
from django.urls import reverse

from .models import UserRole


class DashboardPresentationTests(TestCase):
    def test_header_and_sidebar_use_the_same_dark_green_token(self):
        base_css = (Path(settings.BASE_DIR) / 'static/css/templates/base.css').read_text()
        ui_css = (Path(settings.BASE_DIR) / 'static/css/components/ui.css').read_text()
        header = re.search(
            r'\.site-header\s*\{[^}]*?background:\s*([^;]+);', base_css,
        )
        sidebar = re.search(
            r'\.ui-sidebar-layout > \.sidebar\.ui-sidebar\s*\{[^}]*?background:\s*([^;]+);',
            ui_css,
        )
        self.assertIsNotNone(header)
        self.assertIsNotNone(sidebar)
        self.assertEqual(header.group(1), sidebar.group(1))
        self.assertEqual(header.group(1), 'var(--ui-green-800)')

    def setUp(self):
        self.admin = User.objects.create_superuser('ui-admin', 'ui-admin@example.com', 'password')
        self.engineer = User.objects.create_user('ui-engineer', password='password', is_staff=True)
        self.mayor = User.objects.create_user('ui-mayor', password='password', is_staff=True)
        self.engineering_head = User.objects.create_user('ui-e-head', password='password', is_staff=True)
        self.mayor_head = User.objects.create_user('ui-m-head', password='password', is_staff=True)
        for user, department, role in (
            (self.engineer, 'engineer', 'staff'),
            (self.mayor, 'mayor', 'staff'),
            (self.engineering_head, 'engineer', 'head'),
            (self.mayor_head, 'mayor', 'head'),
        ):
            UserRole.objects.create(user=user, department=department, role=role)

    def test_role_dashboards_share_theme_and_account_navigation(self):
        for user, route in (
            (self.admin, 'admin_dashboard'),
            (self.engineer, 'engineering_dashboard'),
            (self.mayor, 'mayor_dashboard'),
            (self.engineering_head, 'engineering_head_dashboard'),
            (self.mayor_head, 'mayor_head_dashboard'),
        ):
            with self.subTest(route=route):
                self.client.force_login(user)
                response = self.client.get(reverse(route))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'ui-dashboard-theme')
                self.assertContains(response, 'css/components/ui.css')
                self.assertContains(response, 'css/components/toasts.css')
                self.assertContains(response, 'js/components/toasts.js')
                self.assertEqual(response.content.decode().count('aria-label="Account navigation"'), 1)
                self.assertContains(response, reverse('password_change'))
                self.assertContains(response, 'Change Password')
                self.assertContains(response, reverse('logout'))
                self.assertNotContains(response, 'class="ui-toast"')

    def test_message_types_float_outside_sidebar_and_are_dismissible(self):
        self.client.force_login(self.admin)
        self.client.cookies[CookieStorage.cookie_name] = CookieStorage(RequestFactory().get('/'))._encode([
            Message(constants.SUCCESS, 'Project created successfully'),
            Message(constants.ERROR, 'Unable to save'),
            Message(constants.WARNING, 'Check the entered dates'),
            Message(constants.INFO, 'Review is still pending'),
        ])
        response = self.client.get(reverse('admin_dashboard'))
        html = response.content.decode()
        sidebar = html.split('<aside class="sidebar ui-sidebar"', 1)[1].split('</aside>', 1)[0]
        self.assertIn('class="ui-toasts"', html)
        self.assertLess(html.index('class="ui-toasts"'), html.index('<aside class="sidebar ui-sidebar"'))
        for kind in ('success', 'error', 'warning', 'info'):
            self.assertIn(f'ui-toast--{kind}', html)
        self.assertIn('role="alert"', html)
        self.assertIn('role="status"', html)
        self.assertEqual(html.count('aria-label="Dismiss notification"'), 4)
        self.assertNotIn('ui-toast', sidebar)
        self.assertNotIn('Project created successfully', sidebar)

    def test_role_navigation_and_redirect_messages_remain_intact(self):
        self.client.force_login(self.engineering_head)
        self.client.cookies[CookieStorage.cookie_name] = CookieStorage(RequestFactory().get('/'))._encode([
            Message(constants.SUCCESS, 'Saved'),
        ])
        response = self.client.get(reverse('engineering_dashboard'), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ui-toast--success')
        self.assertContains(response, 'Saved')
        self.assertNotContains(response, 'Non-Infrastructure Projects')
