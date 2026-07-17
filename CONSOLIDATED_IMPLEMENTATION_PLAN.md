# CostOptimizer360 — Consolidated Best-in-Market Implementation Plan

**Scope:** Single, implementation-ready synthesis of market + technical research, grounded in the current codebase (`lambda/lambda_function.py`, `cloudformation.yaml`, `target-account-role.yaml`).
**Goal:** Make CostOptimizer360 the most accurate, broadest, and best-presented AWS cost-optimization scanner on the market.
**How to read this:** Section 1 = strategy. Section 2 = prioritized backlog (P0/P1/P2). Section 3 = exact code corrections. Section 4 = dashboard + report spec. Section 5 = new checks ranked by value/effort. Sources at the end.

> Note on citations: external content is paraphrased and rephrased for compliance with licensing restrictions; inline source links are provided throughout.

---

## 1. Executive Summary

### Where the tool stands today
CostOptimizer360 is a **read-only, multi-region scanner** that produces a polished Word/JSON/CSV report. Genuine strengths:
- **Good breadth already:** EC2, stopped-EC2 EBS waste, EBS unattached + gp2→gp3, RDS, Lambda, EIP, NAT gateway, DynamoDB, S3 hygiene, and an RI/SP coverage summary.
- **Live pricing for most services** via the Price List API (`pricing.GetProducts`) with a 1h cache and a strict "no-fallback → raise `PricingUnavailableError`" design that avoids silently fabricating numbers.
- **Report craft** is above average for an OSS scanner: cover page, TOC, KPI cards, matplotlib charts, styled tables, confidence + monthly/annual savings.

### The honest gaps (why we are not yet best-in-market)
1. **Accuracy defects that produce wrong dollar numbers** — the Compute Optimizer option selector is inverted, EC2 is always priced as Linux/Shared, DynamoDB uses stale (pre-Nov-2024) hardcoded rates *and* a unit-math bug, NAT pricing is hardcoded, and RI coverage is counted by instance rather than normalized units. A cost tool that is wrong loses trust instantly.
2. **Security posture blocks enterprise adoption** — a **public, unauthenticated Lambda Function URL** (`AuthType: NONE`, `Principal: '*'`) that accepts **raw AWS access keys** through a web form. This is disqualifying for any serious buyer and is itself a cost/abuse risk.
3. **No interactive dashboard** — the web UI is a form that downloads a file. Every serious competitor leads with an interactive dashboard.
4. **We reimplement what AWS now gives us for free.** AWS **Cost Optimization Hub** consolidates 15+ recommendation types from Compute Optimizer + Cost Explorer and **de-duplicates overlapping savings**; Compute Optimizer now covers **RDS/Aurora, ECS-on-Fargate, EBS, Lambda, idle resources, and commercial-license** optimization. Our hand-rolled CloudWatch heuristics for RDS/Lambda are now *less* accurate than the native APIs. ([Cost Optimization Hub CUR dictionary](https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-cor.html), [Compute Optimizer supported resources](https://docs.aws.amazon.com/compute-optimizer/latest/ug/supported-resources.html))

### The competitive reality
- **Native AWS** (Cost Explorer, Compute Optimizer, Cost Optimization Hub, CUR 2.0) is the free floor and it is rising fast.
- **Commercial tools differentiate on automation and FinOps workflow:** ProsperOps/nOps (autonomous commitment management), Cast AI/Zesty (autonomous K8s + rightsizing that *acts*), CloudZero/Vantage/Cloudability/Finout (visibility, allocation, chargeback, anomaly detection). Reviews consistently split the market into "AWS-native for discovery, third-party for automation." ([eon.io roundup](https://www.eon.io/blog/aws-cost-optimization-tools), [usage.ai roundup](https://www.usage.ai/blog/best-cloud-cost-management-tools), [cloudfix comparison](https://cloudfix.com/blog/aws-cost-optimization-tools-comparison/))
- **Open source to learn from:** [Komiser](https://github.com/tailwarden/komiser) (multi-cloud inventory + resource-level cost breakdown + dashboard), [Cloud Custodian / c7n](https://github.com/cloud-custodian/cloud-custodian) (YAML policy/rules engine + remediation + off-hours scheduling), [Steampipe `mod-aws-thrifty` + Powerpipe](https://github.com/turbot/steampipe-mod-aws-thrifty) (SQL waste benchmarks + dashboards-as-code), [Flowpipe `mod-aws-thrifty`](https://github.com/turbot/flowpipe-mod-aws-thrifty) (remediation pipelines), and [Infracost](https://github.com/infracost/infracost) (shift-left IaC cost estimation + a clean pricing abstraction).

### Path to best-in-market (4 pillars)
- **A. Accuracy & trust (P0):** fix the math, adopt Cost Optimization Hub + Cost Explorer as the source of truth where they exist, and reconcile savings so numbers are defensible.
- **B. Coverage (P1):** idle detection, Graviton/modern-gen migration, commitment purchase recommendations, and 8–10 new services.
- **C. Presentation & prediction (P1):** a real interactive dashboard + an upgraded, prioritized, evidence-backed report with forecasts and what-if simulation.
- **D. Actionability & scale (P2):** multi-account (Organizations), scheduled scans + trend history, and safe one-click/guided remediation (IaC + CLI snippets, à la Cloud Custodian/Flowpipe).

**Positioning statement:** *"The scanner that is as accurate as AWS-native, broader in one view, beautifully presented, and safe to run across your whole Organization — without handing us your keys."*

---

## 2. Prioritized Backlog (P0 / P1 / P2)

Priority = impact on correctness/trust first, then coverage, then differentiation. "Effort" is rough (S/M/L).

### P0 — Correctness, trust, and security (do first; these make current output *wrong or dangerous*)

| ID | Item | Effort |
|----|------|--------|
| P0-1 | Fix inverted Compute Optimizer option selection | S |
| P0-2 | Price EC2/RDS by real OS/tenancy/license (stop assuming Linux/Shared) | M |
| P0-3 | Replace hardcoded DynamoDB + NAT pricing; fix DynamoDB consumed-capacity unit bug | M |
| P0-4 | Remediate security model (auth on endpoint, stop taking raw keys, fix ExternalId) | M |
| P0-5 | Adopt Cost Optimization Hub + reconcile savings (de-dupe, On-Demand vs after-discount) | M |
| P0-6 | Fix RI/SP coverage to normalized-unit / hours basis; actually compute SP coverage | M |

**P0-1 — Compute Optimizer option selection is inverted.**
- **What:** In `scan_ec2_instances`, the "best" option is chosen as `min(options, key=... projectedUtilizationMetrics[0].value)`. That selects the option whose **projected CPU stays lowest = the largest/most over-provisioned instance = least savings**. It also ignores the fields AWS provides for exactly this decision.
- **Why (impact):** Directly produces suboptimal (sometimes negative-value) recommendations and understates savings on the flagship EC2 check. High blast radius.
- **APIs/fields:** `GetEC2InstanceRecommendations` → each `recommendationOptions[]` includes `rank` (1 = AWS's top pick), `performanceRisk`, `savingsOpportunity{ savingsOpportunityPercentage, estimatedMonthlySavings{value} }`, `savingsOpportunityAfterDiscounts`, `projectedUtilizationMetrics[]`, `migrationEffort`, `platformDifferences`. ([InstanceRecommendation](https://docs.aws.amazon.com/compute-optimizer/latest/APIReference/API_InstanceRecommendation.html), [SavingsOpportunity](https://docs.aws.amazon.com/sdk-for-kotlin/api/latest/computeoptimizer/aws.sdk.kotlin.services.computeoptimizer.model/-savings-opportunity/index.html))
- **Fix:** Prefer `rank == 1`; or apply a policy: filter `performanceRisk <= threshold`, then choose max `savingsOpportunity.estimatedMonthlySavings.value`.
- **Accuracy note:** `savingsOpportunity` is **On-Demand-based**; if the customer holds RIs/SPs, use `savingsOpportunityAfterDiscounts` to avoid overstating. ([InstanceSavingsOpportunityAfterDiscounts](https://docs.aws.amazon.com/compute-optimizer/latest/APIReference/API_InstanceSavingsOpportunityAfterDiscounts.html))

**P0-2 — EC2/RDS priced OS-agnostically.**
- **What:** `get_instance_cost` always sends `operatingSystem='Linux'`, `tenancy='Shared'`, `preInstalledSw='NA'`. Windows/RHEL/SUSE/SQL-Server/Dedicated instances are all priced as Linux/Shared.
- **Why:** Windows can cost ~2× Linux for the same shape; a wrong base price makes every derived saving wrong. This is the single biggest pricing-accuracy defect after P0-1.
- **APIs/fields:** From `ec2.describe_instances` read `PlatformDetails` and `UsageOperation`; map to Price List filters `operatingSystem` (Linux / RHEL / SUSE / Windows), `preInstalledSw` (NA / SQL Std / SQL Web / SQL Ent), `licenseModel` (No License required / Bring your own license), `tenancy` (Shared/Dedicated/Host), `capacitystatus` (Used). Same fix for RDS: `licenseModel` (license-included vs BYOL) and edition matter. ([GetProducts](https://docs.aws.amazon.com/boto3/latest/reference/services/pricing/client/get_products.html))
- **Accuracy note:** Prefer the region-native `regionCode` filter over the English `location` map; the hardcoded `REGION_LOCATION_MAP` breaks silently when AWS renames a location.

**P0-3 — Hardcoded/stale DynamoDB & NAT pricing + a unit bug.**
- **What / DynamoDB (`scan_dynamodb_tables`):**
  - On-demand rates are hardcoded at `$0.25/M RRU` and `$1.25/M WRU`. **AWS cut on-demand throughput ~50% on 2024-11-01**; us-east-1 is now ~**$0.125/M RRU** and **$0.625/M WRU**. Result: on-demand cost is overstated ~2× → savings understated (or recommendation flips). ([DynamoDB pricing change](https://www.jusdb.com/blog/dynamodb-cost-optimization-a-comprehensive-guide), [on-demand rates](https://oneuptime.com/blog/post/2026-02-12-dynamodb-on-demand-vs-provisioned/view))
  - **Unit bug:** it reads `ConsumedReadCapacityUnits` with `Statistic='Average'` and multiplies by `86400`. The `Average` of a per-period **sum** metric is not a per-second rate; multiplying by seconds double-distorts. Use `Statistic='Sum'` for total consumed units over the window (→ multiply by On-Demand per-request price directly), or `Sum / period_seconds` for a true per-second average.
- **What / NAT (`scan_nat_gateways`):** `NAT_GW_HOURLY_COST=0.045` and per-GB `=0.045` are hardcoded; both vary by region (hourly ~$0.045–$0.093). ([VPC/NAT pricing](https://docs.aws.amazon.com/vpc/latest/userguide/nat-gateway-pricing.html))
- **APIs/fields:** DynamoDB → `pricing.GetProducts(ServiceCode='AmazonDynamoDB')` filtered by group/usagetype for on-demand RRU/WRU and provisioned RCU/WCU. NAT → `GetProducts(ServiceCode='AmazonEC2', productFamily='NAT Gateway')`, usagetypes `*-NatGateway-Hours` and `*-NatGateway-Bytes`. Discover service codes/attributes with `DescribeServices`/`GetAttributeValues` rather than hardcoding. ([Price List query API](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/using-price-list-query-api.html))
- **Formula (provisioned→on-demand break-even):** 1 provisioned WCU ≈ $0.00065/hr ≈ **$0.4745/mo** and supports ~2.59M writes/mo; the same writes on-demand ≈ 2.59M × $0.625/M ≈ **$1.62** → **break-even ≈ 29% sustained utilization** (reads work out similarly). Below ~29% on-demand wins; the current `<20%` flag is defensible but should be computed from live prices, not assumed. ([throughput-utilization guidance](https://aws.amazon.com/blogs/database/how-to-evaluate-throughput-utilization-for-amazon-dynamodb-tables-in-provisioned-mode/))
- **Accuracy note:** also consider provisioned + auto scaling and reserved capacity before recommending on-demand; note the 4-switch-per-24h limit when advising mode changes. ([capacity mode](https://docs.aws.amazon.com/us_en/amazondynamodb/latest/developerguide/CostOptimization_TableCapacityMode.html))

**P0-4 — Security model (blocks enterprise sales and is an active risk).**
- **What:** `cloudformation.yaml` exposes a **public Function URL** (`AuthType: NONE`, CORS `*`, `FunctionUrlPermission Principal: '*'`, plus a broad `FunctionInvokePermission Principal: '*'`). `create_session` accepts **raw `accessKeyId`/`secretAccessKey`** from the request body. The Lambda execution role has `sts:AssumeRole` on `Resource: '*'`.
- **Why:** Anyone on the internet can invoke it, submit credentials, or use it as a free scanning proxy (abuse → your bill). Long-lived keys transiting an unauthenticated endpoint is disqualifying for enterprise buyers.
- **Fix (concrete):**
  - Put the endpoint behind auth: `AuthType: AWS_IAM` on the Function URL, or API Gateway + Cognito/OIDC; add WAF + throttling. Restrict CORS to your frontend origin.
  - **Never accept long-lived keys.** Standardize on cross-account **`AssumeRole` with a per-customer, randomly-generated `ExternalId`** and a least-privilege read-only policy; add a session policy to hard-cap to read-only as defense in depth.
  - Scope the execution role's `sts:AssumeRole` to a specific role-name pattern (e.g., `arn:aws:iam::*:role/CostOptimizer360Scan`), not `*`.
- **Bug to fix while here:** the target trust policy **requires** `sts:ExternalId == 'InfraOptimizer360'`, but `create_session` calls `assume_role` **without** `ExternalId` → cross-account scans currently fail with `AccessDenied`. Also, a static ExternalId committed to an open-source repo provides **zero** confused-deputy protection — it must be unique per tenant. ([SP/RI cross-account trust discussion](https://repost.aws/articles/ARJ91aD-vDRZOoYdTeYN9aog/avoiding-billing-challenges-best-practices-for-savings-plans-and-ri-management-during-organizations-consolidations))

**P0-5 — Adopt Cost Optimization Hub and reconcile savings.**
- **What:** Add Cost Optimization Hub as a first-class source. It consolidates Compute Optimizer + Cost Explorer recommendations, **de-duplicates overlapping savings**, and returns normalized fields.
- **Why:** Prevents the classic double-count (e.g., counting rightsizing savings *and* Savings Plans savings on the same resource), gives org-wide aggregation, and covers types we don't compute. It's free.
- **APIs/fields:** `cost-optimization-hub:ListRecommendations`, `GetRecommendation`, `ListRecommendationSummaries` → `actionType` (Rightsize / Stop / Delete / Upgrade / MigrateToGraviton / PurchaseSavingsPlans / …), `estimatedMonthlySavings`, `estimatedSavingsPercentage`, `implementationEffort`, `restartNeeded`, `rollbackPossible`, `currentResourceSummary`/`recommendedResourceSummary`. ([ListRecommendations](https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API_CostOptimizationHub_ListRecommendations.html), [de-dup summaries](https://docs.aws.amazon.com/boto3/latest/reference/services/cost-optimization-hub/client/list_recommendation_summaries.html))
- **Accuracy note:** Always label each dollar figure as **On-Demand-based** vs **after existing discounts**, and never sum rightsizing + commitment savings for the same resource without de-duping.

**P0-6 — RI/SP coverage is counted wrong.**
- **What:** `scan_ri_sp_coverage` computes `ri_coverage_pct = ri_count / running_instance_count` and never computes `sp_coverage_pct` (stays 0). RIs are matched by **exact instance type** in `scan_ec2_instances`.
- **Why:** Coverage measured by instance count is misleading; regional Linux/shared RIs have **instance-size flexibility** (a `*.2xlarge` RI covers 2× `*.xlarge`, etc.), and Savings Plans apply to **$/hr of usage**, not instance counts. Exact-type matching both over- and under-counts.
- **APIs/fields:** `ce:GetReservationCoverage` and `ce:GetSavingsPlansCoverage` (coverage in **hours / normalized units / spend**), `ce:GetReservationUtilization`, `ce:GetSavingsPlansUtilization`. Normalization factors: nano .25, micro .5, small 1, medium 2, large 4, xlarge 8, 2xlarge 16, 4xlarge 32, … Zonal RIs = no size flexibility and AZ-bound; Windows/RHEL/dedicated = no size flexibility. ([Cost Explorer operations](https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API_Operations_AWS_Cost_Explorer_Service.html))

### P1 — Coverage, accuracy depth, and presentation

| ID | Item | Effort |
|----|------|--------|
| P1-1 | Interactive in-browser dashboard (async job model) | L |
| P1-2 | Idle-resource detection via Compute Optimizer idle recommendations | M |
| P1-3 | RDS/Aurora rightsizing via Compute Optimizer (replace CloudWatch heuristic) | M |
| P1-4 | Lambda rightsizing via Compute Optimizer + Graviton + fix memory-cut logic | M |
| P1-5 | EC2 memory-awareness + true percentiles via GetMetricData | M |
| P1-6 | Graviton / modern-generation migration recommendations | M |
| P1-7 | Savings Plans & RI **purchase** recommendations | M |
| P1-8 | Quantify S3 savings (Storage Lens / storage metrics) | M |
| P1-9 | Full public-IPv4 accounting (post-2024 charge) | S |

- **P1-1 Interactive dashboard** — see §4A. Requires an async job model (scans exceed synchronous limits): `POST /scan` → `jobId`; worker writes results JSON to S3/DynamoDB; SPA polls `GET /scan/{jobId}` or uses SSE. This unblocks the single biggest UX gap.
- **P1-2 Idle detection** — Compute Optimizer now emits **idle** recommendations (idle EC2/ASG/EBS/RDS and more) with defined idle criteria and remediation (snapshot+delete EBS, stop/turn-off RDS). Higher-confidence and less risky than rightsizing. ([idle recommendations](https://docs.aws.amazon.com/compute-optimizer/latest/ug/view-idle-recommendations.html), [announcement](https://aws.amazon.com/blogs/aws-cloud-financial-management/announcing-idle-recommendations-in-aws-compute-optimizer/))
- **P1-3 RDS via Compute Optimizer** — since 2025, Compute Optimizer produces RDS/Aurora instance **and storage** recommendations for MySQL/PostgreSQL/Aurora using Performance Insights + CloudWatch — more accurate than our `avg_cpu<10 & conn<3` rule. Fall back to CloudWatch only when unenrolled. ([RDS recs](https://aws.amazon.com/blogs/database/how-to-optimize-amazon-rds-and-amazon-aurora-database-costs-performance-with-aws-compute-optimizer), [supported resources](https://docs.aws.amazon.com/compute-optimizer/latest/ug/supported-resources.html))
- **P1-4 Lambda** — use `GetLambdaFunctionRecommendations` (memory options with projected `Duration` + `savingsOpportunity`); recommend **arm64/Graviton**; for compute-bound functions point to **AWS Lambda Power Tuning**. Fix the current heuristic (see §3) — cutting memory can *increase* cost/latency because Lambda CPU scales with memory.
- **P1-5 EC2 metrics** — collect **memory** from the CloudWatch agent (`CWAgent` namespace, `mem_used_percent`) so downsizing isn't blind to memory-bound workloads; switch from `get_metric_statistics` (Average/Max, daily) to `GetMetricData` with `p95`/`p99` `ExtendedStatistics` (batch up to 500 queries/call). The README claims p99 today; the code does not implement it.
- **P1-6 Graviton / modern-gen** — recommend equivalent Graviton shapes (e.g., `m6i`→`m7g`) and last-gen→current-gen (`m5`→`m7i`); Compute Optimizer/COH surface these as `MigrateToGraviton`/upgrade actions. Flag `platformDifferences` (architecture change) so users know it needs a rebuild/test.
- **P1-7 Commitment purchase recs** — `ce:GetSavingsPlansPurchaseRecommendation` (COMPUTE_SP / EC2_INSTANCE_SP / SAGEMAKER_SP) and `ce:GetReservationPurchaseRecommendation`, with configurable `LookbackPeriodInDays` (SEVEN/THIRTY/SIXTY), `TermInYears`, `PaymentOption`, `AccountScope`. This is where the biggest real-world dollars are, and where ProsperOps/nOps win. ([GetReservationPurchaseRecommendation](https://docs.aws.amazon.com/AWSJavaScriptSDK/v3/latest/client/cost-explorer/command/GetReservationPurchaseRecommendationCommand)) 
- **P1-8 S3 quantification** — today S3 savings are always `$0.00`. Pull per-bucket, per-storage-class size from CloudWatch `AWS/S3 BucketSizeBytes` (or S3 Storage Lens) and quantify: incomplete-MPU reclaim, Standard→Intelligent-Tiering/IA/Glacier transitions, and old-version cleanup.
- **P1-9 Public IPv4** — since **2024-02-01 every public IPv4 is billed ~$0.005/hr (~$3.65/mo)** whether attached or not; `scan_elastic_ips` only flags *unattached* EIPs. Add all-public-IPv4 accounting (EIPs + auto-assigned public IPs on ENIs) and recommend reduction (private subnets + endpoints, IPv6, BYOIP). ([VPC pricing](https://aws.amazon.com/vpc/pricing/))

### P2 — Breadth and differentiation

| ID | Item | Effort |
|----|------|--------|
| P2-1 | Multi-account via AWS Organizations (payer-level COH/CE) | M |
| P2-2 | Scheduled scans + historical trend store + drift/anomaly | M |
| P2-3 | Guided/one-click remediation (IaC + CLI snippets, approval workflow) | L |
| P2-4 | New services: EBS snapshots, idle ELB/ALB, ElastiCache, Redshift, OpenSearch, EKS/Kubecost-style, Fargate, WorkSpaces, old-gen (see §5) | L |
| P2-5 | Cost anomaly detection integration | S |
| P2-6 | Off-hours scheduling recommendations (dev/test start/stop) | S |
| P2-7 | Shift-left: pre-deploy IaC cost estimation (Infracost-style) | M |

Details and value/effort ranking for the new services are in **§5**.

---

## 3. Specific Corrections to the Current Code

Concrete, file-anchored fixes. Snippets are illustrative.

### 3.1 Compute Optimizer option-selection heuristic (CRITICAL — inverted logic)
`scan_ec2_instances`, current:
```python
best = min(options, key=lambda x: x.get('projectedUtilizationMetrics', [{}])[0].get('value', 100))
recommended_type = best['instanceType']
```
Problems: (1) picks the option with the **lowest projected utilization** = largest instance = least savings; (2) ignores `rank`, `performanceRisk`, `savingsOpportunity`; (3) `projectedUtilizationMetrics[0]` is order-dependent and may be Memory, not CPU.
Recommended:
```python
def pick_option(rec, max_perf_risk=3):
    opts = rec.get('recommendationOptions', [])
    if not opts:
        return None
    top = [o for o in opts if o.get('rank') == 1]          # AWS's balanced top pick
    if top:
        return top[0]
    risk = {'VeryLow':1,'Low':2,'Medium':3,'High':4}
    ok = [o for o in opts if risk.get(o.get('performanceRisk','High'),4) <= max_perf_risk]
    return max(ok or opts, key=lambda o: o.get('savingsOpportunity', {})
               .get('estimatedMonthlySavings', {}).get('value', 0.0))
```
Then prefer AWS's own `savingsOpportunity.estimatedMonthlySavings` (label On-Demand) or `savingsOpportunityAfterDiscounts` when the account holds RIs/SPs — rather than recomputing via `get_instance_cost` (which risks contradicting AWS's number). ([InstanceRecommendation](https://docs.aws.amazon.com/compute-optimizer/latest/APIReference/API_InstanceRecommendation.html))

### 3.2 OS-agnostic EC2/RDS pricing
`get_instance_cost` hardcodes `operatingSystem='Linux'`, `tenancy='Shared'`, `preInstalledSw='NA'`. Derive them:
```python
inst = ec2.describe_instances(InstanceIds=[iid])['Reservations'][0]['Instances'][0]
platform_details = inst.get('PlatformDetails', 'Linux/UNIX')   # e.g. 'Windows', 'Red Hat Enterprise Linux', 'Windows with SQL Server Standard'
os_name, pre_sw, license_model = map_platform_to_pricing(platform_details)
tenancy = {'default':'Shared','dedicated':'Dedicated','host':'Host'}[inst['Placement']['Tenancy']]
```
Map `PlatformDetails`/`UsageOperation` → `operatingSystem`, `preInstalledSw`, `licenseModel`; pass real `tenancy`. For RDS, add `licenseModel` and engine edition. Prefer the `regionCode` filter over the English `REGION_LOCATION_MAP`. ([GetProducts](https://docs.aws.amazon.com/boto3/latest/reference/services/pricing/client/get_products.html))

### 3.3 DynamoDB — stale rates + unit bug (`scan_dynamodb_tables`)
Current:
```python
provisioned_monthly = (provisioned_rcu*0.00013 + provisioned_wcu*0.00065)*730
on_demand_monthly = (avg_rcu*86400*30*0.25/1_000_000) + (avg_wcu*86400*30*1.25/1_000_000)
```
Fixes:
1. **Rates from Price List** (`ServiceCode='AmazonDynamoDB'`); do not hardcode. Post-2024-11-01 on-demand ≈ $0.125/M RRU, $0.625/M WRU.
2. **Consumed units:** use `Statistic='Sum'` over the window for total consumed RRU/WRU (multiply directly by per-request price). The `Average × 86400` approach is dimensionally wrong. If you want per-second, use `Sum / period_seconds`.
3. Compute the break-even from live prices (~29% today) instead of a fixed 20%. ([rates](https://oneuptime.com/blog/post/2026-02-12-dynamodb-on-demand-vs-provisioned/view), [utilization guidance](https://aws.amazon.com/blogs/database/how-to-evaluate-throughput-utilization-for-amazon-dynamodb-tables-in-provisioned-mode/))

### 3.4 NAT gateway — hardcoded pricing (`scan_nat_gateways`)
Replace `NAT_GW_HOURLY_COST=0.045` / per-GB `0.045` with `GetProducts(ServiceCode='AmazonEC2', productFamily='NAT Gateway')` (usagetypes `*-NatGateway-Hours`, `*-NatGateway-Bytes`). Beyond "idle NAT," add the high-value NAT optimizations and quantify them:
- **S3/DynamoDB gateway VPC endpoints are free** and remove NAT data-processing charges for that traffic;
- interface endpoints for AWS APIs;
- consolidating per-AZ NAT (trade AZ-resilience vs cross-AZ data). ([NAT cost guidance](https://www.cloudzero.com/blog/reduce-nat-gateway-costs/))

### 3.5 Naive RI matching + coverage (`scan_ec2_instances`, `scan_ri_sp_coverage`)
- Stop matching RIs by exact `instance_type` and decrementing a shared dict during iteration (order-dependent, ignores size flexibility, scope, OS, tenancy, AZ).
- Compute coverage with `ce:GetReservationCoverage` + `ce:GetSavingsPlansCoverage` (normalized units / hours / spend). Actually populate `sp_coverage_pct`.
- Don't *skip* RI-covered instances from rightsizing — instead label them "covered by RI/SP; rightsizing may require RI modification/exchange."

### 3.6 Cross-account assume-role is broken + insecure (`create_session`)
```python
assumed_role = sts.assume_role(RoleArn=body['roleArn'], RoleSessionName='InfraOptimizer360Session')
```
- **Missing `ExternalId`** while the trust policy requires `sts:ExternalId=='InfraOptimizer360'` → current cross-account scans fail. Pass a **per-customer** ExternalId:
```python
assumed = sts.assume_role(RoleArn=body['roleArn'],
                          RoleSessionName='CostOptimizer360',
                          ExternalId=body['externalId'],   # unique per tenant, shared out-of-band
                          DurationSeconds=3600)
```
- Remove the raw-credentials path from a public endpoint; require the role path. Add auth on the endpoint (see P0-4). Scope the execution role's `sts:AssumeRole` to a role-name pattern, not `*`.

### 3.7 RDS memory threshold is an absolute constant (`scan_rds_instances`)
`min_freeable_memory < 500_000_000` (500 MB) is wrong across classes (fine for `r5.large`/16 GB, catastrophic for `t3.micro`/1 GB). Use a **relative** threshold (e.g., FreeableMemory < 10–15% of the class's RAM) or, better, migrate to Compute Optimizer RDS recommendations / Performance Insights `DBLoad` vs vCPU.

### 3.8 EC2 metric accuracy (`scan_ec2_instances`)
- Claimed p99 is not implemented — code uses `Average`/`Maximum` over daily periods. Move to `GetMetricData` with `p95`/`p99` and finer periods; batch to avoid throttling and Lambda timeouts on large accounts.
- Downsizing decisions are CPU/network-only; **add memory** (CWAgent) or clearly mark memory as "unknown" and lower confidence accordingly.

### 3.9 Lambda memory-reduction logic (`scan_lambda_functions`)
The rule "memory>1024 & avg_duration<500ms & max<2000ms → cut 25%" ignores that **Lambda CPU scales with memory** — cutting memory can lengthen duration and *raise* cost or latency. Replace with Compute Optimizer's `memorySizeRecommendationOptions` (which model this) or Lambda Power Tuning; also detect arm64 migration savings and account for provisioned concurrency.

### 3.10 gp3 comparison understates cost for large gp2 volumes (`scan_ebs_volumes` / `calculate_ebs_cost`)
gp2 provisions 3 IOPS/GiB, so a >1,000 GiB gp2 volume already has >3,000 IOPS. Comparing it to gp3 at the **fixed 3,000/125 baseline** understates gp3 cost and can *reduce* performance after migration. Compute the gp2 baseline IOPS = `min(max(100, 3*size), 16000)` and size gp3 to match (add the extra-IOPS/throughput cost, which the code already supports) before claiming savings.

### 3.11 Minor but real
- `730 hrs/mo` overstates savings for non-24/7 instances; optionally weight by observed running hours.
- `list_multipart_uploads` isn't paginated (misses >1,000 uploads).
- Surface Compute Optimizer **enrollment status** (`GetEnrollmentStatus`) to the user instead of silently falling back.
- Reconcile "our Price List savings" vs "Compute Optimizer savings" into one labeled number to avoid contradictory figures in the report.

---

## 4. Dashboard + Report Specification

### 4A. Best-in-class in-browser dashboard

**Architecture (required first):** move from synchronous file-download to an **async job model** — `POST /scan` returns `jobId`; a worker (Lambda/Step Functions/Fargate for long scans) writes a normalized results JSON to S3/DynamoDB; the SPA (React/Vue) polls `GET /scan/{jobId}` or subscribes via SSE and renders. This removes timeout limits and enables the interactive UI. Put it behind auth (Cognito/OIDC) + WAF.

**Global controls:** account/Organization selector, region multi-select, service filter, tag/cost-allocation filter, confidence filter, effort/risk filter, currency, and On-Demand vs after-discount toggle.

**Layout / views:**
1. **Overview** — KPI header: total monthly & annualized savings, % of current spend, #recommendations by priority, RI/SP coverage & utilization gauges, "quick wins < 1 day" callout. Savings **treemap** by service and a **waterfall** from current → optimized spend.
2. **By Service / By Account / By Region** — sortable, filterable tables; drill from a bar to the underlying resources.
3. **Rightsizing** — per-resource current vs recommended, with **projected-utilization sparklines** and `performanceRisk`.
4. **Commitments** — coverage & utilization over time; **RI/SP purchase simulator** (term, payment option, lookback) with break-even and risk.
5. **Idle & Waste** — idle EC2/EBS/RDS/EIP/ELB, unattached volumes, old snapshots, incomplete MPUs; each with reclaimable $.
6. **Trends & Forecast** — historical scans, savings realized vs identified, `ce:GetCostForecast`, and anomaly flags.
7. **Recommendation detail (drawer)** — evidence (metrics, percentiles, lookback window), confidence + why, blast radius, **remediation snippets** (AWS CLI + Terraform/CloudFormation), and links to the AWS console resource.

**Charts:** treemap (spend/savings), waterfall (current→optimized), coverage gauges, utilization histograms/heatmaps, trend lines, projected-utilization sparklines. **Every chart is drill-through.**

**Predictions built in:**
- **Forecast** next-period cost with/without acting (`ce:GetCostForecast`).
- **Projected utilization** post-change from Compute Optimizer `projectedUtilizationMetrics`.
- **Break-even** (DynamoDB mode switch, gp2→gp3, RI/SP payback months).
- **What-if commitment simulator** using purchase-recommendation APIs.

**Inspiration:** dashboards-as-code and the check catalog from [Steampipe/Powerpipe `mod-aws-thrifty`](https://github.com/turbot/steampipe-mod-aws-thrifty); resource-level inventory/cost UX from [Komiser](https://github.com/tailwarden/komiser).

### 4B. Upgraded downloadable report

Keep the polished DOCX; add rigor, prioritization, and evidence. Recommended section order:
1. **Executive one-pager** — total savings (monthly/annual + % of spend), top 5 actions, coverage snapshot, risk summary.
2. **Methodology & confidence** — data sources (COH/Compute Optimizer/CE/CloudWatch), lookback window, On-Demand vs after-discount basis, assumptions.
3. **Prioritized action plan** — every recommendation tagged **P0/P1/P2**, with **effort** (S/M/L), **risk/blast radius**, **restart-needed**, and **rollback-possible** (from COH fields).
4. **Per-service sections** — existing tables **plus** an Evidence column (avg/p95/p99, lookback) and the confidence rationale.
5. **Commitments** — coverage, utilization, and purchase recommendations with break-even.
6. **Idle & waste**, **forecast & trend** (if history exists).
7. **Assumptions & caveats** — memory-blind CPU rightsizing, non-24/7 usage, size-flexibility notes.
8. **Appendix** — raw data pointers.

**Formats:** keep JSON/CSV; **add multi-sheet XLSX** (Summary / per-service / RI-SP / raw) with formulas so FinOps can pivot. Charts: add the waterfall and coverage gauges to match the dashboard. Ensure charts have readable labels and color-contrast for accessibility.

---

## 5. New Checks / Services — Ranked by Value-to-Effort

Value = typical $ impact × how commonly it applies. Effort = build complexity. Ordered best-first.

| Rank | Check / Service | Value | Effort | V/E | How (APIs / signals) |
|------|-----------------|-------|--------|-----|----------------------|
| 1 | **Idle resource detection** (EC2/EBS/RDS/ASG) | High | Low | ★★★★★ | Compute Optimizer **idle** recommendations; near-zero-risk deletes/stops |
| 2 | **Cost Optimization Hub aggregation** | High | Low | ★★★★★ | `ListRecommendations`/`ListRecommendationSummaries` (de-duped, org-wide) |
| 3 | **SP/RI purchase recommendations** | Very High | Med | ★★★★★ | `ce:GetSavingsPlansPurchaseRecommendation`, `ce:GetReservationPurchaseRecommendation` |
| 4 | **EBS snapshot cleanup** (orphaned/old, per-snapshot billing) | High | Low | ★★★★☆ | `describe_snapshots` (owner-self) + AMI cross-ref; flag orphaned/aged |
| 5 | **Idle/underused load balancers** (ALB/NLB/CLB) | Med-High | Low | ★★★★☆ | ELBv2 describe + CloudWatch `RequestCount`/`ActiveFlowCount`/`ProcessedBytes` ≈ 0 |
| 6 | **Graviton / modern-gen migration** (EC2/RDS/ElastiCache/OpenSearch) | High | Med | ★★★★☆ | COH `MigrateToGraviton` / Compute Optimizer options + `platformDifferences` |
| 7 | **Off-hours scheduling** (dev/test start/stop) | Med-High | Low | ★★★★☆ | Tag + CloudWatch usage patterns; à la Cloud Custodian `offhours` |
| 8 | **Old-generation instance upgrade** (m4→m7i, gp2→gp3, etc.) | Med | Low | ★★★★☆ | Instance/vol inventory + Price List price-per-perf delta |
| 9 | **ElastiCache rightsizing/idle** | Med | Med | ★★★☆☆ | Compute Optimizer supports ElastiCache; else CloudWatch CPU/Evictions/CurrConnections |
| 10 | **Redshift** (idle/pause, RA3 migration, concurrency scaling) | Med | Med | ★★★☆☆ | CloudWatch + describe clusters; pause/resume + RIs |
| 11 | **OpenSearch** rightsizing/idle | Med | Med | ★★★☆☆ | CloudWatch cluster metrics; storage/instance sizing |
| 12 | **Fargate (ECS) task rightsizing** | Med | Med | ★★★☆☆ | Compute Optimizer ECS-on-Fargate container CPU/memory recs |
| 13 | **EKS / Kubernetes cost** (pod-level) | High | High | ★★★☆☆ | Integrate Kubecost/OpenCost patterns; per-namespace/pod allocation |
| 14 | **Cost anomaly detection** | Med | Low | ★★★★☆ | `ce:GetAnomalies` surfaced in dashboard + report |
| 15 | **VPC endpoints vs NAT** data-charge reduction | Med-High | Med | ★★★☆☆ | Flow-log/traffic analysis for S3/DynamoDB-bound bytes over NAT |
| 16 | **WorkSpaces** (AlwaysOn→AutoStop, idle) | Low-Med | Low | ★★★☆☆ | Compute Optimizer WorkSpaces support + usage metrics |
| 17 | **Public IPv4 reduction** (post-2024 charge) | Low-Med | Low | ★★★☆☆ | `describe_addresses` + ENIs with public IPs; IPAM insights |
| 18 | **Shift-left IaC estimation** (Infracost-style) | Med | Med | ★★☆☆☆ | Parse Terraform plan → Price List; PR cost diff |

**Sequencing:** ranks 1–3 are the fastest ROI (mostly wiring native APIs into our normalized model) and should ship alongside the P0 fixes. Ranks 4–8 are cheap, high-frequency wins. Ranks 9–13 broaden coverage into the enterprise conversation; 13 (EKS) is the one category every roundup says tools ignore — a real differentiator if done well. ([eon.io](https://www.eon.io/blog/aws-cost-optimization-tools))

---

## Accuracy Pitfalls — Quick Reference

- **Compute Optimizer option pick:** use `rank==1` / `performanceRisk` + `savingsOpportunity`, never `min(projectedUtilization)`.
- **Savings basis:** COH/Compute Optimizer `savingsOpportunity` is **On-Demand**; use `…AfterDiscounts` when RIs/SPs exist; never double-count rightsizing + commitments (COH de-dupes).
- **EC2/RDS pricing:** must include OS, preInstalledSw, licenseModel, tenancy, capacitystatus — not Linux/Shared for everything.
- **DynamoDB:** live prices (on-demand halved 2024-11-01); consumed capacity via `Sum`, not `Average×86400`.
- **NAT:** live prices; biggest wins are gateway endpoints, not "delete idle."
- **RI/SP coverage:** normalized units/hours/spend via Cost Explorer, not instance counts; account for size flexibility, scope, OS, AZ.
- **EC2 rightsizing:** CPU-only is memory-blind; use CWAgent memory + p95/p99 via GetMetricData.
- **Lambda:** CPU scales with memory — model it (Compute Optimizer / Power Tuning), don't blindly cut 25%; consider arm64.
- **gp2→gp3:** match gp2's provisioned IOPS on gp3 for large volumes before claiming savings.
- **EIP:** all public IPv4 is billed since 2024-02-01, not just unattached EIPs.
- **Security:** no public unauthenticated endpoint; no raw keys; per-tenant ExternalId; least-privilege scoped AssumeRole.

---

## Sources

AWS documentation (public):
- Compute Optimizer — [InstanceRecommendation](https://docs.aws.amazon.com/compute-optimizer/latest/APIReference/API_InstanceRecommendation.html), [GetEC2InstanceRecommendations](https://docs.aws.amazon.com/compute-optimizer/latest/APIReference/API_GetEC2InstanceRecommendations.html), [SavingsOpportunity](https://docs.aws.amazon.com/sdk-for-kotlin/api/latest/computeoptimizer/aws.sdk.kotlin.services.computeoptimizer.model/-savings-opportunity/index.html), [InstanceSavingsOpportunityAfterDiscounts](https://docs.aws.amazon.com/compute-optimizer/latest/APIReference/API_InstanceSavingsOpportunityAfterDiscounts.html), [supported resources](https://docs.aws.amazon.com/compute-optimizer/latest/ug/supported-resources.html), [idle recommendations](https://docs.aws.amazon.com/compute-optimizer/latest/ug/view-idle-recommendations.html), [idle announcement](https://aws.amazon.com/blogs/aws-cloud-financial-management/announcing-idle-recommendations-in-aws-compute-optimizer/), [RDS recommendations](https://aws.amazon.com/blogs/database/how-to-optimize-amazon-rds-and-amazon-aurora-database-costs-performance-with-aws-compute-optimizer)
- Cost Optimization Hub — [ListRecommendations](https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API_CostOptimizationHub_ListRecommendations.html), [ListRecommendationSummaries (de-dup)](https://docs.aws.amazon.com/boto3/latest/reference/services/cost-optimization-hub/client/list_recommendation_summaries.html), [CUR dictionary (15+ types)](https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-cor.html)
- Cost Explorer — [operations list](https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API_Operations_AWS_Cost_Explorer_Service.html), [GetRightsizingRecommendation](https://docs.aws.amazon.com/boto3/latest/reference/services/ce/client/get_rightsizing_recommendation.html), [GetReservationPurchaseRecommendation](https://docs.aws.amazon.com/AWSJavaScriptSDK/v3/latest/client/cost-explorer/command/GetReservationPurchaseRecommendationCommand)
- Price List — [GetProducts](https://docs.aws.amazon.com/boto3/latest/reference/services/pricing/client/get_products.html), [query API](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/using-price-list-query-api.html), [ListPriceLists](https://docs.aws.amazon.com/boto3/latest/reference/services/pricing/client/list_price_lists.html)
- Pricing pages / mechanics — [VPC/NAT pricing](https://docs.aws.amazon.com/vpc/latest/userguide/nat-gateway-pricing.html) & [VPC pricing (public IPv4)](https://aws.amazon.com/vpc/pricing/), [DynamoDB capacity mode](https://docs.aws.amazon.com/us_en/amazondynamodb/latest/developerguide/CostOptimization_TableCapacityMode.html), [DynamoDB throughput utilization](https://aws.amazon.com/blogs/database/how-to-evaluate-throughput-utilization-for-amazon-dynamodb-tables-in-provisioned-mode/)

Market analyses (third-party; paraphrased): [eon.io](https://www.eon.io/blog/aws-cost-optimization-tools), [usage.ai](https://www.usage.ai/blog/best-cloud-cost-management-tools), [cloudfix](https://cloudfix.com/blog/aws-cost-optimization-tools-comparison/), [amnic](https://amnic.com/blogs/aws-cost-optimization-tools), [nOps](https://nops.io/blog/vantage-vs-nops-vs-cloudzero), [CloudZero](https://www.cloudzero.com/blog/cloudhealth-alternatives/); DynamoDB pricing change: [jusdb](https://www.jusdb.com/blog/dynamodb-cost-optimization-a-comprehensive-guide), [oneuptime](https://oneuptime.com/blog/post/2026-02-12-dynamodb-on-demand-vs-provisioned/view); NAT cost tactics: [CloudZero](https://www.cloudzero.com/blog/reduce-nat-gateway-costs/).

Open-source tools (inspiration): [Komiser](https://github.com/tailwarden/komiser), [Cloud Custodian](https://github.com/cloud-custodian/cloud-custodian), [Steampipe mod-aws-thrifty](https://github.com/turbot/steampipe-mod-aws-thrifty), [Flowpipe mod-aws-thrifty](https://github.com/turbot/flowpipe-mod-aws-thrifty), [Infracost](https://github.com/infracost/infracost).

*Content from third-party sources was rephrased for compliance with licensing restrictions.*
