# TURFBARI Local Assistant Security

## Boundaries

The assistant is read-only. It cannot invoke booking, payment, subscription, account, database write, or shell operations. It searches published public content and selected public platform facts only. It does not provide legal or payment verification.

## No external AI service

- No LLM, embedding API, model provider, API key or third-party AI network call is used.
- Knowledge chunks and search results remain inside the TurfBari application database.
- Website imports are admin-triggered, same-site only, HTTPS, public-address validated, redirect-disabled and limited to text up to 1 MB.
- The migration clears any legacy encrypted provider credential before removing the credential column.

## Conversations

- Anonymous conversations use UUIDs and high-entropy tokens; only token hashes are stored.
- Authenticated conversations are bound to their creator. There is no public transcript-list endpoint.
- Email and phone-like patterns are redacted before storage; obvious password/payment credential submissions are rejected.
- Conversation text is removed after the configured retention period (1–365 days, default 30) by the periodic maintenance tick. Admin analytics shows metadata, not message contents.
- Daily limits and IP/conversation rate limits reduce abuse.

## Knowledge sources

- Search includes only enabled, indexed public materials. Tenant-private records, customer lists, bookings, payment data, internal notes, credentials, unpublished drafts and inactive plans are excluded.
- Live plan/SMS prices and public contact data come from their current database settings.
- Imported files are UTF-8 text or Markdown up to 1 MB and are unpublished drafts until reviewed.
- Source text is escaped/rendered as text and never executed as HTML or instructions.

The assistant is a retrieval feature, not a trained model. It cites source material and returns a no-match message instead of inventing unsupported facts.
