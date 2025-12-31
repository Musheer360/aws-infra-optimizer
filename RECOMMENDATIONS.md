# AWS Infrastructure Optimization - Recommendations Reference

## How Recommendations Are Generated

### 1. EC2 Instance Rightsizing

#### Primary Method: AWS Compute Optimizer
- **Data Source**: AWS Compute Optimizer ML analysis
- **Data Period**: Minimum 14 days of metrics
- **Metrics Analyzed**: CPU, Memory, Network, Disk I/O
- **Confidence**: High

**Criteria:**
- Finding = "Overprovisioned" → Recommend smaller instance
- Finding = "Underprovisioned" → Recommend larger instance (not implemented for safety)

**Example:**
```
Current: m5.xlarge (4 vCPU, 16 GB RAM)
CPU Avg: 15%, Memory Avg: 30%
Recommendation: m5.large (2 vCPU, 8 GB RAM)
Savings: $70/month
```

#### Fallback Method: CloudWatch Metrics
- **Data Source**: CloudWatch CPUUtilization metric
- **Data Period**: 14 days
- **Confidence**: Medium

**Criteria:**
- Average CPU < 10% AND Maximum CPU < 30%
- Recommend one size smaller in same family

**Limitations:**
- Doesn't consider memory utilization (unless CloudWatch agent installed)
- May miss burst workloads
- Doesn't account for network-intensive applications

---

### 2. EBS Volume Optimization

#### Unattached Volumes
- **Detection**: Volume state = "available"
- **Recommendation**: Delete if not needed
- **Confidence**: High
- **Savings**: Full volume cost

**Cost Calculation:**
```
gp2: $0.10/GB-month
gp3: $0.08/GB-month
io1/io2: $0.125/GB-month + IOPS cost
```

#### gp2 → gp3 Migration
- **Detection**: Volume type = "gp2"
- **Recommendation**: Migrate to gp3
- **Confidence**: High
- **Savings**: 20% cost reduction
- **Benefits**: Better performance (3000 IOPS baseline vs 3 IOPS/GB)

**Example:**
```
Volume: 500 GB gp2
Current Cost: $50/month
gp3 Cost: $40/month
Savings: $10/month
```

---

### 3. RDS Instance Rightsizing

#### CloudWatch-Based Analysis
- **Metrics**: CPUUtilization, DatabaseConnections
- **Data Period**: 14 days
- **Confidence**: Medium

**Criteria:**
- Average CPU < 20% AND Average Connections < 5
- Recommend one instance class smaller

**Example:**
```
Current: db.m5.large
CPU Avg: 12%, Connections Avg: 2
Recommendation: db.t3.large
Savings: $85/month
```

**Limitations:**
- Doesn't analyze query complexity
- Doesn't consider read replicas
- Doesn't account for peak traffic patterns
- Ignores storage I/O requirements

**Not Recommended For:**
- Production databases with variable load
- Databases with complex queries
- Multi-AZ configurations without testing

---

### 4. Lambda Function Optimization

#### Memory Over-Provisioning Detection
- **Metrics**: Duration, Invocations, Memory
- **Data Period**: 14 days
- **Confidence**: Medium

**Criteria:**
- Memory > 512 MB AND Average Duration < 1000ms
- Recommend 50% memory reduction
- Only if savings > $1/month

**Cost Calculation:**
```
Cost = (Memory_GB × Duration_seconds × Invocations × $0.0000166667) + (Invocations × $0.0000002)
```

**Example:**
```
Function: DataProcessor
Current: 1024 MB, 500ms avg, 100K invocations/month
Recommended: 512 MB
Current Cost: $8.50/month
New Cost: $4.50/month
Savings: $4/month
```

**Limitations:**
- Assumes consistent workload
- Doesn't account for cold starts
- May impact performance for CPU-bound functions

---

### 5. Elastic IP Optimization

#### Unattached EIP Detection
- **Detection**: EIP without associated InstanceId
- **Recommendation**: Release if not needed
- **Confidence**: High
- **Savings**: $3.60/month per EIP

**Cost:**
```
Attached EIP: Free
Unattached EIP: $0.005/hour = $3.60/month
```

**Common Reasons for Unattached EIPs:**
- Terminated instances
- Testing/development cleanup missed
- Reserved for future use

---

## Confidence Levels Explained

### High Confidence
- Based on AWS Compute Optimizer ML analysis
- Unattached resources (EBS, EIP)
- Clear cost savings with no performance impact (gp2→gp3)

**Action:** Safe to implement after basic testing

### Medium Confidence
- Based on CloudWatch metrics only
- Simplified analysis (CPU only, no memory)
- May not capture all usage patterns

**Action:** Test thoroughly in non-production first

### Low Confidence (Not Used Currently)
- Insufficient data
- Complex workload patterns
- High variability in metrics

**Action:** Gather more data before implementing

---

## What's NOT Considered

### Cost Commitments
- ❌ Reserved Instances
- ❌ Savings Plans
- ❌ Spot Instances

**Impact:** May recommend changes that conflict with existing commitments

### Application Requirements
- ❌ Compliance requirements (specific instance types)
- ❌ Software licensing (per-core licensing)
- ❌ Network throughput requirements
- ❌ Burst performance needs

### Business Context
- ❌ Production vs. development environments
- ❌ Business criticality
- ❌ Planned growth
- ❌ Seasonal traffic patterns

---

## Best Practices for Implementation

### 1. Prioritize by Confidence
```
High Confidence → Implement first
Medium Confidence → Test thoroughly
Low Confidence → Gather more data
```

### 2. Test in Non-Production
- Create test environment with recommended configuration
- Run load tests
- Monitor performance metrics
- Validate application behavior

### 3. Implement Gradually
- Start with development/test environments
- Move to staging
- Finally production (with rollback plan)

### 4. Monitor After Changes
- CPU, Memory, Network metrics
- Application performance
- Error rates
- User experience

### 5. Document Changes
- What was changed
- Why it was changed
- Performance impact
- Cost savings achieved

---

## Common Scenarios

### Scenario 1: Over-Provisioned Web Server
```
Current: m5.2xlarge (8 vCPU, 32 GB)
Usage: CPU 5%, Memory 20%
Recommendation: m5.large (2 vCPU, 8 GB)
Savings: $200/month
Risk: Low (4x headroom)
```

### Scenario 2: Idle Development Database
```
Current: db.m5.xlarge
Usage: CPU 3%, Connections 0.5 avg
Recommendation: db.t3.small
Savings: $150/month
Risk: Low (dev environment)
```

### Scenario 3: Lambda Over-Provisioned
```
Current: 3008 MB, 200ms duration
Recommendation: 1024 MB
Savings: $15/month
Risk: Medium (test for cold starts)
```

### Scenario 4: Forgotten Resources
```
Unattached EBS: 5 volumes, 2 TB total
Unattached EIPs: 3 addresses
Savings: $218/month
Risk: None (verify not needed)
```

---

## Validation Checklist

Before implementing recommendations:

- [ ] Verify resource is not part of Reserved Instance
- [ ] Check if resource is in Auto Scaling group
- [ ] Confirm resource is not required for compliance
- [ ] Review application requirements
- [ ] Check for software licensing constraints
- [ ] Verify no planned growth requiring current capacity
- [ ] Ensure monitoring is in place
- [ ] Have rollback plan ready
- [ ] Test in non-production first
- [ ] Get stakeholder approval for production changes

---

## Pricing Accuracy

### Current Implementation
- Simplified pricing based on us-east-1
- Approximate costs for common instance types
- Does not account for:
  - Regional pricing variations
  - Volume discounts
  - Reserved Instance pricing
  - Savings Plans

### For Production Use
Integrate with AWS Price List API:
```python
pricing = boto3.client('pricing', region_name='us-east-1')
response = pricing.get_products(
    ServiceCode='AmazonEC2',
    Filters=[
        {'Type': 'TERM_MATCH', 'Field': 'instanceType', 'Value': 'm5.large'},
        {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': 'US East (N. Virginia)'}
    ]
)
```

---

## Support & Troubleshooting

### No Recommendations Found
1. Check AWS Compute Optimizer is enabled
2. Verify 14+ days of CloudWatch data
3. Confirm resources exist in selected region
4. Check IAM permissions

### Inaccurate Recommendations
1. Review CloudWatch metrics manually
2. Check for burst workloads
3. Consider application-specific requirements
4. Verify data collection period

### Questions?
- Review CloudWatch Logs for Lambda errors
- Check IAM permissions
- Verify API responses in logs
- Open GitHub issue with details
