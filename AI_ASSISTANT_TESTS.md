# AI Assistant Verification

Run backend tests from `backend/`:

```powershell
python -m pytest -q tests/test_assistant.py
```

Run frontend checks from `frontend/`:

```powershell
npm run typecheck
npm test -- --reporter=dot
npm run build
```

The backend suite covers encrypted/masked credentials, admin authorization, conversation-token isolation, PII redaction, request idempotency and retry, provider failure, daily caps, draft exclusion, published article indexing and live price retrieval. Provider tests use a controlled test double; real-provider smoke testing is the Admin **Test provider** button and requires configured credentials. A real provider integration is not claimed before that external credential/configuration exists.

For a manual UI check, open the public homepage at desktop and mobile widths, tab to the floating assistant, open/minimize/close it, start a fresh conversation, send English/Bengali/Banglish questions, retry a failed request, clear history, and use the source links. Verify the homepage continues to work if provider status is unavailable.
