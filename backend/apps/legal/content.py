"""Legal document text: one place that decides which HTML is allowed (nothing here imports models, so
migrations can use it too)."""

import html
import re

import nh3

ALLOWED_TAGS = {
    "h2", "h3", "h4", "p", "br", "hr", "strong", "b", "em", "i", "u", "s",
    "ul", "ol", "li", "a", "blockquote",
    "table", "thead", "tbody", "tr", "th", "td",
}  # fmt: skip
ALLOWED_ATTRIBUTES = {"a": {"href", "title"}, "th": {"colspan", "rowspan"}, "td": {"colspan", "rowspan"}}
MAX_BODY = 200_000


def sanitize(raw: str) -> str:
    """Strips scripts, styles, event handlers, iframes, images and unsafe links; keeps simple formatting."""
    cleaned = nh3.clean(
        raw or "",
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes={"http", "https", "mailto", "tel"},
        link_rel="noopener noreferrer nofollow",
        strip_comments=True,
    )
    return cleaned.strip()


def is_blank(body: str) -> bool:
    return not to_text(body).strip()


def to_text(body: str) -> str:
    """Plain text, one block per line (for comparing versions and search)."""
    text = re.sub(r"(?i)<br\s*/?>", "\n", body or "")
    text = re.sub(r"(?i)</(p|h[1-6]|li|tr|blockquote|table|ul|ol)>", "\n", text)
    text = re.sub(r"(?i)</t[dh]>", " | ", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


_BOLD = re.compile(r"\*\*([^*]+)\*\*")


def _inline(text: str) -> str:
    return _BOLD.sub(r"<strong>\1</strong>", html.escape(text, quote=False))


def markdown_lite_to_html(text: str) -> str:
    """Converts the old Terms editor format (# heading, - bullet, 1. item, **bold**, blank line = new
    paragraph) to HTML, so migrated documents look exactly as before."""
    out: list[str] = []
    para: list[str] = []
    items: list[str] = []
    ordered = False

    def flush_para():
        if para:
            out.append(f"<p>{_inline(' '.join(para))}</p>")
            para.clear()

    def flush_list():
        if items:
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>" + "".join(f"<li>{_inline(i)}</li>" for i in items) + f"</{tag}>")
            items.clear()

    for raw in (text or "").replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        bullet = re.match(r"^[-*•]\s+(.*)$", line)
        numbered = re.match(r"^(\d+|[০-৯]+)[.)]\s+(.*)$", line)
        if not line:
            flush_para()
            flush_list()
        elif line.startswith("# ") or line.startswith("## "):
            flush_para()
            flush_list()
            level, body = ("h2", line[2:]) if line.startswith("# ") else ("h3", line[3:])
            out.append(f"<{level}>{_inline(body)}</{level}>")
        elif bullet or numbered:
            flush_para()
            is_ordered = bool(numbered)
            if items and is_ordered != ordered:
                flush_list()
            ordered = is_ordered
            items.append(numbered.group(2) if numbered else bullet.group(1))
        else:
            flush_list()
            para.append(line)
    flush_para()
    flush_list()
    return sanitize("".join(out))


def has_bengali(text: str) -> bool:
    return bool(re.search(r"[ঀ-৿]", text or ""))
