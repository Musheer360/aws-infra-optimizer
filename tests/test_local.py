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
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'lambda'))

def create_mock_event(use_role=False):
    """Create a mock API Gateway event"""
    if use_role:
        body = {
            "clientName": "Test Client",
            "services": ["ec2", "ebs", "rds", "lambda", "eip"],
            "region": "us-east-1",
            "roleArn": "arn:aws:iam::123456789012:role/TestRole"
        }
    else:
        # Get credentials from environment or use dummy values
        body = {
            "clientName": "Test Client",
            "services": ["ec2", "ebs", "rds", "lambda", "eip"],
            "region": os.environ.get("AWS_REGION", "us-east-1"),
            "accessKeyId": os.environ.get("AWS_ACCESS_KEY_ID", "AKIAIOSFODNN7EXAMPLE"),
            "secretAccessKey": os.environ.get("AWS_SECRET_ACCESS_KEY", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY")
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
        
        from lambda_function import generate_word_report
        
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
                    'memory_avg': 'N/A'
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
                    'memory_avg': 25.0
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
                    'confidence': 'High'
                },
                {
                    'volume_id': 'vol-0987654321fedcba0',
                    'size': 500,
                    'type': 'gp2',
                    'issue': 'Unattached',
                    'recommendation': 'Delete if not needed or attach to instance',
                    'monthly_savings': 50.00,
                    'confidence': 'High'
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
                    'confidence': 'Medium'
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
                    'confidence': 'Medium'
                }
            ],
            'eip': [
                {
                    'ip_address': '54.123.45.67',
                    'allocation_id': 'eipalloc-12345678',
                    'status': 'Unattached',
                    'monthly_savings': 3.60,
                    'recommendation': 'Release if not needed',
                    'confidence': 'High'
                }
            ]
        }
        
        total_savings = sum(
            sum(r['monthly_savings'] for r in recs)
            for recs in mock_recommendations.values()
        )
        
        print(f"\n📊 Mock Data Summary:")
        print(f"   EC2 Recommendations: {len(mock_recommendations['ec2'])}")
        print(f"   EBS Recommendations: {len(mock_recommendations['ebs'])}")
        print(f"   RDS Recommendations: {len(mock_recommendations['rds'])}")
        print(f"   Lambda Recommendations: {len(mock_recommendations['lambda'])}")
        print(f"   EIP Recommendations: {len(mock_recommendations['eip'])}")
        print(f"   Total Potential Savings: ${total_savings:.2f}/month")
        
        print("\n🔄 Generating Word document...")
        
        doc = generate_word_report(mock_recommendations, total_savings, "Test Client")
        
        filename = f"Test-Client-InfraOptimization-{datetime.now().strftime('%Y%m%d')}.docx"
        doc.save(filename)
        
        file_size = os.path.getsize(filename)
        
        print(f"\n✅ SUCCESS! Mock report generated: {filename}")
        print(f"   File size: {file_size:,} bytes")
        print(f"\n   Open the file to see the report format!")
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
