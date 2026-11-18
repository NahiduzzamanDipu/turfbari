import json
from unittest import mock

from django.core.mail import send_mail


def test_resend_backend_posts_json(settings):
    settings.EMAIL_BACKEND = "apps.common.email_backends.ResendEmailBackend"
    settings.RESEND_API_KEY = "re_test"
    settings.DEFAULT_FROM_EMAIL = "TurfBari <onboarding@resend.dev>"
    with mock.patch("apps.common.email_backends.urllib.request.urlopen") as urlopen:
        urlopen.return_value.__enter__.return_value.read.return_value = b'{"id":"1"}'
        assert send_mail("Hi", "Body", None, ["a@example.com"]) == 1
    request = urlopen.call_args.args[0]
    assert request.full_url == "https://api.resend.com/emails"
    assert request.headers["Authorization"] == "Bearer re_test"
    assert json.loads(request.data) == {
        "from": "TurfBari <onboarding@resend.dev>",
        "to": ["a@example.com"],
        "subject": "Hi",
        "text": "Body",
    }
