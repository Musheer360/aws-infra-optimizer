#!/bin/bash
set -e

echo ""
echo "========================================"
echo "CostOptimizer360 - Local Installation"
echo "========================================"
echo ""

# Auto-install missing dependencies
install_pkg() {
    echo "▶ Installing $1..."
    sudo apt-get install -y "$1" -qq > /dev/null 2>&1
    echo "✓ Installed $1"
}

if ! command -v python3 &> /dev/null; then
    install_pkg python3
fi
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "✓ Found Python $PYTHON_VERSION"

if ! command -v pip3 &> /dev/null && ! python3 -m pip --version &> /dev/null; then
    install_pkg python3-pip
fi
echo "✓ Found pip"

if ! python3 -m venv --help &> /dev/null; then
    install_pkg "python${PYTHON_VERSION}-venv"
fi
echo "✓ Found python3-venv"

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Create virtual environment (always fresh)
VENV_DIR="$SCRIPT_DIR/venv"
rm -rf "$VENV_DIR"

echo ""
echo "▶ Creating virtual environment..."
python3 -m venv "$VENV_DIR"
echo "✓ Virtual environment created"

echo "▶ Activating virtual environment..."
source "$VENV_DIR/bin/activate"
echo "✓ Virtual environment activated"

# Install dependencies
echo ""
echo "▶ Installing Python dependencies..."
pip install -r "$SCRIPT_DIR/requirements.txt" -q
echo "✓ Dependencies installed"

# Make scripts executable
chmod +x "$SCRIPT_DIR/server.py"
chmod +x "$SCRIPT_DIR/serve-infraoptimizer"
chmod +x "$SCRIPT_DIR/stop-infraoptimizer"

# Start the web server
echo ""
bash "$SCRIPT_DIR/serve-infraoptimizer"

echo ""
echo "========================================"
echo "✓ Installation Complete!"
echo "========================================"
echo ""
echo "Commands:"
echo "  Start server:  $SCRIPT_DIR/serve-infraoptimizer"
echo "  Stop server:   $SCRIPT_DIR/stop-infraoptimizer"
echo ""
echo "Access the web interface at:"
echo "  http://localhost:5000"
echo ""
echo "Note:"
echo "  Enter your AWS credentials (Access Key, Secret Key) directly in the web UI to scan resources."
echo ""
