---
name: project-designer
description: "Project architecture constraints and tech decisions. Loaded when the Designer agent works."
---

# Project Design Guide

## Current Architecture
- **Type**: Monolithic CLI framework (not a web service)
- **Entry points**: `install.sh` (installation), Agent skills (runtime behavior)
- **Data flow**: Task Board (JSON) → FSM → Agent Skills → Memory → Events.db
- **Runtime**: Within Claude Code session; Agents read SKILL.md to execute workflows

## Technical Constraints
- **Shell compatibility**: Bash 4+ (macOS/Linux)
- **JSON processing**: Python3 `json` module (no jq dependency)
- **SQLite**: System-provided, used for events.db
- **Zero external dependencies**: No npm/pip/cargo package managers

## Design Document Standards
Output design docs to `.agents/runtime/designer/workspace/design-docs/` containing:
1. Requirements summary (referencing goal IDs)
2. Technical proposal (with alternatives comparison)
3. File change list (add/modify/delete)
4. Test specifications (output to `test-specs/`)
5. ADR format: Context → Decision → Consequences

## Architecture Principles
- Skills are "documentation as code" — SKILL.md is both documentation and behavior definition
- Agent profiles define role personas; skills define workflows
- State persistence: JSON files (task-board, state, inbox, memory)
- Audit log: SQLite events.db (immutable append-only)
- All operations validated through FSM guards
