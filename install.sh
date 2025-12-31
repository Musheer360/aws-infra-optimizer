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
║       AWS Infrastructure Optimizer - Universal Installer       ║
╚════════════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

echo -e "${YELLOW}Choose deployment type:${NC}"
echo ""
echo -e "  ${GREEN}1)${NC} Deploy to AWS Account (Serverless)"
echo "     • Lambda + API Gateway + S3"
echo "     • Supports cross-account IAM roles"
echo "     • Costs ~\$1-2/month"
echo "     • Accessible from anywhere"
echo ""
echo -e "  ${GREEN}2)${NC} Install Locally (Linux/WSL)"
echo "     • Runs as web server on this machine"
echo "     • Uses AWS CLI credentials directly"
echo "     • Free (no AWS infrastructure costs)"
echo "     • Supports multiple AWS profiles"
echo ""
read -p "Enter choice (1 or 2): " DEPLOY_TYPE

if [[ "$DEPLOY_TYPE" == "1" ]]; then
    echo ""
    echo -e "${GREEN}═══ AWS Deployment Selected ═══${NC}"
    echo ""
    
    # Check AWS CLI
    if ! command -v aws &> /dev/null; then
        echo -e "${RED}Error: AWS CLI not installed${NC}"
        echo ""
        echo "Install AWS CLI:"
        echo '  curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"'
        echo "  unzip awscliv2.zip && sudo ./aws/install"
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
    if [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]]; then
        echo "Cancelled"
        exit 0
    fi
    
    # Run AWS deployment
    ./deploy.sh
    
elif [[ "$DEPLOY_TYPE" == "2" ]]; then
    echo ""
    echo -e "${GREEN}═══ Local Installation Selected ═══${NC}"
    echo ""
    
    # Run local installation script
    ./install-local.sh
    
else
    echo -e "${RED}Invalid choice. Please enter 1 or 2.${NC}"
    exit 1
fi
