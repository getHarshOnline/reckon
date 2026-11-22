#!/usr/bin/env bash
# =============================================================================
# Reckon Development Environment Setup
# =============================================================================
#
# This script sets up the complete Reckon development environment including:
# - Python virtual environment with all dependencies
# - Rust extension build via maturin
# - Optional integrations (Gymnasium, MiniGrid, TextWorld, Ollama check)
# - VS Code configuration for proper Python path resolution
# - Port availability checks for debugger UI
#
# Usage:
#   source setup.sh          # Setup and activate environment
#   source setup.sh --full   # Setup with all optional notebook dependencies
#   source setup.sh --check  # Check environment status only
#   deactivate               # Deactivate when done
#
# =============================================================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory (Reckon root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv"
VSCODE_DIR="${SCRIPT_DIR}/.vscode"

# =============================================================================
# Helper Functions
# =============================================================================

print_header() {
    echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

check_command() {
    if command -v "$1" &> /dev/null; then
        print_success "$1 found: $(command -v "$1")"
        return 0
    else
        print_warning "$1 not found"
        return 1
    fi
}

check_port() {
    local port=$1
    if lsof -Pi ":$port" -sTCP:LISTEN -t >/dev/null 2>&1; then
        print_warning "Port $port is already in use"
        return 1
    else
        print_success "Port $port is available"
        return 0
    fi
}

# =============================================================================
# Environment Check Mode
# =============================================================================

check_environment() {
    print_header "Reckon Environment Status"

    echo -e "\n${YELLOW}System Requirements:${NC}"
    check_command python3 || true
    check_command pip || true
    check_command cargo || true
    check_command maturin || true
    check_command node || true
    check_command pnpm || true

    echo -e "\n${YELLOW}Virtual Environment:${NC}"
    if [[ -d "$VENV_DIR" ]]; then
        print_success "venv exists at $VENV_DIR"
        if [[ -n "$VIRTUAL_ENV" ]]; then
            print_success "venv is active: $VIRTUAL_ENV"
        else
            print_warning "venv exists but not activated"
        fi
    else
        print_warning "venv not found"
    fi

    echo -e "\n${YELLOW}Python Packages:${NC}"
    if [[ -n "$VIRTUAL_ENV" ]]; then
        python3 -c "import reckon; print('reckon:', reckon.__version__ if hasattr(reckon, '__version__') else 'installed')" 2>/dev/null && print_success "reckon installed" || print_warning "reckon not installed"
        python3 -c "from reckon._rust import EventLogger" 2>/dev/null && print_success "Rust extension loaded" || print_warning "Rust extension not built"
        python3 -c "import numpy; print(f'numpy: {numpy.__version__}')" 2>/dev/null || print_warning "numpy not installed"
        python3 -c "import matplotlib; print(f'matplotlib: {matplotlib.__version__}')" 2>/dev/null || print_warning "matplotlib not installed"
    else
        print_warning "Activate venv first to check Python packages"
    fi

    echo -e "\n${YELLOW}Optional Dependencies (for notebooks):${NC}"
    if [[ -n "$VIRTUAL_ENV" ]]; then
        python3 -c "import gymnasium; print(f'gymnasium: {gymnasium.__version__}')" 2>/dev/null && print_success "gymnasium" || print_info "gymnasium not installed (optional)"
        python3 -c "import minigrid; print('minigrid: installed')" 2>/dev/null && print_success "minigrid" || print_info "minigrid not installed (optional)"
        python3 -c "import textworld; print('textworld: installed')" 2>/dev/null && print_success "textworld" || print_info "textworld not installed (optional)"
    fi

    echo -e "\n${YELLOW}Ollama (Local LLM):${NC}"
    if curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
        print_success "Ollama server is running"
        local models=$(curl -s http://localhost:11434/api/tags | python3 -c "import sys,json; d=json.load(sys.stdin); print(', '.join(m['name'] for m in d.get('models',[])) or 'no models')" 2>/dev/null || echo "unable to list")
        print_info "Available models: $models"
    else
        print_info "Ollama not running (optional, for notebook 04)"
    fi

    echo -e "\n${YELLOW}Port Availability:${NC}"
    check_port 5173 || print_info "Port 5173 needed for viz-ui dev server"
    check_port 8000 || print_info "Port 8000 needed for viz Python server"
    check_port 11434 || print_info "Port 11434 used by Ollama"

    echo -e "\n${YELLOW}VS Code Configuration:${NC}"
    if [[ -f "${VSCODE_DIR}/settings.json" ]]; then
        print_success ".vscode/settings.json exists"
    else
        print_warning ".vscode/settings.json not found"
    fi
}

# =============================================================================
# VS Code Configuration
# =============================================================================

setup_vscode() {
    print_info "Configuring VS Code settings..."

    mkdir -p "$VSCODE_DIR"

    # Create or update settings.json
    cat > "${VSCODE_DIR}/settings.json" << EOF
{
    "python.defaultInterpreterPath": "${VENV_DIR}/bin/python",
    "python.terminal.activateEnvironment": true,
    "python.analysis.extraPaths": [
        "${SCRIPT_DIR}/src",
        "${SCRIPT_DIR}/notebooks"
    ],
    "python.autoComplete.extraPaths": [
        "${SCRIPT_DIR}/src",
        "${SCRIPT_DIR}/notebooks"
    ],
    "python.envFile": "${SCRIPT_DIR}/.env",
    "jupyter.notebookFileRoot": "${SCRIPT_DIR}/notebooks",
    "jupyter.kernelspec.name": "python3",
    "[python]": {
        "editor.formatOnSave": true,
        "editor.codeActionsOnSave": {
            "source.organizeImports": "explicit"
        }
    },
    "files.exclude": {
        "**/__pycache__": true,
        "**/*.pyc": true,
        "**/.pytest_cache": true,
        "**/node_modules": true,
        "**/.venv": false
    },
    "search.exclude": {
        "**/node_modules": true,
        "**/.venv": true,
        "**/target": true
    }
}
EOF

    print_success "VS Code settings configured"

    # Create .env file for environment variables
    cat > "${SCRIPT_DIR}/.env" << EOF
PYTHONPATH=${SCRIPT_DIR}/src:${SCRIPT_DIR}/notebooks
RECKON_ROOT=${SCRIPT_DIR}
EOF

    print_success "Environment file created"
}

# =============================================================================
# Main Setup
# =============================================================================

setup_environment() {
    local full_install=${1:-false}
    local configure_vscode=${2:-false}

    print_header "Reckon Development Environment Setup"

    # Step 1: Check prerequisites
    echo -e "\n${YELLOW}Step 1: Checking prerequisites...${NC}"

    if ! check_command python3; then
        print_error "Python 3 is required. Install from https://python.org"
        return 1
    fi

    if ! check_command cargo; then
        print_warning "Rust/Cargo not found. Install from https://rustup.rs"
        print_warning "Rust extension will not be built"
    fi

    cd "$SCRIPT_DIR"

    # Step 2: Create/update virtual environment
    echo -e "\n${YELLOW}Step 2: Setting up virtual environment...${NC}"

    if [[ ! -d "$VENV_DIR" ]]; then
        print_info "Creating virtual environment..."
        python3 -m venv "$VENV_DIR"
        print_success "Virtual environment created"
    else
        print_success "Virtual environment exists"
    fi

    # Activate venv
    source "${VENV_DIR}/bin/activate"
    print_success "Virtual environment activated"

    # Upgrade pip
    pip install --upgrade pip --quiet
    print_success "pip upgraded"

    # Step 3: Install Python dependencies
    echo -e "\n${YELLOW}Step 3: Installing Python dependencies...${NC}"

    pip install -e ".[dev,viz]" --quiet
    print_success "Core dependencies installed"

    if [[ "$full_install" == "true" ]]; then
        print_info "Installing optional notebook dependencies..."
        pip install gymnasium minigrid --quiet 2>/dev/null && print_success "gymnasium + minigrid installed" || print_warning "Some optional deps failed"
        # TextWorld and memory-gym can have complex deps, make them optional
        pip install textworld --quiet 2>/dev/null && print_success "textworld installed" || print_info "textworld skipped (complex deps)"
    fi

    # Step 4: Build Rust extension
    echo -e "\n${YELLOW}Step 4: Building Rust extension...${NC}"

    if check_command maturin; then
        maturin develop --quiet 2>/dev/null && print_success "Rust extension built" || print_warning "Rust build failed"
    elif check_command cargo; then
        pip install maturin --quiet
        maturin develop --quiet 2>/dev/null && print_success "Rust extension built" || print_warning "Rust build failed"
    else
        print_warning "Skipping Rust extension (cargo not available)"
    fi

    # Step 5: Configure VS Code (optional - requires --vscode flag)
    echo -e "\n${YELLOW}Step 5: VS Code Configuration...${NC}"
    if [[ "$configure_vscode" == "true" ]]; then
        setup_vscode
    else
        print_info "Skipping VS Code configuration (use --vscode flag to enable)"
        print_info "Run: source setup.sh --vscode"
    fi

    # Step 6: Verify installation
    echo -e "\n${YELLOW}Step 6: Verifying installation...${NC}"

    python3 -c "import reckon" && print_success "reckon imports correctly" || print_error "reckon import failed"
    python3 -c "from reckon._rust import EventLogger" 2>/dev/null && print_success "Rust extension works" || print_warning "Rust extension not loaded"
    python3 -c "from notebooks._utils import NotebookConfig" 2>/dev/null && print_success "Notebook utils work" || print_warning "Notebook utils import issue"

    # Summary
    print_header "Setup Complete!"

    echo -e "\n${GREEN}Environment is ready!${NC}\n"
    echo "Your shell is now in the Reckon virtual environment."
    echo ""
    echo "Quick commands:"
    echo "  cd notebooks && jupyter lab                    # Run notebooks"
    echo "  cd viz-ui && pnpm dev                          # Start debugger UI"
    echo "  pytest src/tests/                              # Run tests"
    echo "  deactivate                                     # Exit venv"
    echo ""

    if [[ "$full_install" != "true" ]]; then
        echo -e "${YELLOW}Note:${NC} Run 'source setup.sh --full' to install optional deps"
        echo "      (gymnasium, minigrid, textworld) for full notebook functionality."
        echo ""
    fi
}

# =============================================================================
# Main Entry Point
# =============================================================================

main() {
    # Parse arguments for --vscode flag (can appear anywhere)
    local configure_vscode=false
    local full_install=false
    local show_help=false
    local check_only=false

    for arg in "$@"; do
        case "$arg" in
            --vscode)
                configure_vscode=true
                ;;
            --full)
                full_install=true
                ;;
            --check)
                check_only=true
                ;;
            --help|-h)
                show_help=true
                ;;
        esac
    done

    if [[ "$show_help" == "true" ]]; then
        echo "Reckon Development Environment Setup"
        echo ""
        echo "Usage:"
        echo "  source setup.sh                  Setup and activate environment"
        echo "  source setup.sh --full           Setup with all optional dependencies"
        echo "  source setup.sh --vscode         Setup with VS Code configuration"
        echo "  source setup.sh --full --vscode  Full setup including VS Code config"
        echo "  source setup.sh --check          Check environment status"
        echo "  source setup.sh --help           Show this help"
        echo ""
        echo "VS Code configuration writes to repo-local .vscode/ directory."
        echo "After setup, use 'deactivate' to exit the virtual environment."
        return 0
    fi

    if [[ "$check_only" == "true" ]]; then
        check_environment
        return 0
    fi

    # Run setup with parsed options
    setup_environment "$full_install" "$configure_vscode"
}

# Run main function
main "$@"
