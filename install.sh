#!/usr/bin/env bash
set -euo pipefail

# Multi-Agent Framework Installer
# Usage: curl -sL https://raw.githubusercontent.com/cintia09/multi-agent-framework/main/install.sh | bash

VERSION="3.1.0"
REPO="https://github.com/cintia09/multi-agent-framework.git"
TMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/multi-agent-framework.XXXXXX")
CLAUDE_DIR="${HOME}/.claude"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}✓${NC} $1"; }
warn()  { echo -e "${YELLOW}⚠${NC} $1"; }
error() { echo -e "${RED}✗${NC} $1"; exit 1; }

usage() {
    echo "Multi-Agent Framework Installer v${VERSION}"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --full        Full install (default)"
    echo "  --check       Check installation status"
    echo "  --uninstall   Remove framework files"
    echo "  --dry-run     Preview changes without applying"
    echo "  -h, --help    Show this help"
}

check_platform() {
    local dir="$1" name="$2"
    local skills agents hooks has_json
    skills=$(ls -d "${dir}/skills/agent-"* 2>/dev/null | wc -l | tr -d ' ')
    agents=$(ls "${dir}/agents/"*.agent.md 2>/dev/null | wc -l | tr -d ' ')
    hooks=$(ls "${dir}/hooks/"*.sh 2>/dev/null | wc -l | tr -d ' ')
    has_json=$([ -f "${dir}/hooks/hooks.json" ] && echo '✅' || echo '❌')
    echo "  ${name}:"
    echo "    Skills: ${skills}/18 | Agents: ${agents}/5 | Hooks: ${hooks}/13 | hooks.json: ${has_json}"
    [ "$skills" -ge 18 ] && [ "$agents" -ge 5 ] && [ "$hooks" -ge 13 ] && [ -f "${dir}/hooks/hooks.json" ]
}

check_install() {
    echo "🔍 Checking installation status..."
    local all_ok=true
    if [ -d "${CLAUDE_DIR}" ]; then
        check_platform "${CLAUDE_DIR}" "Claude Code" || all_ok=false
    else
        echo "  Claude Code: not detected (${CLAUDE_DIR} missing)"
        all_ok=false
    fi
    local COPILOT_DIR="${HOME}/.copilot"
    if [ -d "${COPILOT_DIR}" ]; then
        check_platform "${COPILOT_DIR}" "Copilot CLI" || all_ok=false
    else
        echo "  Copilot CLI: not detected (${COPILOT_DIR} missing)"
    fi
    if [ "$all_ok" = true ]; then
        info "All detected platforms fully installed ✅"
    else
        warn "Installation incomplete on one or more platforms"
    fi
}

uninstall() {
    echo "🗑️ Uninstalling Multi-Agent Framework..."
    # Claude Code cleanup
    if [ -d "${CLAUDE_DIR}" ]; then
        echo "  Cleaning Claude Code (~/.claude)..."
        rm -rf "${CLAUDE_DIR}/skills/agent-"*
        rm -f "${CLAUDE_DIR}/agents/"*.agent.md
        rm -f "${CLAUDE_DIR}/hooks/agent-"*.sh
        rm -f "${CLAUDE_DIR}/hooks/security-scan.sh"
        rm -rf "${CLAUDE_DIR}/hooks/lib"
        rm -f "${CLAUDE_DIR}/rules/agent-workflow.md" "${CLAUDE_DIR}/rules/security.md" "${CLAUDE_DIR}/rules/commit-standards.md"
        if [ -f "${CLAUDE_DIR}/hooks/hooks.json.bak" ]; then
            mv "${CLAUDE_DIR}/hooks/hooks.json.bak" "${CLAUDE_DIR}/hooks/hooks.json"
            info "Restored Claude hooks.json from backup"
        fi
    fi
    # Copilot CLI cleanup
    local COPILOT_DIR="${HOME}/.copilot"
    if [ -d "$COPILOT_DIR" ]; then
        echo "  Cleaning Copilot CLI (~/.copilot)..."
        rm -rf "${COPILOT_DIR}/skills/agent-"*
        rm -f "${COPILOT_DIR}/agents/"*.agent.md
        rm -f "${COPILOT_DIR}/hooks/agent-"*.sh
        rm -f "${COPILOT_DIR}/hooks/security-scan.sh"
        rm -rf "${COPILOT_DIR}/hooks/lib"
        if [ -f "${COPILOT_DIR}/hooks/hooks.json.bak" ]; then
            mv "${COPILOT_DIR}/hooks/hooks.json.bak" "${COPILOT_DIR}/hooks/hooks.json"
            info "Restored Copilot hooks.json from backup"
        fi
    fi
    echo ""
    echo "  ⚠️  Project-level .agents/ directories must be removed manually."
    info "Uninstall complete. hooks.json and instruction files preserved (may contain other config)."
}

install() {
    local dry_run=${1:-false}
    
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🤖 Multi-Agent Framework v${VERSION}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    # Step 1: Download source
    if [ -d "$TMP_DIR" ]; then rm -rf "$TMP_DIR"; fi
    echo "📥 Downloading framework..."
    if [ "$dry_run" = true ]; then
        echo "  [DRY RUN] Would download to ${TMP_DIR}"
    else
        local success=false
        # Method 1: Try tarball download (faster, more reliable)
        local TARBALL_URL="https://github.com/cintia09/multi-agent-framework/archive/refs/heads/main.tar.gz"
        if curl -sL --connect-timeout 10 --max-time 60 "$TARBALL_URL" | tar xz -C /tmp 2>/dev/null; then
            mv /tmp/multi-agent-framework-main "$TMP_DIR" 2>/dev/null && success=true
            # Basic integrity: ensure key files exist
            if [ "$success" = true ] && { [ ! -f "$TMP_DIR/install.sh" ] || [ ! -d "$TMP_DIR/skills" ]; }; then
                warn "Download may be corrupted (missing key files)"
                success=false
                rm -rf "$TMP_DIR"
            fi
        fi
        # Method 2: Fallback to git clone with retry
        if [ "$success" = false ]; then
            warn "Tarball download failed, trying git clone..."
            git config --global http.postBuffer 524288000 2>/dev/null || true
            local attempt=0
            while [ $attempt -lt 3 ]; do
                attempt=$((attempt + 1))
                if git clone --depth 1 "$REPO" "$TMP_DIR" 2>/dev/null; then
                    success=true
                    break
                fi
                rm -rf "$TMP_DIR"
                [ $attempt -lt 3 ] && warn "Clone attempt $attempt failed, retrying..." && sleep 2
            done
        fi
        [ "$success" = false ] && error "Failed to download. Check your network connection."
        info "Downloaded successfully"
    fi
    
    # Step 2: Backup existing config
    if [ -d "${CLAUDE_DIR}/skills/agent-fsm" ]; then
        warn "Existing installation detected"
        if [ "$dry_run" = false ]; then
            local backup="${CLAUDE_DIR}/backup-$(date +%Y%m%d%H%M%S)"
            mkdir -p "$backup"
            cp -r "${CLAUDE_DIR}/skills/agent-"* "$backup/" 2>/dev/null || true
            cp "${CLAUDE_DIR}/agents/"*.agent.md "$backup/" 2>/dev/null || true
            info "Backed up to ${backup}"
        else
            echo "  [DRY RUN] Would backup existing files"
        fi
    fi
    
    # Step 3: Install Skills
    echo "📦 Installing Skills..."
    if [ "$dry_run" = true ]; then
        echo "  [DRY RUN] Would copy skills to ${CLAUDE_DIR}/skills/"
    else
        mkdir -p "${CLAUDE_DIR}/skills"
        cp -r "${TMP_DIR}/skills/agent-"* "${CLAUDE_DIR}/skills/"
        info "18 Skills installed (includes orchestrator + config + docs + hypothesis)"
    fi
    
    # Step 4: Install Agents
    echo "👤 Installing Agent Profiles..."
    if [ "$dry_run" = true ]; then
        echo "  [DRY RUN] Would copy agents to ${CLAUDE_DIR}/agents/"
    else
        mkdir -p "${CLAUDE_DIR}/agents"
        cp "${TMP_DIR}/agents/"*.agent.md "${CLAUDE_DIR}/agents/"
        info "5 Agent Profiles installed"
    fi
    
    # Step 5: Install Hooks
    echo "🪝 Installing Hooks..."
    if [ "$dry_run" = true ]; then
        echo "  [DRY RUN] Would copy hooks to ${CLAUDE_DIR}/hooks/"
    else
        mkdir -p "${CLAUDE_DIR}/hooks"
        cp "${TMP_DIR}/hooks/"*.sh "${CLAUDE_DIR}/hooks/"
        mkdir -p "${CLAUDE_DIR}/hooks/lib"
        cp "${TMP_DIR}/hooks/lib/"*.sh "${CLAUDE_DIR}/hooks/lib/"
        chmod +x "${CLAUDE_DIR}/hooks/agent-"*.sh
        chmod +x "${CLAUDE_DIR}/hooks/security-scan.sh" 2>/dev/null || true
        if [ -f "${CLAUDE_DIR}/hooks/hooks.json" ]; then
            cp "${CLAUDE_DIR}/hooks/hooks.json" "${CLAUDE_DIR}/hooks/hooks.json.bak"
            info "Backed up existing hooks.json → hooks.json.bak"
        fi
        cp "${TMP_DIR}/hooks/hooks.json" "${CLAUDE_DIR}/hooks/"
        info "Hooks installed"
    fi
    
    # Step 6: Append rules to CLAUDE.md + install modular rules
    echo "📝 Installing collaboration rules..."
    if [ "$dry_run" = true ]; then
        echo "  [DRY RUN] Would install rules"
    else
        # Append to CLAUDE.md (legacy, for backward compatibility)
        if ! grep -q "## Agent Collaboration Rules" "${CLAUDE_DIR}/CLAUDE.md" 2>/dev/null; then
            echo "" >> "${CLAUDE_DIR}/CLAUDE.md"
            cat "${TMP_DIR}/docs/agent-rules.md" >> "${CLAUDE_DIR}/CLAUDE.md"
            info "Rules appended to CLAUDE.md"
        else
            info "Rules already present in CLAUDE.md (skipped)"
        fi
        # Install modular rules (.claude/rules/ — Claude Code native)
        if [ -d "${TMP_DIR}/rules" ]; then
            mkdir -p "${CLAUDE_DIR}/rules"
            cp "${TMP_DIR}/rules/"*.md "${CLAUDE_DIR}/rules/" 2>/dev/null || true
            info "Modular rules installed to ${CLAUDE_DIR}/rules/"
        fi
    fi
    
    # Step 7: Install to GitHub Copilot (if ~/.copilot exists)
    if [ -d "${HOME}/.copilot" ]; then
        echo "🤖 Detected GitHub Copilot — installing for dual-platform..."
        if [ "$dry_run" = true ]; then
            echo "  [DRY RUN] Would install to ~/.copilot/"
        else
            local COPILOT_DIR="${HOME}/.copilot"
            # Skills
            mkdir -p "${COPILOT_DIR}/skills"
            for skill_dir in "${TMP_DIR}/skills/agent-"*; do
                local skill_name=$(basename "$skill_dir")
                mkdir -p "${COPILOT_DIR}/skills/${skill_name}"
                cp "${skill_dir}/SKILL.md" "${COPILOT_DIR}/skills/${skill_name}/" 2>/dev/null || true
            done
            # Agent Profiles (same .agent.md format works in Copilot CLI)
            mkdir -p "${COPILOT_DIR}/agents"
            cp "${TMP_DIR}/agents/"*.agent.md "${COPILOT_DIR}/agents/"
            info "5 Agent Profiles installed to ~/.copilot/agents/"
            # Hooks
            mkdir -p "${COPILOT_DIR}/hooks"
            cp "${TMP_DIR}/hooks/"*.sh "${COPILOT_DIR}/hooks/"
            mkdir -p "${COPILOT_DIR}/hooks/lib"
            cp "${TMP_DIR}/hooks/lib/"*.sh "${COPILOT_DIR}/hooks/lib/"
            chmod +x "${COPILOT_DIR}/hooks/"*.sh
            if [ -f "${COPILOT_DIR}/hooks/hooks.json" ]; then
                cp "${COPILOT_DIR}/hooks/hooks.json" "${COPILOT_DIR}/hooks/hooks.json.bak"
                info "Backed up existing Copilot hooks.json → hooks.json.bak"
            fi
            cp "${TMP_DIR}/hooks/hooks-copilot.json" "${COPILOT_DIR}/hooks/hooks.json"
            # Rules → copilot-instructions.md
            if ! grep -q "## Agent Collaboration Rules" "${COPILOT_DIR}/copilot-instructions.md" 2>/dev/null; then
                mkdir -p "${COPILOT_DIR}"
                if ! { echo "" >> "${COPILOT_DIR}/copilot-instructions.md" && \
                       cat "${TMP_DIR}/docs/agent-rules.md" >> "${COPILOT_DIR}/copilot-instructions.md"; }; then
                    warn "Failed to append Copilot rules to copilot-instructions.md"
                fi
            fi
            info "Copilot installation complete (agents + skills + hooks + rules)"
        fi
    fi

    # Step 8: Verify
    if [ "$dry_run" = false ]; then
        echo ""
        echo "🔍 Verifying installation..."
        bash "${TMP_DIR}/scripts/verify-install.sh" 2>/dev/null || warn "Verification script not found, manual check:"
        check_install
    fi
    
    # Step 9: Cleanup
    if [ "$dry_run" = false ]; then
        rm -rf "$TMP_DIR"
    fi
    
    # Step 10: Done
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    info "Multi-Agent Framework v${VERSION} installed!"
    echo ""
    echo "  Platforms: Claude Code$([ -d "${HOME}/.copilot" ] && echo ' + Copilot CLI')"
    echo ""
    echo "  Usage:"
    echo "    /agent           → Select agent role"
    echo "    /agent acceptor  → Switch to Acceptor"
    echo "    \"Initialize Agent system\" → Init in project"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

# Parse arguments
case "${1:-}" in
    --check)     check_install ;;
    --uninstall) uninstall ;;
    --dry-run)   install true ;;
    --full|"")   install false ;;
    -h|--help)   usage ;;
    *)           echo "Unknown option: $1"; usage; exit 1 ;;
esac
