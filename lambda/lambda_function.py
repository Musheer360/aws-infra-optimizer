import json
import boto3
import os
from datetime import datetime, timedelta
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import base64
from io import BytesIO

# Global pricing cache (persists across Lambda invocations)
PRICING_CACHE = {}
CACHE_TTL = 3600  # 1 hour in seconds

# Comprehensive region to location mapping for AWS Pricing API
REGION_LOCATION_MAP = {
    'us-east-1': 'US East (N. Virginia)',
    'us-east-2': 'US East (Ohio)',
    'us-west-1': 'US West (N. California)',
    'us-west-2': 'US West (Oregon)',
    'af-south-1': 'Africa (Cape Town)',
    'ap-east-1': 'Asia Pacific (Hong Kong)',
    'ap-south-1': 'Asia Pacific (Mumbai)',
    'ap-south-2': 'Asia Pacific (Hyderabad)',
    'ap-southeast-1': 'Asia Pacific (Singapore)',
    'ap-southeast-2': 'Asia Pacific (Sydney)',
    'ap-southeast-3': 'Asia Pacific (Jakarta)',
    'ap-southeast-4': 'Asia Pacific (Melbourne)',
    'ap-northeast-1': 'Asia Pacific (Tokyo)',
    'ap-northeast-2': 'Asia Pacific (Seoul)',
    'ap-northeast-3': 'Asia Pacific (Osaka)',
    'ca-central-1': 'Canada (Central)',
    'ca-west-1': 'Canada West (Calgary)',
    'eu-central-1': 'EU (Frankfurt)',
    'eu-central-2': 'Europe (Zurich)',
    'eu-west-1': 'EU (Ireland)',
    'eu-west-2': 'EU (London)',
    'eu-west-3': 'EU (Paris)',
    'eu-south-1': 'EU (Milan)',
    'eu-south-2': 'Europe (Spain)',
    'eu-north-1': 'EU (Stockholm)',
    'il-central-1': 'Israel (Tel Aviv)',
    'me-south-1': 'Middle East (Bahrain)',
    'me-central-1': 'Middle East (UAE)',
    'sa-east-1': 'South America (Sao Paulo)',
}

def lambda_handler(event, context):
    allowed_origin = os.environ.get('ALLOWED_ORIGIN', '*')
    
    if event.get('requestContext', {}).get('http', {}).get('method') == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': allowed_origin,
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Allow-Methods': 'POST, OPTIONS'
            },
            'body': ''
        }
    
    body = json.loads(event['body'])
    services = body.get('services', ['ec2', 'ebs', 'rds', 'lambda', 'eip'])
    client_name = body.get('clientName', 'Client')
    
    # Setup session with auth
    if 'roleArn' in body:
        sts = boto3.client('sts')
        assumed_role = sts.assume_role(
            RoleArn=body['roleArn'],
            RoleSessionName='InfraOptimizer360Session'
        )
        session = boto3.Session(
            aws_access_key_id=assumed_role['Credentials']['AccessKeyId'],
            aws_secret_access_key=assumed_role['Credentials']['SecretAccessKey'],
            aws_session_token=assumed_role['Credentials']['SessionToken'],
            region_name=body.get('region', 'us-east-1')
        )
    else:
        # Support for session token (temporary credentials)
        session_kwargs = {
            'aws_access_key_id': body['accessKeyId'],
            'aws_secret_access_key': body['secretAccessKey'],
            'region_name': body.get('region', 'us-east-1')
        }
        # Add session token if provided (for temporary credentials)
        if body.get('sessionToken'):
            session_kwargs['aws_session_token'] = body['sessionToken']
        session = boto3.Session(**session_kwargs)
    
    # Collect recommendations
    recommendations = {}
    total_savings = 0.0
    
    if 'ec2' in services:
        ec2_recs = scan_ec2_instances(session)
        recommendations['ec2'] = ec2_recs
        total_savings += sum(r['monthly_savings'] for r in ec2_recs)
    
    if 'ebs' in services:
        ebs_recs = scan_ebs_volumes(session)
        recommendations['ebs'] = ebs_recs
        total_savings += sum(r['monthly_savings'] for r in ebs_recs)
    
    if 'rds' in services:
        rds_recs = scan_rds_instances(session)
        recommendations['rds'] = rds_recs
        total_savings += sum(r['monthly_savings'] for r in rds_recs)
    
    if 'lambda' in services:
        lambda_recs = scan_lambda_functions(session)
        recommendations['lambda'] = lambda_recs
        total_savings += sum(r['monthly_savings'] for r in lambda_recs)
    
    if 'eip' in services:
        eip_recs = scan_elastic_ips(session)
        recommendations['eip'] = eip_recs
        total_savings += sum(r['monthly_savings'] for r in eip_recs)
    
    # Generate Word document
    doc = generate_word_report(recommendations, total_savings, client_name)
    
    # Save to buffer
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    
    filename = f"{client_name.replace(' ', '-')}-InfraOptimization-{datetime.now().strftime('%Y%m%d')}.docx"
    
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': allowed_origin,
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Allow-Methods': 'POST, OPTIONS'
        },
        'body': json.dumps({
            'file': base64.b64encode(buffer.read()).decode('utf-8'),
            'filename': filename
        })
    }

def scan_ec2_instances(session):
    recommendations = []
    ec2 = session.client('ec2')
    cloudwatch = session.client('cloudwatch')
    compute_optimizer = session.client('compute-optimizer')
    
    # Check for Reserved Instances
    reserved_instances = {}
    try:
        ris = ec2.describe_reserved_instances(Filters=[{'Name': 'state', 'Values': ['active']}])
        for ri in ris['ReservedInstances']:
            instance_type = ri['InstanceType']
            count = ri['InstanceCount']
            reserved_instances[instance_type] = reserved_instances.get(instance_type, 0) + count
    except Exception as e:
        print(f"RI check error: {e}")
    
    # Try Compute Optimizer first (with pagination)
    try:
        paginator_token = None
        while True:
            params = {}
            if paginator_token:
                params['nextToken'] = paginator_token
            
            response = compute_optimizer.get_ec2_instance_recommendations(**params)
            
            for rec in response.get('instanceRecommendations', []):
                if rec['finding'] in ['Overprovisioned', 'Underprovisioned']:
                    instance_id = rec['instanceArn'].split('/')[-1]
                    current_type = rec['currentInstanceType']
                    
                    # Skip if covered by Reserved Instance
                    if reserved_instances.get(current_type, 0) > 0:
                        reserved_instances[current_type] -= 1
                        continue
                    
                    # Get best recommendation
                    options = rec.get('recommendationOptions', [])
                    if options:
                        best = min(options, key=lambda x: x.get('projectedUtilizationMetrics', [{}])[0].get('value', 100))
                        recommended_type = best['instanceType']
                        
                        # Calculate savings with actual pricing
                        current_cost = get_instance_cost(current_type, session.region_name)
                        recommended_cost = get_instance_cost(recommended_type, session.region_name)
                        monthly_savings = (current_cost - recommended_cost) * 730
                        
                        if monthly_savings > 0:
                            recommendations.append({
                                'instance_id': instance_id,
                                'current_type': current_type,
                                'recommended_type': recommended_type,
                                'current_cost': round(current_cost * 730, 2),
                                'recommended_cost': round(recommended_cost * 730, 2),
                                'monthly_savings': round(monthly_savings, 2),
                                'reason': rec['finding'],
                                'confidence': 'High',
                                'cpu_avg': get_metric_value(rec, 'CPU'),
                                'memory_avg': get_metric_value(rec, 'MEMORY')
                            })
            
            paginator_token = response.get('nextToken')
            if not paginator_token:
                break
                
    except Exception as e:
        print(f"Compute Optimizer not available: {e}")
    
    # Fallback: Check for low utilization via CloudWatch (with pagination)
    try:
        # Get all running instances with pagination
        all_instances = []
        paginator = ec2.get_paginator('describe_instances')
        for page in paginator.paginate(Filters=[{'Name': 'instance-state-name', 'Values': ['running']}]):
            for reservation in page['Reservations']:
                all_instances.extend(reservation['Instances'])
        
        # Check for Auto Scaling groups (with pagination)
        asg_instances = set()
        try:
            asg_client = session.client('autoscaling')
            asg_paginator = asg_client.get_paginator('describe_auto_scaling_groups')
            for page in asg_paginator.paginate():
                for asg in page['AutoScalingGroups']:
                    for instance in asg['Instances']:
                        asg_instances.add(instance['InstanceId'])
        except Exception as e:
            print(f"ASG check warning: {e}")
        
        for instance in all_instances:
            instance_id = instance['InstanceId']
            instance_type = instance['InstanceType']
            
            # Skip if already in Compute Optimizer recommendations
            if any(r['instance_id'] == instance_id for r in recommendations):
                continue
            
            # Skip if in Auto Scaling group
            if instance_id in asg_instances:
                continue
            
            # Skip if covered by Reserved Instance
            if reserved_instances.get(instance_type, 0) > 0:
                reserved_instances[instance_type] -= 1
                continue
            
            # Check CPU utilization
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(days=14)
            
            cpu_stats = cloudwatch.get_metric_statistics(
                Namespace='AWS/EC2',
                MetricName='CPUUtilization',
                Dimensions=[{'Name': 'InstanceId', 'Value': instance_id}],
                StartTime=start_time,
                EndTime=end_time,
                Period=86400,
                Statistics=['Average', 'Maximum']
            )
            
            if cpu_stats['Datapoints'] and len(cpu_stats['Datapoints']) > 0:
                avg_cpu = sum(d['Average'] for d in cpu_stats['Datapoints']) / len(cpu_stats['Datapoints'])
                max_cpu = max(d['Maximum'] for d in cpu_stats['Datapoints'])
                
                if avg_cpu < 10 and max_cpu < 30:
                    current_cost = get_instance_cost(instance_type, session.region_name)
                    # Recommend one size smaller
                    smaller_type = get_smaller_instance_type(instance_type)
                    if smaller_type:
                        smaller_cost = get_instance_cost(smaller_type, session.region_name)
                        monthly_savings = (current_cost - smaller_cost) * 730
                        
                        if monthly_savings > 0:
                            recommendations.append({
                                'instance_id': instance_id,
                                'current_type': instance_type,
                                'recommended_type': smaller_type,
                                'current_cost': round(current_cost * 730, 2),
                                'recommended_cost': round(smaller_cost * 730, 2),
                                'monthly_savings': round(monthly_savings, 2),
                                'reason': 'Low CPU utilization',
                                'confidence': 'Medium',
                                'cpu_avg': round(avg_cpu, 1),
                                'memory_avg': 'N/A'
                            })
    except Exception as e:
        print(f"CloudWatch fallback error: {e}")
    
    return recommendations

def scan_ebs_volumes(session):
    recommendations = []
    ec2 = session.client('ec2')
    
    try:
        # Get all volumes with pagination
        all_volumes = []
        paginator = ec2.get_paginator('describe_volumes')
        for page in paginator.paginate():
            all_volumes.extend(page['Volumes'])
        
        for volume in all_volumes:
            volume_id = volume['VolumeId']
            volume_type = volume['VolumeType']
            size = volume['Size']
            state = volume['State']
            iops = volume.get('Iops', 0)
            throughput = volume.get('Throughput', 0)  # Only for gp3
            
            # Unattached volumes
            if state == 'available':
                monthly_cost = calculate_ebs_cost(volume_type, size, session.region_name, iops, throughput)
                recommendations.append({
                    'volume_id': volume_id,
                    'size': size,
                    'type': volume_type,
                    'issue': 'Unattached',
                    'recommendation': 'Delete if not needed or attach to instance',
                    'monthly_savings': round(monthly_cost, 2),
                    'confidence': 'High'
                })
            
            # gp2 to gp3 migration
            elif volume_type == 'gp2':
                current_cost = calculate_ebs_cost('gp2', size, session.region_name, iops, throughput)
                # gp3 base includes 3000 IOPS and 125 MB/s throughput
                gp3_cost = calculate_ebs_cost('gp3', size, session.region_name, 3000, 125)
                monthly_savings = current_cost - gp3_cost
                
                if monthly_savings > 0:
                    recommendations.append({
                        'volume_id': volume_id,
                        'size': size,
                        'type': volume_type,
                        'issue': 'Using gp2',
                        'recommendation': 'Migrate to gp3 for better performance and cost',
                        'monthly_savings': round(monthly_savings, 2),
                        'confidence': 'High'
                    })
    except Exception as e:
        print(f"EBS scan error: {e}")
    
    return recommendations

def scan_rds_instances(session):
    recommendations = []
    rds = session.client('rds')
    cloudwatch = session.client('cloudwatch')
    
    try:
        # Get all RDS instances with pagination
        all_instances = []
        paginator = rds.get_paginator('describe_db_instances')
        for page in paginator.paginate():
            all_instances.extend(page['DBInstances'])
        
        for db in all_instances:
            db_id = db['DBInstanceIdentifier']
            db_class = db['DBInstanceClass']
            engine = db['Engine']
            multi_az = db.get('MultiAZ', False)
            
            # Check CPU utilization
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(days=14)
            
            cpu_stats = cloudwatch.get_metric_statistics(
                Namespace='AWS/RDS',
                MetricName='CPUUtilization',
                Dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': db_id}],
                StartTime=start_time,
                EndTime=end_time,
                Period=86400,
                Statistics=['Average', 'Maximum']
            )
            
            conn_stats = cloudwatch.get_metric_statistics(
                Namespace='AWS/RDS',
                MetricName='DatabaseConnections',
                Dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': db_id}],
                StartTime=start_time,
                EndTime=end_time,
                Period=86400,
                Statistics=['Average', 'Maximum']
            )
            
            # Only proceed if we have valid data points
            if cpu_stats['Datapoints'] and len(cpu_stats['Datapoints']) > 0 and conn_stats['Datapoints'] and len(conn_stats['Datapoints']) > 0:
                avg_cpu = sum(d['Average'] for d in cpu_stats['Datapoints']) / len(cpu_stats['Datapoints'])
                avg_conn = sum(d['Average'] for d in conn_stats['Datapoints']) / len(conn_stats['Datapoints'])
                
                if avg_cpu < 20 and avg_conn < 5:
                    current_cost = get_rds_cost(db_class, engine, session.region_name, multi_az)
                    smaller_class = get_smaller_rds_class(db_class)
                    
                    if smaller_class:
                        smaller_cost = get_rds_cost(smaller_class, engine, session.region_name, multi_az)
                        monthly_savings = (current_cost - smaller_cost) * 730
                        
                        if monthly_savings > 0:
                            recommendations.append({
                                'db_id': db_id,
                                'current_class': db_class,
                                'recommended_class': smaller_class,
                                'engine': engine,
                                'current_cost': round(current_cost * 730, 2),
                                'recommended_cost': round(smaller_cost * 730, 2),
                                'monthly_savings': round(monthly_savings, 2),
                                'reason': f'Low utilization (CPU: {avg_cpu:.1f}%, Connections: {avg_conn:.0f})',
                                'confidence': 'Medium'
                            })
    except Exception as e:
        print(f"RDS scan error: {e}")
    
    return recommendations

def scan_lambda_functions(session):
    recommendations = []
    lambda_client = session.client('lambda')
    cloudwatch = session.client('cloudwatch')
    
    try:
        # Get all Lambda functions with pagination
        all_functions = []
        paginator = lambda_client.get_paginator('list_functions')
        for page in paginator.paginate():
            all_functions.extend(page['Functions'])
        
        for func in all_functions:
            func_name = func['FunctionName']
            memory_size = func['MemorySize']
            
            # Get average duration
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(days=14)
            
            duration_stats = cloudwatch.get_metric_statistics(
                Namespace='AWS/Lambda',
                MetricName='Duration',
                Dimensions=[{'Name': 'FunctionName', 'Value': func_name}],
                StartTime=start_time,
                EndTime=end_time,
                Period=86400,
                Statistics=['Average', 'Maximum']
            )
            
            invocations = cloudwatch.get_metric_statistics(
                Namespace='AWS/Lambda',
                MetricName='Invocations',
                Dimensions=[{'Name': 'FunctionName', 'Value': func_name}],
                StartTime=start_time,
                EndTime=end_time,
                Period=86400,
                Statistics=['Sum']
            )
            
            # Only proceed if we have valid data
            if duration_stats['Datapoints'] and len(duration_stats['Datapoints']) > 0 and invocations['Datapoints'] and len(invocations['Datapoints']) > 0:
                avg_duration = sum(d['Average'] for d in duration_stats['Datapoints']) / len(duration_stats['Datapoints'])
                total_invocations = sum(d['Sum'] for d in invocations['Datapoints'])
                
                # Skip if no meaningful invocations
                if total_invocations < 100:
                    continue
                
                # Check if memory is over-provisioned (duration is very low relative to timeout)
                if memory_size > 512 and avg_duration < 1000:  # Less than 1 second
                    recommended_memory = max(128, memory_size // 2)
                    
                    current_cost = calculate_lambda_cost(memory_size, avg_duration, total_invocations, session.region_name)
                    recommended_cost = calculate_lambda_cost(recommended_memory, avg_duration, total_invocations, session.region_name)
                    monthly_savings = current_cost - recommended_cost
                    
                    if monthly_savings > 1:  # Only recommend if savings > $1/month
                        recommendations.append({
                            'function_name': func_name,
                            'current_memory': memory_size,
                            'recommended_memory': recommended_memory,
                            'avg_duration': round(avg_duration, 0),
                            'invocations': int(total_invocations),
                            'current_cost': round(current_cost, 2),
                            'recommended_cost': round(recommended_cost, 2),
                            'monthly_savings': round(monthly_savings, 2),
                            'confidence': 'Medium'
                        })
    except Exception as e:
        print(f"Lambda scan error: {e}")
    
    return recommendations

def scan_elastic_ips(session):
    recommendations = []
    ec2 = session.client('ec2')
    
    try:
        addresses = ec2.describe_addresses()
        
        # Get real-time EIP pricing
        eip_hourly_cost = get_eip_cost(session.region_name)
        
        for addr in addresses['Addresses']:
            # Check if unattached (handle both VPC and EC2-Classic scenarios)
            is_attached = 'InstanceId' in addr or 'NetworkInterfaceId' in addr
            if not is_attached:
                # Use AllocationId if available (VPC), otherwise use PublicIp as identifier
                allocation_id = addr.get('AllocationId', addr.get('PublicIp', 'N/A'))
                monthly_cost = eip_hourly_cost * 730  # hours per month
                
                recommendations.append({
                    'ip_address': addr['PublicIp'],
                    'allocation_id': allocation_id,
                    'status': 'Unattached',
                    'monthly_savings': round(monthly_cost, 2),
                    'recommendation': 'Release if not needed',
                    'confidence': 'High'
                })
    except Exception as e:
        print(f"EIP scan error: {e}")
    
    return recommendations

def generate_word_report(recommendations, total_savings, client_name):
    doc = Document()
    
    # Title
    title = doc.add_heading('AWS Infrastructure Optimization Report', 0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    # Metadata
    doc.add_paragraph(f'Client: {client_name}')
    doc.add_paragraph(f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")}')
    doc.add_paragraph('')
    
    # Executive Summary
    doc.add_heading('Executive Summary', 1)
    summary = doc.add_paragraph()
    summary.add_run(f'Total Potential Monthly Savings: ${total_savings:,.2f}\n').bold = True
    
    high_priority = sum(len([r for r in recs if r.get('confidence') == 'High']) for recs in recommendations.values())
    medium_priority = sum(len([r for r in recs if r.get('confidence') == 'Medium']) for recs in recommendations.values())
    
    summary.add_run(f'High Priority Recommendations: {high_priority}\n')
    summary.add_run(f'Medium Priority Recommendations: {medium_priority}\n')
    doc.add_paragraph('')
    
    # EC2 Instances
    if 'ec2' in recommendations and recommendations['ec2']:
        doc.add_heading('EC2 Instance Recommendations', 1)
        table = doc.add_table(rows=1, cols=8)
        table.style = 'Light Grid Accent 1'
        
        headers = ['Instance ID', 'Current Type', 'Recommended', 'Current Cost', 'New Cost', 'Monthly Savings', 'Reason', 'Confidence']
        for i, header in enumerate(headers):
            cell = table.rows[0].cells[i]
            cell.text = header
            set_cell_background(cell, 'FFFF00')
            cell.paragraphs[0].runs[0].font.bold = True
        
        for rec in recommendations['ec2']:
            row = table.add_row()
            row.cells[0].text = rec['instance_id']
            row.cells[1].text = rec['current_type']
            row.cells[2].text = rec['recommended_type']
            row.cells[3].text = f"${rec['current_cost']:.2f}"
            row.cells[4].text = f"${rec['recommended_cost']:.2f}"
            row.cells[5].text = f"${rec['monthly_savings']:.2f}"
            row.cells[6].text = f"{rec['reason']} (CPU: {rec['cpu_avg']}%)"
            row.cells[7].text = rec['confidence']
            
            # Color code by confidence
            if rec['confidence'] == 'High':
                set_cell_background(row.cells[7], '90EE90')
        
        doc.add_paragraph('')
    
    # EBS Volumes
    if 'ebs' in recommendations and recommendations['ebs']:
        doc.add_heading('EBS Volume Recommendations', 1)
        table = doc.add_table(rows=1, cols=6)
        table.style = 'Light Grid Accent 1'
        
        headers = ['Volume ID', 'Size (GB)', 'Type', 'Issue', 'Recommendation', 'Monthly Savings']
        for i, header in enumerate(headers):
            cell = table.rows[0].cells[i]
            cell.text = header
            set_cell_background(cell, 'FFFF00')
            cell.paragraphs[0].runs[0].font.bold = True
        
        for rec in recommendations['ebs']:
            row = table.add_row()
            row.cells[0].text = rec['volume_id']
            row.cells[1].text = str(rec['size'])
            row.cells[2].text = rec['type']
            row.cells[3].text = rec['issue']
            row.cells[4].text = rec['recommendation']
            row.cells[5].text = f"${rec['monthly_savings']:.2f}"
        
        doc.add_paragraph('')
    
    # RDS Instances
    if 'rds' in recommendations and recommendations['rds']:
        doc.add_heading('RDS Instance Recommendations', 1)
        table = doc.add_table(rows=1, cols=7)
        table.style = 'Light Grid Accent 1'
        
        headers = ['DB Identifier', 'Current Class', 'Recommended', 'Current Cost', 'New Cost', 'Monthly Savings', 'Reason']
        for i, header in enumerate(headers):
            cell = table.rows[0].cells[i]
            cell.text = header
            set_cell_background(cell, 'FFFF00')
            cell.paragraphs[0].runs[0].font.bold = True
        
        for rec in recommendations['rds']:
            row = table.add_row()
            row.cells[0].text = rec['db_id']
            row.cells[1].text = rec['current_class']
            row.cells[2].text = rec['recommended_class']
            row.cells[3].text = f"${rec['current_cost']:.2f}"
            row.cells[4].text = f"${rec['recommended_cost']:.2f}"
            row.cells[5].text = f"${rec['monthly_savings']:.2f}"
            row.cells[6].text = rec['reason']
        
        doc.add_paragraph('')
    
    # Lambda Functions
    if 'lambda' in recommendations and recommendations['lambda']:
        doc.add_heading('Lambda Function Recommendations', 1)
        table = doc.add_table(rows=1, cols=7)
        table.style = 'Light Grid Accent 1'
        
        headers = ['Function Name', 'Current Memory', 'Recommended', 'Avg Duration (ms)', 'Current Cost', 'New Cost', 'Monthly Savings']
        for i, header in enumerate(headers):
            cell = table.rows[0].cells[i]
            cell.text = header
            set_cell_background(cell, 'FFFF00')
            cell.paragraphs[0].runs[0].font.bold = True
        
        for rec in recommendations['lambda']:
            row = table.add_row()
            row.cells[0].text = rec['function_name']
            row.cells[1].text = f"{rec['current_memory']} MB"
            row.cells[2].text = f"{rec['recommended_memory']} MB"
            row.cells[3].text = str(int(rec['avg_duration']))
            row.cells[4].text = f"${rec['current_cost']:.2f}"
            row.cells[5].text = f"${rec['recommended_cost']:.2f}"
            row.cells[6].text = f"${rec['monthly_savings']:.2f}"
        
        doc.add_paragraph('')
    
    # Elastic IPs
    if 'eip' in recommendations and recommendations['eip']:
        doc.add_heading('Elastic IP Recommendations', 1)
        table = doc.add_table(rows=1, cols=4)
        table.style = 'Light Grid Accent 1'
        
        headers = ['IP Address', 'Status', 'Monthly Cost', 'Recommendation']
        for i, header in enumerate(headers):
            cell = table.rows[0].cells[i]
            cell.text = header
            set_cell_background(cell, 'FFFF00')
            cell.paragraphs[0].runs[0].font.bold = True
        
        for rec in recommendations['eip']:
            row = table.add_row()
            row.cells[0].text = rec['ip_address']
            row.cells[1].text = rec['status']
            row.cells[2].text = f"${rec['monthly_savings']:.2f}"
            row.cells[3].text = rec['recommendation']
        
        doc.add_paragraph('')
    
    # Implementation Notes
    doc.add_heading('Implementation Notes', 1)
    doc.add_paragraph('• High confidence recommendations are based on AWS Compute Optimizer ML analysis')
    doc.add_paragraph('• Medium confidence recommendations are based on 14-day CloudWatch metrics')
    doc.add_paragraph('• Test changes in non-production environments first')
    doc.add_paragraph('• Consider reserved instances and savings plans before making changes')
    doc.add_paragraph('• Monitor performance after implementing recommendations')
    
    return doc

def set_cell_background(cell, color):
    """Set cell background color (hex color without #)"""
    shading_elm = OxmlElement('w:shd')
    shading_elm.set(qn('w:fill'), color)
    cell._element.get_or_add_tcPr().append(shading_elm)

def get_metric_value(rec, metric_name):
    """Extract metric value from Compute Optimizer recommendation"""
    for metric in rec.get('utilizationMetrics', []):
        if metric['name'] == metric_name:
            return round(metric['value'], 1)
    return 'N/A'

def get_instance_cost(instance_type, region):
    """Get actual EC2 pricing from AWS Price List API with caching"""
    cache_key = f"ec2_{instance_type}_{region}"
    
    # Check cache first
    if cache_key in PRICING_CACHE:
        cached_data = PRICING_CACHE[cache_key]
        if datetime.now().timestamp() - cached_data['timestamp'] < CACHE_TTL:
            return cached_data['price']
    
    try:
        pricing_client = boto3.client('pricing', region_name='us-east-1')
        
        location = REGION_LOCATION_MAP.get(region, 'US East (N. Virginia)')
        
        response = pricing_client.get_products(
            ServiceCode='AmazonEC2',
            Filters=[
                {'Type': 'TERM_MATCH', 'Field': 'instanceType', 'Value': instance_type},
                {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': location},
                {'Type': 'TERM_MATCH', 'Field': 'operatingSystem', 'Value': 'Linux'},
                {'Type': 'TERM_MATCH', 'Field': 'tenancy', 'Value': 'Shared'},
                {'Type': 'TERM_MATCH', 'Field': 'preInstalledSw', 'Value': 'NA'},
                {'Type': 'TERM_MATCH', 'Field': 'capacitystatus', 'Value': 'Used'}
            ],
            MaxResults=10
        )
        
        if response['PriceList']:
            # Parse all results and find the on-demand price
            for price_item in response['PriceList']:
                price_data = json.loads(price_item)
                on_demand = price_data.get('terms', {}).get('OnDemand', {})
                if on_demand:
                    price_dimensions = list(list(on_demand.values())[0]['priceDimensions'].values())
                    for dim in price_dimensions:
                        price_per_unit = dim.get('pricePerUnit', {}).get('USD')
                        if price_per_unit and float(price_per_unit) > 0:
                            price_per_hour = float(price_per_unit)
                            
                            # Cache the result
                            PRICING_CACHE[cache_key] = {
                                'price': price_per_hour,
                                'timestamp': datetime.now().timestamp()
                            }
                            return price_per_hour
    except Exception as e:
        print(f"Price API error for {instance_type}: {e}")
    
    # Fallback to expanded hardcoded prices (us-east-1 as baseline)
    pricing = {
        # T2 family
        't2.nano': 0.0058, 't2.micro': 0.0116, 't2.small': 0.023, 't2.medium': 0.0464, 
        't2.large': 0.0928, 't2.xlarge': 0.1856, 't2.2xlarge': 0.3712,
        # T3 family
        't3.nano': 0.0052, 't3.micro': 0.0104, 't3.small': 0.0208, 't3.medium': 0.0416, 
        't3.large': 0.0832, 't3.xlarge': 0.1664, 't3.2xlarge': 0.3328,
        # T3a family
        't3a.nano': 0.0047, 't3a.micro': 0.0094, 't3a.small': 0.0188, 't3a.medium': 0.0376, 
        't3a.large': 0.0752, 't3a.xlarge': 0.1504, 't3a.2xlarge': 0.3008,
        # T4g family (Graviton)
        't4g.nano': 0.0042, 't4g.micro': 0.0084, 't4g.small': 0.0168, 't4g.medium': 0.0336,
        't4g.large': 0.0672, 't4g.xlarge': 0.1344, 't4g.2xlarge': 0.2688,
        # M5 family
        'm5.large': 0.096, 'm5.xlarge': 0.192, 'm5.2xlarge': 0.384, 'm5.4xlarge': 0.768, 
        'm5.8xlarge': 1.536, 'm5.12xlarge': 2.304, 'm5.16xlarge': 3.072, 'm5.24xlarge': 4.608,
        # M5a family
        'm5a.large': 0.086, 'm5a.xlarge': 0.172, 'm5a.2xlarge': 0.344, 'm5a.4xlarge': 0.688,
        'm5a.8xlarge': 1.376, 'm5a.12xlarge': 2.064, 'm5a.16xlarge': 2.752, 'm5a.24xlarge': 4.128,
        # M6i family
        'm6i.large': 0.096, 'm6i.xlarge': 0.192, 'm6i.2xlarge': 0.384, 'm6i.4xlarge': 0.768, 
        'm6i.8xlarge': 1.536, 'm6i.12xlarge': 2.304, 'm6i.16xlarge': 3.072, 'm6i.24xlarge': 4.608,
        # M6g family (Graviton)
        'm6g.large': 0.077, 'm6g.xlarge': 0.154, 'm6g.2xlarge': 0.308, 'm6g.4xlarge': 0.616,
        'm6g.8xlarge': 1.232, 'm6g.12xlarge': 1.848, 'm6g.16xlarge': 2.464,
        # M7i family
        'm7i.large': 0.1008, 'm7i.xlarge': 0.2016, 'm7i.2xlarge': 0.4032, 'm7i.4xlarge': 0.8064,
        'm7i.8xlarge': 1.6128, 'm7i.12xlarge': 2.4192, 'm7i.16xlarge': 3.2256, 'm7i.24xlarge': 4.8384,
        # M7a family
        'm7a.large': 0.1008, 'm7a.xlarge': 0.2016, 'm7a.2xlarge': 0.4032, 'm7a.4xlarge': 0.8064, 
        'm7a.8xlarge': 1.6128, 'm7a.12xlarge': 2.4192, 'm7a.16xlarge': 3.2256, 'm7a.24xlarge': 4.8384,
        # C5 family
        'c5.large': 0.085, 'c5.xlarge': 0.17, 'c5.2xlarge': 0.34, 'c5.4xlarge': 0.68, 
        'c5.9xlarge': 1.53, 'c5.12xlarge': 2.04, 'c5.18xlarge': 3.06, 'c5.24xlarge': 4.08,
        # C5a family
        'c5a.large': 0.077, 'c5a.xlarge': 0.154, 'c5a.2xlarge': 0.308, 'c5a.4xlarge': 0.616,
        'c5a.8xlarge': 1.232, 'c5a.12xlarge': 1.848, 'c5a.16xlarge': 2.464, 'c5a.24xlarge': 3.696,
        # C6i family
        'c6i.large': 0.085, 'c6i.xlarge': 0.17, 'c6i.2xlarge': 0.34, 'c6i.4xlarge': 0.68, 
        'c6i.8xlarge': 1.36, 'c6i.12xlarge': 2.04, 'c6i.16xlarge': 2.72, 'c6i.24xlarge': 4.08,
        # C6g family (Graviton)
        'c6g.large': 0.068, 'c6g.xlarge': 0.136, 'c6g.2xlarge': 0.272, 'c6g.4xlarge': 0.544, 
        'c6g.8xlarge': 1.088, 'c6g.12xlarge': 1.632, 'c6g.16xlarge': 2.176,
        # C7i family
        'c7i.large': 0.0892, 'c7i.xlarge': 0.1785, 'c7i.2xlarge': 0.357, 'c7i.4xlarge': 0.714,
        'c7i.8xlarge': 1.428, 'c7i.12xlarge': 2.142, 'c7i.16xlarge': 2.856, 'c7i.24xlarge': 4.284,
        # R5 family
        'r5.large': 0.126, 'r5.xlarge': 0.252, 'r5.2xlarge': 0.504, 'r5.4xlarge': 1.008, 
        'r5.8xlarge': 2.016, 'r5.12xlarge': 3.024, 'r5.16xlarge': 4.032, 'r5.24xlarge': 6.048,
        # R5a family
        'r5a.large': 0.113, 'r5a.xlarge': 0.226, 'r5a.2xlarge': 0.452, 'r5a.4xlarge': 0.904,
        'r5a.8xlarge': 1.808, 'r5a.12xlarge': 2.712, 'r5a.16xlarge': 3.616, 'r5a.24xlarge': 5.424,
        # R6i family
        'r6i.large': 0.126, 'r6i.xlarge': 0.252, 'r6i.2xlarge': 0.504, 'r6i.4xlarge': 1.008, 
        'r6i.8xlarge': 2.016, 'r6i.12xlarge': 3.024, 'r6i.16xlarge': 4.032, 'r6i.24xlarge': 6.048,
        # R6g family (Graviton)
        'r6g.large': 0.1008, 'r6g.xlarge': 0.2016, 'r6g.2xlarge': 0.4032, 'r6g.4xlarge': 0.8064,
        'r6g.8xlarge': 1.6128, 'r6g.12xlarge': 2.4192, 'r6g.16xlarge': 3.2256,
        # I3 family (Storage optimized)
        'i3.large': 0.156, 'i3.xlarge': 0.312, 'i3.2xlarge': 0.624, 'i3.4xlarge': 1.248,
        'i3.8xlarge': 2.496, 'i3.16xlarge': 4.992,
        # D2 family (Dense storage)
        'd2.xlarge': 0.69, 'd2.2xlarge': 1.38, 'd2.4xlarge': 2.76, 'd2.8xlarge': 5.52,
    }
    fallback_price = pricing.get(instance_type, 0.10)
    
    # Cache fallback too
    PRICING_CACHE[cache_key] = {
        'price': fallback_price,
        'timestamp': datetime.now().timestamp()
    }
    return fallback_price

def get_rds_cost(db_class, engine, region, multi_az=False):
    """Get actual RDS pricing with caching"""
    cache_key = f"rds_{db_class}_{engine}_{region}_{'multiaz' if multi_az else 'singleaz'}"
    
    # Check cache first
    if cache_key in PRICING_CACHE:
        cached_data = PRICING_CACHE[cache_key]
        if datetime.now().timestamp() - cached_data['timestamp'] < CACHE_TTL:
            return cached_data['price']
    
    try:
        pricing_client = boto3.client('pricing', region_name='us-east-1')
        
        location = REGION_LOCATION_MAP.get(region, 'US East (N. Virginia)')
        
        # Map engine names to pricing API values
        engine_map = {
            'postgres': 'PostgreSQL', 'mysql': 'MySQL', 'mariadb': 'MariaDB',
            'oracle-se': 'Oracle', 'oracle-se1': 'Oracle', 'oracle-se2': 'Oracle', 'oracle-ee': 'Oracle',
            'sqlserver-se': 'SQL Server', 'sqlserver-ee': 'SQL Server', 'sqlserver-ex': 'SQL Server', 'sqlserver-web': 'SQL Server',
            'aurora': 'Aurora MySQL', 'aurora-mysql': 'Aurora MySQL', 'aurora-postgresql': 'Aurora PostgreSQL'
        }
        db_engine = engine_map.get(engine.lower(), 'MySQL')
        
        deployment_option = 'Multi-AZ' if multi_az else 'Single-AZ'
        
        response = pricing_client.get_products(
            ServiceCode='AmazonRDS',
            Filters=[
                {'Type': 'TERM_MATCH', 'Field': 'instanceType', 'Value': db_class},
                {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': location},
                {'Type': 'TERM_MATCH', 'Field': 'databaseEngine', 'Value': db_engine},
                {'Type': 'TERM_MATCH', 'Field': 'deploymentOption', 'Value': deployment_option}
            ],
            MaxResults=10
        )
        
        if response['PriceList']:
            for price_item in response['PriceList']:
                price_data = json.loads(price_item)
                on_demand = price_data.get('terms', {}).get('OnDemand', {})
                if on_demand:
                    price_dimensions = list(list(on_demand.values())[0]['priceDimensions'].values())
                    for dim in price_dimensions:
                        price_per_unit = dim.get('pricePerUnit', {}).get('USD')
                        if price_per_unit and float(price_per_unit) > 0:
                            price_per_hour = float(price_per_unit)
                            
                            # Cache the result
                            PRICING_CACHE[cache_key] = {
                                'price': price_per_hour,
                                'timestamp': datetime.now().timestamp()
                            }
                            return price_per_hour
    except Exception as e:
        print(f"RDS Price API error for {db_class}: {e}")
    
    # Fallback to expanded hardcoded prices (Single-AZ, us-east-1)
    pricing = {
        # T3 family
        'db.t3.micro': 0.017, 'db.t3.small': 0.034, 'db.t3.medium': 0.068, 
        'db.t3.large': 0.136, 'db.t3.xlarge': 0.272, 'db.t3.2xlarge': 0.544,
        # T4g family (Graviton)
        'db.t4g.micro': 0.016, 'db.t4g.small': 0.032, 'db.t4g.medium': 0.064, 
        'db.t4g.large': 0.128, 'db.t4g.xlarge': 0.256, 'db.t4g.2xlarge': 0.512,
        # M5 family
        'db.m5.large': 0.192, 'db.m5.xlarge': 0.384, 'db.m5.2xlarge': 0.768, 
        'db.m5.4xlarge': 1.536, 'db.m5.8xlarge': 3.072, 'db.m5.12xlarge': 4.608,
        'db.m5.16xlarge': 6.144, 'db.m5.24xlarge': 9.216,
        # M6i family
        'db.m6i.large': 0.192, 'db.m6i.xlarge': 0.384, 'db.m6i.2xlarge': 0.768, 
        'db.m6i.4xlarge': 1.536, 'db.m6i.8xlarge': 3.072, 'db.m6i.12xlarge': 4.608,
        'db.m6i.16xlarge': 6.144, 'db.m6i.24xlarge': 9.216, 'db.m6i.32xlarge': 12.288,
        # M6g family (Graviton)
        'db.m6g.large': 0.1536, 'db.m6g.xlarge': 0.3072, 'db.m6g.2xlarge': 0.6144,
        'db.m6g.4xlarge': 1.2288, 'db.m6g.8xlarge': 2.4576, 'db.m6g.12xlarge': 3.6864,
        'db.m6g.16xlarge': 4.9152,
        # R5 family
        'db.r5.large': 0.24, 'db.r5.xlarge': 0.48, 'db.r5.2xlarge': 0.96, 
        'db.r5.4xlarge': 1.92, 'db.r5.8xlarge': 3.84, 'db.r5.12xlarge': 5.76,
        'db.r5.16xlarge': 7.68, 'db.r5.24xlarge': 11.52,
        # R6i family
        'db.r6i.large': 0.24, 'db.r6i.xlarge': 0.48, 'db.r6i.2xlarge': 0.96, 
        'db.r6i.4xlarge': 1.92, 'db.r6i.8xlarge': 3.84, 'db.r6i.12xlarge': 5.76,
        'db.r6i.16xlarge': 7.68, 'db.r6i.24xlarge': 11.52, 'db.r6i.32xlarge': 15.36,
        # R6g family (Graviton)
        'db.r6g.large': 0.192, 'db.r6g.xlarge': 0.384, 'db.r6g.2xlarge': 0.768,
        'db.r6g.4xlarge': 1.536, 'db.r6g.8xlarge': 3.072, 'db.r6g.12xlarge': 4.608,
        'db.r6g.16xlarge': 6.144,
    }
    fallback_price = pricing.get(db_class, 0.10)
    
    # Multi-AZ is typically 2x the Single-AZ price
    if multi_az:
        fallback_price *= 2
    
    # Cache fallback too
    PRICING_CACHE[cache_key] = {
        'price': fallback_price,
        'timestamp': datetime.now().timestamp()
    }
    return fallback_price

def calculate_ebs_cost(volume_type, size_gb, region, iops=0, throughput=0):
    """Calculate monthly EBS cost with real-time pricing when available"""
    cache_key = f"ebs_{volume_type}_{region}"
    
    # Check cache for base price
    base_price_per_gb = None
    if cache_key in PRICING_CACHE:
        cached_data = PRICING_CACHE[cache_key]
        if datetime.now().timestamp() - cached_data['timestamp'] < CACHE_TTL:
            base_price_per_gb = cached_data['price']
    
    if base_price_per_gb is None:
        try:
            pricing_client = boto3.client('pricing', region_name='us-east-1')
            location = REGION_LOCATION_MAP.get(region, 'US East (N. Virginia)')
            
            # Map volume types to pricing API values
            volume_type_map = {
                'gp2': 'General Purpose',
                'gp3': 'General Purpose',
                'io1': 'Provisioned IOPS',
                'io2': 'Provisioned IOPS',
                'st1': 'Throughput Optimized HDD',
                'sc1': 'Cold HDD',
                'standard': 'Magnetic'
            }
            
            response = pricing_client.get_products(
                ServiceCode='AmazonEC2',
                Filters=[
                    {'Type': 'TERM_MATCH', 'Field': 'productFamily', 'Value': 'Storage'},
                    {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': location},
                    {'Type': 'TERM_MATCH', 'Field': 'volumeApiName', 'Value': volume_type}
                ],
                MaxResults=10
            )
            
            if response['PriceList']:
                for price_item in response['PriceList']:
                    price_data = json.loads(price_item)
                    on_demand = price_data.get('terms', {}).get('OnDemand', {})
                    if on_demand:
                        price_dimensions = list(list(on_demand.values())[0]['priceDimensions'].values())
                        for dim in price_dimensions:
                            # Look for per GB-month pricing
                            if 'GB-Mo' in dim.get('unit', ''):
                                price_per_unit = dim.get('pricePerUnit', {}).get('USD')
                                if price_per_unit:
                                    base_price_per_gb = float(price_per_unit)
                                    # Cache it
                                    PRICING_CACHE[cache_key] = {
                                        'price': base_price_per_gb,
                                        'timestamp': datetime.now().timestamp()
                                    }
                                    break
        except Exception as e:
            print(f"EBS pricing API error: {e}")
    
    # Fallback to hardcoded prices (us-east-1)
    if base_price_per_gb is None:
        fallback_pricing = {
            'gp2': 0.10,
            'gp3': 0.08,
            'io1': 0.125,
            'io2': 0.125,
            'st1': 0.045,
            'sc1': 0.015,
            'standard': 0.05
        }
        base_price_per_gb = fallback_pricing.get(volume_type, 0.10)
    
    # Calculate total cost
    total_cost = base_price_per_gb * size_gb
    
    # Add IOPS cost for provisioned IOPS volumes
    if volume_type in ['io1', 'io2'] and iops > 0:
        iops_price = 0.065  # per IOPS-month for io1
        if volume_type == 'io2':
            # io2 has tiered pricing
            if iops <= 32000:
                iops_price = 0.065
            elif iops <= 64000:
                iops_price = 0.046
            else:
                iops_price = 0.032
        total_cost += iops * iops_price
    
    # gp3 additional IOPS/throughput costs (beyond baseline)
    if volume_type == 'gp3':
        # gp3 baseline: 3000 IOPS, 125 MB/s throughput
        if iops > 3000:
            extra_iops = iops - 3000
            total_cost += extra_iops * 0.005  # $0.005 per provisioned IOPS-month
        if throughput > 125:
            extra_throughput = throughput - 125
            total_cost += extra_throughput * 0.04  # $0.04 per provisioned MB/s-month
    
    return total_cost


def calculate_lambda_cost(memory_mb, avg_duration_ms, invocations, region='us-east-1'):
    """Calculate monthly Lambda cost with real-time pricing when available"""
    cache_key = f"lambda_{region}"
    
    # Try to get real-time pricing
    cost_per_gb_second = None
    request_cost_per_million = None
    
    if cache_key in PRICING_CACHE:
        cached_data = PRICING_CACHE[cache_key]
        if datetime.now().timestamp() - cached_data['timestamp'] < CACHE_TTL:
            cost_per_gb_second = cached_data.get('gb_second')
            request_cost_per_million = cached_data.get('request')
    
    if cost_per_gb_second is None:
        try:
            pricing_client = boto3.client('pricing', region_name='us-east-1')
            location = REGION_LOCATION_MAP.get(region, 'US East (N. Virginia)')
            
            response = pricing_client.get_products(
                ServiceCode='AWSLambda',
                Filters=[
                    {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': location}
                ],
                MaxResults=20
            )
            
            if response['PriceList']:
                for price_item in response['PriceList']:
                    price_data = json.loads(price_item)
                    product = price_data.get('product', {})
                    attributes = product.get('attributes', {})
                    group = attributes.get('group', '')
                    
                    on_demand = price_data.get('terms', {}).get('OnDemand', {})
                    if on_demand:
                        price_dimensions = list(list(on_demand.values())[0]['priceDimensions'].values())
                        for dim in price_dimensions:
                            price_per_unit = dim.get('pricePerUnit', {}).get('USD')
                            if price_per_unit and float(price_per_unit) > 0:
                                unit = dim.get('unit', '')
                                if 'second' in unit.lower() or 'Lambda-GB-Second' in group:
                                    cost_per_gb_second = float(price_per_unit)
                                elif 'request' in unit.lower() or 'Request' in group:
                                    request_cost_per_million = float(price_per_unit) * 1000000
                
                if cost_per_gb_second and request_cost_per_million:
                    PRICING_CACHE[cache_key] = {
                        'gb_second': cost_per_gb_second,
                        'request': request_cost_per_million,
                        'timestamp': datetime.now().timestamp()
                    }
        except Exception as e:
            print(f"Lambda pricing API error: {e}")
    
    # Fallback to default pricing (us-east-1)
    if cost_per_gb_second is None:
        cost_per_gb_second = 0.0000166667
    if request_cost_per_million is None:
        request_cost_per_million = 0.20
    
    # Calculate costs
    gb_seconds = (memory_mb / 1024) * (avg_duration_ms / 1000) * invocations
    compute_cost = gb_seconds * cost_per_gb_second
    request_cost = invocations * (request_cost_per_million / 1000000)
    
    return compute_cost + request_cost


def get_eip_cost(region):
    """Get Elastic IP cost for unattached IPs from pricing API"""
    cache_key = f"eip_{region}"
    
    if cache_key in PRICING_CACHE:
        cached_data = PRICING_CACHE[cache_key]
        if datetime.now().timestamp() - cached_data['timestamp'] < CACHE_TTL:
            return cached_data['price']
    
    try:
        pricing_client = boto3.client('pricing', region_name='us-east-1')
        location = REGION_LOCATION_MAP.get(region, 'US East (N. Virginia)')
        
        response = pricing_client.get_products(
            ServiceCode='AmazonEC2',
            Filters=[
                {'Type': 'TERM_MATCH', 'Field': 'productFamily', 'Value': 'IP Address'},
                {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': location},
                {'Type': 'TERM_MATCH', 'Field': 'group', 'Value': 'ElasticIP:IdleAddress'}
            ],
            MaxResults=5
        )
        
        if response['PriceList']:
            for price_item in response['PriceList']:
                price_data = json.loads(price_item)
                on_demand = price_data.get('terms', {}).get('OnDemand', {})
                if on_demand:
                    price_dimensions = list(list(on_demand.values())[0]['priceDimensions'].values())
                    for dim in price_dimensions:
                        price_per_unit = dim.get('pricePerUnit', {}).get('USD')
                        if price_per_unit and float(price_per_unit) > 0:
                            hourly_cost = float(price_per_unit)
                            PRICING_CACHE[cache_key] = {
                                'price': hourly_cost,
                                'timestamp': datetime.now().timestamp()
                            }
                            return hourly_cost
    except Exception as e:
        print(f"EIP pricing API error: {e}")
    
    # Fallback to default price ($0.005/hour for unattached EIP)
    fallback_price = 0.005
    PRICING_CACHE[cache_key] = {
        'price': fallback_price,
        'timestamp': datetime.now().timestamp()
    }
    return fallback_price

def get_smaller_instance_type(instance_type):
    """Get one size smaller instance type, supporting more instance families"""
    # Parse instance type
    parts = instance_type.split('.')
    if len(parts) != 2:
        return None
    
    family = parts[0]
    size = parts[1]
    
    # Size progression (smallest to largest)
    size_order = ['nano', 'micro', 'small', 'medium', 'large', 'xlarge', '2xlarge', '4xlarge', 
                  '8xlarge', '9xlarge', '12xlarge', '16xlarge', '18xlarge', '24xlarge', '32xlarge', '48xlarge', 'metal']
    
    # Try to find current size in order
    try:
        current_idx = size_order.index(size)
        if current_idx > 0:
            return f"{family}.{size_order[current_idx - 1]}"
    except ValueError:
        pass
    
    # Fallback to explicit mapping for edge cases
    size_map = {
        # T2 family
        't2.2xlarge': 't2.xlarge', 't2.xlarge': 't2.large', 't2.large': 't2.medium',
        't2.medium': 't2.small', 't2.small': 't2.micro', 't2.micro': 't2.nano',
        # T3 family
        't3.2xlarge': 't3.xlarge', 't3.xlarge': 't3.large', 't3.large': 't3.medium',
        't3.medium': 't3.small', 't3.small': 't3.micro', 't3.micro': 't3.nano',
        # T3a family
        't3a.2xlarge': 't3a.xlarge', 't3a.xlarge': 't3a.large', 't3a.large': 't3a.medium',
        't3a.medium': 't3a.small', 't3a.small': 't3a.micro', 't3a.micro': 't3a.nano',
        # T4g family (Graviton)
        't4g.2xlarge': 't4g.xlarge', 't4g.xlarge': 't4g.large', 't4g.large': 't4g.medium',
        't4g.medium': 't4g.small', 't4g.small': 't4g.micro', 't4g.micro': 't4g.nano',
        # M5 family
        'm5.24xlarge': 'm5.16xlarge', 'm5.16xlarge': 'm5.12xlarge', 'm5.12xlarge': 'm5.8xlarge',
        'm5.8xlarge': 'm5.4xlarge', 'm5.4xlarge': 'm5.2xlarge', 'm5.2xlarge': 'm5.xlarge', 'm5.xlarge': 'm5.large',
        # M5a family
        'm5a.24xlarge': 'm5a.16xlarge', 'm5a.16xlarge': 'm5a.12xlarge', 'm5a.12xlarge': 'm5a.8xlarge',
        'm5a.8xlarge': 'm5a.4xlarge', 'm5a.4xlarge': 'm5a.2xlarge', 'm5a.2xlarge': 'm5a.xlarge', 'm5a.xlarge': 'm5a.large',
        # M6i family
        'm6i.32xlarge': 'm6i.24xlarge', 'm6i.24xlarge': 'm6i.16xlarge', 'm6i.16xlarge': 'm6i.12xlarge',
        'm6i.12xlarge': 'm6i.8xlarge', 'm6i.8xlarge': 'm6i.4xlarge', 'm6i.4xlarge': 'm6i.2xlarge',
        'm6i.2xlarge': 'm6i.xlarge', 'm6i.xlarge': 'm6i.large',
        # M6g family (Graviton)
        'm6g.16xlarge': 'm6g.12xlarge', 'm6g.12xlarge': 'm6g.8xlarge', 'm6g.8xlarge': 'm6g.4xlarge',
        'm6g.4xlarge': 'm6g.2xlarge', 'm6g.2xlarge': 'm6g.xlarge', 'm6g.xlarge': 'm6g.large',
        # M7i family
        'm7i.48xlarge': 'm7i.24xlarge', 'm7i.24xlarge': 'm7i.16xlarge', 'm7i.16xlarge': 'm7i.12xlarge',
        'm7i.12xlarge': 'm7i.8xlarge', 'm7i.8xlarge': 'm7i.4xlarge', 'm7i.4xlarge': 'm7i.2xlarge',
        'm7i.2xlarge': 'm7i.xlarge', 'm7i.xlarge': 'm7i.large',
        # M7a family
        'm7a.48xlarge': 'm7a.32xlarge', 'm7a.32xlarge': 'm7a.24xlarge', 'm7a.24xlarge': 'm7a.16xlarge',
        'm7a.16xlarge': 'm7a.12xlarge', 'm7a.12xlarge': 'm7a.8xlarge', 'm7a.8xlarge': 'm7a.4xlarge',
        'm7a.4xlarge': 'm7a.2xlarge', 'm7a.2xlarge': 'm7a.xlarge', 'm7a.xlarge': 'm7a.large',
        # C5 family
        'c5.24xlarge': 'c5.18xlarge', 'c5.18xlarge': 'c5.12xlarge', 'c5.12xlarge': 'c5.9xlarge',
        'c5.9xlarge': 'c5.4xlarge', 'c5.4xlarge': 'c5.2xlarge', 'c5.2xlarge': 'c5.xlarge', 'c5.xlarge': 'c5.large',
        # C5a family
        'c5a.24xlarge': 'c5a.16xlarge', 'c5a.16xlarge': 'c5a.12xlarge', 'c5a.12xlarge': 'c5a.8xlarge',
        'c5a.8xlarge': 'c5a.4xlarge', 'c5a.4xlarge': 'c5a.2xlarge', 'c5a.2xlarge': 'c5a.xlarge', 'c5a.xlarge': 'c5a.large',
        # C6i family
        'c6i.32xlarge': 'c6i.24xlarge', 'c6i.24xlarge': 'c6i.16xlarge', 'c6i.16xlarge': 'c6i.12xlarge',
        'c6i.12xlarge': 'c6i.8xlarge', 'c6i.8xlarge': 'c6i.4xlarge', 'c6i.4xlarge': 'c6i.2xlarge',
        'c6i.2xlarge': 'c6i.xlarge', 'c6i.xlarge': 'c6i.large',
        # C6g family (Graviton)
        'c6g.16xlarge': 'c6g.12xlarge', 'c6g.12xlarge': 'c6g.8xlarge', 'c6g.8xlarge': 'c6g.4xlarge',
        'c6g.4xlarge': 'c6g.2xlarge', 'c6g.2xlarge': 'c6g.xlarge', 'c6g.xlarge': 'c6g.large',
        # C7i family
        'c7i.48xlarge': 'c7i.24xlarge', 'c7i.24xlarge': 'c7i.16xlarge', 'c7i.16xlarge': 'c7i.12xlarge',
        'c7i.12xlarge': 'c7i.8xlarge', 'c7i.8xlarge': 'c7i.4xlarge', 'c7i.4xlarge': 'c7i.2xlarge',
        'c7i.2xlarge': 'c7i.xlarge', 'c7i.xlarge': 'c7i.large',
        # R5 family
        'r5.24xlarge': 'r5.16xlarge', 'r5.16xlarge': 'r5.12xlarge', 'r5.12xlarge': 'r5.8xlarge',
        'r5.8xlarge': 'r5.4xlarge', 'r5.4xlarge': 'r5.2xlarge', 'r5.2xlarge': 'r5.xlarge', 'r5.xlarge': 'r5.large',
        # R5a family
        'r5a.24xlarge': 'r5a.16xlarge', 'r5a.16xlarge': 'r5a.12xlarge', 'r5a.12xlarge': 'r5a.8xlarge',
        'r5a.8xlarge': 'r5a.4xlarge', 'r5a.4xlarge': 'r5a.2xlarge', 'r5a.2xlarge': 'r5a.xlarge', 'r5a.xlarge': 'r5a.large',
        # R6i family
        'r6i.32xlarge': 'r6i.24xlarge', 'r6i.24xlarge': 'r6i.16xlarge', 'r6i.16xlarge': 'r6i.12xlarge',
        'r6i.12xlarge': 'r6i.8xlarge', 'r6i.8xlarge': 'r6i.4xlarge', 'r6i.4xlarge': 'r6i.2xlarge',
        'r6i.2xlarge': 'r6i.xlarge', 'r6i.xlarge': 'r6i.large',
        # R6g family (Graviton)
        'r6g.16xlarge': 'r6g.12xlarge', 'r6g.12xlarge': 'r6g.8xlarge', 'r6g.8xlarge': 'r6g.4xlarge',
        'r6g.4xlarge': 'r6g.2xlarge', 'r6g.2xlarge': 'r6g.xlarge', 'r6g.xlarge': 'r6g.large',
        # I3 family (Storage optimized)
        'i3.16xlarge': 'i3.8xlarge', 'i3.8xlarge': 'i3.4xlarge', 'i3.4xlarge': 'i3.2xlarge',
        'i3.2xlarge': 'i3.xlarge', 'i3.xlarge': 'i3.large',
        # D2 family (Dense storage)
        'd2.8xlarge': 'd2.4xlarge', 'd2.4xlarge': 'd2.2xlarge', 'd2.2xlarge': 'd2.xlarge',
    }
    return size_map.get(instance_type)

def get_smaller_rds_class(db_class):
    """Get one size smaller RDS class, supporting more instance families"""
    # Parse db class
    if not db_class.startswith('db.'):
        return None
    
    parts = db_class[3:].split('.')  # Remove 'db.' prefix
    if len(parts) != 2:
        return None
    
    family = parts[0]
    size = parts[1]
    
    # Size progression (smallest to largest)
    size_order = ['micro', 'small', 'medium', 'large', 'xlarge', '2xlarge', '4xlarge', 
                  '8xlarge', '12xlarge', '16xlarge', '24xlarge', '32xlarge']
    
    # Try to find current size in order
    try:
        current_idx = size_order.index(size)
        if current_idx > 0:
            return f"db.{family}.{size_order[current_idx - 1]}"
    except ValueError:
        pass
    
    # Fallback to explicit mapping
    size_map = {
        # T3 family
        'db.t3.2xlarge': 'db.t3.xlarge', 'db.t3.xlarge': 'db.t3.large', 'db.t3.large': 'db.t3.medium',
        'db.t3.medium': 'db.t3.small', 'db.t3.small': 'db.t3.micro',
        # T4g family (Graviton)
        'db.t4g.2xlarge': 'db.t4g.xlarge', 'db.t4g.xlarge': 'db.t4g.large', 'db.t4g.large': 'db.t4g.medium',
        'db.t4g.medium': 'db.t4g.small', 'db.t4g.small': 'db.t4g.micro',
        # M5 family
        'db.m5.24xlarge': 'db.m5.16xlarge', 'db.m5.16xlarge': 'db.m5.12xlarge', 'db.m5.12xlarge': 'db.m5.8xlarge',
        'db.m5.8xlarge': 'db.m5.4xlarge', 'db.m5.4xlarge': 'db.m5.2xlarge', 'db.m5.2xlarge': 'db.m5.xlarge', 'db.m5.xlarge': 'db.m5.large',
        # M6i family
        'db.m6i.32xlarge': 'db.m6i.24xlarge', 'db.m6i.24xlarge': 'db.m6i.16xlarge', 'db.m6i.16xlarge': 'db.m6i.12xlarge',
        'db.m6i.12xlarge': 'db.m6i.8xlarge', 'db.m6i.8xlarge': 'db.m6i.4xlarge', 'db.m6i.4xlarge': 'db.m6i.2xlarge',
        'db.m6i.2xlarge': 'db.m6i.xlarge', 'db.m6i.xlarge': 'db.m6i.large',
        # M6g family (Graviton)
        'db.m6g.16xlarge': 'db.m6g.12xlarge', 'db.m6g.12xlarge': 'db.m6g.8xlarge', 'db.m6g.8xlarge': 'db.m6g.4xlarge',
        'db.m6g.4xlarge': 'db.m6g.2xlarge', 'db.m6g.2xlarge': 'db.m6g.xlarge', 'db.m6g.xlarge': 'db.m6g.large',
        # R5 family
        'db.r5.24xlarge': 'db.r5.16xlarge', 'db.r5.16xlarge': 'db.r5.12xlarge', 'db.r5.12xlarge': 'db.r5.8xlarge',
        'db.r5.8xlarge': 'db.r5.4xlarge', 'db.r5.4xlarge': 'db.r5.2xlarge', 'db.r5.2xlarge': 'db.r5.xlarge', 'db.r5.xlarge': 'db.r5.large',
        # R6i family
        'db.r6i.32xlarge': 'db.r6i.24xlarge', 'db.r6i.24xlarge': 'db.r6i.16xlarge', 'db.r6i.16xlarge': 'db.r6i.12xlarge',
        'db.r6i.12xlarge': 'db.r6i.8xlarge', 'db.r6i.8xlarge': 'db.r6i.4xlarge', 'db.r6i.4xlarge': 'db.r6i.2xlarge',
        'db.r6i.2xlarge': 'db.r6i.xlarge', 'db.r6i.xlarge': 'db.r6i.large',
        # R6g family (Graviton)
        'db.r6g.16xlarge': 'db.r6g.12xlarge', 'db.r6g.12xlarge': 'db.r6g.8xlarge', 'db.r6g.8xlarge': 'db.r6g.4xlarge',
        'db.r6g.4xlarge': 'db.r6g.2xlarge', 'db.r6g.2xlarge': 'db.r6g.xlarge', 'db.r6g.xlarge': 'db.r6g.large',
    }
    return size_map.get(db_class)
