"""Email / share findings scaffold for human-in-the-loop workflow."""

from __future__ import annotations

import urllib.parse
from datetime import datetime, timezone

from blast_lib.config import UIConfig
from blast_lib.run_catalog import catalog_context_text, load_catalog
from blast_lib.user_session import UserRunSession


def findings_summary(config: UIConfig, session: UserRunSession | None) -> str:
    entries = load_catalog(config, session)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H UTC")
    body = [
        f"BLAST run findings ({ts})",
        "",
        f"Open dashboard: {config.dashboard_url}",
        "",
        "Summary (best set per folder):",
        "",
        catalog_context_text(entries, config),
        "",
        "Next: open Agent Chat or Submit Next Job on the dashboard.",
    ]
    return "\n".join(body)


def mailto_link(config: UIConfig, session: UserRunSession | None) -> str | None:
    if not config.notify_email:
        return None
    subject = urllib.parse.quote("BLAST run findings — review on dashboard")
    body = urllib.parse.quote(findings_summary(config, session)[:8000])
    return f"mailto:{config.notify_email}?subject={subject}&body={body}"
