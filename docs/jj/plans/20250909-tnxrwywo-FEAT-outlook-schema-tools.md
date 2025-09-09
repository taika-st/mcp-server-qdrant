# Working Set Plan

**JJ Change ID**: tnxrwywo
**JJ Message**: FEAT: add outlook schema tools for qdrant collections of email
**Date Created**: 2025-09-09
**Author**: Assistant

## Objective
Enable mcp-server-qdrant-pro to expose an Outlook email tool suite that operates on Qdrant collections built from Outlook mail archives. The server must expose only the relevant tool set (GitHub code vs Outlook email) based on a flag in the MCP server JSON config, avoiding irrelevant tools in each mode.

## Requirements
- [ ] Add configuration flag to select the enterprise tool suite (github | outlook)
- [ ] Register only the selected tool suite at startup
- [ ] Provide Outlook-specific tools analogous to existing GitHub tools:
  - search emails by semantic query + filters
  - analyze mailbox patterns and stats
  - find threads grouped by thread_id
- [ ] Define Outlook filterable fields and idempotent payload index creation
- [ ] Keep GitHub as the default suite to preserve existing behavior and tests
- [ ] Documentation and JJ implementation milestones

## Technology Stack Decision
### Evaluated Options
1. Extend existing `enterprise_config` to be multi-suite via environment
   - Pros:
     - Minimal changes to call sites
     - Centralized configuration
   - Cons:
     - Hidden coupling to global state
     - Harder to pass explicit context
2. Introduce a separate Outlook config module and select at runtime
   - Pros:
     - Clear separation of concerns
     - Avoids breaking existing imports/tests
     - Easier to evolve each suite independently
   - Cons:
     - Requires wiring selection logic where needed

### Selected Approach
2. Separate module for Outlook (`enterprise_config_outlook.py`) and select the suite in `QdrantMCPServer` based on a new `ToolSettings.tool_suite` flag. Populate `QdrantSettings.filterable_fields` accordingly before connector/index creation.

## Implementation Milestones
1. Milestone 1: Config flag and planning scaffolding
2. Milestone 2: Outlook filterable fields + index wiring
3. Milestone 3: Outlook tools (search/analyze/find-threads) and registration
4. Milestone 4: Integration smoke test and documentation

## Success Criteria
- [ ] Setting `ENTERPRISE_TOOL_SUITE=outlook` registers only Outlook tools and indexes Outlook fields
- [ ] Default (no flag or `github`) preserves current behavior and passes test suite
- [ ] Outlook tools execute semantic search with filters against an email collection
- [ ] No GitHub-only parameters (e.g., repository_id) surface in Outlook mode
