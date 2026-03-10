#!/usr/bin/env python3
"""
Local test script for AWS Infrastructure Optimizer
Tests the Lambda function logic without deploying to AWS
"""

import json
import sys
import os
from datetime import datetime

# Add lambda directory to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lambda'))

def create_mock_event(use_role=False):
    """Create a mock API Gateway event"""
    if use_role:
        body = {
            "clientName": "Test Client",
            "services": ["ec2", "stopped_ec2", "ebs", "rds", "lambda", "eip", "s3", "natgateway", "dynamodb"],
            "regions": ["us-east-1"],
            "region": "us-east-1",
            "roleArn": "arn:aws:iam::123456789012:role/TestRole"
        }
    else:
        # Get credentials from environment or use dummy values
        body = {
            "clientName": "Test Client",
            "services": ["ec2", "stopped_ec2", "ebs", "rds", "lambda", "eip", "s3", "natgateway", "dynamodb"],
            "regions": [os.environ.get("AWS_REGION", "us-east-1")],
            "region": os.environ.get("AWS_REGION", "us-east-1"),
            "accessKeyId": os.environ.get("AWS_ACCESS_KEY_ID", "AKIAIOSFODNN7EXAMPLE"),
            "secretAccessKey": os.environ.get("AWS_SECRET_ACCESS_KEY", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"),
            "exportFormat": "docx"
        }
    
    return {
        "body": json.dumps(body),
        "requestContext": {
            "http": {
                "method": "POST"
            }
        }
    }

def create_mock_context():
    """Create a mock Lambda context"""
    class MockContext:
        function_name = "InfraOptimizerFunction"
        memory_limit_in_mb = 512
        invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:InfraOptimizerFunction"
        aws_request_id = "test-request-id"
    
    return MockContext()

def test_with_real_aws():
    """Test with real AWS credentials"""
    print("=" * 60)
    print("Testing with REAL AWS credentials")
    print("=" * 60)
    
    # Check if AWS credentials are configured
    if not os.environ.get("AWS_ACCESS_KEY_ID"):
        print("\n⚠️  No AWS credentials found in environment")
        print("Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY to test with real AWS")
        print("Or run: aws configure")
        return False
    
    print(f"\n✓ Using AWS credentials from environment")
    print(f"  Region: {os.environ.get('AWS_REGION', 'us-east-1')}")
    
    try:
        from lambda_function import lambda_handler
        
        event = create_mock_event(use_role=False)
        context = create_mock_context()
        
        print("\n🔄 Scanning AWS infrastructure...")
        print("   This will take 1-2 minutes...\n")
        
        response = lambda_handler(event, context)
        
        if response['statusCode'] == 200:
            body = json.loads(response['body'])
            filename = body['filename']
            
            # Save the Word document
            import base64
            file_data = base64.b64decode(body['file'])
            
            with open(filename, 'wb') as f:
                f.write(file_data)
            
            print(f"\n✅ SUCCESS! Report generated: {filename}")
            print(f"   File size: {len(file_data):,} bytes")
            print(f"\n   Open the file to see recommendations!")
            return True
        else:
            print(f"\n❌ Error: {response}")
            return False
            
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_mock_data():
    """Test with mock data (no AWS credentials needed)"""
    print("=" * 60)
    print("Testing with MOCK data (no AWS credentials needed)")
    print("=" * 60)
    
    try:
        # Import after setting mock environment
        os.environ['TESTING_MODE'] = 'true'
        
        from lambda_function import generate_word_report, generate_json_report, generate_csv_report, format_tags_str
        
        # Create mock recommendations
        mock_recommendations = {
            'ec2': [
                {
                    'instance_id': 'i-1234567890abcdef0',
                    'current_type': 'm5.xlarge',
                    'recommended_type': 'm5.large',
                    'current_cost': 140.16,
                    'recommended_cost': 70.08,
                    'monthly_savings': 70.08,
                    'reason': 'Low CPU utilization',
                    'confidence': 'High',
                    'cpu_avg': 8.5,
                    'memory_avg': 'N/A',
                    'region': 'us-east-1',
                    'tags': {'Name': 'web-server-prod', 'Owner': 'platform-team'}
                },
                {
                    'instance_id': 'i-0987654321fedcba0',
                    'current_type': 't3.medium',
                    'recommended_type': 't3.small',
                    'current_cost': 30.37,
                    'recommended_cost': 15.18,
                    'monthly_savings': 15.19,
                    'reason': 'Overprovisioned',
                    'confidence': 'High',
                    'cpu_avg': 12.3,
                    'memory_avg': 25.0,
                    'region': 'us-east-1',
                    'tags': {'Name': 'api-server', 'Team': 'backend'}
                }
            ],
            'stopped_ec2': [
                {
                    'instance_id': 'i-0aaa111222333bbb',
                    'instance_type': 'm5.large',
                    'stopped_days': 45,
                    'attached_volumes': 2,
                    'monthly_savings': 25.60,
                    'reason': 'Instance stopped for 45 days with 2 attached EBS volume(s)',
                    'recommendation': 'Create AMI backup and terminate instance, or delete unneeded EBS volumes',
                    'confidence': 'High',
                    'region': 'us-east-1',
                    'tags': {'Name': 'old-staging-server'}
                }
            ],
            'ebs': [
                {
                    'volume_id': 'vol-1234567890abcdef0',
                    'size': 100,
                    'type': 'gp2',
                    'issue': 'Using gp2',
                    'recommendation': 'Migrate to gp3 for better performance and cost',
                    'monthly_savings': 2.00,
                    'confidence': 'High',
                    'region': 'us-east-1',
                    'tags': {}
                },
                {
                    'volume_id': 'vol-0987654321fedcba0',
                    'size': 500,
                    'type': 'gp2',
                    'issue': 'Unattached',
                    'recommendation': 'Delete if not needed or attach to instance',
                    'monthly_savings': 50.00,
                    'confidence': 'High',
                    'region': 'us-east-1',
                    'tags': {'Name': 'backup-vol'}
                }
            ],
            'rds': [
                {
                    'db_id': 'test-database',
                    'current_class': 'db.m5.large',
                    'recommended_class': 'db.t3.medium',
                    'engine': 'postgres',
                    'current_cost': 140.16,
                    'recommended_cost': 49.64,
                    'monthly_savings': 90.52,
                    'reason': 'Low utilization (CPU: 8.2%, Connections: 2)',
                    'confidence': 'Medium',
                    'region': 'us-east-1',
                    'tags': {'Name': 'staging-db', 'Owner': 'data-team'}
                }
            ],
            'lambda': [
                {
                    'function_name': 'data-processor',
                    'current_memory': 1024,
                    'recommended_memory': 512,
                    'avg_duration': 450,
                    'invocations': 50000,
                    'current_cost': 8.50,
                    'recommended_cost': 4.50,
                    'monthly_savings': 4.00,
                    'confidence': 'Medium',
                    'region': 'us-east-1',
                    'tags': {'Team': 'data-eng'}
                }
            ],
            'eip': [
                {
                    'ip_address': '54.123.45.67',
                    'allocation_id': 'eipalloc-12345678',
                    'status': 'Unattached',
                    'monthly_savings': 3.60,
                    'recommendation': 'Release if not needed',
                    'confidence': 'High',
                    'region': 'us-east-1',
                    'tags': {}
                }
            ],
            's3': [
                {
                    'bucket_name': 'my-data-bucket-prod',
                    'region': 'us-east-1',
                    'issues': 'No lifecycle policy configured, No Intelligent-Tiering configured',
                    'has_lifecycle': False,
                    'has_intelligent_tiering': False,
                    'incomplete_uploads': 0,
                    'recommendation': 'Add lifecycle policy to transition/expire objects; Enable Intelligent-Tiering for automatic cost optimization',
                    'monthly_savings': 0.0,
                    'confidence': 'Medium',
                    'tags': {'Owner': 'data-team'}
                },
                {
                    'bucket_name': 'temp-uploads-bucket',
                    'region': 'us-west-2',
                    'issues': 'No lifecycle policy configured, 5 incomplete multipart upload(s)',
                    'has_lifecycle': False,
                    'has_intelligent_tiering': True,
                    'incomplete_uploads': 5,
                    'recommendation': 'Add lifecycle policy to transition/expire objects; Abort 5 incomplete multipart upload(s) to reclaim storage',
                    'monthly_savings': 0.0,
                    'confidence': 'Medium',
                    'tags': {}
                }
            ],
            'natgateway': [
                {
                    'nat_gateway_id': 'nat-0123456789abcdef0',
                    'vpc_id': 'vpc-12345678',
                    'subnet_id': 'subnet-12345678',
                    'state': 'available',
                    'avg_daily_gb': 0.15,
                    'avg_connections': 5.2,
                    'monthly_cost': 33.95,
                    'monthly_savings': 33.95,
                    'reason': 'Low data transfer (0.15 GB/day avg, 5 avg connections)',
                    'recommendation': 'Consider removing if not needed, or use VPC endpoints for AWS service traffic',
                    'confidence': 'Medium',
                    'region': 'us-east-1',
                    'tags': {'Name': 'nat-dev'}
                }
            ],
            'dynamodb': [
                {
                    'table_name': 'user-sessions',
                    'billing_mode': 'PROVISIONED',
                    'provisioned_rcu': 100,
                    'provisioned_wcu': 50,
                    'avg_rcu': 5.2,
                    'avg_wcu': 2.1,
                    'rcu_utilization': 5.2,
                    'wcu_utilization': 4.2,
                    'current_cost': 33.22,
                    'recommended_cost': 5.10,
                    'monthly_savings': 28.12,
                    'recommendation': 'Consider switching to On-Demand billing mode',
                    'reason': 'Low utilization (RCU: 5.2%, WCU: 4.2%)',
                    'confidence': 'Medium',
                    'region': 'us-east-1',
                    'tags': {'Name': 'sessions-table', 'Team': 'auth'}
                }
            ]
        }
        
        # Mock RI/SP coverage summary
        mock_ri_sp_summary = {
            'total_running_instances': 10,
            'ri_covered_instances': 3,
            'ri_coverage_pct': 30.0,
            'active_ris': [
                {'instance_type': 'm5.large', 'count': 2, 'offering_type': 'All Upfront', 'end_date': '2027-01-15'},
                {'instance_type': 't3.medium', 'count': 1, 'offering_type': 'Partial Upfront', 'end_date': '2026-06-20'}
            ],
            'savings_plans': [],
            'sp_coverage_pct': 0.0
        }
        
        total_savings = sum(
            sum(r['monthly_savings'] for r in recs)
            for recs in mock_recommendations.values()
        )
        
        print(f"\n📊 Mock Data Summary:")
        print(f"   EC2 Recommendations: {len(mock_recommendations['ec2'])}")
        print(f"   Stopped EC2 Recommendations: {len(mock_recommendations['stopped_ec2'])}")
        print(f"   EBS Recommendations: {len(mock_recommendations['ebs'])}")
        print(f"   RDS Recommendations: {len(mock_recommendations['rds'])}")
        print(f"   Lambda Recommendations: {len(mock_recommendations['lambda'])}")
        print(f"   EIP Recommendations: {len(mock_recommendations['eip'])}")
        print(f"   S3 Recommendations: {len(mock_recommendations['s3'])}")
        print(f"   NAT Gateway Recommendations: {len(mock_recommendations['natgateway'])}")
        print(f"   DynamoDB Recommendations: {len(mock_recommendations['dynamodb'])}")
        print(f"   Total Potential Savings: ${total_savings:.2f}/month (${total_savings * 12:.2f}/year)")
        print(f"   RI Coverage: {mock_ri_sp_summary['ri_coverage_pct']}%")
        
        print("\n🔄 Generating Word document...")
        
        doc = generate_word_report(mock_recommendations, total_savings, "Test Client", mock_ri_sp_summary)
        
        filename = f"Test-Client-InfraOptimization-{datetime.now().strftime('%Y%m%d')}.docx"
        doc.save(filename)
        
        file_size = os.path.getsize(filename)
        
        print(f"\n✅ SUCCESS! Mock report generated: {filename}")
        print(f"   File size: {file_size:,} bytes")
        
        # Also generate JSON and CSV reports for testing
        print("\n🔄 Generating JSON report...")
        json_report = generate_json_report(mock_recommendations, total_savings, "Test Client", mock_ri_sp_summary)
        json_filename = f"Test-Client-InfraOptimization-{datetime.now().strftime('%Y%m%d')}.json"
        with open(json_filename, 'w') as f:
            f.write(json_report)
        print(f"   ✅ JSON report generated: {json_filename} ({len(json_report):,} bytes)")
        
        print("\n🔄 Generating CSV report...")
        csv_report = generate_csv_report(mock_recommendations, total_savings, "Test Client")
        csv_filename = f"Test-Client-InfraOptimization-{datetime.now().strftime('%Y%m%d')}.csv"
        with open(csv_filename, 'w') as f:
            f.write(csv_report)
        print(f"   ✅ CSV report generated: {csv_filename} ({len(csv_report):,} bytes)")
        
        print(f"\n   Open the files to see the report formats!")
        print(f"   This shows what a real report would look like.")
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("\n🧪 AWS Infrastructure Optimizer - Local Test\n")
    
    print("Choose test mode:")
    print("1. Test with REAL AWS credentials (scans your actual infrastructure)")
    print("2. Test with MOCK data (no AWS credentials needed)")
    print("3. Run both tests")
    
    choice = input("\nEnter choice (1/2/3): ").strip()
    
    if choice == "1":
        success = test_with_real_aws()
    elif choice == "2":
        success = test_mock_data()
    elif choice == "3":
        print("\n" + "=" * 60)
        print("Running MOCK test first...")
        print("=" * 60)
        mock_success = test_mock_data()
        
        print("\n\n" + "=" * 60)
        print("Running REAL AWS test...")
        print("=" * 60)
        real_success = test_with_real_aws()
        
        success = mock_success and real_success
    else:
        print("Invalid choice")
        return 1
    
    if success:
        print("\n" + "=" * 60)
        print("✅ All tests passed!")
        print("=" * 60)
        return 0
    else:
        print("\n" + "=" * 60)
        print("❌ Tests failed")
        print("=" * 60)
        return 1

if __name__ == "__main__":
    sys.exit(main())
