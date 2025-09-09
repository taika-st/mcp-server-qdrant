"""
Outlook email tools for Qdrant-backed semantic search.

This module provides MCP tools designed for email/mailbox search use cases,
with semantic search, mailbox pattern analysis, and thread discovery.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastmcp import Context
from qdrant_client import models

from mcp_server_qdrant.qdrant import QdrantConnector, Entry, ArbitraryFilter

logger = logging.getLogger(__name__)


def _ensure_condition_list(condition: models.Condition | List[models.Condition] | None) -> List[models.Condition]:
    if condition is None:
        return []
    elif isinstance(condition, list):
        return condition
    else:
        return [condition]


def _format_email_entry(entry: Entry) -> str:
    if not entry.metadata:
        return f"<email><content>{entry.content}</content></email>"

    md = entry.metadata
    em = md.get("email", {}) if isinstance(md, dict) else {}

    subject = em.get("subject", "(no subject)")
    sender = em.get("from", "unknown")
    to = em.get("to", "unknown")
    date = em.get("date", "unknown")
    thread_id = em.get("thread_id", "")
    labels = em.get("labels", [])
    has_attachments = em.get("has_attachments", False)

    labels_str = ", ".join(labels) if labels else "None"

    return (
        f"<email>\n"
        f"<subject>{subject}</subject>\n"
        f"<from>{sender}</from>\n"
        f"<to>{to}</to>\n"
        f"<date>{date}</date>\n"
        f"<thread_id>{thread_id}</thread_id>\n"
        f"<labels>{labels_str}</labels>\n"
        f"<has_attachments>{str(has_attachments).lower()}</has_attachments>\n"
        f"<content>\n{entry.content}\n</content>\n"
        f"</email>"
    )


async def search_emails(
    ctx: Context,
    qdrant_connector: QdrantConnector,
    search_limit: int,
    collection_name: str,
    query: str,
    query_filter: ArbitraryFilter | None = None,
) -> List[str]:
    """
    Search Outlook emails by semantic content and metadata filters.
    """

    await ctx.debug(f"Searching emails for query: {query}")

    combined_filter = models.Filter(**query_filter) if query_filter else None

    entries = await qdrant_connector.search(
        query,
        collection_name=collection_name,
        limit=search_limit,
        query_filter=combined_filter,
    )

    if not entries:
        return [f"No emails found for query '{query}'"]

    results: List[str] = [f"Found {len(entries)} emails for query '{query}':"]
    for e in entries:
        results.append(_format_email_entry(e))
    return results


async def analyze_mailbox(
    ctx: Context,
    qdrant_connector: QdrantConnector,
    search_limit: int,
    collection_name: str,
    query_filter: ArbitraryFilter | None = None,
    focus_terms: Optional[List[str]] = None,
) -> List[str]:
    """
    Analyze mailbox patterns and summarize key statistics using a semantic sample.
    """

    analysis_query = "email message communication thread subject"
    if focus_terms:
        try:
            tokens = " ".join([t for t in focus_terms if isinstance(t, str) and t])
            if tokens:
                analysis_query = f"{tokens} {analysis_query}"
        except Exception:
            pass

    combined_filter = models.Filter(**query_filter) if query_filter else None

    analysis_limit = min(search_limit * 3, 100)
    entries = await qdrant_connector.search(
        analysis_query,
        collection_name=collection_name,
        limit=analysis_limit,
        query_filter=combined_filter,
    )

    if not entries:
        return ["No emails matched the specified criteria"]

    # Aggregate statistics
    from collections import Counter

    senders = Counter()
    labels = Counter()
    threads = Counter()
    dates = Counter()

    for e in entries:
        md = e.metadata or {}
        em = md.get("email", {}) if isinstance(md, dict) else {}
        sender = em.get("from")
        if sender:
            senders[sender] += 1
        for lbl in em.get("labels", []) or []:
            labels[lbl] += 1
        tid = em.get("thread_id")
        if tid:
            threads[tid] += 1
        day = (em.get("date") or "").split("T")[0] if em.get("date") else None
        if day:
            dates[day] += 1

    def _top(counter: Counter, n=5) -> str:
        return ", ".join([f"{k} ({v})" for k, v in counter.most_common(n)]) or "None"

    summary = [
        "Mailbox Analysis Summary:",
        f"- Top senders: {_top(senders)}",
        f"- Top labels: {_top(labels)}",
        f"- Top threads: {_top(threads)}",
        f"- Active days: {_top(dates)}",
        f"- Sample size: {len(entries)}",
    ]

    return ["\n".join(summary)]


async def find_threads(
    ctx: Context,
    qdrant_connector: QdrantConnector,
    search_limit: int,
    collection_name: str,
    query: Optional[str] = None,
    query_filter: ArbitraryFilter | None = None,
    thread_id: Optional[str] = None,
) -> List[str]:
    """
    Find and summarize email threads either by thread_id or by semantic topic.
    """

    # If thread_id specified, add equality condition to filter
    combined_filter = models.Filter(**query_filter) if query_filter else None

    # If no query provided, use a generic conversation signal
    effective_query = query or "conversation thread reply forward"

    entries = await qdrant_connector.search(
        effective_query,
        collection_name=collection_name,
        limit=min(search_limit * 3, 200),
        query_filter=combined_filter,
    )

    if not entries:
        if thread_id:
            return [f"No emails found for thread '{thread_id}'"]
        return ["No threads found for the specified query"]

    # Group by thread_id
    from collections import defaultdict

    by_thread: Dict[str, List[Entry]] = defaultdict(list)
    for e in entries:
        em = (e.metadata or {}).get("email", {}) if isinstance(e.metadata, dict) else {}
        tid = em.get("thread_id") or "(no-thread)"
        by_thread[tid].append(e)

    # Sort threads by size (desc)
    ranked_threads = sorted(by_thread.items(), key=lambda kv: len(kv[1]), reverse=True)

    results: List[str] = [f"Found {len(ranked_threads)} threads (top {min(5, len(ranked_threads))} shown):"]
    for idx, (tid, items) in enumerate(ranked_threads[:5], start=1):
        subjects = [((it.metadata or {}).get("email", {}) or {}).get("subject", "") for it in items]
        first_subject = subjects[0] if subjects else "(no subject)"
        results.append(
            f"<thread rank=\"{idx}\">\n"
            f"<thread_id>{tid}</thread_id>\n"
            f"<message_count>{len(items)}</message_count>\n"
            f"<sample_subject>{first_subject}</sample_subject>\n"
            f"</thread>"
        )

    return results
