"""
CostOptimizer360 - pure recommendation-enrichment helpers.

This module contains **pure functions only** (no boto3 / no network) so the
accuracy-critical logic can be unit tested deterministically. It is imported by
lambda_function.py and works both inside the Lambda zip (task root on sys.path)
and the local Flask server (lambda dir inserted on sys.path).

Responsibilities:
  * Map EC2 PlatformDetails -> AWS Price List API filter values (OS-aware pricing).
  * Select the correct AWS Compute Optimizer recommendation option (rank/risk/savings)
    instead of the previously-inverted min(projectedUtilization) heuristic.
  * Extract AWS-provided savings (On-Demand vs after-discount) from an option.
  * Derive gp2 baseline IOPS/throughput so gp2->gp3 savings are not overstated.
  * Attach effort / risk / priority / quick-win / annualized savings and a
    remediation snippet to every recommendation so the report and dashboard can
    prioritize by value-vs-effort (the #1 FinOps pain point).
"""

# ---------------------------------------------------------------------------
# EC2 platform -> Price List API filter mapping
# ---------------------------------------------------------------------------
# EC2 DescribeInstances returns PlatformDetails (e.g. "Linux/UNIX", "Windows",
# "Red Hat Enterprise Linux", "Windows with SQL Server Standard"). These map to
# the AWS Price List `operatingSystem` and `preInstalledSw` filter values.
# Pricing Linux for a Windows box understates cost by ~2x, so this matters a lot.
_PLATFORM_DETAILS_MAP = {
    'Linux/UNIX': ('Linux', 'NA'),
    'Ubuntu Pro': ('Linux', 'NA'),
    'Red Hat Enterprise Linux': ('RHEL', 'NA'),
    'Red Hat Enterprise Linux with HA': ('Red Hat Enterprise Linux with HA', 'NA'),
    'Red Hat Enterprise Linux with SQL Server Standard': ('RHEL', 'SQL Std'),
    'Red Hat Enterprise Linux with SQL Server Enterprise': ('RHEL', 'SQL Ent'),
    'Red Hat Enterprise Linux with SQL Server Web': ('RHEL', 'SQL Web'),
    'SUSE Linux': ('SUSE', 'NA'),
    'Windows': ('Windows', 'NA'),
    'Windows BYOL': ('Windows', 'NA'),
    'Windows with SQL Server Standard': ('Windows', 'SQL Std'),
    'Windows with SQL Server Web': ('Windows', 'SQL Web'),
    'Windows with SQL Server Enterprise': ('Windows', 'SQL Ent'),
    'Linux with SQL Server Standard': ('Linux', 'SQL Std'),
    'Linux with SQL Server Web': ('Linux', 'SQL Web'),
    'Linux with SQL Server Enterprise': ('Linux', 'SQL Ent'),
}


def map_platform_to_pricing(platform_details):
    """Return (operating_system, pre_installed_sw) Price List filter values.

    Falls back to the most common ('Linux', 'NA') for unknown platforms so we
    never crash, but the mapping covers all the platforms that materially change
    the hourly price (Windows, RHEL, SUSE, SQL Server editions).
    """
    key = (platform_details or 'Linux/UNIX').strip()
    if key in _PLATFORM_DETAILS_MAP:
        return _PLATFORM_DETAILS_MAP[key]
    # Heuristic fallback for platform strings we did not enumerate explicitly.
    lowered = key.lower()
    if 'windows' in lowered:
        pre = 'NA'
        if 'sql server enterprise' in lowered:
            pre = 'SQL Ent'
        elif 'sql server web' in lowered:
            pre = 'SQL Web'
        elif 'sql server' in lowered:
            pre = 'SQL Std'
        return ('Windows', pre)
    if 'red hat' in lowered or 'rhel' in lowered:
        return ('RHEL', 'NA')
    if 'suse' in lowered:
        return ('SUSE', 'NA')
    return ('Linux', 'NA')


def tenancy_to_pricing(tenancy):
    """Map EC2 Placement.Tenancy to Price List `tenancy` value."""
    return {'default': 'Shared', 'dedicated': 'Dedicated', 'host': 'Host'}.get(
        (tenancy or 'default').lower(), 'Shared'
    )


# ---------------------------------------------------------------------------
# AWS Compute Optimizer option selection
# ---------------------------------------------------------------------------
_PERF_RISK_RANK = {'VeryLow': 1, 'Low': 2, 'Medium': 3, 'High': 4, 'VeryHigh': 5}


def pick_compute_optimizer_option(rec, max_perf_risk=3):
    """Select the best rightsizing option from a Compute Optimizer recommendation.

    AWS ranks options with `rank` (1 == AWS's balanced top pick). The previous
    code used ``min(projectedUtilizationMetrics.value)`` which selects the option
    whose projected CPU stays *lowest* -> the largest / least-saving instance.
    That is inverted. We instead:
      1. Prefer the option AWS ranked #1.
      2. Otherwise keep options whose performanceRisk is acceptable and choose
         the one with the greatest AWS-estimated monthly savings.
    """
    options = rec.get('recommendationOptions') or []
    if not options:
        return None

    ranked = [o for o in options if o.get('rank') == 1]
    if ranked:
        return ranked[0]

    def _savings(o):
        val, _ = co_option_savings(o)
        return val or 0.0

    acceptable = [
        o for o in options
        if _PERF_RISK_RANK.get(o.get('performanceRisk', 'High'), 4) <= max_perf_risk
    ]
    pool = acceptable or options
    return max(pool, key=_savings)


def co_option_savings(option):
    """Return (monthly_savings, basis) from a Compute Optimizer option.

    Prefers ``savingsOpportunityAfterDiscounts`` (nets out existing RI/SP
    commitments -> avoids overstating savings for covered resources). Falls back
    to the On-Demand ``savingsOpportunity``. Returns (None, None) when absent.
    """
    if not option:
        return None, None
    after = (option.get('savingsOpportunityAfterDiscounts') or {}).get(
        'estimatedMonthlySavings', {}
    ).get('value')
    if after is not None:
        try:
            return float(after), 'after_discounts'
        except (TypeError, ValueError):
            pass
    on_demand = (option.get('savingsOpportunity') or {}).get(
        'estimatedMonthlySavings', {}
    ).get('value')
    if on_demand is not None:
        try:
            return float(on_demand), 'on_demand'
        except (TypeError, ValueError):
            pass
    return None, None


# ---------------------------------------------------------------------------
# EBS gp2 -> gp3 sizing
# ---------------------------------------------------------------------------
def gp2_baseline_iops(size_gb):
    """gp2 provisions 3 IOPS/GiB (min 100, max 16000).

    A >~334 GiB gp2 volume already exceeds gp3's free 3,000 IOPS baseline, so a
    faithful gp3 replacement must pay for the extra IOPS. Ignoring this overstates
    gp2->gp3 savings and can silently reduce performance after migration.
    """
    try:
        size_gb = float(size_gb)
    except (TypeError, ValueError):
        return 100
    return int(min(max(100, 3 * size_gb), 16000))


def gp2_baseline_throughput(size_gb):
    """Approximate gp2 sustained throughput (MB/s).

    gp2 delivers up to 250 MB/s for volumes >= ~334 GiB; smaller volumes stay
    at/under gp3's free 125 MB/s baseline, so we treat those as 125 (no extra
    gp3 throughput cost) and only charge the extra for large volumes.
    """
    try:
        size_gb = float(size_gb)
    except (TypeError, ValueError):
        return 125
    return 250 if size_gb >= 334 else 125


def gp3_target_performance(size_gb):
    """Return (iops, throughput) gp3 must provision to match a gp2 volume."""
    iops = max(3000, gp2_baseline_iops(size_gb))
    throughput = max(125, gp2_baseline_throughput(size_gb))
    return iops, throughput


# ---------------------------------------------------------------------------
# RDS instance-class memory (approx GiB) for relative memory-pressure checks
# ---------------------------------------------------------------------------
_RDS_SIZE_MULT = {
    'micro': 0.125, 'small': 0.25, 'medium': 0.5, 'large': 1, 'xlarge': 2,
    '2xlarge': 4, '4xlarge': 8, '8xlarge': 16, '9xlarge': 18, '12xlarge': 24,
    '16xlarge': 32, '24xlarge': 48, '32xlarge': 64,
}


def rds_class_memory_gb(db_class):
    """Approximate RAM (GiB) for an RDS instance class like 'db.m5.large'.

    Memory-optimized families (r/x/z) start at 16 GiB for .large; general
    purpose/burstable (t/m/c) start at 8 GiB and double per size step. Returns
    None for unknown classes so callers can fall back. Enables a *relative*
    memory-pressure threshold instead of a flat 500 MB that is wrong across sizes.
    """
    if not db_class or not db_class.startswith('db.'):
        return None
    parts = db_class.split('.')
    if len(parts) != 3:
        return None
    family, size = parts[1], parts[2]
    if size not in _RDS_SIZE_MULT:
        return None
    mem_optimized = family[:1] in ('r', 'x', 'z')
    base_large = 16 if mem_optimized else 8
    return base_large * _RDS_SIZE_MULT[size]


# ---------------------------------------------------------------------------
# Effort / risk / priority scoring + remediation
# ---------------------------------------------------------------------------
# Default action profile per finding type. Scanners may override effort/risk on
# an individual recommendation (e.g. from Compute Optimizer restartNeeded).
_ACTION_PROFILE = {
    'ec2':                {'effort': 'Medium', 'risk': 'Medium'},
    'stopped_ec2':        {'effort': 'Low',    'risk': 'Medium'},
    'ebs':                {'effort': 'Low',    'risk': 'Low'},
    'ebs_snapshot':       {'effort': 'Low',    'risk': 'Medium'},
    'rds':                {'effort': 'Medium', 'risk': 'Medium'},
    'lambda':             {'effort': 'Low',    'risk': 'Low'},
    'eip':                {'effort': 'Low',    'risk': 'Low'},
    'public_ipv4':        {'effort': 'Medium', 'risk': 'Low'},
    'natgateway':         {'effort': 'Medium', 'risk': 'Medium'},
    's3':                 {'effort': 'Low',    'risk': 'Low'},
    'dynamodb':           {'effort': 'Low',    'risk': 'Medium'},
    'elb':                {'effort': 'Low',    'risk': 'Medium'},
    'graviton':           {'effort': 'High',   'risk': 'Medium'},
    'savings_plan':       {'effort': 'Low',    'risk': 'Low'},
    'reserved_instance':  {'effort': 'Low',    'risk': 'Low'},
}

_CONFIDENCE_WEIGHT = {'High': 1.0, 'Medium': 0.75, 'Low': 0.5}
_EFFORT_WEIGHT = {'Low': 1.0, 'Medium': 0.7, 'High': 0.45}
_RISK_WEIGHT = {'Low': 1.0, 'Medium': 0.75, 'High': 0.5}


def priority_score(monthly_savings, confidence, effort, risk):
    """Numeric score (higher == do sooner). Combines $ with confidence/effort/risk."""
    try:
        monthly_savings = float(monthly_savings or 0)
    except (TypeError, ValueError):
        monthly_savings = 0.0
    return round(
        monthly_savings
        * _CONFIDENCE_WEIGHT.get(confidence, 0.6)
        * _EFFORT_WEIGHT.get(effort, 0.7)
        * _RISK_WEIGHT.get(risk, 0.75),
        2,
    )


def priority_tier(score, quick_win):
    """Human-readable tier used for grouping in the dashboard/report."""
    if quick_win and score >= 5:
        return 'Quick Win'
    if score >= 100:
        return 'High'
    if score >= 20:
        return 'Medium'
    return 'Low'


def _remediation_snippet(service, rec):
    """Best-effort AWS CLI snippet a user can adapt. Informational only."""
    region = rec.get('region', '<region>')
    try:
        if service == 'ebs':
            vid = rec.get('volume_id', '<vol-id>')
            if rec.get('issue') == 'Unattached':
                return f"aws ec2 delete-volume --volume-id {vid} --region {region}"
            return (f"aws ec2 modify-volume --volume-id {vid} --volume-type gp3 "
                    f"--region {region}")
        if service == 'ebs_snapshot':
            return (f"aws ec2 delete-snapshot --snapshot-id {rec.get('snapshot_id', '<snap-id>')} "
                    f"--region {region}")
        if service == 'eip':
            return (f"aws ec2 release-address --allocation-id "
                    f"{rec.get('allocation_id', '<alloc-id>')} --region {region}")
        if service == 'ec2':
            return (f"# Stop, change type, then start (requires downtime):\n"
                    f"aws ec2 stop-instances --instance-ids {rec.get('instance_id', '<id>')} --region {region}\n"
                    f"aws ec2 modify-instance-attribute --instance-id {rec.get('instance_id', '<id>')} "
                    f"--instance-type {rec.get('recommended_type', '<type>')} --region {region}\n"
                    f"aws ec2 start-instances --instance-ids {rec.get('instance_id', '<id>')} --region {region}")
        if service == 'stopped_ec2':
            return (f"aws ec2 create-image --instance-id {rec.get('instance_id', '<id>')} "
                    f"--name backup-{rec.get('instance_id', 'id')} --region {region}  "
                    f"# then terminate-instances after verifying the AMI")
        if service == 'lambda':
            return (f"aws lambda update-function-configuration --function-name "
                    f"{rec.get('function_name', '<fn>')} --memory-size "
                    f"{rec.get('recommended_memory', '<mb>')} --region {region}")
        if service == 'rds':
            return (f"aws rds modify-db-instance --db-instance-identifier "
                    f"{rec.get('db_id', '<db>')} --db-instance-class "
                    f"{rec.get('recommended_class', '<class>')} --apply-immediately --region {region}")
        if service == 'dynamodb':
            return (f"aws dynamodb update-table --table-name {rec.get('table_name', '<table>')} "
                    f"--billing-mode PAY_PER_REQUEST --region {region}")
        if service == 'natgateway':
            return (f"# Confirm no required routes, then:\n"
                    f"aws ec2 delete-nat-gateway --nat-gateway-id "
                    f"{rec.get('nat_gateway_id', '<nat-id>')} --region {region}")
        if service == 'elb':
            arn = rec.get('load_balancer_arn')
            if arn:
                return f"aws elbv2 delete-load-balancer --load-balancer-arn {arn} --region {region}"
            return (f"aws elb delete-load-balancer --load-balancer-name "
                    f"{rec.get('load_balancer_name', '<name>')} --region {region}")
        if service == 's3':
            return (f"# Enable Intelligent-Tiering / add a lifecycle policy for "
                    f"{rec.get('bucket_name', '<bucket>')} in the S3 console or via put-bucket-lifecycle-configuration")
        if service == 'graviton':
            return "# Rebuild the workload for arm64 and deploy to a Graviton instance type"
        if service == 'savings_plan':
            return "# Review and purchase in AWS Cost Explorer > Savings Plans > Purchase"
        if service == 'reserved_instance':
            return "# Review and purchase in the EC2/RDS console > Reserved Instances"
    except Exception:
        return ''
    return ''


def enrich_recommendation(service, rec):
    """Attach annualized savings, effort, risk, priority and remediation in place."""
    monthly = rec.get('monthly_savings', 0) or 0
    try:
        monthly = float(monthly)
    except (TypeError, ValueError):
        monthly = 0.0
    rec['annual_savings'] = round(monthly * 12, 2)

    profile = _ACTION_PROFILE.get(service, {'effort': 'Medium', 'risk': 'Medium'})
    # Respect any effort/risk the scanner already set (e.g. from Compute Optimizer).
    effort = rec.get('effort') or profile['effort']
    risk = rec.get('risk') or profile['risk']

    # Rec-specific refinements.
    if service == 'ebs' and rec.get('issue') == 'Unattached':
        risk = 'Low'
    if service == 'eip' and rec.get('status') == 'Unattached':
        effort, risk = 'Low', 'Low'

    confidence = rec.get('confidence', 'Medium')
    score = priority_score(monthly, confidence, effort, risk)
    quick_win = (effort == 'Low' and risk == 'Low' and monthly > 0)

    rec['effort'] = effort
    rec['risk'] = risk
    rec['priority_score'] = score
    rec['quick_win'] = quick_win
    rec['priority'] = priority_tier(score, quick_win)
    if 'savings_basis' not in rec:
        rec['savings_basis'] = 'on_demand'
    if not rec.get('remediation'):
        rec['remediation'] = _remediation_snippet(service, rec)
    return rec


def enrich_recommendations(recommendations):
    """Enrich every recommendation across all services. Returns summary metrics."""
    for service, recs in recommendations.items():
        if isinstance(recs, list):
            for rec in recs:
                enrich_recommendation(service, rec)

    quick_wins = 0
    high_priority = 0
    for recs in recommendations.values():
        if isinstance(recs, list):
            for rec in recs:
                if rec.get('quick_win'):
                    quick_wins += 1
                if rec.get('priority') == 'High':
                    high_priority += 1
    return {'quick_wins': quick_wins, 'high_priority': high_priority}
