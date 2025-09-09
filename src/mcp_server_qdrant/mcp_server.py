import json
import logging
from typing import Any, Dict, Optional

from fastmcp import Context, FastMCP

from qdrant_client import models

from mcp_server_qdrant.common.filters import make_indexes
from mcp_server_qdrant.common.func_tools import make_partial_function

from mcp_server_qdrant.embeddings.base import EmbeddingProvider
from mcp_server_qdrant.embeddings.factory import create_embedding_provider
from mcp_server_qdrant.qdrant import ArbitraryFilter, Entry, QdrantConnector
from mcp_server_qdrant.settings import (
    EmbeddingProviderSettings,
    QdrantSettings,
    ToolSettings,
)
from mcp_server_qdrant.enterprise_tools import (
    search_repository,
    analyze_repository_patterns,
    find_implementations,
)
from mcp_server_qdrant.outlook_tools import (
    search_emails,
    analyze_mailbox,
    find_threads,
)


logger = logging.getLogger(__name__)


# FastMCP is an alternative interface for declaring the capabilities
# of the server. Its API is based on FastAPI.
class QdrantMCPServer(FastMCP):
    """
    A MCP server for Qdrant.
    """

    def __init__(
        self,
        tool_settings: ToolSettings,
        qdrant_settings: QdrantSettings,
        embedding_provider_settings: Optional[EmbeddingProviderSettings] = None,
        embedding_provider: Optional[EmbeddingProvider] = None,
        name: str = "mcp-server-qdrant",
        instructions: str | None = None,
        **settings: Any,
    ):
        # Allow None for backward compatibility in tests; default to ToolSettings()
        self.tool_settings = tool_settings or ToolSettings()
        self.qdrant_settings = qdrant_settings

        # Backward-compat: accept legacy alias 'embedding_settings' and map to embedding_provider_settings
        if embedding_provider_settings is None and "embedding_settings" in settings:
            legacy = settings.pop("embedding_settings")
            if isinstance(legacy, EmbeddingProviderSettings):
                embedding_provider_settings = legacy
            elif isinstance(legacy, dict):
                embedding_provider_settings = EmbeddingProviderSettings(**legacy)

        if embedding_provider_settings and embedding_provider:
            raise ValueError(
                "Cannot provide both embedding_provider_settings and embedding_provider"
            )

        if not embedding_provider_settings and not embedding_provider:
            raise ValueError(
                "Must provide either embedding_provider_settings or embedding_provider"
            )

        self.embedding_provider_settings: Optional[EmbeddingProviderSettings] = None
        self.embedding_provider: Optional[EmbeddingProvider] = None

        if embedding_provider_settings:
            self.embedding_provider_settings = embedding_provider_settings
            self.embedding_provider = create_embedding_provider(
                embedding_provider_settings
            )
        else:
            self.embedding_provider_settings = None
            self.embedding_provider = embedding_provider

        assert self.embedding_provider is not None, "Embedding provider is required"

        self.qdrant_connector = QdrantConnector(
            qdrant_settings.location,
            qdrant_settings.api_key,
            qdrant_settings.collection_name,
            self.embedding_provider,
            qdrant_settings.local_path,
            make_indexes(qdrant_settings.filterable_fields_dict()),
        )

        super().__init__(name=name, instructions=instructions, **settings)

        # Provide a lightweight compatibility shim for tests that access server.app._tools
        class _ToolShim:
            def __init__(self, name: str, fn):
                self.name = name
                self.fn = fn

        class _AppShim:
            def __init__(self):
                self._tools: Dict[str, _ToolShim] = {}

        # Only create if missing to avoid shadowing FastMCP internals if present
        if not hasattr(self, "app"):
            self.app = _AppShim()

        self.setup_tools()

    def format_entry(self, entry: Entry) -> str:
        """
        Feel free to override this method in your subclass to customize the format of the entry.
        """
        entry_metadata = json.dumps(entry.metadata) if entry.metadata else ""
        return f"<entry><content>{entry.content}</content><metadata>{entry_metadata}</metadata></entry>"

    def _parse_themes_json(self, themes: str | None) -> list[str] | None:
        """
        Parse themes from JSON string to list.

        :param themes: JSON string representation of themes array
        :return: List of themes or None
        :raises ValueError: If themes is not a valid JSON array
        """
        if not themes:
            return None

        try:
            themes_list = json.loads(themes)
            if not isinstance(themes_list, list):
                raise ValueError("themes must be a JSON array")
            return themes_list
        except (json.JSONDecodeError, ValueError) as e:
            raise ValueError(f"Invalid themes format: {e}. Expected JSON array like '[\"auth\", \"db\"]'")

    def setup_tools(self):
        """
        Register enterprise-specific tools for GitHub codebase search or Outlook email search
        based on the configured tool suite.
        """
        # Local shim to mirror what tests expect when iterating server.app._tools
        class _ToolShim:
            def __init__(self, name: str, fn):
                self.name = name
                self.fn = fn

        filterable_conditions = self.qdrant_settings.filterable_fields_dict_with_conditions()

        # Branch tool registration based on selected suite
        suite = getattr(self.tool_settings, "tool_suite", None) or getattr(
            self.qdrant_settings, "tool_suite", "github"
        )

        # -------------------------------
        # GitHub Suite
        # -------------------------------
        async def enterprise_search_repository(
            ctx: Context,
            repository_id: str,
            query: str,
            themes: str | None = None,
            programming_language: str | None = None,
            complexity_score: int | None = None,
            file_type: str | None = None,
            directory: str | None = None,
            has_code_patterns: bool | None = None,
            query_filter: ArbitraryFilter | None = None,
        ):
            # Parse themes JSON string to list
            try:
                themes_list = self._parse_themes_json(themes)
            except ValueError as e:
                await ctx.error(str(e))
                return [f"Error: {e}"]

            # Build filter conditions from parameters (exclude repository_id here; core tool enforces it)
            filter_conditions: Dict[str, Any] = {}
            if themes_list:
                filter_conditions["themes"] = themes_list
            if programming_language:
                filter_conditions["programming_language"] = programming_language
            if complexity_score is not None:
                filter_conditions["complexity_score"] = complexity_score
            if file_type:
                filter_conditions["file_type"] = file_type
            if directory:
                filter_conditions["directory"] = directory
            if has_code_patterns is not None:
                filter_conditions["has_code_patterns"] = has_code_patterns

            # Optionally augment semantic query with theme tokens to improve recall
            if themes_list:
                try:
                    theme_tokens = " ".join([t for t in themes_list if isinstance(t, str) and t])
                    if theme_tokens:
                        query = f"{query} {theme_tokens}"
                except Exception:
                    # Non-fatal; proceed without augmentation
                    pass

            # Build Qdrant filter
            from mcp_server_qdrant.common.filters import make_filter
            built_filter = make_filter(filterable_conditions, filter_conditions)
            combined_filter = models.Filter(**built_filter) if built_filter else None

            # Sanitize to avoid triggering fallback in enterprise_tools by removing 'should'
            if combined_filter is not None:
                def _as_list(x):
                    if x is None:
                        return []
                    return x if isinstance(x, list) else [x]
                must_conditions = _as_list(getattr(combined_filter, "must", None))
                must_not_conditions = _as_list(getattr(combined_filter, "must_not", None))
                combined_filter = models.Filter(
                    must=must_conditions or None,
                    must_not=must_not_conditions or None,
                    should=None,
                )

            # Combine with any additional query filter, including 'should' conditions
            if query_filter and combined_filter:
                additional_filter = models.Filter(**query_filter)
                # Ensure we have lists before concatenating
                must_conditions = []
                must_not_conditions = []
                should_conditions = []

                # Handle combined_filter.must
                if combined_filter.must is not None:
                    if isinstance(combined_filter.must, list):
                        must_conditions.extend(combined_filter.must)
                    else:
                        must_conditions.append(combined_filter.must)

                # Handle additional_filter.must
                if additional_filter.must is not None:
                    if isinstance(additional_filter.must, list):
                        must_conditions.extend(additional_filter.must)
                    else:
                        must_conditions.append(additional_filter.must)

                # Handle combined_filter.must_not
                if combined_filter.must_not is not None:
                    if isinstance(combined_filter.must_not, list):
                        must_not_conditions.extend(combined_filter.must_not)
                    else:
                        must_not_conditions.append(combined_filter.must_not)

                # Handle additional_filter.must_not
                if additional_filter.must_not is not None:
                    if isinstance(additional_filter.must_not, list):
                        must_not_conditions.extend(additional_filter.must_not)
                    else:
                        must_not_conditions.append(additional_filter.must_not)

                # Handle should conditions
                if getattr(combined_filter, "should", None) is not None:
                    if isinstance(combined_filter.should, list):
                        should_conditions.extend(combined_filter.should)
                    else:
                        should_conditions.append(combined_filter.should)

                if getattr(additional_filter, "should", None) is not None:
                    if isinstance(additional_filter.should, list):
                        should_conditions.extend(additional_filter.should)
                    else:
                        should_conditions.append(additional_filter.should)

                combined_filter = models.Filter(
                    must=must_conditions if must_conditions else None,
                    should=should_conditions if should_conditions else None,
                    must_not=must_not_conditions if must_not_conditions else None
                )
            elif query_filter:
                combined_filter = models.Filter(**query_filter)

            return await search_repository(
                ctx,
                self.qdrant_connector,
                self.qdrant_settings.search_limit,
                filterable_conditions,
                repository_id,
                query,
                self.qdrant_settings.collection_name or "qdrant_collection",
                combined_filter.model_dump() if combined_filter else None,
            )

        async def enterprise_analyze_patterns(
            ctx: Context,
            repository_id: str,
            themes: str | None = None,
            programming_language: str | None = None,
            directory: str | None = None,
        ):
            # Parse themes JSON string to list
            try:
                themes_list = self._parse_themes_json(themes)
            except ValueError as e:
                await ctx.error(str(e))
                return [f"Error: {e}"]
            return await analyze_repository_patterns(
                ctx,
                self.qdrant_connector,
                self.qdrant_settings.search_limit,
                filterable_conditions,
                repository_id,
                self.qdrant_settings.collection_name or "qdrant_collection",
                themes_list,
                programming_language,
                directory,
            )

        async def enterprise_find_implementations(
            ctx: Context,
            repository_id: str,
            pattern_query: str,
            themes: str | None = None,
            programming_language: str | None = None,
            min_complexity: int | None = None,
        ):
            # Parse themes JSON string to list
            try:
                themes_list = self._parse_themes_json(themes)
            except ValueError as e:
                await ctx.error(str(e))
                return [f"Error: {e}"]
            return await find_implementations(
                ctx,
                self.qdrant_connector,
                self.qdrant_settings.search_limit,
                filterable_conditions,
                repository_id,
                pattern_query,
                self.qdrant_settings.collection_name or "qdrant_collection",
                themes_list,
                programming_language,
                min_complexity,
            )

        # -------------------------------
        # Outlook Suite
        # -------------------------------
        async def enterprise_search_emails(
            ctx: Context,
            query: str,
            sender: str | None = None,
            to: str | None = None,
            labels: str | None = None,
            has_attachments: bool | None = None,
            is_html: bool | None = None,
            content_length: int | None = None,
            thread_id: str | None = None,
            message_id: str | None = None,
            subject: str | None = None,
            sentiment: str | None = None,
            priority: str | None = None,
            language: str | None = None,
            date: str | None = None,
            query_filter: ArbitraryFilter | None = None,
        ):
            # Parse labels JSON if provided
            labels_list: list[str] | None = None
            if labels:
                try:
                    labels_list = json.loads(labels)
                    if not isinstance(labels_list, list):
                        raise ValueError("labels must be a JSON array")
                except (json.JSONDecodeError, ValueError) as e:
                    await ctx.error(str(e))
                    return [f"Error: {e}"]

            filter_conditions: Dict[str, Any] = {}
            if sender:
                filter_conditions["email.from"] = sender
            if to:
                filter_conditions["email.to"] = to
            if labels_list:
                filter_conditions["email.labels"] = labels_list
            if has_attachments is not None:
                filter_conditions["email.has_attachments"] = has_attachments
            if is_html is not None:
                filter_conditions["email.is_html"] = is_html
            if content_length is not None:
                filter_conditions["email.content_length"] = content_length
            if thread_id:
                filter_conditions["email.thread_id"] = thread_id
            if message_id:
                filter_conditions["email.message_id"] = message_id
            if subject:
                filter_conditions["email.subject"] = subject
            if sentiment:
                filter_conditions["email.sentiment"] = sentiment
            if priority:
                filter_conditions["email.priority"] = priority
            if language:
                filter_conditions["email.language"] = language
            if date:
                filter_conditions["email.date"] = date

            from mcp_server_qdrant.common.filters import make_filter
            built_filter = make_filter(filterable_conditions, filter_conditions)
            combined_filter = models.Filter(**built_filter) if built_filter else None

            # Merge with additional query_filter if present
            if query_filter and combined_filter:
                additional_filter = models.Filter(**query_filter)
                def _as_list(x):
                    if x is None:
                        return []
                    return x if isinstance(x, list) else [x]
                must = _as_list(getattr(combined_filter, "must", None)) + _as_list(getattr(additional_filter, "must", None))
                must_not = _as_list(getattr(combined_filter, "must_not", None)) + _as_list(getattr(additional_filter, "must_not", None))
                should = _as_list(getattr(combined_filter, "should", None)) + _as_list(getattr(additional_filter, "should", None))
                combined_filter = models.Filter(
                    must=must or None,
                    must_not=must_not or None,
                    should=should or None,
                )
            elif query_filter:
                combined_filter = models.Filter(**query_filter)

            return await search_emails(
                ctx,
                self.qdrant_connector,
                self.qdrant_settings.search_limit,
                self.qdrant_settings.collection_name or "qdrant_collection",
                query,
                combined_filter.model_dump() if combined_filter else None,
            )

        async def enterprise_analyze_mailbox(
            ctx: Context,
            focus_terms: str | None = None,
            sender: str | None = None,
            to: str | None = None,
            labels: str | None = None,
            has_attachments: bool | None = None,
            is_html: bool | None = None,
            sentiment: str | None = None,
            priority: str | None = None,
            language: str | None = None,
            date: str | None = None,
        ):
            # Parse focus_terms and labels JSON arrays
            focus_terms_list: list[str] | None = None
            labels_list: list[str] | None = None
            try:
                if focus_terms:
                    focus_terms_list = json.loads(focus_terms)
                    if not isinstance(focus_terms_list, list):
                        raise ValueError("focus_terms must be a JSON array")
            except (json.JSONDecodeError, ValueError) as e:
                await ctx.error(str(e))
                return [f"Error: {e}"]
            try:
                if labels:
                    labels_list = json.loads(labels)
                    if not isinstance(labels_list, list):
                        raise ValueError("labels must be a JSON array")
            except (json.JSONDecodeError, ValueError) as e:
                await ctx.error(str(e))
                return [f"Error: {e}"]

            filter_conditions: Dict[str, Any] = {}
            if sender:
                filter_conditions["email.from"] = sender
            if to:
                filter_conditions["email.to"] = to
            if labels_list:
                filter_conditions["email.labels"] = labels_list
            if has_attachments is not None:
                filter_conditions["email.has_attachments"] = has_attachments
            if is_html is not None:
                filter_conditions["email.is_html"] = is_html
            if sentiment:
                filter_conditions["email.sentiment"] = sentiment
            if priority:
                filter_conditions["email.priority"] = priority
            if language:
                filter_conditions["email.language"] = language
            if date:
                filter_conditions["email.date"] = date

            from mcp_server_qdrant.common.filters import make_filter
            built_filter = make_filter(filterable_conditions, filter_conditions)
            combined_filter = models.Filter(**built_filter) if built_filter else None

            return await analyze_mailbox(
                ctx,
                self.qdrant_connector,
                self.qdrant_settings.search_limit,
                self.qdrant_settings.collection_name or "qdrant_collection",
                combined_filter.model_dump() if combined_filter else None,
                focus_terms_list,
            )

        async def enterprise_find_threads(
            ctx: Context,
            query: str | None = None,
            thread_id: str | None = None,
            sender: str | None = None,
            to: str | None = None,
            labels: str | None = None,
            date: str | None = None,
        ):
            labels_list: list[str] | None = None
            if labels:
                try:
                    labels_list = json.loads(labels)
                    if not isinstance(labels_list, list):
                        raise ValueError("labels must be a JSON array")
                except (json.JSONDecodeError, ValueError) as e:
                    await ctx.error(str(e))
                    return [f"Error: {e}"]

            filter_conditions: Dict[str, Any] = {}
            if thread_id:
                filter_conditions["email.thread_id"] = thread_id
            if sender:
                filter_conditions["email.from"] = sender
            if to:
                filter_conditions["email.to"] = to
            if labels_list:
                filter_conditions["email.labels"] = labels_list
            if date:
                filter_conditions["email.date"] = date

            from mcp_server_qdrant.common.filters import make_filter
            built_filter = make_filter(filterable_conditions, filter_conditions)
            combined_filter = models.Filter(**built_filter) if built_filter else None

            return await find_threads(
                ctx,
                self.qdrant_connector,
                self.qdrant_settings.search_limit,
                self.qdrant_settings.collection_name or "qdrant_collection",
                query,
                combined_filter.model_dump() if combined_filter else None,
                thread_id,
            )

        # Register suite-specific tools
        if suite == "outlook":
            # If arbitrary filters are not allowed, strip query_filter arg via partial
            if not self.qdrant_settings.allow_arbitrary_filter:
                enterprise_search_emails = make_partial_function(enterprise_search_emails, {"query_filter": None})

            self.tool(
                enterprise_search_emails,
                name="qdrant-search-emails",
                description=self.tool_settings.search_emails_description,
            )
            if hasattr(self, "app") and hasattr(self.app, "_tools"):
                self.app._tools["qdrant-search-emails"] = _ToolShim("qdrant-search-emails", enterprise_search_emails)

            self.tool(
                enterprise_analyze_mailbox,
                name="qdrant-analyze-mailbox",
                description=self.tool_settings.analyze_mailbox_description,
            )
            if hasattr(self, "app") and hasattr(self.app, "_tools"):
                self.app._tools["qdrant-analyze-mailbox"] = _ToolShim("qdrant-analyze-mailbox", enterprise_analyze_mailbox)

            self.tool(
                enterprise_find_threads,
                name="qdrant-find-threads",
                description=self.tool_settings.find_threads_description,
            )
            if hasattr(self, "app") and hasattr(self.app, "_tools"):
                self.app._tools["qdrant-find-threads"] = _ToolShim("qdrant-find-threads", enterprise_find_threads)
        else:
            # Apply query_filter removal if arbitrary filters not allowed
            if not self.qdrant_settings.allow_arbitrary_filter:
                enterprise_search_repository = make_partial_function(enterprise_search_repository, {"query_filter": None})

            # Register enterprise tools with expected names used in tests
            self.tool(
                enterprise_search_repository,
                name="qdrant-search-repository",
                description=self.tool_settings.search_repository_description
            )
            if hasattr(self, "app") and hasattr(self.app, "_tools"):
                self.app._tools["qdrant-search-repository"] = _ToolShim("qdrant-search-repository", enterprise_search_repository)

            self.tool(
                enterprise_analyze_patterns,
                name="qdrant-analyze-patterns",
                description=self.tool_settings.analyze_patterns_description
            )
            if hasattr(self, "app") and hasattr(self.app, "_tools"):
                self.app._tools["qdrant-analyze-patterns"] = _ToolShim("qdrant-analyze-patterns", enterprise_analyze_patterns)

            self.tool(
                enterprise_find_implementations,
                name="qdrant-find-implementations",
                description=self.tool_settings.find_implementations_description
            )
            if hasattr(self, "app") and hasattr(self.app, "_tools"):
                self.app._tools["qdrant-find-implementations"] = _ToolShim("qdrant-find-implementations", enterprise_find_implementations)
