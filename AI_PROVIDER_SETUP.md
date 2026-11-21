# TURFBARI AI Provider Setup

## Provider

The backend implements the common OpenAI-compatible `/chat/completions` and `/embeddings` APIs. No provider SDK or frontend key is used. The admin chooses a provider HTTPS base URL, chat model and embedding model.

## Configure

1. Ensure `DJANGO_SECRET_KEY` is set to a strong, persistent production secret.
2. Ensure Redis/Celery is configured for asynchronous knowledge indexing. On Render, the existing periodic `POST /api/system/tick/` job can process pending indexing when a worker is unavailable.
3. Sign in as Platform Admin and open **AI Assistant**.
4. Enter the provider HTTPS URL, supported chat model, supported embedding model, and provider API key. Save. The key is encrypted and only a masked form is shown later.
5. Set generation length, context, retention, daily message cap, token rates, welcome messages and default language. Token rates are per million tokens in USD; leave zero if unknown.
6. Use **Test provider**. It performs a real one-word completion request and can incur a small fee.
7. Re-index public knowledge. Verify sources show Indexed, then ask a test question in English and Bengali.

## Required environment/configuration

No new provider environment variable is required: the key and endpoint are set under Admin → AI Assistant and the encrypted key uses `DJANGO_SECRET_KEY`. Existing deployment requirements still apply:

- `DJANGO_SECRET_KEY` stable and private.
- Existing database, Redis broker and Celery worker/beat, or Render’s configured system tick endpoint.
- Outbound HTTPS access from backend to the provider.
- Admin-only access to AI configuration.

Do not place a provider key in `VITE_*`, frontend `.env`, Git, logs or chat.

## Troubleshooting

- “Not configured”: save a valid provider key.
- “Provider rejected request”: confirm endpoint and model names/API access.
- “Provider unavailable”: check outbound network, provider status, DNS, credential validity and rate limits.
- Sources remain Pending without Celery: verify the external system tick is configured and authorized.
- Changing/rotating Django `SECRET_KEY`: re-enter the provider credential because old ciphertext cannot be decrypted.
- No current plan/SMS price: the authoritative platform data may not be configured; the assistant is instructed to say it cannot verify that value.
