# TURFBARI AI Assistant Architecture

## Overview

The public homepage assistant is an informational, read-only feature. React calls Django endpoints; Django performs retrieval and calls an OpenAI-compatible HTTPS API. Provider credentials are encrypted in `AssistantSettings` with the existing Fernet utility and are never sent to the browser. Provider/model settings are stored in the platform database, not frontend environment variables.

## Components

- `apps.assistant.AssistantSettings`: provider, model, generation limits, daily cap, retention, cost rates, welcome text and encrypted API key.
- `KnowledgeArticle`: bilingual, administrator-reviewed help content. Drafts are excluded.
- `KnowledgeSource` and `KnowledgeChunk`: source/version/status metadata and chunk text/embedding. Embeddings are stored as JSON so the local MariaDB and hosted PostgreSQL configurations share the same schema; cosine similarity is calculated in the app. If embeddings are unavailable, retrieval uses lexical overlap. The initial index scans at most 1,500 chunks per request; use PostgreSQL/pgvector or a dedicated retrieval service if the approved corpus grows beyond this bound.
- `Conversation` / `ConversationMessage`: anonymous UUID plus token hash, optional authenticated user, bounded message history, request idempotency, retrieved source references, model usage and feedback.
- `AssistantUsageDay`: locked daily message counter, based on Asia/Dhaka local dates.

## Request flow

1. The browser requests public status and suggested questions.
2. A new conversation gets a random UUID and a 256-bit random secret; only its SHA-256 digest is stored.
3. The message endpoint validates size, language, conversation token, retention, daily cap and request idempotency.
4. Email addresses, phone-like numbers, and detected credential patterns are redacted before conversation storage or model submission. Password/payment credential patterns are rejected.
5. Retrieval uses enabled, indexed public chunks. Live subscription plans, SMS rates and contact details come directly from current authoritative database rows; old embeddings are excluded for SMS pricing.
6. Django sends a grounded prompt plus bounded context to the configured provider. The answer and reported token usage are stored. Only preconfigured internal application routes and retrieved local source links are returned.
7. Provider failure returns a safe error. Homepage and booking flows remain independent.

## Knowledge synchronization

Published FAQs, public active plans, current SMS rate, current effective published legal versions and published help articles are indexed. Updates mark the related source pending through model signals and enqueue Celery re-indexing. If the broker is unreachable, the existing `/api/system/tick/` maintenance job processes pending sources. Admins can request re-indexing manually. Admin-imported public URLs are limited to the configured site host; redirects, private addresses, unsupported content types and files over 1 MB are rejected. Uploads are UTF-8 `.txt`/Markdown and are always imported as drafts.

## Public endpoints

- `GET /api/public/assistant/status/`
- `POST /api/public/assistant/conversations/`
- `POST /api/public/assistant/messages/`
- `POST /api/public/assistant/conversations/clear/`
- `POST /api/public/assistant/feedback/`

The conversation token is required for message, clear and feedback requests. Public chat is limited by IP and conversation token. Message text is limited to 2,000 characters, conversations to 40 stored messages, and daily usage is limited by admin setting.

## Admin endpoints

All require the platform-admin permission:

- `/api/admin/assistant/settings/`
- `/api/admin/assistant/test/`
- `/api/admin/assistant/articles/` and `/api/admin/assistant/articles/{uuid}/`
- `/api/admin/assistant/import/`
- `/api/admin/assistant/questions/` and `/api/admin/assistant/questions/{uuid}/`
- `/api/admin/assistant/sources/` and `/api/admin/assistant/sources/{uuid}/`
- `/api/admin/assistant/reindex/`
- `/api/admin/assistant/analytics/`

Admin APIs mask credentials, never return their plaintext, and audit settings, sources and content changes.

## Initial-release boundaries

There is no vector database dependency: local development uses MariaDB, while the code stores portable JSON embeddings and calculates similarity in Python. Website crawl is administrator-triggered for an explicitly supplied same-site URL, not an unrestricted crawler. SMS/email templates, unpublished legal drafts, tenant-private records, customer lists, bookings and payment submissions are not knowledge sources. The assistant cannot execute operations.
