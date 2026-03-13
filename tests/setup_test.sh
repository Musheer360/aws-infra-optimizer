#!/bin/bash

echo "Setting up local testing environment..."

# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate

# Install dependencies
pip install -q python-docx boto3 matplotlib

echo ""
echo "✅ Setup complete!"
echo ""
echo "To test:"
echo "  source venv/bin/activate"
echo "  python3 test_local.py"
echo ""
