# TURFBARI Website Assistant Knowledge Base

## Approved sources

The local search index contains published homepage FAQs, public active subscription plans, current SMS price, current published legal documents, administrator-published bilingual help articles and a reviewed product overview. Current prices and public contact data are read from authoritative database settings when relevant.

Only internal application routes are returned as links. Answers are rendered as text/Markdown, never raw HTML.

## Publish an article

1. In **Admin → Website Assistant**, add English content and optional Bengali translation.
2. Save it as a draft and review accuracy and privacy.
3. Publish the article when ready.
4. Re-index public knowledge and confirm the source shows **Indexed**.

Website imports and text/Markdown uploads are drafts. Re-import a page to refresh its stored copy. Do not publish internal notes, credentials, customer information or payment records.

## Index status

- Pending: content changed or awaits background processing.
- Processing: text is being split into local searchable chunks.
- Indexed: local lexical search can use the source.
- Failed: inspect the safe error code; failed sources are not available to visitors.

No embeddings or external model calls are used. Unpublished FAQs/articles, draft or archived policies, inactive plans and tenant-private data are excluded.
