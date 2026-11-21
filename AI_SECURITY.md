# TURFBARI AI Security and Privacy

## Boundaries

The assistant is public, read-only and cannot invoke booking, payment, subscription, account, SQL or shell operations. Source text is quoted reference data and never supersedes system rules. Answers are not payment verification or legal advice. The assistant does not claim to be a human agent.

## Provider secrets and outbound requests

- API keys are Fernet-encrypted at rest using the existing Django secret and masked in the admin interface/API.
- Provider calls run only on Django over HTTPS. HTTP, credentials embedded in provider URLs, non-public DNS addresses and redirects are rejected.
- The admin “Test provider” action makes a real, potentially billable provider request.
- Rotating `DJANGO_SECRET_KEY` makes previously encrypted credentials unreadable; save the provider key again afterward.

## Conversations

- Anonymous IDs use UUIDs and high-entropy tokens; only token hashes are stored.
- Authenticated conversations are bound to their creator. There is no public transcript-list endpoint.
- Email and phone-like patterns are redacted before model submission/storage; obvious password/payment-credential submissions are rejected. Visitors are told not to submit sensitive data.
- Conversation content is removed after the configured retention period (1–365 days, default 30) by the periodic maintenance tick. The admin analytics view shows metadata, not message text.
- Daily request caps and IP/conversation rate limits bound abuse and provider costs.

## Retrieval and uploads

- Retrieval includes only approved public material; no tenant data, customer records, payment records, internal admin notes, credentials, unpublished drafts or inactive plans.
- Live plan prices, SMS segment pricing and public contact fields are queried from authoritative platform settings/models.
- Help uploads are UTF-8 text or Markdown up to 1 MB, imported as unpublished drafts. Website imports are restricted to the configured public-site host, require HTTPS and public DNS, disallow redirects, and accept only text content up to 1 MB.
- Retrieved text is treated as untrusted prompt-injection input. Uploads are never executed and chat responses are rendered without injecting HTML.

## Retention and cost

Prompt/completion tokens reported by the provider are stored. An optional estimate is calculated from admin-configured USD rates per million chat tokens; it excludes embedding/indexing costs. No cost is shown as exact provider billing. Configure daily caps conservatively and monitor provider invoices.
