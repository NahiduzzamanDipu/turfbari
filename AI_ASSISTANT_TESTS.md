# TURFBARI Website Assistant Verification

Backend tests:

```powershell
python -m pytest -q tests/test_assistant.py
```

Frontend checks:

```powershell
npm run typecheck
npm test -- --reporter=dot
npm run build
```

Coverage includes local-only status, no external provider configuration, approved-source retrieval, bilingual output, follow-up context, honest no-match behavior, PII redaction, idempotency, daily limits, draft exclusion, indexing, and admin permissions.

Manual UI check: at desktop and mobile widths, keyboard-open the homepage widget, switch language, ask a published FAQ question, follow a suggested question, inspect citations, retry and clear the conversation. Re-index after publishing new knowledge. Verify the widget remains available without any third-party AI credentials.
