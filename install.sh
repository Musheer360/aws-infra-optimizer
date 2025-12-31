#!/bin/bash

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

clear
echo -e "${BLUE}"
cat << "EOF"
╔════════════════════════════════════════════════════════════════╗
║       AWS Infrastructure Optimizer - Universal Installer       ║
╚════════════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

echo -e "${YELLOW}Choose deployment type:${NC}"
echo ""
echo "  1) Deploy to AWS Account"
echo "     - Serverless (Lambda + API Gateway + S3)"
echo "     - Supports cross-account IAM roles"
echo "     - Costs ~\$1-2/month"
echo ""
echo "  2) Install on This Machine"
echo "     - Runs as web server on this machine"
echo "     - Uses AWS credentials directly"
echo "     - Free (no AWS infrastructure costs)"
echo ""
read -p "Enter choice (1 or 2): " DEPLOY_TYPE

if [[ "$DEPLOY_TYPE" == "1" ]]; then
    echo -e "\n${GREEN}═══ Deploying to AWS Account ═══${NC}\n"
    
    # Check AWS CLI
    if ! command -v aws &> /dev/null; then
        echo -e "${RED}Error: AWS CLI not installed${NC}"
        echo "Install: https://aws.amazon.com/cli/"
        exit 1
    fi
    
    # Get AWS info
    ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "")
    if [[ -z "$ACCOUNT_ID" ]]; then
        echo -e "${RED}Error: AWS credentials not configured${NC}"
        echo "Run: aws configure"
        exit 1
    fi
    
    REGION=${AWS_REGION:-us-east-1}
    echo -e "${YELLOW}AWS Account:${NC} $ACCOUNT_ID"
    echo -e "${YELLOW}Region:${NC} $REGION"
    echo ""
    
    read -p "Continue with AWS deployment? (y/n): " CONFIRM
    if [[ "$CONFIRM" != "y" ]]; then
        echo "Cancelled"
        exit 0
    fi
    
    # Run AWS deployment
    ./deploy.sh
    
elif [[ "$DEPLOY_TYPE" == "2" ]]; then
    echo -e "\n${GREEN}═══ Installing on This Machine ═══${NC}\n"
    
    # Check Python
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}Error: Python 3 not installed${NC}"
        echo "Install: sudo apt install python3 python3-venv python3-pip"
        exit 1
    fi
    
    # Check AWS CLI
    if ! command -v aws &> /dev/null; then
        echo -e "${YELLOW}Warning: AWS CLI not installed${NC}"
        echo "You'll need it to scan AWS resources"
        echo "Install: sudo apt install awscli"
        echo ""
        read -p "Continue anyway? (y/n): " CONFIRM
        if [[ "$CONFIRM" != "y" ]]; then
            exit 0
        fi
    fi
    
    echo -e "${YELLOW}Step 1:${NC} Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    
    echo -e "${YELLOW}Step 2:${NC} Installing Python dependencies..."
    pip install -q flask python-docx boto3 flask-cors
    
    echo -e "${YELLOW}Step 3:${NC} Creating local server..."
    cat > local_server.py << 'PYEOF'
#!/usr/bin/env python3
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

@app.route('/')
def index():
    return send_from_directory('frontend', 'index-local.html')

@app.route('/optimize', methods=['POST', 'OPTIONS'])
def optimize():
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.json
        
        # Import Lambda function
        from lambda_function import (
            scan_ec2_instances, scan_ebs_volumes, scan_rds_instances,
            scan_lambda_functions, scan_elastic_ips, generate_word_report
        )
        import boto3
        
        # Create session with AWS CLI credentials
        session = boto3.Session(region_name=data.get('region', 'us-east-1'))
        
        # Collect recommendations
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
        
        # Generate Word document
        doc = generate_word_report(
            recommendations,
            total_savings,
            data.get('clientName', 'Client')
        )
        
        # Save to BytesIO
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
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("\n" + "="*60)
    print("AWS Infrastructure Optimizer - Local Server")
    print("="*60)
    print("\nServer running at: http://localhost:5000")
    print("\nPress Ctrl+C to stop\n")
    app.run(host='0.0.0.0', port=5000, debug=False)
PYEOF
    
    chmod +x local_server.py
    
    echo -e "${YELLOW}Step 4:${NC} Creating local frontend..."
    cat > frontend/index-local.html << 'HTMLEOF'
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AWS Infrastructure Optimizer (Local)</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

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

        .subtitle {
            text-align: center;
            color: #666;
            margin-bottom: 30px;
            font-size: 14px;
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

        input[type="text"],
        select {
            width: 100%;
            padding: 12px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 14px;
            transition: border-color 0.3s;
        }

        input[type="text"]:focus,
        select:focus {
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

        .checkbox-item:hover {
            background: #e9ecef;
        }

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

        button:active {
            transform: translateY(0);
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

        .info {
            background: #e3f2fd;
            color: #1976d2;
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 20px;
            font-size: 13px;
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
        <p class="subtitle">Running locally - uses AWS CLI credentials</p>

        <div class="info">
            <strong>Local Mode:</strong> This uses your AWS CLI credentials. Run <code>aws configure</code> if not set up.
        </div>

        <form id="optimizerForm">
            <div class="form-group">
                <label>Client Name</label>
                <input type="text" id="clientName" placeholder="Enter client or account name" required>
            </div>

            <div class="form-group">
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
                    <option value="eu-west-1">EU (Ireland)</option>
                    <option value="eu-central-1">EU (Frankfurt)</option>
                    <option value="ap-southeast-1">Asia Pacific (Singapore)</option>
                    <option value="ap-southeast-2">Asia Pacific (Sydney)</option>
                    <option value="ap-northeast-1">Asia Pacific (Tokyo)</option>
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
        document.getElementById('optimizerForm').addEventListener('submit', async (e) => {
            e.preventDefault();

            const clientName = document.getElementById('clientName').value;
            const region = document.getElementById('region').value;
            
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
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        clientName,
                        region,
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
    </script>
</body>
</html>
HTMLEOF
    
    echo -e "${YELLOW}Step 5:${NC} Creating startup script..."
    cat > start_local.sh << 'STARTEOF'
#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
python3 local_server.py
STARTEOF
    
    chmod +x start_local.sh
    
    echo -e "${YELLOW}Step 6:${NC} Creating systemd service (optional)..."
    cat > infra-optimizer.service << SERVICEEOF
[Unit]
Description=AWS Infrastructure Optimizer Local Server
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$(pwd)
ExecStart=$(pwd)/start_local.sh
Restart=on-failure

[Install]
WantedBy=multi-user.target
SERVICEEOF
    
    echo ""
    echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}✅ Local Installation Complete!${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "${YELLOW}To start the server:${NC}"
    echo "  ./start_local.sh"
    echo ""
    echo -e "${YELLOW}Then open in browser:${NC}"
    echo "  http://localhost:5000"
    echo ""
    echo -e "${YELLOW}To run as system service (optional):${NC}"
    echo "  sudo cp infra-optimizer.service /etc/systemd/system/"
    echo "  sudo systemctl enable infra-optimizer"
    echo "  sudo systemctl start infra-optimizer"
    echo ""
    echo -e "${YELLOW}AWS Credentials:${NC}"
    echo "  Make sure AWS CLI is configured: aws configure"
    echo ""
    
else
    echo -e "${RED}Invalid choice${NC}"
    exit 1
fi
