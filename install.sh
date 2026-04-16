#!/usr/bin/env bash
set -euo pipefail

# CodeNook v4.9.5 Installer
# Usage: curl -sL https://raw.githubusercontent.com/cintia09/CodeNook/main/install.sh | bash

VERSION="latest"
REPO="https://github.com/cintia09/CodeNook.git"
TMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/CodeNook.XXXXXX")
trap 'rm -rf "$TMP_DIR"' EXIT

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${GREEN}✓${NC} $1"; }
warn()  { echo -e "${YELLOW}⚠${NC} $1"; }
error() { echo -e "${RED}✗${NC} $1"; exit 1; }

usage() {
    echo "CodeNook Installer v${VERSION}"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --install        Install framework (default)"
    echo "  --check          Check installation status"
    echo "  --uninstall      Remove global skills"
    echo "  --project-clean  Remove agent system from current project"
    echo "  --dry-run        Preview changes without applying"
    echo "  -h, --help       Show this help"
}

# ── Download ──────────────────────────────────────────────

download() {
    echo "📥 Downloading framework..."
    local success=false

    # Method 1: Tarball (faster)
    local TARBALL_URL="https://github.com/cintia09/CodeNook/archive/refs/heads/main.tar.gz"
    if curl -sL --connect-timeout 10 --max-time 60 "$TARBALL_URL" | tar xz -C "$TMP_DIR" --strip-components=1 2>/dev/null; then
        [ -f "$TMP_DIR/install.sh" ] && [ -d "$TMP_DIR/skills" ] && success=true
    fi

    # Method 2: Git clone fallback
    if [ "$success" = false ]; then
        warn "Tarball failed, trying git clone..."
        rm -rf "$TMP_DIR" && mkdir -p "$TMP_DIR"
        git clone --depth 1 "$REPO" "$TMP_DIR" 2>/dev/null || error "Download failed. Check network."
        success=true
    fi

    # Validate download integrity
    if [ ! -f "$TMP_DIR/VERSION" ] || [ ! -d "$TMP_DIR/skills/codenook-init" ]; then
        error "Downloaded content is incomplete. Missing VERSION or skills/codenook-init."
    fi
    VERSION=$(cat "$TMP_DIR/VERSION" | tr -d '[:space:]')
    if [ -z "$VERSION" ]; then
        error "VERSION file is empty. Download may be corrupted."
    fi
    info "Downloaded v${VERSION}"

    # Security scan before installation
    echo ""
    echo "🔐 Running security scan..."
    if [ -f "$TMP_DIR/skill-security-scan.sh" ]; then
        chmod +x "$TMP_DIR/skill-security-scan.sh"
        if ! "$TMP_DIR/skill-security-scan.sh" "$TMP_DIR/skills/codenook-init"; then
            local scan_exit=$?
            if [ "$scan_exit" -eq 2 ]; then
                error "Security scan BLOCKED installation. Critical issues found."
            else
                warn "Security scan found warnings. Review above before proceeding."
                read -r -p "Continue installation? [y/N] " confirm
                if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
                    error "Installation cancelled by user."
                fi
            fi
        fi
    else
        warn "Security scanner not found in download — skipping scan"
    fi
}

# ── Install ──────────────────────────────────────────────

install_platform() {
    local dir="$1" name="$2" src="$TMP_DIR/skills"

    echo -e "  ${CYAN}${name}${NC} → ${dir}/skills/"

    # codenook-init (SKILL.md + templates/ + hitl-adapters/)
    mkdir -p "${dir}/skills/codenook-init/templates"
    mkdir -p "${dir}/skills/codenook-init/hitl-adapters"
    cp "${src}/codenook-init/SKILL.md" "${dir}/skills/codenook-init/"
    cp "${src}/codenook-init/templates/"* "${dir}/skills/codenook-init/templates/"
    # Copy only files (exclude __pycache__ and other directories)
    find "${src}/codenook-init/hitl-adapters/" -maxdepth 1 -type f -exec cp {} "${dir}/skills/codenook-init/hitl-adapters/" \;
    chmod +x "${dir}/skills/codenook-init/hitl-adapters/"*.sh 2>/dev/null || true
    chmod +x "${dir}/skills/codenook-init/hitl-adapters/"*.py 2>/dev/null || true

    # Remove old codenook-engine if present (v4.0 consolidation)
    if [ -d "${dir}/skills/codenook-engine" ]; then
        rm -rf "${dir}/skills/codenook-engine"
        echo -e "    ${YELLOW}Removed old codenook-engine (now built into codenook-init)${NC}"
    fi
}

install() {
    local dry_run=${1:-false}

    if [ "$dry_run" = false ]; then
        download
    else
        echo "  [DRY RUN] Would download from GitHub"
    fi

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🤖 CodeNook v${VERSION}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    if [ "$dry_run" = true ]; then
        echo "  [DRY RUN] Would install:"
        echo "    ~/.copilot/skills/codenook-init/"
        echo "    ~/.claude/skills/codenook-init/"
        return
    fi

    echo "📦 Installing skills..."

    # Copilot CLI
    if [ -d "${HOME}/.copilot" ] || command -v copilot &>/dev/null; then
        install_platform "${HOME}/.copilot" "Copilot CLI"
        info "Copilot CLI: skill installed"
    else
        warn "Copilot CLI not detected (skipped)"
    fi

    # Claude Code
    if [ -d "${HOME}/.claude" ] || command -v claude &>/dev/null; then
        install_platform "${HOME}/.claude" "Claude Code"
        info "Claude Code: skill installed"
    else
        warn "Claude Code not detected (skipped)"
    fi

    # Verify
    echo ""
    echo "🔍 Verifying..."
    check_install

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    info "Installed! v${VERSION}"
    echo ""
    echo "  What's installed:"
    echo "    codenook-init     — Initialize agent system in any project"
    echo "    5 agent templates — acceptor, designer, implementer, reviewer, tester"
    echo "    6 HITL scripts    — local-html, terminal, confluence, github-issue, verify, server"
    echo "    1 engine template — orchestration w/ dual-agent cross-exam + phase constitution"
    echo ""
    echo "  Quick start:"
    echo "    cd your-project"
    echo '    "Initialize agent system"  → generates agents/ + codenook/'
    echo '    "Create task <title>"      → add a task'
    echo '    "Run task T-001"           → start orchestration'
    echo '    Each phase: document → HITL approve → execute → report → HITL approve'
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

# ── Check ─────────────────────────────────────────────────

check_platform() {
    local dir="$1" name="$2"
    local ok=true
    echo -e "  ${CYAN}${name}${NC}:"

    if [ -f "${dir}/skills/codenook-init/SKILL.md" ]; then
        local templates=$(ls "${dir}/skills/codenook-init/templates/"*.agent.md 2>/dev/null | wc -l | tr -d ' ')
        local adapters=$(find "${dir}/skills/codenook-init/hitl-adapters/" -maxdepth 1 -type f 2>/dev/null | wc -l | tr -d ' ')
        local has_engine="❌"
        [ -f "${dir}/skills/codenook-init/templates/codenook.instructions.md" ] && has_engine="✅"
        echo "    codenook-init:    ✅ (${templates} agent templates, ${adapters} HITL scripts, engine ${has_engine})"
    else
        echo "    codenook-init:    ❌ missing"
        ok=false
    fi

    # Warn about old codenook-engine
    if [ -d "${dir}/skills/codenook-engine" ]; then
        echo "    codenook-engine:  ⚠️  obsolete (run --install to clean up)"
    fi

    $ok
}

check_install() {
    echo "🔍 Checking installation..."
    local any=false

    if [ -d "${HOME}/.copilot/skills" ]; then
        check_platform "${HOME}/.copilot" "Copilot CLI" && any=true
    fi
    if [ -d "${HOME}/.claude/skills" ]; then
        check_platform "${HOME}/.claude" "Claude Code" && any=true
    fi

    if [ "$any" = false ]; then
        warn "No installation found. Run: $0 --install"
    fi
}

# ── Uninstall ────────────────────────────────────────────

uninstall() {
    echo "🗑️ Uninstalling CodeNook..."

    for dir in "${HOME}/.copilot" "${HOME}/.claude"; do
        if [ -d "${dir}/skills/codenook-init" ] || [ -d "${dir}/skills/codenook-engine" ]; then
            echo "  Removing from ${dir}..."
            rm -rf "${dir}/skills/codenook-init"
            rm -rf "${dir}/skills/codenook-engine"  # Clean old engine if present
            info "Removed from $(basename "$dir")"
        fi
    done

    echo ""
    echo "  ℹ️  Use --project-clean to remove agent system from a project."
    info "Uninstall complete"
}

# ── Project Clean ────────────────────────────────────────

project_clean() {
    echo "🗑️ Removing CodeNook from current project..."

    local removed=0
    for root in .github .claude; do
        if [ -d "${root}/agents" ] || [ -d "${root}/codenook" ]; then
            echo "  Cleaning ${root}/..."
            rm -rf "${root}/agents" && removed=$((removed + 1))
            rm -rf "${root}/codenook" && removed=$((removed + 1))
            # Remove instructions file if it exists
            rm -f "${root}/instructions/codenook.instructions.md" 2>/dev/null
            rmdir "${root}/instructions" 2>/dev/null || true
        fi
    done

    # Clean CLAUDE.md framework block if present
    if [ -f "CLAUDE.md" ] && grep -q "Multi-Agent Framework" CLAUDE.md 2>/dev/null; then
        warn "CLAUDE.md may contain framework instructions — review manually."
    fi

    if [ "$removed" -gt 0 ]; then
        info "Agent system removed from project."
    else
        warn "No agent system found in current directory."
    fi
}

# ── Main ──────────────────────────────────────────────────

case "${1:-}" in
    --install|"")      install false ;;
    --check)           check_install ;;
    --uninstall)       uninstall ;;
    --project-clean)   project_clean ;;
    --dry-run)         install true ;;
    -h|--help)         usage ;;
    *)                 echo "Unknown option: $1"; usage; exit 1 ;;
esac
