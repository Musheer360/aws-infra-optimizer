#!/bin/bash

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

clear
echo -e "${BLUE}"
cat << "EOF"
╔════════════════════════════════════════════════════════════════╗
║   AWS Infrastructure Optimizer - Local Installation Script     ║
╚════════════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

echo -e "${CYAN}This script installs the AWS Infrastructure Optimizer locally${NC}"
echo -e "${CYAN}on your Linux system or WSL environment.${NC}"
echo ""
echo -e "${YELLOW}Features:${NC}"
echo "  • Uses AWS CLI credentials directly (no need to enter in browser)"
echo "  • Runs as a local web server on http://localhost:5000"
echo "  • No AWS infrastructure costs"
echo "  • Supports AWS profiles for multi-account management"
echo ""

# Detect OS
detect_os() {
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        OS=$ID
        OS_VERSION=$VERSION_ID
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        OS="macos"
    else
        OS="unknown"
    fi
    
    # Check if running in WSL
    if grep -qi microsoft /proc/version 2>/dev/null; then
        IS_WSL=true
    else
        IS_WSL=false
    fi
}

detect_os

echo -e "${YELLOW}System Detection:${NC}"
if [[ "$IS_WSL" == true ]]; then
    echo -e "  Operating System: ${GREEN}WSL (Windows Subsystem for Linux)${NC}"
else
    echo -e "  Operating System: ${GREEN}${OS}${NC}"
fi
echo ""

# Check prerequisites
echo -e "${YELLOW}Checking prerequisites...${NC}"
echo ""

# Check Python 3
PYTHON_CMD=""
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
    PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
    echo -e "  ✅ Python 3: ${GREEN}$PYTHON_VERSION${NC}"
elif command -v python &> /dev/null; then
    PY_VERSION=$(python --version 2>&1 | cut -d' ' -f2)
    if [[ "$PY_VERSION" == 3* ]]; then
        PYTHON_CMD="python"
        echo -e "  ✅ Python 3: ${GREEN}$PY_VERSION${NC}"
    fi
fi

if [[ -z "$PYTHON_CMD" ]]; then
    echo -e "  ❌ Python 3: ${RED}Not installed${NC}"
    echo ""
    echo -e "${YELLOW}Install Python 3:${NC}"
    if [[ "$OS" == "ubuntu" || "$OS" == "debian" ]]; then
        echo "  sudo apt update && sudo apt install python3 python3-pip python3-venv"
    elif [[ "$OS" == "centos" || "$OS" == "rhel" || "$OS" == "fedora" ]]; then
        echo "  sudo dnf install python3 python3-pip"
    elif [[ "$OS" == "macos" ]]; then
        echo "  brew install python3"
    fi
    exit 1
fi

# Check pip
if command -v pip3 &> /dev/null; then
    PIP_CMD="pip3"
    echo -e "  ✅ pip3: ${GREEN}Available${NC}"
elif command -v pip &> /dev/null; then
    PIP_CMD="pip"
    echo -e "  ✅ pip: ${GREEN}Available${NC}"
else
    echo -e "  ❌ pip: ${RED}Not installed${NC}"
    echo ""
    echo -e "${YELLOW}Install pip:${NC}"
    echo "  $PYTHON_CMD -m ensurepip --upgrade"
    exit 1
fi

# Check AWS CLI
AWS_CLI_OK=false
if command -v aws &> /dev/null; then
    AWS_VERSION=$(aws --version 2>&1 | cut -d' ' -f1 | cut -d'/' -f2)
    echo -e "  ✅ AWS CLI: ${GREEN}$AWS_VERSION${NC}"
    
    # Check if credentials are configured
    if aws sts get-caller-identity &> /dev/null; then
        ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)
        CURRENT_USER=$(aws sts get-caller-identity --query Arn --output text 2>/dev/null | rev | cut -d'/' -f1 | rev)
        echo -e "  ✅ AWS Credentials: ${GREEN}Configured (Account: $ACCOUNT_ID)${NC}"
        AWS_CLI_OK=true
    else
        echo -e "  ⚠️  AWS Credentials: ${YELLOW}Not configured${NC}"
    fi
else
    echo -e "  ❌ AWS CLI: ${RED}Not installed${NC}"
fi

if [[ "$AWS_CLI_OK" != true ]]; then
    echo ""
    echo -e "${YELLOW}Note:${NC} AWS CLI is required to scan AWS resources."
    echo ""
    echo -e "${YELLOW}Install AWS CLI:${NC}"
    if [[ "$OS" == "ubuntu" || "$OS" == "debian" ]]; then
        echo "  sudo apt install awscli"
        echo "  # Or install latest version:"
        echo '  curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"'
        echo "  unzip awscliv2.zip && sudo ./aws/install"
    elif [[ "$OS" == "centos" || "$OS" == "rhel" || "$OS" == "fedora" ]]; then
        echo "  sudo dnf install awscli"
    elif [[ "$OS" == "macos" ]]; then
        echo "  brew install awscli"
    fi
    echo ""
    echo -e "${YELLOW}Configure AWS CLI:${NC}"
    echo "  aws configure"
    echo ""
    read -p "Continue installation anyway? (y/n): " CONTINUE
    if [[ "$CONTINUE" != "y" && "$CONTINUE" != "Y" ]]; then
        echo "Installation cancelled."
        exit 0
    fi
fi

echo ""
echo -e "${YELLOW}Starting installation...${NC}"
echo ""

# Create virtual environment
echo -e "${YELLOW}Step 1/5:${NC} Creating Python virtual environment..."
$PYTHON_CMD -m venv venv
echo -e "  ${GREEN}✓${NC} Virtual environment created"

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo -e "${YELLOW}Step 2/5:${NC} Installing Python dependencies..."
pip install --upgrade pip -q
pip install flask flask-cors python-docx boto3 -q
echo -e "  ${GREEN}✓${NC} Dependencies installed"

# Create local server with AWS CLI credential support
echo -e "${YELLOW}Step 3/5:${NC} Creating local server..."
cat > local_server.py << 'PYEOF'
#!/usr/bin/env python3
"""
AWS Infrastructure Optimizer - Local Server
Uses AWS CLI credentials for authentication (no credentials entered in browser)
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'lambda'))

from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
import json
from datetime import datetime
from io import BytesIO

app = Flask(__name__)
CORS(app)

# Store current AWS profile (can be changed via API)
current_profile = os.environ.get('AWS_PROFILE', 'default')

@app.route('/')
def index():
    return send_from_directory('frontend', 'index-local.html')

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({'status': 'ok', 'profile': current_profile})

@app.route('/profiles', methods=['GET'])
def list_profiles():
    """List available AWS profiles"""
    import configparser
    profiles = ['default']
    
    # Check ~/.aws/credentials
    creds_file = os.path.expanduser('~/.aws/credentials')
    if os.path.exists(creds_file):
        config = configparser.ConfigParser()
        config.read(creds_file)
        profiles = list(config.sections())
        if 'default' not in profiles:
            profiles.insert(0, 'default')
    
    # Also check ~/.aws/config for SSO profiles
    config_file = os.path.expanduser('~/.aws/config')
    if os.path.exists(config_file):
        config = configparser.ConfigParser()
        config.read(config_file)
        for section in config.sections():
            if section.startswith('profile '):
                profile_name = section.replace('profile ', '')
                if profile_name not in profiles:
                    profiles.append(profile_name)
    
    return jsonify({'profiles': profiles, 'current': current_profile})

@app.route('/profile', methods=['POST'])
def set_profile():
    """Set current AWS profile"""
    global current_profile
    data = request.json
    current_profile = data.get('profile', 'default')
    os.environ['AWS_PROFILE'] = current_profile
    return jsonify({'profile': current_profile})

@app.route('/verify-credentials', methods=['POST'])
def verify_credentials():
    """Verify AWS credentials are working"""
    try:
        import boto3
        data = request.json
        profile = data.get('profile', current_profile)
        region = data.get('region', 'us-east-1')
        
        session = boto3.Session(profile_name=profile, region_name=region)
        sts = session.client('sts')
        identity = sts.get_caller_identity()
        
        return jsonify({
            'valid': True,
            'account': identity['Account'],
            'arn': identity['Arn'],
            'user_id': identity['UserId']
        })
    except Exception as e:
        return jsonify({
            'valid': False,
            'error': str(e)
        }), 400

@app.route('/optimize', methods=['POST', 'OPTIONS'])
def optimize():
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.json
        
        from lambda_function import (
            scan_ec2_instances, scan_ebs_volumes, scan_rds_instances,
            scan_lambda_functions, scan_elastic_ips, generate_word_report
        )
        import boto3
        
        # Use AWS CLI profile credentials (no credentials from browser)
        profile = data.get('profile', current_profile)
        region = data.get('region', 'us-east-1')
        
        try:
            session = boto3.Session(profile_name=profile, region_name=region)
            # Verify credentials work
            sts = session.client('sts')
            sts.get_caller_identity()
        except Exception as e:
            return jsonify({
                'error': f'AWS credentials error: {str(e)}. Please run "aws configure" or check your AWS profile.'
            }), 401
        
        recommendations = {}
        total_savings = 0.0
        
        services = data.get('services', ['ec2', 'ebs', 'rds', 'lambda', 'eip'])
        
        if 'ec2' in services:
            recs = scan_ec2_instances(session)
            recommendations['ec2'] = recs
            total_savings += sum(r['monthly_savings'] for r in recs)
        
        if 'ebs' in services:
            recs = scan_ebs_volumes(session)
            recommendations['ebs'] = recs
            total_savings += sum(r['monthly_savings'] for r in recs)
        
        if 'rds' in services:
            recs = scan_rds_instances(session)
            recommendations['rds'] = recs
            total_savings += sum(r['monthly_savings'] for r in recs)
        
        if 'lambda' in services:
            recs = scan_lambda_functions(session)
            recommendations['lambda'] = recs
            total_savings += sum(r['monthly_savings'] for r in recs)
        
        if 'eip' in services:
            recs = scan_elastic_ips(session)
            recommendations['eip'] = recs
            total_savings += sum(r['monthly_savings'] for r in recs)
        
        doc = generate_word_report(
            recommendations,
            total_savings,
            data.get('clientName', 'Client')
        )
        
        buffer = BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        
        filename = f"{data.get('clientName', 'Client').replace(' ', '-')}-InfraOptimization-{datetime.now().strftime('%Y%m%d')}.docx"
        
        return send_file(
            buffer,
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("\n" + "="*60)
    print("AWS Infrastructure Optimizer - Local Server")
    print("="*60)
    print(f"\nUsing AWS Profile: {current_profile}")
    print("\nServer running at: http://localhost:5000")
    print("\nPress Ctrl+C to stop\n")
    app.run(host='127.0.0.1', port=5000, debug=False)
PYEOF

chmod +x local_server.py
echo -e "  ${GREEN}✓${NC} Local server created"

# Create local frontend with AWS CLI credential support
echo -e "${YELLOW}Step 4/5:${NC} Creating local frontend..."
cat > frontend/index-local.html << 'HTMLEOF'
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AWS Infrastructure Optimizer (Local)</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }
        .container {
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            padding: 40px;
            max-width: 600px;
            width: 100%;
        }
        h1 {
            color: #333;
            text-align: center;
            margin-bottom: 10px;
            font-size: 28px;
        }
        .badge {
            display: inline-block;
            background: #4CAF50;
            color: white;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 600;
            margin-left: 10px;
        }
        .subtitle {
            text-align: center;
            color: #666;
            margin-bottom: 30px;
            font-size: 14px;
        }
        .info {
            background: #e3f2fd;
            color: #1976d2;
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 20px;
            font-size: 13px;
        }
        .info.success {
            background: #e8f5e9;
            color: #2e7d32;
        }
        .info.warning {
            background: #fff3e0;
            color: #ef6c00;
        }
        .info.error {
            background: #ffebee;
            color: #c62828;
        }
        .credential-status {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .credential-status .icon {
            font-size: 18px;
        }
        .form-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            margin-bottom: 8px;
            color: #555;
            font-weight: 600;
            font-size: 14px;
        }
        input[type="text"], select {
            width: 100%;
            padding: 12px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 14px;
            transition: border-color 0.3s;
        }
        input[type="text"]:focus, select:focus {
            outline: none;
            border-color: #667eea;
        }
        .checkbox-group {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 10px;
            margin-top: 10px;
        }
        .checkbox-item {
            display: flex;
            align-items: center;
            padding: 10px;
            background: #f8f9fa;
            border-radius: 8px;
            cursor: pointer;
            transition: background 0.3s;
        }
        .checkbox-item:hover { background: #e9ecef; }
        .checkbox-item input[type="checkbox"] {
            margin-right: 8px;
            cursor: pointer;
            width: 18px;
            height: 18px;
        }
        .checkbox-item label {
            margin: 0;
            cursor: pointer;
            font-weight: normal;
        }
        button {
            width: 100%;
            padding: 14px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
            margin-top: 20px;
        }
        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(102, 126, 234, 0.4);
        }
        button:disabled {
            background: #ccc;
            cursor: not-allowed;
            transform: none;
        }
        .loading {
            display: none;
            text-align: center;
            margin-top: 20px;
        }
        .spinner {
            border: 4px solid #f3f3f3;
            border-top: 4px solid #667eea;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            animation: spin 1s linear infinite;
            margin: 0 auto;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        .error {
            background: #fee;
            color: #c33;
            padding: 12px;
            border-radius: 8px;
            margin-top: 15px;
            display: none;
            font-size: 14px;
        }
        .profile-section {
            display: flex;
            gap: 10px;
            align-items: flex-end;
        }
        .profile-section .form-group {
            flex: 1;
            margin-bottom: 0;
        }
        .profile-section button {
            width: auto;
            padding: 12px 20px;
            margin-top: 0;
            font-size: 14px;
        }
        .small-text {
            font-size: 12px;
            color: #999;
            margin-top: 5px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔍 AWS Infrastructure Optimizer<span class="badge">LOCAL</span></h1>
        <p class="subtitle">Running locally using AWS CLI credentials</p>

        <div id="credentialStatus" class="info">
            <div class="credential-status">
                <span class="icon">⏳</span>
                <span>Checking AWS credentials...</span>
            </div>
        </div>

        <form id="optimizerForm">
            <div class="form-group">
                <label>Client Name</label>
                <input type="text" id="clientName" placeholder="Enter client or account name" required>
            </div>

            <div class="profile-section">
                <div class="form-group">
                    <label>AWS Profile</label>
                    <select id="awsProfile">
                        <option value="default">default</option>
                    </select>
                    <p class="small-text">Select AWS CLI profile to use</p>
                </div>
                <button type="button" id="verifyBtn" onclick="verifyCredentials()">Verify</button>
            </div>

            <div class="form-group" style="margin-top: 20px;">
                <label>Select Services to Scan</label>
                <div class="checkbox-group">
                    <div class="checkbox-item">
                        <input type="checkbox" id="ec2" value="ec2" checked>
                        <label for="ec2">EC2 Instances</label>
                    </div>
                    <div class="checkbox-item">
                        <input type="checkbox" id="ebs" value="ebs" checked>
                        <label for="ebs">EBS Volumes</label>
                    </div>
                    <div class="checkbox-item">
                        <input type="checkbox" id="rds" value="rds" checked>
                        <label for="rds">RDS Databases</label>
                    </div>
                    <div class="checkbox-item">
                        <input type="checkbox" id="lambda" value="lambda" checked>
                        <label for="lambda">Lambda Functions</label>
                    </div>
                    <div class="checkbox-item">
                        <input type="checkbox" id="eip" value="eip" checked>
                        <label for="eip">Elastic IPs</label>
                    </div>
                </div>
            </div>

            <div class="form-group">
                <label>AWS Region</label>
                <select id="region" required>
                    <option value="us-east-1">US East (N. Virginia)</option>
                    <option value="us-east-2">US East (Ohio)</option>
                    <option value="us-west-1">US West (N. California)</option>
                    <option value="us-west-2">US West (Oregon)</option>
                    <option value="af-south-1">Africa (Cape Town)</option>
                    <option value="ap-east-1">Asia Pacific (Hong Kong)</option>
                    <option value="ap-south-1">Asia Pacific (Mumbai)</option>
                    <option value="ap-south-2">Asia Pacific (Hyderabad)</option>
                    <option value="ap-southeast-1">Asia Pacific (Singapore)</option>
                    <option value="ap-southeast-2">Asia Pacific (Sydney)</option>
                    <option value="ap-southeast-3">Asia Pacific (Jakarta)</option>
                    <option value="ap-southeast-4">Asia Pacific (Melbourne)</option>
                    <option value="ap-northeast-1">Asia Pacific (Tokyo)</option>
                    <option value="ap-northeast-2">Asia Pacific (Seoul)</option>
                    <option value="ap-northeast-3">Asia Pacific (Osaka)</option>
                    <option value="ca-central-1">Canada (Central)</option>
                    <option value="ca-west-1">Canada (Calgary)</option>
                    <option value="eu-central-1">Europe (Frankfurt)</option>
                    <option value="eu-central-2">Europe (Zurich)</option>
                    <option value="eu-west-1">Europe (Ireland)</option>
                    <option value="eu-west-2">Europe (London)</option>
                    <option value="eu-west-3">Europe (Paris)</option>
                    <option value="eu-south-1">Europe (Milan)</option>
                    <option value="eu-south-2">Europe (Spain)</option>
                    <option value="eu-north-1">Europe (Stockholm)</option>
                    <option value="il-central-1">Israel (Tel Aviv)</option>
                    <option value="me-south-1">Middle East (Bahrain)</option>
                    <option value="me-central-1">Middle East (UAE)</option>
                    <option value="sa-east-1">South America (São Paulo)</option>
                </select>
            </div>

            <button type="submit" id="generateBtn">Generate Optimization Report</button>
        </form>

        <div class="loading" id="loading">
            <div class="spinner"></div>
            <p style="margin-top: 15px; color: #667eea; font-weight: 600;">Analyzing infrastructure...</p>
            <p style="margin-top: 5px; color: #999; font-size: 13px;">This may take 1-2 minutes</p>
        </div>

        <div class="error" id="error"></div>
    </div>

    <script>
        // Load profiles on page load
        async function loadProfiles() {
            try {
                const response = await fetch('/profiles');
                const data = await response.json();
                
                const select = document.getElementById('awsProfile');
                select.innerHTML = '';
                
                data.profiles.forEach(profile => {
                    const option = document.createElement('option');
                    option.value = profile;
                    option.textContent = profile;
                    if (profile === data.current) {
                        option.selected = true;
                    }
                    select.appendChild(option);
                });
                
                // Verify default credentials
                verifyCredentials();
            } catch (error) {
                updateCredentialStatus('error', 'Failed to connect to server. Make sure the server is running.');
            }
        }
        
        async function verifyCredentials() {
            const profile = document.getElementById('awsProfile').value;
            const region = document.getElementById('region').value;
            
            updateCredentialStatus('checking', 'Verifying AWS credentials...');
            
            try {
                const response = await fetch('/verify-credentials', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ profile, region })
                });
                
                const data = await response.json();
                
                if (data.valid) {
                    updateCredentialStatus('success', 
                        `✅ Connected to AWS Account: ${data.account}`);
                    document.getElementById('generateBtn').disabled = false;
                } else {
                    updateCredentialStatus('error', 
                        `❌ ${data.error}. Run "aws configure" to set up credentials.`);
                    document.getElementById('generateBtn').disabled = true;
                }
            } catch (error) {
                updateCredentialStatus('error', 
                    '❌ Failed to verify credentials. Check server connection.');
                document.getElementById('generateBtn').disabled = true;
            }
        }
        
        function updateCredentialStatus(type, message) {
            const statusDiv = document.getElementById('credentialStatus');
            statusDiv.className = 'info ' + type;
            statusDiv.innerHTML = `<div class="credential-status"><span>${message}</span></div>`;
        }
        
        // Re-verify when profile or region changes
        document.getElementById('awsProfile').addEventListener('change', verifyCredentials);
        document.getElementById('region').addEventListener('change', verifyCredentials);
        
        document.getElementById('optimizerForm').addEventListener('submit', async (e) => {
            e.preventDefault();

            const clientName = document.getElementById('clientName').value;
            const region = document.getElementById('region').value;
            const profile = document.getElementById('awsProfile').value;
            
            const services = [];
            document.querySelectorAll('.checkbox-item input[type="checkbox"]:checked').forEach(cb => {
                services.push(cb.value);
            });

            if (services.length === 0) {
                showError('Please select at least one service to scan');
                return;
            }

            document.getElementById('generateBtn').disabled = true;
            document.getElementById('loading').style.display = 'block';
            document.getElementById('error').style.display = 'none';

            try {
                const response = await fetch('/optimize', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        clientName,
                        region,
                        profile,
                        services
                    })
                });

                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.error || 'Failed to generate report');
                }

                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = response.headers.get('content-disposition')?.split('filename=')[1] || 'report.docx';
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);

            } catch (error) {
                showError(error.message);
            } finally {
                document.getElementById('generateBtn').disabled = false;
                document.getElementById('loading').style.display = 'none';
            }
        });

        function showError(message) {
            const errorDiv = document.getElementById('error');
            errorDiv.textContent = message;
            errorDiv.style.display = 'block';
        }
        
        // Initialize on page load
        loadProfiles();
    </script>
</body>
</html>
HTMLEOF

echo -e "  ${GREEN}✓${NC} Local frontend created"

# Create startup scripts
echo -e "${YELLOW}Step 5/5:${NC} Creating startup scripts..."

# Main startup script
cat > start.sh << 'STARTEOF'
#!/bin/bash
cd "$(dirname "$0")"

# Activate virtual environment
if [[ -f venv/bin/activate ]]; then
    source venv/bin/activate
else
    echo "Error: Virtual environment not found. Run install-local.sh first."
    exit 1
fi

# Start server
echo ""
echo "Starting AWS Infrastructure Optimizer..."
echo "Press Ctrl+C to stop"
echo ""
python3 local_server.py
STARTEOF
chmod +x start.sh

# Background startup script
cat > start-background.sh << 'BGSTARTEOF'
#!/bin/bash
cd "$(dirname "$0")"

# Activate virtual environment
if [[ -f venv/bin/activate ]]; then
    source venv/bin/activate
else
    echo "Error: Virtual environment not found. Run install-local.sh first."
    exit 1
fi

# Check if already running
if [[ -f server.pid ]] && ps -p $(cat server.pid) > /dev/null 2>&1; then
    echo "Server is already running (PID: $(cat server.pid))"
    echo "Stop it first: ./stop.sh"
    exit 1
fi

# Start in background
nohup python3 local_server.py > server.log 2>&1 &
echo $! > server.pid
sleep 2

if ps -p $(cat server.pid) > /dev/null 2>&1; then
    echo "✅ Server started successfully"
    echo "   PID: $(cat server.pid)"
    echo "   URL: http://localhost:5000"
    echo "   Logs: tail -f server.log"
    echo "   Stop: ./stop.sh"
else
    echo "❌ Server failed to start"
    cat server.log
    exit 1
fi
BGSTARTEOF
chmod +x start-background.sh

# Stop script
cat > stop.sh << 'STOPEOF'
#!/bin/bash
cd "$(dirname "$0")"

if [[ -f server.pid ]]; then
    PID=$(cat server.pid)
    if ps -p $PID > /dev/null 2>&1; then
        kill $PID
        rm server.pid
        echo "✅ Server stopped (PID: $PID)"
    else
        rm server.pid
        echo "Server was not running"
    fi
else
    echo "No server.pid file found"
fi
STOPEOF
chmod +x stop.sh

# Create systemd service file
cat > aws-infra-optimizer.service << SERVICEEOF
[Unit]
Description=AWS Infrastructure Optimizer Local Server
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$(pwd)
ExecStart=$(pwd)/venv/bin/python3 $(pwd)/local_server.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICEEOF

echo -e "  ${GREEN}✓${NC} Startup scripts created"

# Create .gitignore for local files
cat >> .gitignore << 'GITIGNOREEOF'

# Local installation files
venv/
server.pid
server.log
*.service
GITIGNOREEOF

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ Local Installation Complete!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${YELLOW}Quick Start:${NC}"
echo "  ./start.sh                  # Start server (foreground)"
echo "  ./start-background.sh       # Start server (background)"
echo "  ./stop.sh                   # Stop background server"
echo ""
echo -e "${YELLOW}Then open in browser:${NC}"
echo "  http://localhost:5000"
echo ""
echo -e "${YELLOW}Run as System Service (optional):${NC}"
echo "  sudo cp aws-infra-optimizer.service /etc/systemd/system/"
echo "  sudo systemctl enable aws-infra-optimizer"
echo "  sudo systemctl start aws-infra-optimizer"
echo ""
echo -e "${YELLOW}AWS Authentication:${NC}"
echo "  Uses AWS CLI credentials (~/.aws/credentials)"
echo "  Configure with: aws configure"
echo "  Or set AWS_PROFILE environment variable"
echo ""
echo -e "${CYAN}Note: This local version cannot use cross-account IAM roles.${NC}"
echo -e "${CYAN}To scan other accounts, configure separate AWS CLI profiles.${NC}"
echo ""
