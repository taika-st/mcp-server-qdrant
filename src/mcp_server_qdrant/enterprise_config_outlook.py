"""
Enterprise configuration for Outlook email search.

This module provides predefined filterable field configurations optimized for
email/mailbox search use cases, with fields mapped to the metadata.email.*
structure produced by the Outlook OLM ingestion pipeline.
"""

from mcp_server_qdrant.settings import FilterableField

# Outlook Email Search Filterable Fields Configuration
# No globally required field; mailbox is scoped by the selected collection.
ENTERPRISE_EMAIL_FILTERABLE_FIELDS = [
    # TEXTUAL FIELDS (full-text preference semantics via MatchText in Filter.should)
    FilterableField(
        name="email.subject",
        description="Email subject text (full-text, partial matches allowed)",
        field_type="text",
        condition="any",
        required=False,
    ),
    FilterableField(
        name="email.to",
        description="Email recipients (string, full-text match across addresses)",
        field_type="text",
        condition="any",
        required=False,
    ),

    # KEYWORD FIELDS (exact matching or set membership)
    FilterableField(
        name="email.from",
        description="Email sender (exact match)",
        field_type="keyword",
        condition="==",
        required=False,
    ),
    FilterableField(
        name="email.thread_id",
        description="Thread/conversation identifier",
        field_type="keyword",
        condition="==",
        required=False,
    ),
    FilterableField(
        name="email.message_id",
        description="Unique message-id header",
        field_type="keyword",
        condition="==",
        required=False,
    ),
    FilterableField(
        name="email.labels",
        description="Email labels/tags (array); matches if any provided label is present",
        field_type="keyword",
        condition="any",
        required=False,
    ),
    FilterableField(
        name="email.sentiment",
        description="Detected sentiment (e.g., 'positive', 'neutral', 'negative')",
        field_type="keyword",
        condition="==",
        required=False,
    ),
    FilterableField(
        name="email.priority",
        description="Email priority (e.g., 'high', 'normal', 'low')",
        field_type="keyword",
        condition="==",
        required=False,
    ),
    FilterableField(
        name="email.language",
        description="Detected content language",
        field_type="keyword",
        condition="==",
        required=False,
    ),
    FilterableField(
        name="email.date",
        description="Message date/time (ISO 8601 as keyword equality)",
        field_type="keyword",
        condition="==",
        required=False,
    ),

    # BOOLEAN FIELDS
    FilterableField(
        name="email.has_attachments",
        description="Whether the email has attachments (true/false)",
        field_type="boolean",
        condition="==",
        required=False,
    ),
    FilterableField(
        name="email.is_html",
        description="Whether the email body is HTML (true/false)",
        field_type="boolean",
        condition="==",
        required=False,
    ),

    # NUMERIC FIELDS
    FilterableField(
        name="email.content_length",
        description="Minimum content length",
        field_type="integer",
        condition=">=",
        required=False,
    ),
]

# Convenience functions mirroring the GitHub enterprise config API

def get_outlook_filterable_fields_dict() -> dict[str, FilterableField]:
    """Return Outlook email filterable fields as a dictionary keyed by field name."""
    return {field.name: field for field in ENTERPRISE_EMAIL_FILTERABLE_FIELDS}


def get_outlook_filterable_fields_with_conditions() -> dict[str, FilterableField]:
    """Return only Outlook email filterable fields that have conditions (exposed as tool parameters)."""
    return {
        field.name: field
        for field in ENTERPRISE_EMAIL_FILTERABLE_FIELDS
        if field.condition is not None
    }
