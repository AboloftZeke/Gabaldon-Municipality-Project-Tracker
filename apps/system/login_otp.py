"""Secure email OTP issuance and verification for pending logins."""

import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import User
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from .models import LoginOTPChallenge


class OTPCooldownError(Exception):
    pass


class OTPRateLimitError(Exception):
    pass


class OTPDeliveryError(Exception):
    pass


def _new_code():
    return f'{secrets.randbelow(1_000_000):06d}'


def _create_challenge(user):
    now = timezone.now()
    cooldown_start = now - timedelta(seconds=settings.LOGIN_OTP_RESEND_COOLDOWN)
    rate_window_start = now - timedelta(seconds=settings.LOGIN_OTP_RATE_WINDOW)

    with transaction.atomic():
        User.objects.select_for_update().get(pk=user.pk)
        latest = (
            LoginOTPChallenge.objects.filter(user=user)
            .order_by('-created_at')
            .first()
        )
        if latest and latest.created_at > cooldown_start:
            raise OTPCooldownError
        if LoginOTPChallenge.objects.filter(
            user=user,
            created_at__gte=rate_window_start,
        ).count() >= settings.LOGIN_OTP_RATE_LIMIT:
            raise OTPRateLimitError

        LoginOTPChallenge.objects.filter(
            user=user,
            consumed_at__isnull=True,
        ).update(consumed_at=now)

        code = _new_code()
        challenge = LoginOTPChallenge.objects.create(
            user=user,
            code_hash=make_password(code),
            expires_at=now + timedelta(seconds=settings.LOGIN_OTP_TIMEOUT),
            attempts_remaining=settings.LOGIN_OTP_MAX_ATTEMPTS,
        )
    return challenge, code


def issue_login_otp(user):
    challenge, code = _create_challenge(user)
    context = {
        'user': user,
        'code': code,
        'expiry_minutes': max(1, settings.LOGIN_OTP_TIMEOUT // 60),
    }
    subject = ''.join(render_to_string(
        'registration/login_otp_subject.txt',
        context,
    ).splitlines())
    message = EmailMultiAlternatives(
        subject,
        render_to_string('registration/login_otp_email.txt', context),
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
    )
    message.attach_alternative(
        render_to_string('registration/login_otp_email.html', context),
        'text/html',
    )
    try:
        message.send(fail_silently=False)
    except Exception as exc:
        LoginOTPChallenge.objects.filter(pk=challenge.pk).update(
            consumed_at=timezone.now(),
        )
        raise OTPDeliveryError from exc
    return challenge


def verify_login_otp(challenge_id, code):
    now = timezone.now()
    with transaction.atomic():
        challenge = (
            LoginOTPChallenge.objects.select_for_update()
            .select_related('user')
            .filter(pk=challenge_id)
            .first()
        )
        if (
            challenge is None
            or challenge.consumed_at is not None
            or challenge.expires_at <= now
            or challenge.attempts_remaining == 0
        ):
            return None

        if not check_password(code, challenge.code_hash):
            challenge.attempts_remaining -= 1
            if challenge.attempts_remaining == 0:
                challenge.consumed_at = now
            challenge.save(update_fields=['attempts_remaining', 'consumed_at'])
            return None

        challenge.consumed_at = now
        challenge.save(update_fields=['consumed_at'])
        return challenge.user


def active_challenge(challenge_id):
    now = timezone.now()
    return LoginOTPChallenge.objects.select_related('user').filter(
        pk=challenge_id,
        consumed_at__isnull=True,
        expires_at__gt=now,
        attempts_remaining__gt=0,
    ).first()
