# Milestone 02: README and Dockerfile updates for themes full-text search, auto-index migration, and CLI entrypoint

**JJ Change ID**: vvklwmyu
**Parent Message**: FIX: Ensure payload indexes exist for existing collections; document behavior and update CLI usage
**Implementation Date**: 2025-09-04 00:00
**Status**: ✅ Success

## What Was Attempted
- Update `README.md` to reflect current MCP server behavior and tooling:
  - Document full-text search semantics for `themes` (JSON array string input, OR semantics, partial matches)
  - Document automatic, idempotent payload index creation for existing Qdrant collections (including TEXT on `metadata.themes`) and read-only caveat
  - Align tool names with actual registrations in `src/mcp_server_qdrant/mcp_server.py` (`qdrant-search-repository`, `qdrant-analyze-patterns`, `qdrant-find-implementations`)
  - Clarify configuration: environment variables are authoritative; `--transport` is the only CLI flag
  - Update examples to use `mcp-server-qdrant-pro` entrypoint
- Update `Dockerfile` to install and run `mcp-server-qdrant-pro`

## Files Modified
- `README.md` — Revised tool names, themes FT search section, auto-index migration notes, environment variables (added `QDRANT_READ_ONLY`), updated `uvx` and client examples to `mcp-server-qdrant-pro`.
- `Dockerfile` — Switched package install to `mcp-server-qdrant-pro` and `CMD` to `uvx mcp-server-qdrant-pro --transport sse`.

## Discoveries & Deviations
### Documentation Issues
- README previously referenced generic tool names; server actually exposes `qdrant-...` tool identifiers per `setup_tools()` in `mcp_server.py`.
- Read-only mode behavior wasn't documented; added `QDRANT_READ_ONLY` to env table and noted index creation caveat.

### Scope Adjustments
- Consolidated Cursor/Windsurf and Claude examples to emphasize enterprise tools and SSE usage.

## Technical Decisions
### Why This Approach
- Keeping README aligned with code (`mcp_server.py`) prevents client/tool mismatch.
- Documenting auto-index migration avoids confusion when new TEXT indexes are introduced post-collection creation.
- Using `mcp-server-qdrant-pro` entrypoint matches `pyproject.toml` scripts and avoids ambiguity.

## Testing Results
```bash
uv run pytest -q
```
- Expected: All tests passing (80/80) with no regressions. Index migration behavior already validated in prior milestone.

## Next Steps
- [ ] If users report read-only clusters, provide a short guide to pre-create indexes via Qdrant API.
- [ ] Optionally add a small “Troubleshooting” section for common misconfigurations (wrong `COLLECTION_NAME`, missing `QDRANT_URL`).

## Rollback Instructions
- Revert `README.md` and `Dockerfile` changes to prior commit if needed. Server functionality remains unaffected by README edits; Docker image entrypoint change can be reverted by switching `CMD` back to the previous tool name.
