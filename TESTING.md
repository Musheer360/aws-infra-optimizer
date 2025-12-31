# Local Testing Guide

## Quick Start

### Option 1: Test with Mock Data (No AWS Needed)

```bash
# Install dependencies
pip install -r requirements-local.txt

# Run test
python3 test_local.py
# Choose option 2 (Mock data)
```

This generates a sample Word document showing what the report looks like, using fake data.

### Option 2: Test with Real AWS Account

```bash
# Configure AWS credentials
aws configure
# OR set environment variables:
export AWS_ACCESS_KEY_ID="your-key"
export AWS_SECRET_ACCESS_KEY="your-secret"
export AWS_REGION="us-east-1"

# Install dependencies
pip install -r requirements-local.txt

# Run test
python3 test_local.py
# Choose option 1 (Real AWS)
```

This scans your actual AWS infrastructure and generates a real report.

## What Gets Tested

### Mock Mode
- ✅ Word document generation
- ✅ Table formatting and styling
- ✅ Report structure
- ✅ Cost calculations
- ❌ AWS API calls (skipped)

### Real AWS Mode
- ✅ AWS API authentication
- ✅ EC2, EBS, RDS, Lambda, EIP scanning
- ✅ Compute Optimizer integration
- ✅ CloudWatch metrics retrieval
- ✅ Complete end-to-end flow

## Expected Output

### Mock Mode
```
🧪 AWS Infrastructure Optimizer - Local Test

Choose test mode:
1. Test with REAL AWS credentials
2. Test with MOCK data
3. Run both tests

Enter choice (1/2/3): 2

============================================================
Testing with MOCK data (no AWS credentials needed)
============================================================

📊 Mock Data Summary:
   EC2 Recommendations: 2
   EBS Recommendations: 2
   RDS Recommendations: 1
   Lambda Recommendations: 1
   EIP Recommendations: 1
   Total Potential Savings: $235.39/month

🔄 Generating Word document...

✅ SUCCESS! Mock report generated: Test-Client-InfraOptimization-20251230.docx
   File size: 45,231 bytes

   Open the file to see the report format!
```

### Real AWS Mode
```
============================================================
Testing with REAL AWS credentials
============================================================

✓ Using AWS credentials from environment
  Region: us-east-1

🔄 Scanning AWS infrastructure...
   This will take 1-2 minutes...

✅ SUCCESS! Report generated: Test-Client-InfraOptimization-20251230.docx
   File size: 52,847 bytes

   Open the file to see recommendations!
```

## Troubleshooting

### "ModuleNotFoundError: No module named 'docx'"
```bash
pip install python-docx
```

### "Unable to locate credentials"
```bash
# Option 1: Configure AWS CLI
aws configure

# Option 2: Set environment variables
export AWS_ACCESS_KEY_ID="your-key"
export AWS_SECRET_ACCESS_KEY="your-secret"

# Option 3: Use mock mode (no credentials needed)
python3 test_local.py
# Choose option 2
```

### "Access Denied" errors
Your AWS credentials need these permissions:
- `compute-optimizer:Get*`
- `ec2:Describe*`
- `rds:Describe*`
- `lambda:List*`
- `cloudwatch:GetMetricStatistics`

### "Compute Optimizer not available"
This is normal! The script falls back to CloudWatch metrics. To enable Compute Optimizer:
```bash
aws compute-optimizer update-enrollment-status --status Active
```

## What's Different from Production?

### Local Testing
- Runs on your machine
- Uses your local AWS credentials
- Saves Word document to current directory
- No API Gateway or S3 involved

### Production Deployment
- Runs in AWS Lambda
- Uses Lambda execution role
- Returns base64-encoded document via API
- Frontend hosted on S3

## Next Steps

After successful local testing:

1. **Review the generated Word document**
   - Check report format
   - Verify recommendations make sense
   - Validate cost calculations

2. **Test with different AWS accounts**
   - Development account first
   - Then staging/production

3. **Deploy to AWS**
   ```bash
   ./deploy.sh
   ```

4. **Test the web interface**
   - Open the frontend URL
   - Generate reports via browser
   - Test cross-account access

## Files Generated

- `Test-Client-InfraOptimization-YYYYMMDD.docx` - The Word report
- No other files created

## Cleanup

```bash
# Remove generated reports
rm *.docx
```

## Advanced Testing

### Test Specific Services Only

Edit `test_local.py` and modify the services list:

```python
body = {
    "services": ["ec2", "ebs"],  # Only test EC2 and EBS
    ...
}
```

### Test Different Regions

```bash
export AWS_REGION="eu-west-1"
python3 test_local.py
```

### Test Cross-Account (Local)

```python
# In test_local.py, use role-based auth:
body = {
    "roleArn": "arn:aws:iam::123456789012:role/YourRole",
    ...
}
```

## Performance

- **Mock mode**: < 1 second
- **Real AWS mode**: 1-2 minutes (depends on number of resources)

## Cost

Local testing is **free** - you only pay for AWS API calls:
- Compute Optimizer: Free
- CloudWatch GetMetricStatistics: $0.01 per 1000 requests
- EC2/RDS Describe APIs: Free

**Typical cost per test: < $0.01**
