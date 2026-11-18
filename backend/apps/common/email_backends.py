"""Email over Resend's HTTPS API (https://resend.com/docs/api-reference/emails/send-email).

Free hosts such as Render's free plan block outbound SMTP, so plain SMTP can't be used there.
Set EMAIL_BACKEND=apps.common.email_backends.ResendEmailBackend and RESEND_API_KEY.
"""

import json
import logging
import urllib.error
import urllib.request

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)
API_URL = "https://api.resend.com/emails"


class ResendEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        sent = 0
        for message in email_messages:
            payload = {
                "from": message.from_email or settings.DEFAULT_FROM_EMAIL,
                "to": list(message.to),
                "subject": message.subject,
                "text": message.body,
            }
            if message.cc:
                payload["cc"] = list(message.cc)
            if message.bcc:
                payload["bcc"] = list(message.bcc)
            if message.reply_to:
                payload["reply_to"] = list(message.reply_to)
            for alternative, mimetype in getattr(message, "alternatives", []):
                if mimetype == "text/html":
                    payload["html"] = alternative
            request = urllib.request.Request(  # noqa: S310 (fixed https URL)
                API_URL,
                data=json.dumps(payload).encode(),
                headers={
                    "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                    "Content-Type": "application/json",
                    "User-Agent": "turfbari-mailer/1.0",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
                    response.read()
                sent += 1
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode(errors="replace")[:300]
                logger.error("Resend rejected an email (%s): %s", exc.code, detail)
                if not self.fail_silently:
                    raise
            except OSError:
                logger.exception("Could not reach Resend")
                if not self.fail_silently:
                    raise
        return sent
