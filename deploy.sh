#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo ""
echo "=========================================="
echo "   CostOptimizer360 - Deployment Installer"
echo "=========================================="
echo ""
echo "Choose deployment mode:"
echo ""
echo "  1) AWS Cloud Deployment"
echo "     - Deploys Lambda, API Gateway, S3 frontend"
echo "     - Supports cross-account IAM roles"
echo "     - Supports AWS credentials authentication"
echo "     - Requires AWS account with admin permissions"
echo ""
echo "  2) Local Installation (Linux/WSL)"
echo "     - Full web interface on your machine"
echo "     - Web server runs on http://localhost:5000"
echo "     - Start/stop with simple commands"
echo "     - Auto-start on boot option"
echo "     - No AWS infrastructure needed"
echo ""
read -rp "Select deployment mode (1 or 2): " DEPLOY_MODE

case $DEPLOY_MODE in
    1)
        echo ""
        echo "=== AWS Cloud Deployment Selected ==="
        ;;
    2)
        echo ""
        echo "=== Local Installation Selected ==="
        echo ""
        
        # Get the script directory
        SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        
        # Run local installer
        if [ -f "$SCRIPT_DIR/local/install.sh" ]; then
            bash "$SCRIPT_DIR/local/install.sh"
        else
            echo "Error: local/install.sh not found"
            exit 1
        fi
        exit 0
        ;;
    *)
        echo "Invalid option. Please run again and select 1 or 2."
        exit 1
        ;;
esac

echo -e "${GREEN}CostOptimizer360 - Cloud Deployment${NC}"
echo "========================================"

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo -e "${RED}Error: AWS CLI is not installed${NC}"
    exit 1
fi

# Get AWS account ID and region
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION=${AWS_REGION:-us-east-1}

echo -e "${YELLOW}Account ID:${NC} $ACCOUNT_ID"
echo -e "${YELLOW}Region:${NC} $REGION"
echo ""

# Generate unique bucket name
BUCKET_NAME="infra-optimizer-${ACCOUNT_ID}-${REGION}"
STACK_NAME="aws-infra-optimizer"

echo -e "${YELLOW}Step 1: Creating Lambda deployment package${NC}"
cd lambda
pip install -r requirements.txt -t package/ --quiet
cd package
zip -r ../lambda-package.zip . -q
cd ..
zip -g lambda-package.zip lambda_function.py -q
cd ..
echo -e "${GREEN}✓ Lambda package created${NC}"

echo ""
echo -e "${YELLOW}Step 2: Creating Lambda layer for python-docx${NC}"
mkdir -p layers/python/lib/python3.11/site-packages
pip install python-docx -t layers/python/lib/python3.11/site-packages/ --quiet
cd layers
zip -r python-docx-layer.zip python -q
cd ..
echo -e "${GREEN}✓ Lambda layer created${NC}"

echo ""
echo -e "${YELLOW}Step 3: Creating S3 bucket for deployment artifacts${NC}"
if aws s3 ls "s3://${BUCKET_NAME}" 2>&1 | grep -q 'NoSuchBucket'; then
    aws s3 mb "s3://${BUCKET_NAME}" --region "${REGION}"
    echo -e "${GREEN}✓ Bucket created: ${BUCKET_NAME}${NC}"
else
    echo -e "${GREEN}✓ Bucket already exists: ${BUCKET_NAME}${NC}"
fi

echo ""
echo -e "${YELLOW}Step 4: Uploading deployment artifacts${NC}"
aws s3 cp lambda/lambda-package.zip "s3://${BUCKET_NAME}/lambda-package.zip" --quiet
aws s3 cp layers/python-docx-layer.zip "s3://${BUCKET_NAME}/layers/python-docx-layer.zip" --quiet
echo -e "${GREEN}✓ Artifacts uploaded${NC}"

echo ""
echo -e "${YELLOW}Step 5: Deploying CloudFormation stack${NC}"
aws cloudformation deploy \
    --template-file cloudformation.yaml \
    --stack-name "${STACK_NAME}" \
    --parameter-overrides "BucketName=${BUCKET_NAME}" \
    --capabilities CAPABILITY_NAMED_IAM \
    --region "${REGION}"

echo -e "${GREEN}✓ CloudFormation stack deployed${NC}"

echo ""
echo -e "${YELLOW}Step 6: Updating Lambda function code${NC}"
FUNCTION_NAME=$(aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --query "Stacks[0].Outputs[?OutputKey=='LambdaRoleArn'].OutputValue" \
    --output text \
    --region "${REGION}" | cut -d'/' -f2 | sed 's/Role/Function/')

aws lambda update-function-code \
    --function-name InfraOptimizerFunction \
    --s3-bucket "${BUCKET_NAME}" \
    --s3-key lambda-package.zip \
    --region "${REGION}" \
    --no-cli-pager > /dev/null

echo -e "${GREEN}✓ Lambda function updated${NC}"

echo ""
echo -e "${YELLOW}Step 7: Getting API Gateway endpoint${NC}"
API_ENDPOINT=$(aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --query "Stacks[0].Outputs[?OutputKey=='ApiEndpoint'].OutputValue" \
    --output text \
    --region "${REGION}")

echo -e "${GREEN}✓ API Endpoint: ${API_ENDPOINT}${NC}"

echo ""
echo -e "${YELLOW}Step 8: Updating frontend with API endpoint${NC}"
sed "s|API_GATEWAY_URL_PLACEHOLDER|${API_ENDPOINT}|g" frontend/index.html > frontend/index-updated.html
aws s3 cp frontend/index-updated.html "s3://${BUCKET_NAME}/index.html" \
    --content-type "text/html" \
    --region "${REGION}" \
    --quiet
rm frontend/index-updated.html
echo -e "${GREEN}✓ Frontend uploaded${NC}"

echo ""
echo -e "${YELLOW}Step 9: Getting frontend URL${NC}"
FRONTEND_URL=$(aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --query "Stacks[0].Outputs[?OutputKey=='FrontendURL'].OutputValue" \
    --output text \
    --region "${REGION}")

echo -e "${GREEN}✓ Frontend URL: ${FRONTEND_URL}${NC}"

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Deployment Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${YELLOW}Frontend URL:${NC} ${FRONTEND_URL}"
echo -e "${YELLOW}API Endpoint:${NC} ${API_ENDPOINT}"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo "1. Open the frontend URL in your browser"
echo "2. For cross-account access, deploy target-account-role.yaml in target accounts"
echo "3. Enable AWS Compute Optimizer for best recommendations"
echo ""
echo -e "${YELLOW}Cleanup:${NC}"
rm -rf lambda/package lambda/lambda-package.zip layers/python layers/python-docx-layer.zip
echo -e "${GREEN}✓ Temporary files cleaned up${NC}"
