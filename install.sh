#!/usr/bin/env bash
set -euo pipefail

# CodeNook v4.0 Installer
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
    echo "  --install     Install v4.0 framework (default)"
    echo "  --check       Check installation status"
    echo "  --uninstall   Remove framework files"
    echo "  --clean-v3    Remove v3.x legacy files only"
    echo "  --dry-run     Preview changes without applying"
    echo "  -h, --help    Show this help"
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

    [ -f "$TMP_DIR/VERSION" ] && VERSION=$(cat "$TMP_DIR/VERSION" | tr -d '[:space:]')
    info "Downloaded v${VERSION}"
}

# ── Install v4.0 ─────────────────────────────────────────

install_platform() {
    local dir="$1" name="$2" src="$TMP_DIR/skills"

    echo -e "  ${CYAN}${name}${NC} → ${dir}/skills/"

    # Remove old skill names (pre-rename: agent-init, agent-orchestrator)
    for old_name in agent-init agent-orchestrator; do
        [ -d "${dir}/skills/${old_name}" ] && rm -rf "${dir}/skills/${old_name}" && echo "    🗑️ Removed old ${old_name}"
    done

    # codenook-init (SKILL.md + templates/)
    mkdir -p "${dir}/skills/codenook-init/templates"
    cp "${src}/codenook-init/SKILL.md" "${dir}/skills/codenook-init/"
    cp "${src}/codenook-init/templates/"*.agent.md "${dir}/skills/codenook-init/templates/"

    # codenook-engine (SKILL.md + hitl-adapters/)
    mkdir -p "${dir}/skills/codenook-engine/hitl-adapters"
    cp "${src}/codenook-engine/SKILL.md" "${dir}/skills/codenook-engine/"
    cp "${src}/codenook-engine/hitl-adapters/"* "${dir}/skills/codenook-engine/hitl-adapters/"
    chmod +x "${dir}/skills/codenook-engine/hitl-adapters/"*.sh 2>/dev/null || true
    chmod +x "${dir}/skills/codenook-engine/hitl-adapters/"*.py 2>/dev/null || true
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
        echo "    ~/.copilot/skills/codenook-engine/"
        echo "    ~/.claude/skills/codenook-init/"
        echo "    ~/.claude/skills/codenook-engine/"
        return
    fi

    echo "📦 Installing skills..."

    # Copilot CLI
    if [ -d "${HOME}/.copilot" ] || command -v copilot &>/dev/null; then
        install_platform "${HOME}/.copilot" "Copilot CLI"
        info "Copilot CLI: 2 skills installed"
    else
        warn "Copilot CLI not detected (skipped)"
    fi

    # Claude Code
    if [ -d "${HOME}/.claude" ] || command -v claude &>/dev/null; then
        install_platform "${HOME}/.claude" "Claude Code"
        info "Claude Code: 2 skills installed"
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
    echo "    codenook-init          — Initialize agent system in any project"
    echo "    codenook-engine  — Task routing, HITL gates, memory"
    echo "    5 agent templates   — acceptor, designer, implementer, reviewer, tester"
    echo "    4 HITL adapters     — local-html, terminal, confluence, github-issue"
    echo ""
    echo "  Quick start:"
    echo "    cd your-project"
    echo '    "Initialize agent system"  → generates .github/agents/'
    echo '    "Create task <title>"      → add a task'
    echo '    "Run task T-001"           → start orchestration'
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

# ── Check ─────────────────────────────────────────────────

check_platform_v4() {
    local dir="$1" name="$2"
    local ok=true
    echo -e "  ${CYAN}${name}${NC}:"

    # Check codenook-init
    if [ -f "${dir}/skills/codenook-init/SKILL.md" ]; then
        local templates=$(ls "${dir}/skills/codenook-init/templates/"*.agent.md 2>/dev/null | wc -l | tr -d ' ')
        echo "    codenook-init:          ✅ (${templates} templates)"
    else
        echo "    codenook-init:          ❌ missing"
        ok=false
    fi

    # Check codenook-engine
    if [ -f "${dir}/skills/codenook-engine/SKILL.md" ]; then
        local adapters=$(ls "${dir}/skills/codenook-engine/hitl-adapters/"* 2>/dev/null | wc -l | tr -d ' ')
        echo "    codenook-engine:  ✅ (${adapters} HITL adapters)"
    else
        echo "    codenook-engine:  ❌ missing"
        ok=false
    fi

    # Warn about v3.x leftovers
    local legacy=$(ls -d "${dir}/skills/agent-fsm" "${dir}/skills/agent-switch" "${dir}/skills/agent-messaging" 2>/dev/null | wc -l | tr -d ' ')
    if [ "$legacy" -gt 0 ]; then
        echo "    ⚠️  v3.x legacy skills detected (${legacy} dirs). Run --clean-v3 to remove."
    fi

    $ok
}

check_install() {
    echo "🔍 Checking v4.0 installation..."
    local any=false

    if [ -d "${HOME}/.copilot/skills" ]; then
        check_platform_v4 "${HOME}/.copilot" "Copilot CLI" && any=true
    fi
    if [ -d "${HOME}/.claude/skills" ]; then
        check_platform_v4 "${HOME}/.claude" "Claude Code" && any=true
    fi

    if [ "$any" = false ]; then
        warn "No platform installation found. Run: $0 --install"
    fi
}

# ── Uninstall v4.0 ───────────────────────────────────────

uninstall() {
    echo "🗑️ Uninstalling CodeNook v4.0..."

    for dir in "${HOME}/.copilot" "${HOME}/.claude"; do
        if [ -d "${dir}/skills/codenook-init" ] || [ -d "${dir}/skills/codenook-engine" ]; then
            echo "  Removing from ${dir}..."
            rm -rf "${dir}/skills/codenook-init"
            rm -rf "${dir}/skills/codenook-engine"
            info "Removed from $(basename $dir)"
        fi
    done

    echo ""
    echo "  ℹ️  Project-level files (.github/agents/, .claude/agents/) are not removed."
    echo "  ℹ️  To also remove v3.x files, run: $0 --clean-v3"
    info "Uninstall complete"
}

# ── Clean v3.x legacy ────────────────────────────────────

clean_v3() {
    echo "🧹 Cleaning v3.x legacy files..."

    # Known v3.x skill names (exhaustive list)
    local v3_skills="agent-acceptor agent-config agent-designer agent-docs agent-events agent-fsm agent-hitl-gate agent-hooks agent-hypothesis agent-implementer agent-init agent-memory agent-messaging agent-orchestrator agent-reviewer agent-switch agent-task-board agent-teams agent-tester agent-worktree"

    for dir in "${HOME}/.copilot" "${HOME}/.claude"; do
        if [ -d "$dir" ]; then
            echo "  Scanning ${dir}..."
            local removed=0
            # v3.x skills (exact names only — won't touch user-created skills)
            for name in $v3_skills; do
                if [ -d "${dir}/skills/${name}" ]; then
                    rm -rf "${dir}/skills/${name}"
                    removed=$((removed + 1))
                fi
            done
            # v3.x agents
            rm -f "${dir}/agents/"*.agent.md 2>/dev/null && removed=$((removed + 1))
            # v3.x hooks
            rm -f "${dir}/hooks/agent-"*.sh 2>/dev/null
            rm -f "${dir}/hooks/security-scan.sh" 2>/dev/null
            rm -rf "${dir}/hooks/lib" 2>/dev/null
            rm -f "${dir}/hooks/hooks.json" "${dir}/hooks/hooks.json.bak" 2>/dev/null
            rmdir "${dir}/hooks" 2>/dev/null || true
            # v3.x rules
            rm -f "${dir}/rules/"*.md 2>/dev/null
            rmdir "${dir}/rules" 2>/dev/null || true
            # v3.x backups
            rm -rf "${dir}/backup-"* 2>/dev/null

            [ "$removed" -gt 0 ] && info "Cleaned ${removed} v3.x items from $(basename $dir)"
        fi
    done

    info "v3.x cleanup complete"
}

# ── Main ──────────────────────────────────────────────────

case "${1:-}" in
    --install|"")  install false ;;
    --check)       check_install ;;
    --uninstall)   uninstall ;;
    --clean-v3)    clean_v3 ;;
    --dry-run)     install true ;;
    -h|--help)     usage ;;
    *)             echo "Unknown option: $1"; usage; exit 1 ;;
esac
