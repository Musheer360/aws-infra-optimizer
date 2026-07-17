"""
Unit tests for CostOptimizer360 accuracy helpers and report generation.

These tests are deterministic and do NOT touch AWS - they validate the pure
enrichment logic (Compute Optimizer option selection, OS pricing map, gp2/gp3
sizing, effort/risk/priority scoring) and that every report format renders with
the full enriched data model (including the new services).

Run:  pytest tests/test_optimizer.py -q
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lambda'))

import enrichment  # noqa: E402


# --------------------------------------------------------------------------
# Platform -> pricing mapping
# --------------------------------------------------------------------------
def test_map_platform_linux_default():
    assert enrichment.map_platform_to_pricing('Linux/UNIX') == ('Linux', 'NA')
    assert enrichment.map_platform_to_pricing(None) == ('Linux', 'NA')


def test_map_platform_windows_and_sql():
    assert enrichment.map_platform_to_pricing('Windows') == ('Windows', 'NA')
    assert enrichment.map_platform_to_pricing('Windows with SQL Server Standard') == ('Windows', 'SQL Std')
    assert enrichment.map_platform_to_pricing('Windows with SQL Server Enterprise') == ('Windows', 'SQL Ent')


def test_map_platform_rhel_suse():
    assert enrichment.map_platform_to_pricing('Red Hat Enterprise Linux') == ('RHEL', 'NA')
    assert enrichment.map_platform_to_pricing('SUSE Linux') == ('SUSE', 'NA')


def test_map_platform_unknown_heuristic():
    # Unknown but clearly Windows-ish string still resolves to Windows.
    os_name, pre = enrichment.map_platform_to_pricing('Windows Server 2022 Datacenter')
    assert os_name == 'Windows'


def test_tenancy_mapping():
    assert enrichment.tenancy_to_pricing('default') == 'Shared'
    assert enrichment.tenancy_to_pricing('dedicated') == 'Dedicated'
    assert enrichment.tenancy_to_pricing('host') == 'Host'


# --------------------------------------------------------------------------
# Compute Optimizer option selection (the previously-inverted bug)
# --------------------------------------------------------------------------
def test_pick_option_prefers_rank_one():
    rec = {'recommendationOptions': [
        {'instanceType': 'big', 'rank': 2, 'projectedUtilizationMetrics': [{'value': 5}]},
        {'instanceType': 'right', 'rank': 1, 'projectedUtilizationMetrics': [{'value': 45}]},
    ]}
    assert enrichment.pick_compute_optimizer_option(rec)['instanceType'] == 'right'


def test_pick_option_not_lowest_utilization():
    # Without rank, must NOT pick the lowest-utilization (largest) option;
    # should pick greatest savings within acceptable performance risk.
    rec = {'recommendationOptions': [
        {'instanceType': 'huge', 'performanceRisk': 'VeryLow',
         'projectedUtilizationMetrics': [{'value': 3}],
         'savingsOpportunity': {'estimatedMonthlySavings': {'value': 10}}},
        {'instanceType': 'right', 'performanceRisk': 'Low',
         'projectedUtilizationMetrics': [{'value': 55}],
         'savingsOpportunity': {'estimatedMonthlySavings': {'value': 120}}},
    ]}
    chosen = enrichment.pick_compute_optimizer_option(rec)
    assert chosen['instanceType'] == 'right'  # NOT 'huge'


def test_pick_option_respects_perf_risk_cap():
    rec = {'recommendationOptions': [
        {'instanceType': 'risky', 'performanceRisk': 'VeryHigh',
         'savingsOpportunity': {'estimatedMonthlySavings': {'value': 500}}},
        {'instanceType': 'safe', 'performanceRisk': 'Low',
         'savingsOpportunity': {'estimatedMonthlySavings': {'value': 100}}},
    ]}
    chosen = enrichment.pick_compute_optimizer_option(rec, max_perf_risk=3)
    assert chosen['instanceType'] == 'safe'


def test_co_savings_prefers_after_discounts():
    opt = {
        'savingsOpportunity': {'estimatedMonthlySavings': {'value': 100}},
        'savingsOpportunityAfterDiscounts': {'estimatedMonthlySavings': {'value': 40}},
    }
    val, basis = enrichment.co_option_savings(opt)
    assert val == 40.0 and basis == 'after_discounts'


def test_co_savings_on_demand_fallback():
    opt = {'savingsOpportunity': {'estimatedMonthlySavings': {'value': 75}}}
    val, basis = enrichment.co_option_savings(opt)
    assert val == 75.0 and basis == 'on_demand'


# --------------------------------------------------------------------------
# gp2 -> gp3 sizing
# --------------------------------------------------------------------------
def test_gp2_baseline_iops():
    assert enrichment.gp2_baseline_iops(100) == 300      # 3 * size, min 100
    assert enrichment.gp2_baseline_iops(10) == 100       # floor
    assert enrichment.gp2_baseline_iops(2000) == 6000    # 3 * 2000
    assert enrichment.gp2_baseline_iops(10000) == 16000  # cap


def test_gp3_target_matches_large_gp2():
    # A 2 TiB gp2 has 6000 baseline IOPS -> gp3 must provision 6000 (>3000 free).
    iops, tput = enrichment.gp3_target_performance(2000)
    assert iops == 6000
    assert tput >= 125


def test_gp3_target_small_volume_uses_free_baseline():
    iops, tput = enrichment.gp3_target_performance(100)
    assert iops == 3000 and tput == 125


# --------------------------------------------------------------------------
# RDS class memory
# --------------------------------------------------------------------------
def test_rds_class_memory():
    assert enrichment.rds_class_memory_gb('db.m5.large') == 8
    assert enrichment.rds_class_memory_gb('db.r5.large') == 16
    assert enrichment.rds_class_memory_gb('db.t3.micro') == 1
    assert enrichment.rds_class_memory_gb('db.r5.xlarge') == 32
    assert enrichment.rds_class_memory_gb('bogus') is None


# --------------------------------------------------------------------------
# Scoring + enrichment
# --------------------------------------------------------------------------
def test_priority_score_and_tier():
    high = enrichment.priority_score(1000, 'High', 'Low', 'Low')
    low = enrichment.priority_score(1000, 'Low', 'High', 'High')
    assert high > low
    assert enrichment.priority_tier(high, True) in ('High', 'Quick Win')


def test_enrich_recommendation_fields():
    rec = {'monthly_savings': 50, 'confidence': 'High', 'volume_id': 'vol-1',
           'issue': 'Unattached', 'region': 'us-east-1'}
    enrichment.enrich_recommendation('ebs', rec)
    assert rec['annual_savings'] == 600
    assert rec['effort'] == 'Low' and rec['risk'] == 'Low'
    assert rec['quick_win'] is True
    assert rec['priority'] in ('Quick Win', 'High', 'Medium', 'Low')
    assert 'delete-volume' in rec['remediation']


def test_enrich_recommendations_summary():
    recs = {
        'ebs': [{'monthly_savings': 40, 'confidence': 'High', 'issue': 'Unattached', 'volume_id': 'v'}],
        'ec2': [{'monthly_savings': 500, 'confidence': 'High', 'instance_id': 'i',
                 'effort': 'Medium', 'risk': 'Medium'}],
    }
    metrics = enrichment.enrich_recommendations(recs)
    assert metrics['quick_wins'] >= 1
    assert 'high_priority' in metrics


# --------------------------------------------------------------------------
# Report generation with the full enriched model (needs runtime deps)
# --------------------------------------------------------------------------
def _mock_result():
    recs = {
        'ec2': [{'instance_id': 'i-1', 'current_type': 'm5.xlarge', 'recommended_type': 'm5.large',
                 'current_cost': 140.16, 'recommended_cost': 70.08, 'monthly_savings': 70.08,
                 'reason': 'Overprovisioned', 'confidence': 'High', 'cpu_avg': 8.5,
                 'memory_avg': 'N/A', 'region': 'us-east-1', 'source': 'Compute Optimizer',
                 'savings_basis': 'after_discounts', 'tags': {'Name': 'web'}}],
        'ebs_snapshot': [{'snapshot_id': 'snap-1', 'size': 100, 'age_days': 200,
                          'source_volume': 'vol-x', 'issue': 'Orphaned', 'monthly_savings': 5.0,
                          'recommendation': 'Delete orphaned snapshot', 'confidence': 'High',
                          'region': 'us-east-1', 'tags': {}}],
        'elb': [{'load_balancer_name': 'idle-alb', 'load_balancer_arn': 'arn:...:lb/app/idle-alb/x',
                 'type': 'application', 'metric': 'RequestCount=0 over 14d', 'monthly_savings': 16.43,
                 'reason': 'No traffic in 14 days', 'recommendation': 'Delete idle load balancer',
                 'confidence': 'High', 'region': 'us-east-1', 'tags': {}}],
        'savings_plan': [{'type': 'Compute Savings Plan', 'term': 'One Year',
                          'payment_option': 'No Upfront', 'hourly_commitment': '2.50',
                          'estimated_savings_pct': '28', 'monthly_savings': 300.0,
                          'savings_basis': 'commitment_purchase', 'recommendation': 'Purchase SP',
                          'confidence': 'High', 'region': 'global', 'tags': {}}],
        's3': [{'bucket_name': 'b1', 'region': 'us-east-1', 'issues': 'No lifecycle policy',
                'recommendation': 'Add lifecycle', 'monthly_savings': 0.0, 'confidence': 'Medium',
                'tags': {}}],
    }
    enrichment.enrich_recommendations(recs)
    return {
        'recommendations': recs,
        'total_savings': 91.51,
        'commitment_savings': 300.0,
        'ri_sp_summary': {'total_running_instances': 10, 'ri_covered_instances': 3,
                          'ri_coverage_pct': 30.0, 'sp_coverage_pct': 12.0,
                          'active_ris': [], 'savings_plans': []},
        'forecast': {'month_to_date': 1234.56, 'forecast_month': 2500.0},
        'metrics': {'quick_wins': 2, 'high_priority': 1},
        'regions': ['us-east-1'],
        'services': ['ec2', 'ebs_snapshot', 'elb', 's3', 'commitments'],
        'generated_at': '2026-01-01 00:00:00 UTC',
    }


def test_reports_render_all_formats():
    import importlib
    lf = importlib.import_module('lambda_function')
    result = _mock_result()

    # JSON
    js = lf.generate_json_report(result['recommendations'], result['total_savings'], 'Acme', result['ri_sp_summary'])
    assert 'ec2' in js and 'annual_savings' in js

    # CSV includes new services
    csv_out = lf.generate_csv_report(result['recommendations'], result['total_savings'], 'Acme')
    assert 'EBS_SNAPSHOT' in csv_out and 'ELB' in csv_out and 'SAVINGS_PLAN' in csv_out

    # HTML dashboard is self-contained and embeds the data + renderer
    html = lf.generate_html_report(result, 'Acme')
    assert 'CostOpt360' in html and 'renderDashboard' in html and 'idle-alb' in html

    # XLSX returns non-trivial bytes with a zip signature
    xlsx = lf.generate_xlsx_report(result, 'Acme')
    assert isinstance(xlsx, bytes) and xlsx[:2] == b'PK' and len(xlsx) > 2000

    # Word doc renders and is a valid docx (zip)
    doc = lf.generate_word_report(result['recommendations'], result['total_savings'], 'Acme',
                                  result['ri_sp_summary'], result)
    from io import BytesIO
    buf = BytesIO(); doc.save(buf)
    assert buf.tell() > 5000


def test_scan_result_summary_shape():
    import importlib
    lf = importlib.import_module('lambda_function')
    summary = lf.scan_result_summary(_mock_result())
    for key in ('totalMonthlySavings', 'totalAnnualSavings', 'commitmentMonthlySavings',
                'recommendationCounts', 'quickWins', 'highPriority', 'recommendations', 'forecast'):
        assert key in summary
    assert summary['recommendationCounts']['ec2'] == 1


def test_html_export_escapes_hostile_tags():
    """A malicious resource tag must not break out of the <script> block."""
    import importlib
    lf = importlib.import_module('lambda_function')
    result = _mock_result()
    result['recommendations']['ec2'][0]['tags'] = {
        'Name': '</script><script>alert(document.domain)</script>'
    }
    html = lf.generate_html_report(result, 'Acme')
    # The raw closing-script breakout must not appear; it should be unicode-escaped.
    assert '</script><script>alert' not in html
    assert '\\u003c/script\\u003e' in html or '\\u003cscript\\u003e' in html

