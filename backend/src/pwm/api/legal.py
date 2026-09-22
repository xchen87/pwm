"""The privacy policy, terms and sub-processor list, served from docs/legal with the
company details filled in from configuration. Public: Google's consent screen and the app
stores need a URL for them. The markdown is rendered by a deliberately small converter."""

import html
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from pwm.config import Settings, get_settings

router = APIRouter()
LEGAL_DIR = Path(__file__).resolve().parents[4] / "docs" / "legal"
PAGES = {"privacy": "privacy-policy.md", "terms": "terms.md", "subprocessors": "subprocessors.md"}
STYLE = (
    "body{max-width:42rem;margin:2rem auto;padding:0 1rem;font:16px/1.55 system-ui,sans-serif;"
    "color:#1c1c1a;background:#fafaf7}table{border-collapse:collapse}td,th{border:1px solid #ddd;"
    "padding:.3rem .6rem;text-align:left;vertical-align:top}"
)


def placeholders(settings: Settings) -> dict[str, str]:
    retention = (
        "kept, encrypted, for as long as the source is connected; a retention window that "
        "removes older text automatically is planned and not yet in place."
    )
    return {
        "COMPANY": settings.legal_company,
        "PRODUCT": settings.legal_product,
        "ADDRESS": settings.legal_address,
        "CONTACT_EMAIL": settings.legal_contact_email,
        "GOVERNING_LAW": settings.legal_governing_law,
        "LIABILITY_CAP": settings.legal_liability_cap,
        "HOSTING_PROVIDER": settings.legal_hosting_provider,
        "HOSTING_REGION": settings.legal_hosting_region,
        "TERMS_VERSION": settings.terms_version,
        "MINIMUM_AGE": str(settings.minimum_age),
        "BACKFILL_DAYS": str(settings.backfill_days),
        "BACKUP_DAYS": str(settings.legal_backup_days),
        "PUBLIC_URL": settings.public_url.rstrip("/"),
        "RETENTION_NOTE": retention,
    }


DRAFT_BANNER = "**Draft for legal review. Not yet in force.**"


def render(markdown: str, values: dict[str, str]) -> str:
    text = re.sub(r"\{\{(\w+)\}\}", lambda m: values.get(m.group(1), m.group(0)), markdown)
    # The banner is not something to forget to remove: it disappears by itself once every
    # placeholder has been filled in, and not before.
    if "{{" not in text:
        text = text.replace(DRAFT_BANNER, "")
    out: list[str] = []
    paragraph: list[str] = []
    in_list: str | bool = False
    in_table = False

    def inline(line: str) -> str:
        line = html.escape(line)
        line = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
        return re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2">\1</a>', line)

    def flush() -> None:
        nonlocal in_list, in_table
        if paragraph:
            out.append(f"<p>{' '.join(inline(line) for line in paragraph)}</p>")
            paragraph.clear()
        if in_list:
            out.append(f"</{in_list}>")
            in_list = False
        if in_table:
            out.append("</table>")
            in_table = False

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            flush()
        elif stripped.startswith("#"):
            flush()
            level = len(stripped) - len(stripped.lstrip("#"))
            out.append(f"<h{level}>{inline(stripped.lstrip('#').strip())}</h{level}>")
        elif stripped.startswith("- ") or re.match(r"\d+\. ", stripped):
            ordered = not stripped.startswith("- ")
            if paragraph or in_table:
                flush()
            if not in_list:
                out.append("<ol>" if ordered else "<ul>")
                in_list = "ol" if ordered else "ul"
            out.append(f"<li>{inline(re.sub(r'^(- |\d+\. )', '', stripped))}</li>")
        elif stripped.startswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if all(set(c) <= set("-: ") for c in cells):
                continue
            if not in_table:
                if paragraph or in_list:
                    flush()
                out.append("<table>")
                in_table = True
                out.append("<tr>" + "".join(f"<th>{inline(c)}</th>" for c in cells) + "</tr>")
            else:
                out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in cells) + "</tr>")
        else:
            if in_table or in_list:
                flush()
            paragraph.append(stripped)
    flush()
    return "\n".join(out)


@router.get("/legal/{page}", response_class=HTMLResponse)
def legal(page: str) -> HTMLResponse:
    if page not in PAGES:
        raise HTTPException(404)
    settings = get_settings()
    body = render((LEGAL_DIR / PAGES[page]).read_text("utf-8"), placeholders(settings))
    title = html.escape(settings.legal_product)
    return HTMLResponse(
        f"<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' "
        f"content='width=device-width,initial-scale=1'><title>{title}</title>"
        f"<style>{STYLE}</style></head><body>{body}</body></html>"
    )
