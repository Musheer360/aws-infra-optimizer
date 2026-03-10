# 🚀 Universal Installer Guide

## One Command, Two Options

```bash
./install.sh
```

Choose your deployment:
- **Option 1**: AWS (serverless, cross-account, $1-2/month)
- **Option 2**: Local (free, single account, your machine)

---

## Option 1: AWS Deployment

### What Gets Installed

```
AWS Account
├── S3 Bucket (frontend hosting)
├── Lambda Function (optimization logic)
├── API Gateway (HTTP API)
├── IAM Roles (permissions)
└── CloudWatch Logs (monitoring)
```

### Installation Steps

```bash
./install.sh
# Choose: 1

# Installer will:
# 1. Check AWS CLI and credentials
# 2. Package Lambda function
# 3. Create Lambda layer (python-docx)
# 4. Deploy CloudFormation stack
# 5. Upload frontend to S3
# 6. Output URLs
```

### What You Get

```
Frontend URL: http://bucket-name.s3-website-region.amazonaws.com
API Endpoint: https://api-id.execute-api.region.amazonaws.com/prod/optimize
```

### Features

✅ Cross-account scanning (IAM roles)
✅ Dual authentication (Role + Credentials)
✅ Auto-scaling
✅ High availability
✅ HTTPS
✅ CloudWatch monitoring

### Cost

- **Monthly**: $1-2
- **Per Scan**: ~$0.01

---

## Option 2: Local Installation

### What Gets Installed

```
Your Machine
├── Python virtual environment
├── Flask web server
├── Local frontend (index-local.html)
├── Startup script (start_local.sh)
└── Systemd service (optional)
```

### Installation Steps

```bash
./install.sh
# Choose: 2

# Installer will:
# 1. Check Python and AWS CLI
# 2. Create virtual environment
# 3. Install dependencies (Flask, python-docx, boto3)
# 4. Generate local server script
# 5. Generate local frontend
# 6. Create startup script
# 7. Create systemd service file
```

### What You Get

```
Local Server: http://localhost:5000
Startup Script: ./start_local.sh
Service File: infra-optimizer.service
```

### Features

✅ Zero AWS infrastructure costs
✅ Complete local control
✅ Uses AWS CLI credentials
✅ Same scanning capabilities
✅ Can run as system service
✅ Docker support

### Cost

- **Monthly**: $0 (free)
- **Per Scan**: $0

### Limitations

❌ No cross-account roles
❌ AWS CLI credentials only
❌ Single user
❌ HTTP only (unless behind proxy)

---

## Quick Comparison

| Feature | AWS | Local |
|---------|-----|-------|
| **Setup** | 5-10 min | 2-3 min |
| **Cost** | $1-2/month | Free |
| **Cross-Account** | ✅ Yes | ❌ No |
| **Scalability** | Auto | Single |
| **Access** | Internet | Local/LAN |
| **Maintenance** | Minimal | Manual |

---

## After Installation

### AWS Deployment

```bash
# Open frontend URL in browser
# Example: http://infra-optimizer-123456789012-us-east-1.s3-website-us-east-1.amazonaws.com

# For cross-account access:
# 1. Deploy target-account-role.yaml in other accounts
# 2. Use Role ARN in frontend
```

### Local Deployment

```bash
# Start server
./start_local.sh

# Open browser
http://localhost:5000

# Or install as system service
sudo cp infra-optimizer.service /etc/systemd/system/
sudo systemctl enable infra-optimizer
sudo systemctl start infra-optimizer
```

---

## Edge Cases Handled

### AWS Deployment

✅ **No AWS credentials**: Installer checks and prompts
✅ **Bucket name conflict**: Uses account ID in name
✅ **Region mismatch**: Uses AWS_REGION or defaults to us-east-1
✅ **Existing stack**: Updates instead of creating
✅ **Permission errors**: Clear error messages
✅ **Lambda timeout**: Set to 5 minutes
✅ **CORS issues**: Properly configured

### Local Deployment

✅ **No Python**: Installer checks and provides install command
✅ **No AWS CLI**: Warning but continues (needed for scanning)
✅ **Port 5000 taken**: Error message with troubleshooting
✅ **Virtual env exists**: Reuses or recreates
✅ **Missing dependencies**: Auto-installs via pip
✅ **AWS credentials**: Uses CLI config or environment variables
✅ **Multiple regions**: Selectable in frontend

---

## Troubleshooting

### AWS Deployment Issues

**"AWS CLI not installed"**
```bash
# Install AWS CLI
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install
```

**"AWS credentials not configured"**
```bash
aws configure
# Enter your credentials
```

**"Stack creation failed"**
```bash
# Check CloudFormation console for details
aws cloudformation describe-stack-events --stack-name aws-infra-optimizer
```

### Local Deployment Issues

**"Python 3 not installed"**
```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip
```

**"Address already in use"**
```bash
# Find and kill process on port 5000
lsof -i :5000
kill -9 <PID>
```

**"Unable to locate credentials"**
```bash
# Configure AWS CLI
aws configure

# Or set environment variables
export AWS_ACCESS_KEY_ID="your-key"
export AWS_SECRET_ACCESS_KEY="your-secret"
```

---

## Advanced Usage

### Run Both Deployments

You can run both simultaneously:

```bash
# Deploy to AWS
./install.sh  # Choose 1

# Install locally
./install.sh  # Choose 2

# Now you have:
# - AWS: https://your-bucket.s3-website-region.amazonaws.com
# - Local: http://localhost:5000
```

### Custom Configuration

**AWS Deployment:**
```bash
# Use different region
export AWS_REGION=eu-west-1
./install.sh  # Choose 1
```

**Local Deployment:**
```bash
# Use different port
# Edit local_server.py after installation:
# app.run(host='0.0.0.0', port=8080)
```

### Docker Deployment (Local)

```bash
# After local installation
docker build -t infra-optimizer .
docker run -p 5000:5000 \
    -e AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID \
    -e AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY \
    infra-optimizer
```

---

## Uninstallation

### AWS Deployment

```bash
# Delete CloudFormation stack
aws cloudformation delete-stack --stack-name aws-infra-optimizer

# Delete S3 bucket (after emptying)
aws s3 rm s3://your-bucket-name --recursive
aws s3 rb s3://your-bucket-name
```

### Local Deployment

```bash
# Stop service (if installed)
sudo systemctl stop infra-optimizer
sudo systemctl disable infra-optimizer
sudo rm /etc/systemd/system/infra-optimizer.service

# Remove files
rm -rf venv
rm local_server.py start_local.sh infra-optimizer.service
rm frontend/index-local.html
```

---

## Security Best Practices

### AWS Deployment

1. ✅ Use IAM roles instead of credentials when possible
2. ✅ Enable CloudTrail for audit logs
3. ✅ Restrict S3 bucket access if needed
4. ✅ Use VPC endpoints for Lambda (optional)
5. ✅ Enable S3 bucket encryption

### Local Deployment

1. ✅ Run on localhost only (edit local_server.py)
2. ✅ Add authentication (Flask-HTTPAuth)
3. ✅ Use reverse proxy with HTTPS (nginx)
4. ✅ Firewall rules (ufw/firewalld)
5. ✅ Secure AWS credentials

---

## Getting Help

### Documentation

- **README.md**: Complete documentation
- **LOCAL_DEPLOYMENT.md**: Local setup details
- **DEPLOYMENT_COMPARISON.md**: Feature comparison
- **QUICKSTART.md**: AWS quick start
- **TESTING.md**: Local testing guide

### Logs

**AWS:**
```bash
# CloudWatch Logs
aws logs tail /aws/lambda/InfraOptimizerFunction --follow
```

**Local:**
```bash
# Systemd service logs
sudo journalctl -u infra-optimizer -f

# Or run in foreground
./start_local.sh
```

### Common Issues

1. Check AWS credentials: `aws sts get-caller-identity`
2. Verify permissions: Review IAM policies
3. Test connectivity: `curl http://localhost:5000` (local)
4. Review logs: CloudWatch (AWS) or journalctl (local)

---

## Next Steps

After installation:

1. ✅ **Test the installation**
   - Generate a test report
   - Verify recommendations
   - Check Word document format

2. ✅ **Enable Compute Optimizer** (optional but recommended)
   ```bash
   aws compute-optimizer update-enrollment-status --status Active
   ```
   Wait 14 days for ML recommendations

3. ✅ **Set up cross-account access** (AWS only)
   - Deploy target-account-role.yaml in other accounts
   - Use Role ARN in frontend

4. ✅ **Schedule regular scans**
   - Weekly for active accounts
   - Monthly for stable accounts

5. ✅ **Track savings**
   - Document implemented changes
   - Calculate actual savings
   - Report to stakeholders

---

## Support

For issues or questions:

1. Check documentation (README.md, LOCAL_DEPLOYMENT.md)
2. Review logs (CloudWatch or journalctl)
3. Verify AWS credentials and permissions
4. Test with mock data (test_local.py)
5. Open GitHub issue with details

---

**Ready to install? Run `./install.sh` now!** 🚀
