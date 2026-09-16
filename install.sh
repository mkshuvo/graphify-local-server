#!/usr/bin/env bash
# ==============================================================================
# Graphify 2.0 -- Automated Zero-Friction Setup Script (macOS & Linux)
# ==============================================================================
# Usage:
#   bash install.sh
#   ./install.sh --start
#   ./install.sh --codebase /path/to/repo --start
# ==============================================================================

set -e

# ANSI Color codes
BOLD="\033[1m"
GREEN="\033[0;32m"
CYAN="\033[0;36m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
MAGENTA="\033[0;35m"
RESET="\033[0m"

log_step() { echo -e "${CYAN}[*]${RESET} $1"; }
log_ok()   { echo -e "${GREEN}[OK]${RESET} $1"; }
log_warn() { echo -e "${YELLOW}[!]${RESET} $1"; }
log_fail() { echo -e "${RED}[ERROR]${RESET} $1"; }

# Resolve script root directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$SCRIPT_DIR"

echo -e "${MAGENTA}====================================================================${RESET}"
echo -e "${BOLD}       Graphify 2.0 -- Automatic Setup Engine (macOS & Linux)       ${RESET}"
echo -e "${MAGENTA}====================================================================${RESET}"
echo -e "  Repository: ${SCRIPT_DIR}"
echo ""

# 1. Detect Operating System
OS="$(uname -s)"
case "$OS" in
    Darwin*)  PLATFORM="macOS" ;;
    Linux*)   PLATFORM="Linux" ;;
    *)        PLATFORM="Unknown ($OS)" ;;
esac
log_step "Detected operating system: ${BOLD}${PLATFORM}${RESET}"

# 2. Detect Python 3.10+
log_step "Checking Python interpreter..."

PYTHON_BIN=""

# Check if local .venv already has working python
if [ -f ".venv/bin/python" ]; then
    PYTHON_BIN=".venv/bin/python"
fi

if [ -z "$PYTHON_BIN" ] && command -v python3 >/dev/null 2>&1; then
    VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || true)
    if [ "$(printf '%s\n' "3.10" "$VER" | sort -V | head -n1)" = "3.10" ]; then
        PYTHON_BIN="python3"
    fi
fi

if [ -z "$PYTHON_BIN" ] && command -v python >/dev/null 2>&1; then
    VER=$(python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || true)
    if [ "$(printf '%s\n' "3.10" "$VER" | sort -V | head -n1)" = "3.10" ]; then
        PYTHON_BIN="python"
    fi
fi

# If python3 is missing or too old, attempt automated installation
if [ -z "$PYTHON_BIN" ]; then
    log_warn "Python 3.10+ was not found on your system."

    if [ "$PLATFORM" = "macOS" ]; then
        if command -v brew >/dev/null 2>&1; then
            log_step "Attempting Homebrew installation of python3..."
            brew install python3
            PYTHON_BIN="python3"
        else
            log_fail "Please install Homebrew (https://brew.sh) or Python 3.10+ from https://www.python.org/downloads/"
            exit 1
        fi
    elif [ "$PLATFORM" = "Linux" ]; then
        if command -v apt-get >/dev/null 2>&1; then
            log_step "Debian/Ubuntu detected. Installing python3, venv, and pip..."
            sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip
            PYTHON_BIN="python3"
        elif command -v dnf >/dev/null 2>&1; then
            log_step "Fedora/RHEL detected. Installing python3 and pip..."
            sudo dnf install -y python3 python3-pip
            PYTHON_BIN="python3"
        elif command -v pacman >/dev/null 2>&1; then
            log_step "Arch Linux detected. Installing python..."
            sudo pacman -S --noconfirm python python-pip
            PYTHON_BIN="python3"
        else
            log_fail "Please install Python 3.10+ with your distribution package manager."
            exit 1
        fi
    fi
fi

log_ok "Using Python: ${BOLD}$(${PYTHON_BIN} --version)${RESET}"

# 3. Invoke Universal Python Installer Engine
log_step "Invoking installation and dependency resolver..."
"${PYTHON_BIN}" install.py "$@"

# 4. Make launcher scripts executable
chmod +x start.sh 2>/dev/null || true
chmod +x install.sh 2>/dev/null || true

log_ok "Setup completed successfully!"
