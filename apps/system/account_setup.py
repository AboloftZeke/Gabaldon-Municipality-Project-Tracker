"""Secure account-setup email delivery for users without passwords."""

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode


class AccountSetupDeliveryError(Exception):
    """Raised when an account-setup message cannot be delivered."""


def send_account_setup_email(user, request):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    setup_url = request.build_absolute_uri(
        reverse(
            'account_setup_confirm',
            kwargs={'uidb64': uid, 'token': token},
        )
    )
    context = {
        'user': user,
        'setup_url': setup_url,
        'expiry_hours': max(1, settings.PASSWORD_RESET_TIMEOUT // 3600),
    }
    subject = ''.join(
        render_to_string(
            'registration/account_setup_subject.txt',
            context,
        ).splitlines()
    )
    message = EmailMultiAlternatives(
        subject,
        render_to_string('registration/account_setup_email.txt', context),
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
    )
    message.attach_alternative(
        render_to_string('registration/account_setup_email.html', context),
        'text/html',
    )

    try:
        sent_count = message.send(fail_silently=False)
    except Exception as exc:
        raise AccountSetupDeliveryError from exc

    if sent_count != 1:
        raise AccountSetupDeliveryError
