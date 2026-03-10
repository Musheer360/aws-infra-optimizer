# Local Deployment Guide

## Overview

Run AWS Infrastructure Optimizer on your local Linux/WSL machine without any AWS infrastructure costs.

## Architecture Comparison

### AWS Deployment
```
Browser → S3 → API Gateway → Lambda → AWS Services
```
- Serverless, scalable
- Cross-account roles supported
- Costs ~$1-2/month

### Local Deployment
```
Browser → Flask Server (localhost:5000) → AWS Services
```
- Runs on your machine
- Uses AWS CLI credentials only
- Free (no AWS infrastructure)
- No cross-account support

## Installation

### Quick Install

```bash
./install.sh
# Choose option 2 (Local Installation)
```

### Manual Install

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install flask python-docx boto3 flask-cors

# Start server
python3 local_server.py
```

## Usage

### Start Server

```bash
./start_local.sh
```

Server runs at: **http://localhost:5000**

### Configure AWS Credentials

The local server uses AWS CLI credentials:

```bash
aws configure
```

Or set environment variables:

```bash
export AWS_ACCESS_KEY_ID="your-key"
export AWS_SECRET_ACCESS_KEY="your-secret"
export AWS_REGION="us-east-1"
```

### Generate Report

1. Open http://localhost:5000 in browser
2. Enter client name
3. Select services to scan
4. Choose AWS region
5. Click "Generate Optimization Report"
6. Download Word document

## Run as System Service

### Install Service

```bash
sudo cp infra-optimizer.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable infra-optimizer
sudo systemctl start infra-optimizer
```

### Manage Service

```bash
# Check status
sudo systemctl status infra-optimizer

# View logs
sudo journalctl -u infra-optimizer -f

# Restart
sudo systemctl restart infra-optimizer

# Stop
sudo systemctl stop infra-optimizer
```

## Access from Other Machines

### Same Network

Server binds to `0.0.0.0:5000`, accessible from other machines:

```
http://YOUR_IP:5000
```

Find your IP:
```bash
hostname -I | awk '{print $1}'
```

### Firewall Configuration

```bash
# Ubuntu/Debian
sudo ufw allow 5000/tcp

# RHEL/CentOS
sudo firewall-cmd --add-port=5000/tcp --permanent
sudo firewall-cmd --reload
```

## Security Considerations

### Local Deployment

⚠️ **Important Security Notes:**

1. **No Authentication**: Local server has no built-in auth
2. **Network Exposure**: Accessible to anyone on your network
3. **AWS Credentials**: Uses your personal AWS credentials

### Recommended Security

#### Option 1: Localhost Only

Edit `local_server.py`:
```python
app.run(host='127.0.0.1', port=5000, debug=False)
```

#### Option 2: Add Basic Auth

```bash
pip install flask-httpauth
```

Edit `local_server.py`:
```python
from flask_httpauth import HTTPBasicAuth
auth = HTTPBasicAuth()

users = {
    "admin": "your-password"
}

@auth.verify_password
def verify_password(username, password):
    if username in users and users[username] == password:
        return username

@app.route('/')
@auth.login_required
def index():
    return send_from_directory('frontend', 'index-local.html')
```

#### Option 3: Use Reverse Proxy

```nginx
# /etc/nginx/sites-available/infra-optimizer
server {
    listen 80;
    server_name your-domain.com;
    
    auth_basic "Restricted";
    auth_basic_user_file /etc/nginx/.htpasswd;
    
    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Limitations vs AWS Deployment

### Not Supported in Local Mode

❌ **Cross-Account Roles**: Can only scan the account configured in AWS CLI
❌ **IAM Role Authentication**: Only AWS CLI credentials
❌ **Scalability**: Single-threaded Flask server
❌ **High Availability**: No redundancy
❌ **HTTPS**: HTTP only (unless behind reverse proxy)

### Supported Features

✅ **All Services**: EC2, EBS, RDS, Lambda, EIP
✅ **Compute Optimizer**: If enabled in your account
✅ **CloudWatch Metrics**: Full access
✅ **Word Reports**: Same format as AWS deployment
✅ **Multiple Regions**: Can scan any region

## Performance

### Resource Usage

- **Memory**: ~100-200 MB
- **CPU**: Minimal (spikes during scans)
- **Disk**: ~50 MB (dependencies)

### Scan Times

Same as AWS deployment:
- Small account (10-20 resources): 30-60 seconds
- Medium account (50-100 resources): 1-2 minutes
- Large account (200+ resources): 2-5 minutes

## Troubleshooting

### "Address already in use"

Port 5000 is taken:

```bash
# Find process
lsof -i :5000

# Kill it
kill -9 <PID>

# Or use different port
# Edit local_server.py: app.run(port=5001)
```

### "Unable to locate credentials"

AWS CLI not configured:

```bash
aws configure
# Enter your credentials
```

### "Permission denied"

```bash
chmod +x start_local.sh
chmod +x local_server.py
```

### "Module not found"

```bash
source venv/bin/activate
pip install flask python-docx boto3 flask-cors
```

### "Connection refused" from other machines

Check firewall:

```bash
sudo ufw status
sudo ufw allow 5000/tcp
```

## Upgrading

### Update Code

```bash
git pull  # If using git
./install.sh  # Choose option 2
```

### Update Dependencies

```bash
source venv/bin/activate
pip install --upgrade flask python-docx boto3 flask-cors
```

## Uninstall

### Remove Local Installation

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

## Comparison: When to Use Each

### Use AWS Deployment When:

✅ Need cross-account scanning
✅ Want serverless/scalable solution
✅ Multiple users accessing
✅ Need high availability
✅ Want HTTPS out of the box

### Use Local Deployment When:

✅ Single user/personal use
✅ Want zero AWS infrastructure costs
✅ Have a dedicated Linux machine
✅ Only need to scan one account
✅ Prefer local control

## Advanced Configuration

### Custom Port

Edit `local_server.py`:
```python
app.run(host='0.0.0.0', port=8080, debug=False)
```

### Enable Debug Mode

```python
app.run(host='0.0.0.0', port=5000, debug=True)
```

⚠️ **Never use debug mode in production!**

### Custom AWS Profile

```bash
export AWS_PROFILE=my-profile
./start_local.sh
```

### Environment Variables

Create `.env` file:
```bash
AWS_REGION=us-east-1
AWS_PROFILE=default
FLASK_PORT=5000
```

Load in `local_server.py`:
```python
from dotenv import load_dotenv
load_dotenv()
```

## Docker Deployment (Alternative)

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . .

RUN pip install flask python-docx boto3 flask-cors

EXPOSE 5000

CMD ["python3", "local_server.py"]
```

### Build and Run

```bash
docker build -t infra-optimizer .
docker run -p 5000:5000 \
    -e AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID \
    -e AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY \
    -e AWS_REGION=us-east-1 \
    infra-optimizer
```

## FAQ

### Q: Can I scan multiple AWS accounts?

**A:** Not directly. You need to switch AWS CLI profiles:

```bash
export AWS_PROFILE=account1
# Generate report

export AWS_PROFILE=account2
# Generate report
```

### Q: Is it secure to run on my machine?

**A:** Yes, if:
- Only accessible from localhost
- Or behind authentication
- AWS credentials properly secured

### Q: Can I run this on Windows?

**A:** Yes, via WSL (Windows Subsystem for Linux):
1. Install WSL: `wsl --install`
2. Run installer in WSL
3. Access from Windows browser: http://localhost:5000

### Q: How do I update to latest version?

**A:** Re-run installer:
```bash
./install.sh  # Choose option 2
```

### Q: Can I run both AWS and local deployments?

**A:** Yes! They're independent:
- AWS: https://your-s3-bucket.s3-website-region.amazonaws.com
- Local: http://localhost:5000

## Support

For issues:
1. Check logs: `sudo journalctl -u infra-optimizer -f`
2. Verify AWS credentials: `aws sts get-caller-identity`
3. Test connectivity: `curl http://localhost:5000`
4. Review TESTING.md for local testing
