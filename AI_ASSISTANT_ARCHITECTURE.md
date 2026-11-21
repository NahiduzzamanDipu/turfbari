# TURFBARI Website Assistant Architecture

## Overview

The public homepage assistant is a local, bilingual knowledge search feature. It does not call an LLM, embedding service, or any external AI API. It searches approved TurfBari content and current platform database values, then returns concise excerpts with source links. This is retrieval, not model training or free-form language generation.

## Components

- `AssistantSettings`: enabled state, bilingual greeting, language preference, daily limit and conversation retention.
- `KnowledgeArticle`: bilingual admin-reviewed help material; drafts are excluded.
- `KnowledgeSource` and `KnowledgeChunk`: locally stored source/version/status metadata and searchable text chunks. Search uses Unicode-aware lexical matching; there are no embeddings.
- `Conversation` and `ConversationMessage`: anonymous UUID plus token hash, optional authenticated user, bounded context, idempotency and feedback.
- `AssistantUsageDay`: locked daily message counter in Asia/Dhaka local time.

## Request flow

1. Browser fetches public status and suggested questions.
2. Django creates an anonymous conversation with a random secret whose hash alone is stored.
3. Message requests are validated for size, language, token, retention, usage caps and idempotency.
4. Email, phone-like and credential patterns are redacted or rejected.
5. Short follow-ups include recent visitor questions for local search context.
6. Search retrieves only enabled, indexed public knowledge. Current plan/SMS prices and public contact fields are read from authoritative database records.
7. The assistant returns source excerpts or a clear no-match response. It cannot invent or execute actions.

## Knowledge synchronization

Published FAQs, public active plans, current SMS rate, current published legal versions, admin-published help articles and a short product overview are indexed into the app database. Updates enqueue local re-indexing; the existing system tick handles pending work if Celery is unavailable. Admins can re-index on demand. Admin website imports are restricted to the configured site hostname; redirects, private addresses, unsupported content types and files over 1 MB are rejected. Text/Markdown uploads and imported pages remain drafts until reviewed and published.

If the local index is empty after a fresh deployment, the first public chat request builds it from approved database sources before searching.

## Endpoints

Public:

- `GET /api/public/assistant/status/`
- `POST /api/public/assistant/conversations/`
- `POST /api/public/assistant/messages/`
- `POST /api/public/assistant/conversations/clear/`
- `POST /api/public/assistant/feedback/`

Admin endpoints under `/api/admin/assistant/` manage local settings, articles/imports, suggested questions, sources, indexing and usage analytics. All require platform-admin permission.

Messages are limited to 2,000 characters, conversations to 40 messages, and daily volume to the configured cap. There are no provider credentials, outbound model requests, token charges or API setup requirements.
