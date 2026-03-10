#!/bin/bash
set -e

echo ""
echo "========================================"
echo "CostOptimizer360 - Local Installation"
echo "========================================"
echo ""

# Check for Python 3
if ! command -v python3 &> /dev/null; then
    echo "✗ Python 3 is required but not installed."
    echo "  Please install Python 3.8 or higher."
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "✓ Found Python $PYTHON_VERSION"

# Check for pip
if ! command -v pip3 &> /dev/null && ! python3 -m pip --version &> /dev/null; then
    echo "✗ pip is required but not installed."
    echo "  Please install pip for Python 3."
    exit 1
fi
echo "✓ Found pip"

# Check for AWS CLI
if ! command -v aws &> /dev/null; then
    echo ""
    echo "⚠ AWS CLI is not installed."
    echo "  The tool requires AWS CLI to be configured with valid credentials."
    echo ""
    read -rp "Do you want to continue anyway? (y/n): " continue_without_aws
    if [[ ! "$continue_without_aws" =~ ^[Yy]$ ]]; then
        echo ""
        echo "Please install AWS CLI first:"
        echo "  https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
        exit 1
    fi
else
    echo "✓ Found AWS CLI"
    
    # Check if AWS credentials are configured
    if aws sts get-caller-identity &> /dev/null; then
        ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)
        echo "✓ AWS credentials configured (Account: $ACCOUNT_ID)"
    else
        echo ""
        echo "⚠ AWS credentials are not configured or invalid."
        echo "  Run 'aws configure' to set up your credentials."
        echo ""
    fi
fi

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Ask for installation mode
echo ""
echo "Choose installation mode:"
echo ""
echo "  1) Web Server Mode (Recommended)"
echo "     - Full web interface"
echo "     - Runs on http://localhost:5000"
echo "     - Start/Stop with simple commands"
echo "     - Auto-start on boot"
echo ""
echo "  2) CLI Only Mode"
echo "     - Command-line tool only"
echo "     - No web interface"
echo ""
read -rp "Select mode (1 or 2): " INSTALL_MODE

# Create virtual environment (optional but recommended)
echo ""
read -rp "Create a virtual environment? (recommended) (y/n): " create_venv

if [[ "$create_venv" =~ ^[Yy]$ ]]; then
    VENV_DIR="$SCRIPT_DIR/venv"
    
    if [ -d "$VENV_DIR" ]; then
        echo "Virtual environment already exists at $VENV_DIR"
        read -rp "Remove and recreate? (y/n): " recreate_venv
        if [[ "$recreate_venv" =~ ^[Yy]$ ]]; then
            rm -rf "$VENV_DIR"
        fi
    fi
    
    if [ ! -d "$VENV_DIR" ]; then
        echo ""
        echo "▶ Creating virtual environment..."
        python3 -m venv "$VENV_DIR"
        echo "✓ Virtual environment created"
    fi
    
    echo "▶ Activating virtual environment..."
    source "$VENV_DIR/bin/activate"
    echo "✓ Virtual environment activated"
    
    PIP_CMD="pip"
else
    PIP_CMD="pip3"
fi

# Install dependencies
echo ""
echo "▶ Installing Python dependencies..."
$PIP_CMD install -r "$SCRIPT_DIR/requirements.txt" -q
echo "✓ Dependencies installed"

# Make scripts executable
chmod +x "$SCRIPT_DIR/server.py"
chmod +x "$SCRIPT_DIR/serve-infraoptimizer"
chmod +x "$SCRIPT_DIR/stop-infraoptimizer"

# Handle installation mode
case $INSTALL_MODE in
    1)
        # Web Server Mode
        echo ""
        echo "▶ Setting up Web Server Mode..."
        
        # Ask if user wants to start the server now
        read -rp "Start the web server now? (y/n): " start_now
        
        if [[ "$start_now" =~ ^[Yy]$ ]]; then
            echo ""
            bash "$SCRIPT_DIR/serve-infraoptimizer"
        fi
        
        echo ""
        echo "========================================"
        echo "✓ Web Server Installation Complete!"
        echo "========================================"
        echo ""
        echo "Web Server Commands:"
        echo "  Start server:  $SCRIPT_DIR/serve-infraoptimizer"
        echo "  Stop server:   $SCRIPT_DIR/stop-infraoptimizer"
        echo ""
        echo "Access the web interface at:"
        echo "  http://localhost:5000"
        ;;
    2)
        # CLI Only Mode
        echo ""
        echo "========================================"
        echo "✓ CLI Installation Complete!"
        echo "========================================"
        echo ""
        echo "Note: CLI mode is not yet implemented."
        echo "Please use Web Server Mode for now."
        echo ""
        echo "Start the web server with:"
        echo "  $SCRIPT_DIR/serve-infraoptimizer"
        ;;
    *)
        echo "Invalid option, defaulting to Web Server Mode"
        echo ""
        echo "========================================"
        echo "✓ Installation Complete!"
        echo "========================================"
        echo ""
        echo "Web Server Commands:"
        echo "  Start server:  $SCRIPT_DIR/serve-infraoptimizer"
        echo "  Stop server:   $SCRIPT_DIR/stop-infraoptimizer"
        ;;
esac

echo ""
echo "To add to PATH (optional):"
echo "  echo 'export PATH=\"\$PATH:$SCRIPT_DIR\"' >> ~/.bashrc"
echo "  source ~/.bashrc"
echo ""
echo "Prerequisites:"
echo "  1. AWS CLI configured with credentials: aws configure"
echo "  2. IAM permissions for EC2, RDS, Lambda, CloudWatch, Pricing API"
echo ""
