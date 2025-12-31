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
        session = boto3.Session(
            aws_access_key_id=body['accessKeyId'],
            aws_secret_access_key=body['secretAccessKey'],
            region_name=body.get('region', 'us-east-1')
        )
    
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
    
    # Try Compute Optimizer first
    try:
        response = compute_optimizer.get_ec2_instance_recommendations()
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
    except Exception as e:
        print(f"Compute Optimizer not available: {e}")
    
    # Fallback: Check for low utilization via CloudWatch
    try:
        instances = ec2.describe_instances(
            Filters=[{'Name': 'instance-state-name', 'Values': ['running']}]
        )
        
        # Check for Auto Scaling groups
        asg_instances = set()
        try:
            asg_client = session.client('autoscaling')
            asgs = asg_client.describe_auto_scaling_groups()
            for asg in asgs['AutoScalingGroups']:
                for instance in asg['Instances']:
                    asg_instances.add(instance['InstanceId'])
        except:
            pass
        
        for reservation in instances['Reservations']:
            for instance in reservation['Instances']:
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
                
                if cpu_stats['Datapoints']:
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
        volumes = ec2.describe_volumes()
        
        for volume in volumes['Volumes']:
            volume_id = volume['VolumeId']
            volume_type = volume['VolumeType']
            size = volume['Size']
            state = volume['State']
            
            # Unattached volumes
            if state == 'available':
                monthly_cost = calculate_ebs_cost(volume_type, size, session.region_name)
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
                current_cost = calculate_ebs_cost('gp2', size, session.region_name)
                gp3_cost = calculate_ebs_cost('gp3', size, session.region_name)
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
        instances = rds.describe_db_instances()
        
        for db in instances['DBInstances']:
            db_id = db['DBInstanceIdentifier']
            db_class = db['DBInstanceClass']
            engine = db['Engine']
            
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
            
            if cpu_stats['Datapoints'] and conn_stats['Datapoints']:
                avg_cpu = sum(d['Average'] for d in cpu_stats['Datapoints']) / len(cpu_stats['Datapoints'])
                avg_conn = sum(d['Average'] for d in conn_stats['Datapoints']) / len(conn_stats['Datapoints'])
                
                if avg_cpu < 20 and avg_conn < 5:
                    current_cost = get_rds_cost(db_class, engine, session.region_name)
                    smaller_class = get_smaller_rds_class(db_class)
                    
                    if smaller_class:
                        smaller_cost = get_rds_cost(smaller_class, engine, session.region_name)
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
        functions = lambda_client.list_functions()
        
        for func in functions['Functions']:
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
            
            if duration_stats['Datapoints'] and invocations['Datapoints']:
                avg_duration = sum(d['Average'] for d in duration_stats['Datapoints']) / len(duration_stats['Datapoints'])
                total_invocations = sum(d['Sum'] for d in invocations['Datapoints'])
                
                # Check if memory is over-provisioned (duration is very low relative to timeout)
                if memory_size > 512 and avg_duration < 1000:  # Less than 1 second
                    recommended_memory = max(128, memory_size // 2)
                    
                    current_cost = calculate_lambda_cost(memory_size, avg_duration, total_invocations)
                    recommended_cost = calculate_lambda_cost(recommended_memory, avg_duration, total_invocations)
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
        
        for addr in addresses['Addresses']:
            if 'InstanceId' not in addr:  # Unattached
                recommendations.append({
                    'ip_address': addr['PublicIp'],
                    'allocation_id': addr['AllocationId'],
                    'status': 'Unattached',
                    'monthly_savings': 3.60,  # $0.005/hour * 730 hours
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
        
        # Map region codes to location names
        region_map = {
            'us-east-1': 'US East (N. Virginia)', 'us-east-2': 'US East (Ohio)',
            'us-west-1': 'US West (N. California)', 'us-west-2': 'US West (Oregon)',
            'eu-west-1': 'EU (Ireland)', 'eu-central-1': 'EU (Frankfurt)',
            'ap-southeast-1': 'Asia Pacific (Singapore)', 'ap-northeast-1': 'Asia Pacific (Tokyo)',
            'ap-southeast-2': 'Asia Pacific (Sydney)', 'ap-south-1': 'Asia Pacific (Mumbai)',
        }
        location = region_map.get(region, 'US East (N. Virginia)')
        
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
            MaxResults=1
        )
        
        if response['PriceList']:
            price_data = json.loads(response['PriceList'][0])
            on_demand = price_data['terms']['OnDemand']
            price_dimensions = list(on_demand.values())[0]['priceDimensions']
            price_per_hour = float(list(price_dimensions.values())[0]['pricePerUnit']['USD'])
            
            # Cache the result
            PRICING_CACHE[cache_key] = {
                'price': price_per_hour,
                'timestamp': datetime.now().timestamp()
            }
            return price_per_hour
    except Exception as e:
        print(f"Price API error for {instance_type}: {e}")
    
    # Fallback to expanded hardcoded prices
    pricing = {
        't2.micro': 0.0116, 't2.small': 0.023, 't2.medium': 0.0464, 't2.large': 0.0928, 't2.xlarge': 0.1856, 't2.2xlarge': 0.3712,
        't3.micro': 0.0104, 't3.small': 0.0208, 't3.medium': 0.0416, 't3.large': 0.0832, 't3.xlarge': 0.1664, 't3.2xlarge': 0.3328,
        't3a.micro': 0.0094, 't3a.small': 0.0188, 't3a.medium': 0.0376, 't3a.large': 0.0752, 't3a.xlarge': 0.1504, 't3a.2xlarge': 0.3008,
        'm5.large': 0.096, 'm5.xlarge': 0.192, 'm5.2xlarge': 0.384, 'm5.4xlarge': 0.768, 'm5.8xlarge': 1.536, 'm5.12xlarge': 2.304,
        'm6i.large': 0.096, 'm6i.xlarge': 0.192, 'm6i.2xlarge': 0.384, 'm6i.4xlarge': 0.768, 'm6i.8xlarge': 1.536,
        'm7a.large': 0.1008, 'm7a.xlarge': 0.2016, 'm7a.2xlarge': 0.4032, 'm7a.4xlarge': 0.8064, 'm7a.8xlarge': 1.6128,
        'c5.large': 0.085, 'c5.xlarge': 0.17, 'c5.2xlarge': 0.34, 'c5.4xlarge': 0.68, 'c5.9xlarge': 1.53, 'c5.18xlarge': 3.06,
        'c6i.large': 0.085, 'c6i.xlarge': 0.17, 'c6i.2xlarge': 0.34, 'c6i.4xlarge': 0.68, 'c6i.8xlarge': 1.36, 'c6i.16xlarge': 2.72,
        'c6g.large': 0.068, 'c6g.xlarge': 0.136, 'c6g.2xlarge': 0.272, 'c6g.4xlarge': 0.544, 'c6g.8xlarge': 1.088,
        'r5.large': 0.126, 'r5.xlarge': 0.252, 'r5.2xlarge': 0.504, 'r5.4xlarge': 1.008, 'r5.8xlarge': 2.016,
        'r6i.large': 0.126, 'r6i.xlarge': 0.252, 'r6i.2xlarge': 0.504, 'r6i.4xlarge': 1.008, 'r6i.8xlarge': 2.016,
    }
    fallback_price = pricing.get(instance_type, 0.10)
    
    # Cache fallback too
    PRICING_CACHE[cache_key] = {
        'price': fallback_price,
        'timestamp': datetime.now().timestamp()
    }
    return fallback_price

def get_rds_cost(db_class, engine, region):
    """Get actual RDS pricing with caching"""
    cache_key = f"rds_{db_class}_{engine}_{region}"
    
    # Check cache first
    if cache_key in PRICING_CACHE:
        cached_data = PRICING_CACHE[cache_key]
        if datetime.now().timestamp() - cached_data['timestamp'] < CACHE_TTL:
            return cached_data['price']
    
    try:
        pricing_client = boto3.client('pricing', region_name='us-east-1')
        
        region_map = {
            'us-east-1': 'US East (N. Virginia)', 'us-east-2': 'US East (Ohio)',
            'us-west-1': 'US West (N. California)', 'us-west-2': 'US West (Oregon)',
            'eu-west-1': 'EU (Ireland)', 'eu-central-1': 'EU (Frankfurt)',
        }
        location = region_map.get(region, 'US East (N. Virginia)')
        
        # Map engine names
        engine_map = {
            'postgres': 'PostgreSQL', 'mysql': 'MySQL', 'mariadb': 'MariaDB',
            'oracle': 'Oracle', 'sqlserver': 'SQL Server', 'aurora': 'Aurora MySQL',
            'aurora-mysql': 'Aurora MySQL', 'aurora-postgresql': 'Aurora PostgreSQL'
        }
        db_engine = engine_map.get(engine.lower(), 'MySQL')
        
        response = pricing_client.get_products(
            ServiceCode='AmazonRDS',
            Filters=[
                {'Type': 'TERM_MATCH', 'Field': 'instanceType', 'Value': db_class},
                {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': location},
                {'Type': 'TERM_MATCH', 'Field': 'databaseEngine', 'Value': db_engine},
                {'Type': 'TERM_MATCH', 'Field': 'deploymentOption', 'Value': 'Single-AZ'}
            ],
            MaxResults=1
        )
        
        if response['PriceList']:
            price_data = json.loads(response['PriceList'][0])
            on_demand = price_data['terms']['OnDemand']
            price_dimensions = list(on_demand.values())[0]['priceDimensions']
            price_per_hour = float(list(price_dimensions.values())[0]['pricePerUnit']['USD'])
            
            # Cache the result
            PRICING_CACHE[cache_key] = {
                'price': price_per_hour,
                'timestamp': datetime.now().timestamp()
            }
            return price_per_hour
    except Exception as e:
        print(f"RDS Price API error for {db_class}: {e}")
    
    # Fallback to expanded hardcoded prices
    pricing = {
        'db.t3.micro': 0.017, 'db.t3.small': 0.034, 'db.t3.medium': 0.068, 'db.t3.large': 0.136, 'db.t3.xlarge': 0.272, 'db.t3.2xlarge': 0.544,
        'db.t4g.micro': 0.016, 'db.t4g.small': 0.032, 'db.t4g.medium': 0.064, 'db.t4g.large': 0.128, 'db.t4g.xlarge': 0.256, 'db.t4g.2xlarge': 0.512,
        'db.m5.large': 0.192, 'db.m5.xlarge': 0.384, 'db.m5.2xlarge': 0.768, 'db.m5.4xlarge': 1.536, 'db.m5.8xlarge': 3.072,
        'db.m6i.large': 0.192, 'db.m6i.xlarge': 0.384, 'db.m6i.2xlarge': 0.768, 'db.m6i.4xlarge': 1.536, 'db.m6i.8xlarge': 3.072,
        'db.r5.large': 0.24, 'db.r5.xlarge': 0.48, 'db.r5.2xlarge': 0.96, 'db.r5.4xlarge': 1.92, 'db.r5.8xlarge': 3.84,
        'db.r6i.large': 0.24, 'db.r6i.xlarge': 0.48, 'db.r6i.2xlarge': 0.96, 'db.r6i.4xlarge': 1.92, 'db.r6i.8xlarge': 3.84,
    }
    fallback_price = pricing.get(db_class, 0.10)
    
    # Cache fallback too
    PRICING_CACHE[cache_key] = {
        'price': fallback_price,
        'timestamp': datetime.now().timestamp()
    }
    return fallback_price

def calculate_ebs_cost(volume_type, size_gb, region):
    """Calculate monthly EBS cost"""
    pricing = {
        'gp2': 0.10,  # per GB-month
        'gp3': 0.08,
        'io1': 0.125,
        'io2': 0.125,
        'st1': 0.045,
        'sc1': 0.015
    }
    return pricing.get(volume_type, 0.10) * size_gb

def calculate_lambda_cost(memory_mb, avg_duration_ms, invocations):
    """Calculate monthly Lambda cost"""
    gb_seconds = (memory_mb / 1024) * (avg_duration_ms / 1000) * invocations
    cost_per_gb_second = 0.0000166667
    request_cost = invocations * 0.0000002
    return (gb_seconds * cost_per_gb_second) + request_cost

def get_smaller_instance_type(instance_type):
    """Get one size smaller instance type"""
    size_map = {
        # T2 family
        't2.2xlarge': 't2.xlarge', 't2.xlarge': 't2.large', 't2.large': 't2.medium',
        't2.medium': 't2.small', 't2.small': 't2.micro',
        # T3 family
        't3.2xlarge': 't3.xlarge', 't3.xlarge': 't3.large', 't3.large': 't3.medium',
        't3.medium': 't3.small', 't3.small': 't3.micro',
        # T3a family
        't3a.2xlarge': 't3a.xlarge', 't3a.xlarge': 't3a.large', 't3a.large': 't3a.medium',
        't3a.medium': 't3a.small', 't3a.small': 't3a.micro',
        # M5 family
        'm5.24xlarge': 'm5.12xlarge', 'm5.12xlarge': 'm5.8xlarge', 'm5.8xlarge': 'm5.4xlarge',
        'm5.4xlarge': 'm5.2xlarge', 'm5.2xlarge': 'm5.xlarge', 'm5.xlarge': 'm5.large',
        # M6i family
        'm6i.32xlarge': 'm6i.16xlarge', 'm6i.16xlarge': 'm6i.8xlarge', 'm6i.8xlarge': 'm6i.4xlarge',
        'm6i.4xlarge': 'm6i.2xlarge', 'm6i.2xlarge': 'm6i.xlarge', 'm6i.xlarge': 'm6i.large',
        # M7a family
        'm7a.48xlarge': 'm7a.32xlarge', 'm7a.32xlarge': 'm7a.16xlarge', 'm7a.16xlarge': 'm7a.8xlarge',
        'm7a.8xlarge': 'm7a.4xlarge', 'm7a.4xlarge': 'm7a.2xlarge', 'm7a.2xlarge': 'm7a.xlarge', 'm7a.xlarge': 'm7a.large',
        # C5 family
        'c5.24xlarge': 'c5.18xlarge', 'c5.18xlarge': 'c5.9xlarge', 'c5.9xlarge': 'c5.4xlarge',
        'c5.4xlarge': 'c5.2xlarge', 'c5.2xlarge': 'c5.xlarge', 'c5.xlarge': 'c5.large',
        # C6i family
        'c6i.32xlarge': 'c6i.16xlarge', 'c6i.16xlarge': 'c6i.8xlarge', 'c6i.8xlarge': 'c6i.4xlarge',
        'c6i.4xlarge': 'c6i.2xlarge', 'c6i.2xlarge': 'c6i.xlarge', 'c6i.xlarge': 'c6i.large',
        # C6g family (Graviton)
        'c6g.16xlarge': 'c6g.8xlarge', 'c6g.8xlarge': 'c6g.4xlarge', 'c6g.4xlarge': 'c6g.2xlarge',
        'c6g.2xlarge': 'c6g.xlarge', 'c6g.xlarge': 'c6g.large',
        # R5 family
        'r5.24xlarge': 'r5.12xlarge', 'r5.12xlarge': 'r5.8xlarge', 'r5.8xlarge': 'r5.4xlarge',
        'r5.4xlarge': 'r5.2xlarge', 'r5.2xlarge': 'r5.xlarge', 'r5.xlarge': 'r5.large',
        # R6i family
        'r6i.32xlarge': 'r6i.16xlarge', 'r6i.16xlarge': 'r6i.8xlarge', 'r6i.8xlarge': 'r6i.4xlarge',
        'r6i.4xlarge': 'r6i.2xlarge', 'r6i.2xlarge': 'r6i.xlarge', 'r6i.xlarge': 'r6i.large',
    }
    return size_map.get(instance_type)

def get_smaller_rds_class(db_class):
    """Get one size smaller RDS class"""
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
        # R5 family
        'db.r5.24xlarge': 'db.r5.16xlarge', 'db.r5.16xlarge': 'db.r5.12xlarge', 'db.r5.12xlarge': 'db.r5.8xlarge',
        'db.r5.8xlarge': 'db.r5.4xlarge', 'db.r5.4xlarge': 'db.r5.2xlarge', 'db.r5.2xlarge': 'db.r5.xlarge', 'db.r5.xlarge': 'db.r5.large',
        # R6i family
        'db.r6i.32xlarge': 'db.r6i.24xlarge', 'db.r6i.24xlarge': 'db.r6i.16xlarge', 'db.r6i.16xlarge': 'db.r6i.12xlarge',
        'db.r6i.12xlarge': 'db.r6i.8xlarge', 'db.r6i.8xlarge': 'db.r6i.4xlarge', 'db.r6i.4xlarge': 'db.r6i.2xlarge',
        'db.r6i.2xlarge': 'db.r6i.xlarge', 'db.r6i.xlarge': 'db.r6i.large',
    }
    return size_map.get(db_class)
