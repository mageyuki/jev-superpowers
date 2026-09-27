#!/usr/bin/env bash
set -euo pipefail

echo "⚡ Installing jev-superpowers..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Legacy backends need no Python client. Fail before creating directories or copying skills.
case "${JEV_BACKEND:-}" in
    typesafe|laya) BACKEND="$JEV_BACKEND" ;;
    "")
        if [ -n "${TYPESAFE_BASE_URL:-}" ] || [ "${TYPESAFE_BACKEND:-}" = "laya" ]; then
            BACKEND=laya
        elif command -v python3 >/dev/null 2>&1; then
            BACKEND=""
        elif [ -n "${TYPESAFE_API_KEY:-}" ]; then
            BACKEND=typesafe
        else
            BACKEND=""
        fi ;;
    opencode-zen) BACKEND="" ;;
    *) echo "Invalid JEV_BACKEND" >&2; exit 1 ;;
esac
if [ "$BACKEND" = "typesafe" ] && [ -z "${TYPESAFE_API_KEY:-}" ]; then
    echo "Missing TypeSafe credential; configure TypeSafe, OpenCode Zen, or Laya" >&2
    exit 1
fi
if [ -z "$BACKEND" ]; then
    if ! command -v python3 >/dev/null 2>&1; then
        echo "❌ Python 3 is required for System One backend configuration." >&2
        exit 1
    fi
    BACKEND="$(python3 "${SCRIPT_DIR}/scripts/jev-systemone.py" --check-backend)" || exit 1
fi
echo "✔ System One backend configured: ${BACKEND}"
if [ "$BACKEND" = "laya" ]; then
    export TYPESAFE_API_KEY="${TYPESAFE_API_KEY:-${JEV_LOCAL_KEY:-local}}"
elif [ "$BACKEND" = "opencode-zen" ]; then
    echo "  Typed decisions: python3 ${SCRIPT_DIR}/scripts/jev-systemone.py"
    echo "  Zen does not replace jev-scout registry searches or git jev check."
fi

TARGET_DIR="${HOME}/.agents/skills"
mkdir -p "${TARGET_DIR}"

# Copy all skills
cp -r "${SCRIPT_DIR}/skills/"* "${TARGET_DIR}/"

echo "✔ Skills installed to ${TARGET_DIR}:"
ls -d "${TARGET_DIR}/jev-"*

# Check prerequisite binaries
echo ""
echo "🔍 Checking TypeSafe Jev tooling on PATH..."

check_tool() {
    local tool="$1"
    local install_cmd="$2"
    if [ $# -ge 3 ]; then
        local probe="$3"
        if $probe >/dev/null 2>&1; then
            echo "  ✔ $tool found"
        else
            echo "  ✘ $tool MISSING! Install via: $install_cmd"
            MISSING=$((MISSING + 1))
        fi
    elif command -v "$tool" >/dev/null 2>&1; then
        echo "  ✔ $tool found ($(command -v "$tool"))"
    else
        echo "  ✘ $tool MISSING! Install via: $install_cmd"
        MISSING=$((MISSING + 1))
    fi
}

MISSING=0
check_tool "jev-scout" "cargo install jev-scout"
check_tool "jev-axi" "npm install -g jev-axi"
check_tool "git-jev" "git jev install" "git jev --version"
check_tool "jev-guard" "npm install -g jev-guard"
check_tool "supercov" "npm install -g supercov"
check_tool "limpet" "git clone https://github.com/noplan-inc/limpet ~/limpet (or /plugin install limpet@limpet)" "[ -f \"$HOME/limpet/limpet.py\" ] || command -v limpet || (command -v claude >/dev/null 2>&1 && claude plugin list 2>/dev/null | grep -q limpet)"
check_tool "jev-seo" "cargo install jev-seo"

echo ""
if [ "$MISSING" -gt 0 ]; then
    echo "⚠️  Skills installed successfully, but ${MISSING} prerequisite tool(s) were not detected."
    echo "   Install the missing tools above to activate their respective Jev reflex gates."
else
    echo "✔ All TypeSafe Jev tools and environment variables verified!"
fi
echo "🚀 jev-superpowers ready! Use 'jev-using-superpowers' or 'jev-brainstorming' in your agent sessions."
