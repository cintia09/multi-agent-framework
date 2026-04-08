#!/usr/bin/env bash
set -euo pipefail

# Multi-Agent Framework Installer
# Usage: curl -sL https://raw.githubusercontent.com/cintia09/multi-agent-framework/main/install.sh | bash

VERSION="3.0.0"
REPO="https://github.com/cintia09/multi-agent-framework.git"
TMP_DIR="/tmp/multi-agent-framework"
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

check_install() {
    echo "🔍 Checking installation status..."
    local skills=$(ls -d "${CLAUDE_DIR}/skills/agent-"* 2>/dev/null | wc -l | tr -d ' ')
    local agents=$(ls "${CLAUDE_DIR}/agents/"*.agent.md 2>/dev/null | wc -l | tr -d ' ')
    local hooks=$(ls "${CLAUDE_DIR}/hooks/agent-"*.sh 2>/dev/null | wc -l | tr -d ' ')
    echo "  Skills: ${skills}/15"
    echo "  Agents: ${agents}/5"
    echo "  Hooks:  ${hooks}/12"
    echo "  hooks.json: $([ -f "${CLAUDE_DIR}/hooks/hooks.json" ] && echo '✅' || echo '❌')"
    if [ "$skills" -ge 15 ] && [ "$agents" -ge 5 ] && [ "$hooks" -ge 12 ]; then
        info "Installation complete ✅"
    else
        warn "Installation incomplete"
    fi
}

uninstall() {
    echo "🗑️ Uninstalling Multi-Agent Framework..."
    rm -rf "${CLAUDE_DIR}/skills/agent-"*
    rm -f "${CLAUDE_DIR}/agents/"*.agent.md
    rm -f "${CLAUDE_DIR}/hooks/agent-"*.sh
    # Don't remove hooks.json or CLAUDE.md (may have other content)
    info "Uninstalled. hooks.json and CLAUDE.md preserved (may contain other config)."
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
        info "15 Skills installed (includes orchestrator template)"
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
        chmod +x "${CLAUDE_DIR}/hooks/agent-"*.sh
        chmod +x "${CLAUDE_DIR}/hooks/security-scan.sh" 2>/dev/null || true
        if [ -f "${CLAUDE_DIR}/hooks/hooks.json" ]; then
            warn "hooks.json already exists — merge manually if needed"
        else
            cp "${TMP_DIR}/hooks/hooks.json" "${CLAUDE_DIR}/hooks/"
        fi
        info "Hooks installed"
    fi
    
    # Step 6: Append rules
    echo "📝 Appending collaboration rules..."
    if [ "$dry_run" = true ]; then
        echo "  [DRY RUN] Would append rules to ${CLAUDE_DIR}/CLAUDE.md"
    else
        if ! grep -q "## Agent Collaboration Rules" "${CLAUDE_DIR}/CLAUDE.md" 2>/dev/null; then
            echo "" >> "${CLAUDE_DIR}/CLAUDE.md"
            cat "${TMP_DIR}/docs/agent-rules.md" >> "${CLAUDE_DIR}/CLAUDE.md"
            info "Rules appended to CLAUDE.md"
        else
            info "Rules already present in CLAUDE.md (skipped)"
        fi
    fi
    
    # Step 7: Verify
    if [ "$dry_run" = false ]; then
        echo ""
        echo "🔍 Verifying installation..."
        bash "${TMP_DIR}/scripts/verify-install.sh" 2>/dev/null || warn "Verification script not found, manual check:"
        check_install
    fi
    
    # Step 8: Cleanup
    if [ "$dry_run" = false ]; then
        rm -rf "$TMP_DIR"
    fi
    
    # Step 9: Done
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    info "Multi-Agent Framework v${VERSION} installed!"
    echo ""
    echo "  使用方式:"
    echo "    /agent           → 选择角色"
    echo "    /agent acceptor  → 切换到验收者"
    echo "    \"初始化 Agent 系统\" → 在项目中初始化"
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
