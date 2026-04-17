# CodeNook v5.0 — Proof of Concept

> ⚠️ **Experimental**. Not part of the v4.9.5 stable installer. This
> directory contains a clean-slate redesign that runs alongside v4.x
> in the same repo for now. See the project root `PIPELINE.md` and the
> session plan for the rationale.

CodeNook v5.0 reframes the framework as a **conversation-driven local
workspace operating system** for Claude Code and Copilot CLI:

- The workspace (`.codenook/`) is the source of truth — session-,
  device-, and platform-independent.
- The main session is a **pure router**; substantive work is
  delegated to single-shot sub-agents via Mode B (`general-purpose +
  profile self-load`).
- All credentials live in the OS keyring; workspace files only
  hold `${keyring:codenook/<key>}` references.
- Every session start runs a **security-auditor** agent that
  performs preflight + secret scan + keyring health check.

## Layout

```
skills/codenook-v5-poc/
├── init.sh                    # bootstrap a workspace
├── templates/
│   ├── core/codenook-core.md  # ~1.6K-line orchestrator spec
│   ├── prompts-templates/     # role templates
│   ├── prompts-criteria/      # 7 acceptance-criteria templates
│   ├── agents/                # 11 Mode B agent profiles
│   ├── subtask-runner.sh      # decomposition runner
│   ├── queue-runner.sh        # parallel scheduler
│   ├── dispatch-audit.sh      # 6-check delegation auditor
│   ├── preflight.sh           # 10-check workspace health
│   ├── secret-scan.sh         # 16-pattern credential scanner
│   ├── keyring-helper.sh      # cross-platform keyring wrapper
│   ├── session-runner.sh      # manual session lifecycle CLI
│   ├── rebuild-task-board.sh  # derive task-board.json from state
│   └── hitl-adapters/
│       └── terminal.sh
├── tests/                     # 21 static + dynamic tests
└── README.md                  # this file
```

## Try it

```bash
# In a fresh project directory:
bash /path/to/CodeNook/skills/codenook-v5-poc/init.sh

# Then open the project in Claude Code or Copilot CLI.
# The bootloader at CLAUDE.md will route you into the orchestrator.
```

## Platform support

| Platform | Status | Notes |
|---|---|---|
| macOS | ✅ Tested | Keyring backend: macOS Keychain |
| Linux | ✅ Static-tested | Keyring backend: SecretService / KWallet (libsecret) |
| Windows (Git Bash / WSL2) | ✅ Static-tested | Keyring: Windows Credential Locker. CMD / PowerShell not supported. |

`python3` is required (Git Bash for Windows: install Python 3 and add
to PATH, or use the `py -3` shim).

## Tests

```bash
bash skills/codenook-v5-poc/tests/run-all.sh
```

Currently: **21 tests pass** (T1, T8–T27).

## Status & roadmap

This POC is feature-frozen for the v5.0 milestone. v5.1 will add the
knowledge loader, tri-axial distillation auto-mode, and the HTML
dashboard. v6.x may introduce non-SDLC profiles (writing / research /
ops) sharing the same kernel layer.
