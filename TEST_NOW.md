# 🧪 Test Locally in 3 Steps

## Step 1: Setup (30 seconds)

```bash
cd aws-infra-optimizer
./setup_test.sh
```

This creates a virtual environment and installs dependencies.

## Step 2: Activate Environment

```bash
source venv/bin/activate
```

## Step 3: Run Test

```bash
python3 test_local.py
```

Choose option **2** for mock data (no AWS needed).

---

## What You'll Get

A Word document like this:

```
Test-Client-InfraOptimization-20251230.docx
```

Open it to see:
- Executive summary with total savings
- EC2 rightsizing recommendations
- EBS volume optimizations
- RDS database recommendations
- Lambda memory optimizations
- Elastic IP waste detection

---

## Example Output

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

---

## Test with Real AWS (Optional)

If you want to scan your actual AWS infrastructure:

```bash
# Configure AWS credentials
aws configure

# Run test
python3 test_local.py
# Choose option 1
```

This will:
- Connect to your AWS account
- Scan EC2, EBS, RDS, Lambda, EIP
- Generate real recommendations
- Take 1-2 minutes

---

## Troubleshooting

### "python3: command not found"
Install Python 3:
```bash
sudo apt install python3 python3-venv
```

### "Permission denied: ./setup_test.sh"
```bash
chmod +x setup_test.sh
./setup_test.sh
```

### Want to test with real AWS but no credentials?
```bash
export AWS_ACCESS_KEY_ID="your-key"
export AWS_SECRET_ACCESS_KEY="your-secret"
export AWS_REGION="us-east-1"
```

---

## What's Next?

After testing locally:

1. ✅ Review the generated Word document
2. ✅ Verify the report format looks good
3. ✅ Check recommendations make sense
4. 🚀 Deploy to AWS: `./deploy.sh`

---

## Quick Commands

```bash
# Setup
./setup_test.sh
source venv/bin/activate

# Test with mock data
python3 test_local.py  # Choose 2

# Test with real AWS
python3 test_local.py  # Choose 1

# Cleanup
deactivate
rm -rf venv *.docx
```

---

**Ready? Run `./setup_test.sh` now!** 🚀
