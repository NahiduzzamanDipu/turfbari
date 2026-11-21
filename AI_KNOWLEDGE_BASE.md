# TURFBARI AI Knowledge Base

## Approved source types

The index includes published homepage FAQs, public active subscription plans, the current SMS price, current effective published legal versions, and administrator-published bilingual help articles. The platform overview is a reviewed built-in article. Dynamic prices and public contact details are queried live on relevant questions rather than trusted from an old embedding.

Only these safe public routes may be returned as source/navigation links: FAQ (`/#faq-title`), plans (`/#plans`), legal document routes, turf registration (`/register-turf`), demo pages, contact (`/#contact`) and legal index (`/legal`). The browser renders returned answer text as text/Markdown components, not raw HTML.

## Add a help article

1. In Admin → AI Assistant, enter English title/content and optional Bengali title/content.
2. Save as a draft and review the content for accuracy and privacy.
3. Enable “Published and available to the public assistant”, then save.
4. The source is marked pending and indexed in the background. Use **Re-index public knowledge** if needed.
5. Check the source status in the Knowledge indexing card.

Website imports and text/Markdown uploads are drafts. Imported pages are static snapshots; re-import when that page changes. Never include internal support notes, API credentials, account data, customer information, or payment records.

## Index status

- Pending: content changed or awaits a worker/tick.
- Processing: chunking and optional embedding generation are running.
- Indexed: retrieval can use the source.
- Failed: inspect the safe error code; the source does not become model context until successfully indexed.

Unpublished FAQ/article content and draft, archived, future-effective or superseded legal text is excluded. Disable a source in Admin → AI Assistant to remove it from retrieval immediately; re-indexing reconciles removed and unpublished records.
