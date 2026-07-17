# CostOptimizer360

Automated infrastructure optimization scanner that analyzes your AWS resources and generates Word reports with actionable recommendations to reduce costs and improve efficiency.

## Features

- **Broad Multi-Service Scanning**: EC2, EBS volumes, EBS snapshots, stopped-EC2 EBS waste, RDS, Lambda, Elastic IPs / public IPv4, NAT gateways, load balancers (ALB/NLB/GWLB/Classic), S3, DynamoDB
- **Rate optimization**: Savings Plans purchase recommendations + RI/Savings Plans coverage & utilization (via Cost Explorer)
- **Interactive dashboard**: In-browser results dashboard with KPI cards, charts, and a filterable/sortable/searchable recommendations table with drill-down remediation snippets
- **Accurate metrics & predictions**: Live AWS Price List pricing for every service (OS/tenancy/license-aware EC2 & RDS), cost forecast + month-to-date spend, effort/risk/priority and quick-win scoring on every recommendation
- **AWS Compute Optimizer**: Uses AWS's own ranked recommendation and `savingsOpportunity` (including after-discount savings) when enrolled, with CloudWatch fallback
- **Multiple export formats**: Word (.docx), Excel (.xlsx, multi-sheet), self-contained HTML dashboard, JSON, and CSV
- **Dual Authentication**: Cross-account IAM Role (with ExternalId) or AWS credentials
- **Two deployment modes**: Serverless AWS (Lambda Function URL + S3) or local Flask server

### Accuracy improvements (v2)

This release fixes several correctness issues and makes savings numbers defensible:

- **Correct Compute Optimizer option selection** (previously the code picked the *largest* / least-saving option); now uses AWS's `rank`, `performanceRisk`, and `savingsOpportunity`.
- **OS/tenancy/license-aware EC2 & RDS pricing** (previously everything was priced as Linux/Shared, understating Windows/RHEL/SQL by ~2x).
- **Live DynamoDB & NAT gateway pricing** from the Price List API (previously hardcoded), plus a fix to the DynamoDB consumed-capacity unit math.
- **gp2→gp3** sizing now matches gp2's baseline IOPS/throughput so savings aren't overstated for large volumes.
- **Relative RDS memory-pressure** threshold instead of a flat 500 MB.
- **Cross-account role assumption fixed** (ExternalId is now passed; the trust policy and role names are consistent).
- **Waste-elimination savings and Savings Plans (rate) savings are reported separately** to avoid double counting.

## Architecture

```
┌─────────────┐      ┌──────────────────┐      ┌─────────────────┐
│   Browser   │─────▶│  Lambda Function │─────▶│ Lambda Function │
│  (S3 Site + │      │  URL (HTTPS)     │      │  (Python 3.11)  │
│  dashboard) │◀─────│                  │◀─────│                 │
└─────────────┘      └──────────────────┘      └─────────────────┘
                                                        │
                                                        ▼
                                    ┌────────────────────────────────┐
                                    │   AWS Services (Read-Only)     │
                                    │  • Compute Optimizer / Cost    │
                                    │    Optimization Hub            │
                                    │  • Cost Explorer (coverage,    │
                                    │    forecast, purchase recs)    │
                                    │  • CloudWatch • Price List     │
                                    │  • EC2/EBS/RDS/Lambda/ELB/S3/  │
                                    │    DynamoDB/NAT (describe)      │
                                    └────────────────────────────────┘
```

The browser also renders an interactive results dashboard (KPIs, charts, filterable
recommendations table) from the JSON the function returns, in addition to the
downloadable report.

## Recommendations Logic

### EC2 Instances

**Data Sources:**
1. **AWS Compute Optimizer** (Primary): ML-based recommendations using 14+ days of metrics
2. **CloudWatch Metrics** (Fallback): CPU utilization analysis

**Criteria:**
- Average CPU < 10% and Max CPU < 30% over 14 days → Downsize recommendation
- Compute Optimizer "Overprovisioned" finding → Specific instance type recommendation
- Excludes stopped instances and Auto Scaling groups

**Accuracy Measures:**
- Uses p99 metrics to avoid false positives from burst workloads
- Considers instance family compatibility
- Accounts for EBS-optimized costs

### EBS Volumes

**Recommendations:**
1. **Unattached Volumes**: Immediate cost savings by deletion
2. **gp2 → gp3 Migration**: 20% cost reduction with better performance

**Cost Calculation:**
- Regional pricing per GB-month
- Includes IOPS and throughput costs for provisioned volumes

### RDS Instances

**Criteria:**
- Average CPU < 20% AND Average Connections < 5 over 14 days
- Recommends one instance class smaller

**Considerations:**
- Multi-AZ configurations
- Read replicas
- Reserved instance commitments

### Lambda Functions

**Criteria:**
- Memory > 512 MB AND Average Duration < 1 second
- Recommends 50% memory reduction

**Cost Calculation:**
- GB-seconds pricing: $0.0000166667 per GB-second
- Request pricing: $0.20 per 1M requests
- Only recommends if savings > $1/month

### Elastic IPs

**Simple Check:**
- Unattached EIPs cost $3.60/month ($0.005/hour)
- Immediate savings by release

## Deployment Options

### Option 1: AWS Cloud Deployment (Recommended for Production)

**Serverless, scalable, supports cross-account roles**

```bash
./deploy.sh
# Choose option 1 (AWS Cloud Deployment)
```

**Features:**
- Web-based UI hosted on S3
- Cross-account IAM role support
- AWS credentials authentication
- Shareable frontend URL

**Requirements:**
- AWS CLI configured with admin permissions
- Ability to create CloudFormation stacks, Lambda, S3, API Gateway, IAM roles
- Costs ~$1-2/month

### Option 2: Local Installation (Linux/WSL)

**Full web interface running locally on your machine**

```bash
./deploy.sh
# Choose option 2 (Local Installation)
```

Or directly:

```bash
cd local
./install.sh
```

**Features:**
- Same web UI as AWS Cloud deployment
- Runs on http://localhost:5000
- Start/stop with simple commands: `serve-infraoptimizer` / `stop-infraoptimizer`
- Auto-start on system boot (via systemd)
- Enter AWS credentials directly or use AWS CLI profiles

**Requirements:**
- Linux or WSL
- Python 3.8+
- AWS CLI configured with valid credentials
- Free (no AWS infrastructure costs)

**Limitations:**
- No cross-account IAM roles (use separate AWS CLI profiles per account)
- Single user
- No high availability

### Local Web Server Usage

#### Starting the Server

```bash
# Start the web server (runs in background, auto-starts on boot)
./local/serve-infraoptimizer
```

This will:
- Start the server on http://localhost:5000
- Run in the background
- Configure auto-start on system boot (via systemd)

#### Stopping the Server

```bash
# Stop the web server and disable auto-start
./local/stop-infraoptimizer
```

This will:
- Stop the running server
- Disable auto-start on boot
- Clean up log files

#### Server Management

| Command | Description |
|---------|-------------|
| `./local/serve-infraoptimizer` | Start server, enable auto-start |
| `./local/stop-infraoptimizer` | Stop server, disable auto-start |

#### Web Interface

Once started, access the web interface at:
- **Frontend**: http://localhost:5000
- **API**: http://localhost:5000/api/generate

Choose between:
- **AWS CLI Profile**: Select a profile from ~/.aws/credentials
- **Direct Credentials**: Enter AWS access keys manually

---

## AWS Deployment (Detailed)

### Prerequisites

- AWS CLI configured with appropriate credentials
- Permissions to create CloudFormation stacks, Lambda, S3, API Gateway, IAM roles
- Python 3.11+ (for local testing)

### Quick Deploy

```bash
cd aws-infra-optimizer
./deploy.sh
```

The script will:
1. Create Lambda deployment package
2. Build python-docx layer
3. Create S3 bucket for artifacts
4. Deploy CloudFormation stack
5. Upload frontend with API endpoint
6. Output frontend URL

### Manual Deployment

```bash
# 1. Package Lambda function
cd lambda
pip install -r requirements.txt -t package/
cd package && zip -r ../lambda-package.zip .
cd .. && zip -g lambda-package.zip lambda_function.py

# 2. Create Lambda layer
mkdir -p layers/python/lib/python3.11/site-packages
pip install python-docx -t layers/python/lib/python3.11/site-packages/
cd layers && zip -r python-docx-layer.zip python

# 3. Deploy CloudFormation
aws cloudformation deploy \
    --template-file cloudformation.yaml \
    --stack-name aws-infra-optimizer \
    --parameter-overrides BucketName=your-unique-bucket-name \
    --capabilities CAPABILITY_NAMED_IAM \
    --region us-east-1

# 4. Update Lambda code
aws lambda update-function-code \
    --function-name InfraOptimizerFunction \
    --zip-file fileb://lambda/lambda-package.zip

# 5. Upload frontend
aws s3 cp frontend/index.html s3://your-bucket-name/index.html
```

## Cross-Account Access

To scan resources in other AWS accounts, deploy a read-only role in each target account.

### 1. Deploy Role in Target Account

```bash
aws cloudformation deploy \
    --template-file target-account-role.yaml \
    --stack-name costoptimizer360-role \
    --parameter-overrides TrustedAccountId=<LAMBDA_ACCOUNT_ID> ExternalId=<YOUR_EXTERNAL_ID> \
    --capabilities CAPABILITY_NAMED_IAM \
    --region us-east-1
```

- `TrustedAccountId` is the account where the CostOptimizer360 Lambda is deployed. The role trusts that account's `CostOptimizer360LambdaExecutionRole`.
- `ExternalId` defaults to `CostOptimizer360` and **must match** the Lambda's `EXTERNAL_ID` environment variable (or the `externalId` supplied in the request). Use a unique value per tenant for stronger confused-deputy protection.

### 2. Get Role ARN

```bash
aws cloudformation describe-stacks \
    --stack-name costoptimizer360-role \
    --query "Stacks[0].Outputs[?OutputKey=='RoleArn'].OutputValue" \
    --output text
```

### 3. Use in Frontend

Enter the Role ARN in the "IAM Role" tab of the web interface. If you set a custom `ExternalId`, configure the Lambda's `EXTERNAL_ID` environment variable to the same value.

## Usage

1. **Open Frontend URL** (from deployment output)

2. **Enter Client Name** (for report filename)

3. **Select Services to Scan**
   - EC2 Instances
   - EBS Volumes
   - RDS Databases
   - Lambda Functions
   - Elastic IPs

4. **Choose Region** (where resources are located)

5. **Select Authentication Method**
   - **IAM Role**: For cross-account access (recommended)
   - **AWS Credentials**: For direct access

6. **Generate Report** (takes 1-2 minutes)

7. **Download Word Document** with recommendations

## Report Structure

```
AWS Infrastructure Optimization Report
├── Executive Summary
│   ├── Total Potential Monthly Savings
│   ├── High Priority Recommendations
│   └── Medium Priority Recommendations
│
├── EC2 Instance Recommendations
│   └── Table: Instance ID, Current Type, Recommended, Costs, Savings, Reason
│
├── EBS Volume Recommendations
│   └── Table: Volume ID, Size, Type, Issue, Recommendation, Savings
│
├── RDS Instance Recommendations
│   └── Table: DB ID, Current Class, Recommended, Costs, Savings, Reason
│
├── Lambda Function Recommendations
│   └── Table: Function Name, Memory, Duration, Costs, Savings
│
├── Elastic IP Recommendations
│   └── Table: IP Address, Status, Cost, Recommendation
│
└── Implementation Notes
    ├── Testing guidelines
    ├── Reserved instance considerations
    └── Monitoring recommendations
```

## Permissions Required

### Lambda Execution Role (Deployed Automatically)

```yaml
- compute-optimizer:GetEC2InstanceRecommendations
- compute-optimizer:GetEBSVolumeRecommendations
- compute-optimizer:GetLambdaFunctionRecommendations
- ec2:DescribeInstances
- ec2:DescribeVolumes
- ec2:DescribeAddresses
- rds:DescribeDBInstances
- lambda:ListFunctions
- lambda:GetFunction
- cloudwatch:GetMetricStatistics
- sts:AssumeRole
```

### Cross-Account Role (Target Accounts)

Same permissions as above, but with trust relationship to Lambda account.

## Enabling AWS Compute Optimizer

For best recommendations, enable Compute Optimizer:

```bash
aws compute-optimizer update-enrollment-status \
    --status Active \
    --region us-east-1
```

**Note:** Requires 14 days of data collection before recommendations are available.

## Cost Considerations

### Deployment Costs
- **Lambda**: ~$0.20 per 1000 scans (5-minute execution)
- **API Gateway**: ~$1 per million requests
- **S3**: Minimal (static hosting)
- **CloudWatch Logs**: ~$0.50/GB ingested

### API Costs (Per Scan)
- **Compute Optimizer**: Free
- **CloudWatch GetMetricStatistics**: $0.01 per 1000 requests
- **EC2/RDS Describe APIs**: Free

**Estimated Cost**: $5-20/month for regular usage

## Troubleshooting

### "Compute Optimizer not available"

**Cause**: Compute Optimizer not enabled or insufficient data

**Solution**:
1. Enable Compute Optimizer (see above)
2. Wait 14 days for data collection
3. Scanner will use CloudWatch metrics as fallback

### "Insufficient permissions"

**Cause**: Lambda role or cross-account role missing permissions

**Solution**:
1. Check CloudFormation stack deployed successfully
2. Verify IAM role policies
3. For cross-account, ensure trust relationship is correct

### "No recommendations found"

**Possible Reasons**:
1. Resources are already optimized
2. Insufficient CloudWatch data (< 14 days)
3. Resources are in different region than selected

**Solution**:
- Check resources exist in selected region
- Verify CloudWatch metrics are being collected
- Try scanning different services

### "Lambda timeout"

**Cause**: Too many resources or slow API responses

**Solution**:
1. Increase Lambda timeout in CloudFormation (default: 300s)
2. Scan fewer services at once
3. Check CloudWatch Logs for specific errors

## Accuracy & Limitations

### High Accuracy
- ✅ Compute Optimizer recommendations (ML-based)
- ✅ Unattached EBS volumes and EIPs
- ✅ gp2 → gp3 migrations

### Medium Accuracy
- ⚠️ CloudWatch-based EC2 rightsizing (may miss burst patterns)
- ⚠️ RDS rightsizing (doesn't account for query complexity)
- ⚠️ Lambda memory optimization (assumes consistent workload)

### Not Considered
- ❌ Spot Instance opportunities
- ❌ Application-specific requirements
- ❌ Compliance and regulatory constraints
- ❌ Business criticality of resources
- ❌ Kubernetes / EKS pod-level cost allocation

> Reserved Instances and Savings Plans **are** now considered: coverage/utilization is read from Cost Explorer, Compute Optimizer's after-discount savings are used when available, and Savings Plans purchase recommendations are surfaced separately from waste-elimination savings.

**Always test recommendations in non-production environments first.**

## Pricing Data

All pricing is fetched live from the **AWS Price List API** (`pricing:GetProducts`) and cached in-memory for 1 hour:

- **EC2**: on-demand hourly price, OS/tenancy/preinstalled-software aware (Linux, RHEL, SUSE, Windows, SQL Server editions; Shared/Dedicated/Host).
- **RDS**: on-demand price by engine and deployment option (Single-AZ / Multi-AZ).
- **EBS**: per-GB-month plus provisioned IOPS (io1/io2) and gp3 IOPS/throughput beyond the free baseline.
- **Lambda**: GB-second and per-request pricing.
- **Elastic IP / public IPv4**: idle-address hourly price (all public IPv4 is billed since Feb 1 2024).
- **DynamoDB & NAT Gateway**: fetched from the Price List API, with current published us-east-1 rates as a graceful fallback if a lookup fails (so a recommendation is never dropped).

When AWS Compute Optimizer is enrolled, its own `savingsOpportunity` / `savingsOpportunityAfterDiscounts` estimates are preferred for rightsizing so numbers match the AWS console.

## Security Best Practices

> **Important — public endpoint:** The default CloudFormation deploys a Lambda **Function URL with `AuthType: NONE`** (publicly invokable). This is convenient for a quick internal/demo deployment, but for any shared or production use you should place it behind authentication (Function URL `AWS_IAM` auth, or API Gateway + Cognito/OIDC) and a WAF, and restrict CORS to your frontend origin. Prefer the **cross-account IAM role** flow over pasting long-lived access keys into the form.

1. **Use IAM Roles with an ExternalId** instead of long-lived credentials whenever possible. The execution role's `sts:AssumeRole` is scoped to `role/CostOptimizer360CrossAccountRole` only.
2. **Use a unique ExternalId per tenant** (set the Lambda `EXTERNAL_ID` env var and the target role parameter to match).
3. **Rotate credentials** if using access keys; they are used only for the request and never stored.
4. **Enable CloudTrail** to audit API calls.
5. **Least privilege**: the deployed policy grants only read/describe, pricing, Cost Explorer, and Compute Optimizer actions.
6. **Restrict the frontend/API** to known origins/IPs where possible.

## Cleanup

To remove all resources:

```bash
# Delete CloudFormation stack
aws cloudformation delete-stack --stack-name aws-infra-optimizer

# Delete S3 bucket (after emptying)
aws s3 rm s3://your-bucket-name --recursive
aws s3 rb s3://your-bucket-name

# Delete cross-account roles in target accounts
aws cloudformation delete-stack --stack-name infra-optimizer-role
```

## Contributing

Contributions welcome! Areas for improvement:

1. **More Services**: S3, DynamoDB, ElastiCache, Redshift
2. **Better Pricing**: Integration with AWS Price List API
3. **Trend Analysis**: Historical cost tracking
4. **Automated Actions**: Auto-apply safe recommendations
5. **Notifications**: SNS/Email alerts for high-value recommendations

## License

MIT License - See LICENSE file for details

## Support

For issues or questions:
1. Check CloudWatch Logs for Lambda errors
2. Review IAM permissions
3. Verify AWS Compute Optimizer is enabled
4. Open an issue on GitHub

## Changelog

### v2.0.0 (2026-07-17)
- **Accuracy**: fixed inverted Compute Optimizer option selection; OS/tenancy/license-aware EC2 & RDS pricing; live DynamoDB & NAT pricing; DynamoDB consumed-capacity unit fix; gp2→gp3 IOPS/throughput-aware savings; relative RDS memory threshold.
- **Cross-account fix**: ExternalId is now passed on AssumeRole; role names/trust policy made consistent; `sts:AssumeRole` scoped.
- **New checks**: EBS snapshots (orphaned/old), idle load balancers (ALB/NLB/GWLB/Classic), public IPv4 accounting, Savings Plans purchase recommendations, RI/SP coverage & utilization via Cost Explorer, cost forecast + month-to-date spend.
- **Interactive dashboard** in the browser (KPIs, charts, filterable/sortable table with remediation snippets).
- **New exports**: Excel (.xlsx) and self-contained HTML dashboard, alongside Word/JSON/CSV.
- **Prioritization**: every recommendation now carries effort, risk, priority, quick-win flag, annualized savings, savings basis, and a remediation snippet.
- **Reports**: added Top Quick Wins, methodology/basis, forecast, and sections for the new services.
- **Security/least-privilege**: refreshed IAM policies; documented public-endpoint hardening.

### v1.0.0 (2025-12-30)
- Initial release
- EC2, EBS, RDS, Lambda, EIP scanning
- Compute Optimizer integration
- Word report generation
- Cross-account support
- Web-based interface
