#!/bin/bash
set -e

echo ""
echo "=========================================="
echo "   CostOptimizer360 - Deployment Installer"
echo "=========================================="
echo ""
echo "Choose deployment mode:"
echo ""
echo "  1) AWS Cloud Deployment"
echo "     - Serverless: Lambda + API Gateway + S3 frontend"
echo "     - Requires AWS CLI configured with admin credentials"
echo ""
echo "  2) Local Installation (Linux/WSL)"
echo "     - Web interface on http://localhost:5000"
echo "     - No AWS infrastructure needed"
echo ""
read -rp "Select deployment mode (1 or 2): " DEPLOY_MODE

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

case $DEPLOY_MODE in
    2)
        echo ""
        if [ -f "$SCRIPT_DIR/local/install.sh" ]; then
            bash "$SCRIPT_DIR/local/install.sh"
        else
            echo "Error: local/install.sh not found"
            exit 1
        fi
        exit 0
        ;;
    1)
        ;;
    *)
        echo "Invalid option. Please run again and select 1 or 2."
        exit 1
        ;;
esac

# === AWS Cloud Deployment ===

STACK_NAME="costoptimizer360"
REGION="${AWS_REGION:-us-east-1}"

# Step 1: Deploy CloudFormation stack
echo "Deploying CloudFormation stack..."
aws cloudformation deploy \
    --template-file cloudformation.yaml \
    --stack-name $STACK_NAME \
    --capabilities CAPABILITY_NAMED_IAM \
    --region $REGION

# Get outputs
echo "Getting stack outputs..."
BUCKET_NAME=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --region $REGION \
    --query 'Stacks[0].Outputs[?OutputKey==`FrontendURL`].OutputValue' \
    --output text | sed 's|http://||' | sed 's|.s3-website.*||')

API_ENDPOINT=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --region $REGION \
    --query 'Stacks[0].Outputs[?OutputKey==`ApiEndpoint`].OutputValue' \
    --output text)

LAMBDA_NAME=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --region $REGION \
    --query 'Stacks[0].Outputs[?OutputKey==`LambdaFunctionName`].OutputValue' \
    --output text)

# Step 2: Package Lambda function
echo "Packaging Lambda function..."
cd lambda
pip install -r requirements.txt -t . > /dev/null 2>&1
zip -r ../lambda.zip . -x "*.pyc" -x "__pycache__/*" > /dev/null 2>&1
cd ..

# Step 3: Deploy Lambda code
echo "Deploying Lambda function..."
aws lambda update-function-code \
    --function-name $LAMBDA_NAME \
    --zip-file fileb://lambda.zip \
    --region $REGION \
    --no-cli-pager > /dev/null

# Step 4: Update frontend with API endpoint
echo "Updating frontend..."
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
sed "s|API_GATEWAY_URL_PLACEHOLDER|$API_ENDPOINT|g" frontend/index.html > frontend/index-deploy.html

# Step 5: Upload frontend to S3
echo "Uploading frontend to S3..."
aws s3 cp frontend/index-deploy.html s3://$BUCKET_NAME/index.html --region $REGION

# Cleanup
rm -f lambda.zip frontend/index-deploy.html

echo ""
echo "=== Deployment Complete ==="
echo "Frontend URL: http://$BUCKET_NAME.s3-website.$REGION.amazonaws.com"
echo "API Endpoint: $API_ENDPOINT"
echo "Account ID: $ACCOUNT_ID"
echo ""
echo "For cross-account access, deploy target-account-role.yaml in target accounts."
echo ""
