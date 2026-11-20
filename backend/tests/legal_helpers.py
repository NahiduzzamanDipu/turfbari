"""Small helpers for driving the Legal & Compliance admin API in tests."""

from apps.legal.models import LegalDocument


def doc_id(category: str, sector_slug: str | None = None) -> str:
    qs = LegalDocument.objects.filter(category=category)
    qs = qs.filter(sector__slug=sector_slug) if sector_slug else qs.filter(sector__isnull=True)
    return str(qs.get().pk)


def draft(admin, category="terms", sector=None, body_en="<h2>Terms</h2><p>Be on time</p>", **fields):
    d = admin.post(f"/api/admin/legal/documents/{doc_id(category, sector)}/versions/").json()
    payload = {"title_en": d["title_en"] or "Terms", "body_en": body_en, **fields}
    r = admin.put(f"/api/admin/legal/versions/{d['id']}/", payload, format="json")
    assert r.status_code == 200, r.json()
    return r.json()


def publish(
    admin, category="terms", sector=None, body_en="<h2>Terms</h2><p>Be on time</p>", reaccept="all", **kw
):
    d = draft(admin, category, sector, body_en)
    body = {"reacceptance": reaccept, **kw}
    r = admin.post(f"/api/admin/legal/versions/{d['id']}/publish/", body, format="json")
    assert r.status_code == 200, r.json()
    return r.json()


def accepted_ids(turf_page: dict) -> list[int]:
    return [d["version_id"] for d in turf_page["legal"]]
