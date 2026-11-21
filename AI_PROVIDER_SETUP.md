# TURFBARI Local Website Assistant Setup

The assistant requires no AI provider, API key, model account, or paid external service. It searches locally indexed, published TurfBari content and live values from the application database.

## Enable and populate

1. Sign in as Platform Admin and open **Website Assistant**.
2. Enable the assistant, set English/Bengali welcome text and daily limits, then save.
3. Review published FAQs, active public plans, current SMS pricing, published legal documents and public contact settings. Those are indexed from the site's own data.
4. Add bilingual help articles as needed. Imported pages/uploads are drafts; review and publish them before visitors can receive those excerpts.
5. Use **Re-index public knowledge** after publishing changes. The first public chat also builds the index automatically if it is empty. The existing system maintenance tick processes later updates if no Celery worker is available.
6. Ask test questions in English, Bengali and Banglish on the homepage.

## How answers work

This is a local retrieval assistant, not a generative LLM. It finds matching approved content and quotes the relevant passages with links. When the site's published data does not contain an answer, it says so rather than guessing. It does not learn/train a model; publishing and re-indexing updates its searchable website knowledge.

## No external AI connection

The assistant code makes no external LLM or embedding requests and stores no model API key. Its old provider settings and encrypted credential are removed by migration. It has no provider test button because no provider is involved.

## Troubleshooting

- If the widget is hidden, confirm **Enable assistant on the public homepage** is on.
- If a question has no useful result, publish a relevant FAQ/help article and re-index.
- Check source status in **Website Assistant → Knowledge indexing**.
- Current plan, SMS price and public support details are queried directly from current platform data; verify those settings if they are missing.
- The assistant is intentionally limited to published material and cannot answer arbitrary general questions reliably.
