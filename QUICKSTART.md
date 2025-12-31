# Quick Start Guide

## 5-Minute Setup

### Step 1: Deploy Infrastructure
```bash
cd aws-infra-optimizer
./deploy.sh
```

**Output:**
```
Frontend URL: http://infra-optimizer-123456789012-us-east-1.s3-website-us-east-1.amazonaws.com
API Endpoint: https://abc123.execute-api.us-east-1.amazonaws.com/prod/optimize
```

### Step 2: Enable Compute Optimizer (Optional but Recommended)
```bash
aws compute-optimizer update-enrollment-status --status Active --region us-east-1
```

**Note:** Wait 14 days for data collection, or use CloudWatch fallback immediately.

### Step 3: Generate Your First Report

1. Open the Frontend URL in your browser
2. Enter a client name (e.g., "Production Account")
3. Select services to scan (all checked by default)
4. Choose your region
5. Select authentication:
   - **Same Account**: Use "AWS Credentials" tab
   - **Cross-Account**: Use "IAM Role" tab (see below)
6. Click "Generate Optimization Report"
7. Download the Word document

---

## Cross-Account Setup (Optional)

### Deploy Role in Target Account
```bash
aws cloudformation deploy \
    --template-file target-account-role.yaml \
    --stack-name infra-optimizer-role \
    --parameter-overrides TrustedAccountId=123456789012 \
    --capabilities CAPABILITY_NAMED_IAM \
    --region us-east-1
```

Replace `123456789012` with your Lambda account ID.

### Get Role ARN
```bash
aws cloudformation describe-stacks \
    --stack-name infra-optimizer-role \
    --query "Stacks[0].Outputs[?OutputKey=='RoleArn'].OutputValue" \
    --output text
```

### Use in Frontend
Copy the Role ARN and paste it in the "IAM Role" tab.

---

## What to Expect

### First Scan (Without Compute Optimizer)
- **EC2**: Basic CPU-based recommendations
- **EBS**: Unattached volumes and gp2→gp3 migrations
- **RDS**: Low utilization databases
- **Lambda**: Over-provisioned memory
- **EIP**: Unattached elastic IPs

**Typical Savings**: $50-500/month for small accounts

### After 14 Days (With Compute Optimizer)
- **EC2**: ML-based rightsizing with high confidence
- **Better accuracy**: Considers memory, network, disk I/O
- **More recommendations**: Catches subtle over-provisioning

**Typical Savings**: $200-2000/month for medium accounts

---

## Sample Report Output

```
AWS Infrastructure Optimization Report
Client: Production Account
Generated: 2025-12-30 08:52:00 UTC

Executive Summary
Total Potential Monthly Savings: $847.50
High Priority Recommendations: 12
Medium Priority Recommendations: 8

EC2 Instance Recommendations
┌──────────────┬──────────────┬──────────────┬──────────┬──────────┬─────────┐
│ Instance ID  │ Current Type │ Recommended  │ Current  │ New Cost │ Savings │
├──────────────┼──────────────┼──────────────┼──────────┼──────────┼─────────┤
│ i-abc123     │ m5.xlarge    │ m5.large     │ $140.16  │ $70.08   │ $70.08  │
│ i-def456     │ t3.medium    │ t3.small     │ $30.37   │ $15.18   │ $15.19  │
└──────────────┴──────────────┴──────────────┴──────────┴──────────┴─────────┘

EBS Volume Recommendations
┌──────────────┬──────┬──────┬────────────┬──────────────────────┬─────────┐
│ Volume ID    │ Size │ Type │ Issue      │ Recommendation       │ Savings │
├──────────────┼──────┼──────┼────────────┼──────────────────────┼─────────┤
│ vol-abc123   │ 100  │ gp2  │ Using gp2  │ Migrate to gp3       │ $2.00   │
│ vol-def456   │ 500  │ gp2  │ Unattached │ Delete if not needed │ $50.00  │
└──────────────┴──────┴──────┴────────────┴──────────────────────┴─────────┘

... (more sections)
```

---

## Common First-Time Issues

### Issue: "Compute Optimizer not available"
**Solution:** Normal for first scan. Scanner uses CloudWatch fallback. Enable Compute Optimizer for better recommendations.

### Issue: "No recommendations found"
**Possible Causes:**
- Resources are already optimized ✅
- Wrong region selected
- Insufficient CloudWatch data

**Solution:** Try different region or wait for more metrics data.

### Issue: "Access Denied"
**Cause:** Missing IAM permissions

**Solution:**
```bash
# Check Lambda role has required permissions
aws iam get-role-policy \
    --role-name InfraOptimizerLambdaRole \
    --policy-name InfraOptimizerPolicy
```

---

## Next Steps

### 1. Review Recommendations
- Focus on "High Confidence" items first
- Check "Unattached" resources (quick wins)
- Review gp2→gp3 migrations (safe changes)

### 2. Test Changes
- Start with development/test environments
- Monitor performance after changes
- Document results

### 3. Implement in Production
- Schedule maintenance window
- Have rollback plan ready
- Monitor closely after changes

### 4. Schedule Regular Scans
- Weekly for active accounts
- Monthly for stable accounts
- After major deployments

### 5. Track Savings
- Document implemented changes
- Calculate actual savings
- Report to stakeholders

---

## Cost of Running This Tool

### One-Time Setup
- CloudFormation: Free
- S3 bucket: ~$0.50/month
- Lambda deployment: Free

### Per Scan
- Lambda execution: ~$0.0002 (5 minutes @ 512MB)
- API Gateway: ~$0.000001
- CloudWatch API calls: ~$0.01

**Total per scan: ~$0.01**

**Monthly cost for 100 scans: ~$1-2**

---

## Tips for Maximum Savings

### 1. Scan All Regions
```bash
for region in us-east-1 us-west-2 eu-west-1; do
    echo "Scanning $region..."
    # Use frontend with different region
done
```

### 2. Scan Multiple Accounts
- Deploy cross-account roles in all accounts
- Scan each account separately
- Aggregate savings across organization

### 3. Focus on High-Impact Items
- Large EC2 instances (m5.4xlarge+)
- Unattached resources (immediate savings)
- RDS instances (typically expensive)

### 4. Automate Regular Scans
- Set up weekly Lambda trigger
- Email reports automatically
- Track savings over time

---

## Support

### Documentation
- **README.md**: Full documentation
- **RECOMMENDATIONS.md**: Detailed recommendation logic
- **This file**: Quick start guide

### Troubleshooting
1. Check CloudWatch Logs: `/aws/lambda/InfraOptimizerFunction`
2. Verify IAM permissions
3. Test with AWS CLI commands manually
4. Review CloudFormation stack events

### Getting Help
- Check CloudWatch Logs for errors
- Review IAM permissions
- Verify Compute Optimizer status
- Open GitHub issue with details

---

## Success Metrics

After implementing recommendations, track:

- **Cost Reduction**: Monthly AWS bill decrease
- **Resource Efficiency**: CPU/Memory utilization improvement
- **Performance**: Application response times
- **Availability**: Uptime and error rates

**Typical Results:**
- 15-30% cost reduction for over-provisioned accounts
- 5-10% for well-managed accounts
- 40%+ for accounts with many forgotten resources

---

## What's Next?

### Phase 2 Features (Future)
- S3 bucket optimization
- DynamoDB table analysis
- ElastiCache recommendations
- Redshift cluster optimization
- Cost trend analysis
- Automated implementation
- Slack/Email notifications

### Contribute
- Fork the repository
- Add new service scanners
- Improve pricing accuracy
- Add more recommendation logic
- Submit pull requests

---

**Ready to save money? Run `./deploy.sh` now!** 🚀
