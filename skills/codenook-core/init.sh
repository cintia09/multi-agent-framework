#!/usr/bin/env bash
# init.sh — CodeNook v6 installer & plugin manager (M1 skeleton).
#
# M1 scope: subcommand dispatcher only. Each non-meta subcommand body is a
# stub that prints "TODO: ..." and exits 2 (not implemented). Real logic is
# implemented incrementally in M2..M5 per docs/v6/implementation-v6.md.

set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION_FILE="$SELF_DIR/VERSION"

usage() {
  cat <<'EOF'
CodeNook v6 — installer & plugin manager

Usage:
  init.sh                                 seed workspace in CWD (M1 stub)
  init.sh --install-plugin <path|url>     install a plugin tarball/zip/url
  init.sh --uninstall-plugin <name>       uninstall a workspace plugin
  init.sh --scaffold-plugin <name>        create a new plugin skeleton
  init.sh --pack-plugin <dir>             validate + tar.gz a plugin dir
  init.sh --upgrade-core                  upgrade the codenook-core skeleton
  init.sh --refresh-models                re-probe model catalog (resets 30d TTL)
  init.sh --version                       print core version
  init.sh --help                          show this help

All non-meta subcommands are stubs in M1 (exit 2: TODO).
EOF
}

stub() {
  # $1 = subcommand label
  echo "TODO: $1 not implemented in M1 skeleton" >&2
  exit 2
}

main() {
  if [ $# -eq 0 ]; then
    usage
    exit 0
  fi
  case "$1" in
    --help|-h)
      usage; exit 0 ;;
    --version)
      cat "$VERSION_FILE"; exit 0 ;;
    --install-plugin)
      stub "--install-plugin" ;;
    --uninstall-plugin|--remove-plugin)
      stub "--uninstall-plugin" ;;
    --scaffold-plugin)
      stub "--scaffold-plugin" ;;
    --pack-plugin)
      stub "--pack-plugin" ;;
    --upgrade-core)
      stub "--upgrade-core" ;;
    --refresh-models)
      stub "--refresh-models" ;;
    *)
      echo "unknown subcommand: $1" >&2
      usage >&2
      exit 2 ;;
  esac
}

main "$@"
