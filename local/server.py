#!/usr/bin/env python3
"""
CostOptimizer360 - Local Web Server
Flask-based backend server that mirrors the AWS Lambda functionality.
Runs on localhost:5000 by default.
"""

import os
import sys
import json
import base64
import uuid
import threading
from datetime import datetime
from io import BytesIO
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

# Add lambda directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'lambda'))

# Get the directory where server.py is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(SCRIPT_DIR, 'web')

app = Flask(__name__, static_folder=WEB_DIR)
CORS(app)

# Progress tracking for scans
SCAN_PROGRESS = {}


@app.route('/')
def serve_frontend():
    """Serve the main frontend page."""
    return send_from_directory(WEB_DIR, 'index.html')


@app.route('/<path:filename>')
def serve_static(filename):
    """Serve static files from web directory."""
    return send_from_directory(WEB_DIR, filename)


@app.route('/api/progress/<scan_id>', methods=['GET'])
def get_progress(scan_id):
    """Get progress of a running scan."""
    if scan_id not in SCAN_PROGRESS:
        return jsonify({'status': 'not_found'}), 404
    
    progress = SCAN_PROGRESS[scan_id]
    return jsonify(progress)


def run_scan_async(scan_id, body, session_kwargs):
    """Run the scan in a background thread with progress updates."""
    try:
        import boto3
        from lambda_function import (
            scan_ec2_instances, scan_ebs_volumes, scan_rds_instances,
            scan_lambda_functions, scan_elastic_ips, scan_s3_buckets,
            scan_stopped_ec2_instances, scan_nat_gateways, scan_dynamodb_tables,
            scan_ri_sp_coverage, generate_word_report, generate_json_report,
            generate_csv_report, create_session, format_tags_str
        )
        
        client_name = body.get('clientName', 'Client')
        services = body.get('services', ['ec2', 'ebs', 'rds', 'lambda', 'eip'])
        export_format = body.get('exportFormat', 'docx')
        
        # Handle multi-region
        regions_input = body.get('regions', body.get('region', 'us-east-1'))
        if isinstance(regions_input, str):
            if regions_input == 'all':
                temp_session = boto3.Session(**session_kwargs)
                ec2_client = temp_session.client('ec2')
                regions = [r['RegionName'] for r in ec2_client.describe_regions()['Regions']]
            else:
                regions = [regions_input]
        else:
            regions = regions_input
        
        total_steps = len(regions) * len(services)
        if 's3' in services:
            total_steps += 1  # S3 is global, scanned once
        current_step = 0
        
        recommendations = {}
        total_savings = 0.0
        ri_sp_summary = None
        
        service_scanners = {
            'ec2': ('EC2 Instances', scan_ec2_instances),
            'stopped_ec2': ('Stopped EC2 Instances', scan_stopped_ec2_instances),
            'ebs': ('EBS Volumes', scan_ebs_volumes),
            'rds': ('RDS Databases', scan_rds_instances),
            'lambda': ('Lambda Functions', scan_lambda_functions),
            'eip': ('Elastic IPs', scan_elastic_ips),
            'natgateway': ('NAT Gateways', scan_nat_gateways),
            'dynamodb': ('DynamoDB Tables', scan_dynamodb_tables),
        }
        
        for region in regions:
            region_session_kwargs = {**session_kwargs, 'region_name': region}
            session = boto3.Session(**region_session_kwargs)
            
            for service_key in services:
                if service_key == 's3':
                    continue  # S3 handled separately (global)
                
                if service_key in service_scanners:
                    label, scanner_fn = service_scanners[service_key]
                    current_step += 1
                    region_label = f" ({region})" if len(regions) > 1 else ""
                    SCAN_PROGRESS[scan_id] = {
                        'status': 'scanning',
                        'current_service': f'{label}{region_label}',
                        'progress': round(current_step / max(total_steps, 1) * 100),
                        'step': current_step,
                        'total_steps': total_steps
                    }
                    
                    recs = scanner_fn(session)
                    for r in recs:
                        r['region'] = region
                    recommendations.setdefault(service_key, []).extend(recs)
                    total_savings += sum(r.get('monthly_savings', 0) for r in recs)
        
        # S3 is global - scan once
        if 's3' in services:
            current_step += 1
            SCAN_PROGRESS[scan_id] = {
                'status': 'scanning',
                'current_service': 'S3 Buckets',
                'progress': round(current_step / max(total_steps, 1) * 100),
                'step': current_step,
                'total_steps': total_steps
            }
            s3_session_kwargs = {**session_kwargs, 'region_name': 'us-east-1'}
            s3_session = boto3.Session(**s3_session_kwargs)
            recs = scan_s3_buckets(s3_session)
            recommendations['s3'] = recs
        
        # RI/SP coverage
        if 'ec2' in services:
            SCAN_PROGRESS[scan_id] = {
                'status': 'scanning',
                'current_service': 'RI/SP Coverage',
                'progress': 95,
                'step': current_step,
                'total_steps': total_steps
            }
            ri_session_kwargs = {**session_kwargs, 'region_name': regions[0]}
            ri_session = boto3.Session(**ri_session_kwargs)
            ri_sp_summary = scan_ri_sp_coverage(ri_session)
        
        # Generate report
        SCAN_PROGRESS[scan_id] = {
            'status': 'generating',
            'current_service': 'Generating report...',
            'progress': 98,
            'step': current_step,
            'total_steps': total_steps
        }
        
        if export_format == 'json':
            report_content = generate_json_report(recommendations, total_savings, client_name, ri_sp_summary)
            file_content = report_content.encode('utf-8')
            filename = f"{client_name.replace(' ', '-')}-CostOptimizer360-{datetime.now().strftime('%Y%m%d')}.json"
        elif export_format == 'csv':
            report_content = generate_csv_report(recommendations, total_savings, client_name)
            file_content = report_content.encode('utf-8')
            filename = f"{client_name.replace(' ', '-')}-CostOptimizer360-{datetime.now().strftime('%Y%m%d')}.csv"
        else:
            doc = generate_word_report(recommendations, total_savings, client_name, ri_sp_summary)
            buffer = BytesIO()
            doc.save(buffer)
            buffer.seek(0)
            file_content = buffer.read()
            filename = f"{client_name.replace(' ', '-')}-CostOptimizer360-{datetime.now().strftime('%Y%m%d')}.docx"
        
        SCAN_PROGRESS[scan_id] = {
            'status': 'complete',
            'current_service': 'Complete',
            'progress': 100,
            'result': {
                'file': base64.b64encode(file_content).decode('utf-8'),
                'filename': filename,
                'totalMonthlySavings': round(total_savings, 2),
                'totalAnnualSavings': round(total_savings * 12, 2),
                'recommendationCounts': {k: len(v) for k, v in recommendations.items() if isinstance(v, list)},
                'riSpCoverage': ri_sp_summary
            }
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        SCAN_PROGRESS[scan_id] = {
            'status': 'error',
            'current_service': 'Error',
            'progress': 0,
            'error': str(e)
        }


@app.route('/api/generate', methods=['POST', 'OPTIONS'])
def generate_report():
    """Generate optimization report - uses credentials provided in request body only."""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        import boto3
        
        body = request.get_json()
        if not body:
            return jsonify({'message': 'Request body is required'}), 400
        
        # Require credentials from request body - no CLI or role-based auth
        if 'accessKeyId' not in body or 'secretAccessKey' not in body:
            return jsonify({'message': 'AWS credentials (accessKeyId and secretAccessKey) are required'}), 400
        
        if not body['accessKeyId'].strip() or not body['secretAccessKey'].strip():
            return jsonify({'message': 'AWS credentials cannot be empty'}), 400
        
        region = body.get('region', 'us-east-1')
        
        # Build session kwargs for credential verification
        session_kwargs = {
            'aws_access_key_id': body['accessKeyId'].strip(),
            'aws_secret_access_key': body['secretAccessKey'].strip(),
            'region_name': region
        }
        
        if body.get('sessionToken'):
            session_kwargs['aws_session_token'] = body['sessionToken'].strip()
        
        session = boto3.Session(**session_kwargs)
        
        # Verify credentials before proceeding
        try:
            sts = session.client('sts')
            sts.get_caller_identity()
        except Exception as e:
            return jsonify({
                'message': f'AWS credentials error: {str(e)}'
            }), 401
        
        # Check if async mode requested (for progress tracking)
        use_async = body.get('async', True)
        
        if use_async:
            scan_id = str(uuid.uuid4())
            SCAN_PROGRESS[scan_id] = {
                'status': 'starting',
                'current_service': 'Initializing...',
                'progress': 0
            }
            
            thread = threading.Thread(
                target=run_scan_async,
                args=(scan_id, body, session_kwargs),
                daemon=True
            )
            thread.start()
            
            return jsonify({
                'scanId': scan_id,
                'status': 'started',
                'message': 'Scan started. Poll /api/progress/<scanId> for updates.'
            })
        else:
            # Synchronous mode (backward compatible)
            from lambda_function import (
                scan_ec2_instances, scan_ebs_volumes, scan_rds_instances,
                scan_lambda_functions, scan_elastic_ips, scan_s3_buckets,
                scan_stopped_ec2_instances, scan_nat_gateways, scan_dynamodb_tables,
                scan_ri_sp_coverage, generate_word_report, generate_json_report,
                generate_csv_report, format_tags_str
            )
            
            client_name = body.get('clientName', 'Client')
            services = body.get('services', ['ec2', 'ebs', 'rds', 'lambda', 'eip'])
            export_format = body.get('exportFormat', 'docx')
            
            recommendations = {}
            total_savings = 0.0
            
            # Handle multi-region
            regions_input = body.get('regions', body.get('region', 'us-east-1'))
            if isinstance(regions_input, str):
                regions = [regions_input]
            else:
                regions = regions_input
            
            service_scanners = {
                'ec2': scan_ec2_instances,
                'stopped_ec2': scan_stopped_ec2_instances,
                'ebs': scan_ebs_volumes,
                'rds': scan_rds_instances,
                'lambda': scan_lambda_functions,
                'eip': scan_elastic_ips,
                'natgateway': scan_nat_gateways,
                'dynamodb': scan_dynamodb_tables,
            }
            
            for region_name in regions:
                region_kwargs = {**session_kwargs, 'region_name': region_name}
                region_session = boto3.Session(**region_kwargs)
                
                for svc in services:
                    if svc == 's3':
                        continue
                    if svc in service_scanners:
                        recs = service_scanners[svc](region_session)
                        for r in recs:
                            r['region'] = region_name
                        recommendations.setdefault(svc, []).extend(recs)
                        total_savings += sum(r.get('monthly_savings', 0) for r in recs)
            
            if 's3' in services:
                s3_kwargs = {**session_kwargs, 'region_name': 'us-east-1'}
                s3_session = boto3.Session(**s3_kwargs)
                recommendations['s3'] = scan_s3_buckets(s3_session)
            
            ri_sp_summary = None
            if 'ec2' in services:
                ri_kwargs = {**session_kwargs, 'region_name': regions[0]}
                ri_session = boto3.Session(**ri_kwargs)
                ri_sp_summary = scan_ri_sp_coverage(ri_session)
            
            if export_format == 'json':
                content = generate_json_report(recommendations, total_savings, client_name, ri_sp_summary)
                file_content = content.encode('utf-8')
                filename = f"{client_name.replace(' ', '-')}-CostOptimizer360-{datetime.now().strftime('%Y%m%d')}.json"
            elif export_format == 'csv':
                content = generate_csv_report(recommendations, total_savings, client_name)
                file_content = content.encode('utf-8')
                filename = f"{client_name.replace(' ', '-')}-CostOptimizer360-{datetime.now().strftime('%Y%m%d')}.csv"
            else:
                doc = generate_word_report(recommendations, total_savings, client_name, ri_sp_summary)
                buffer = BytesIO()
                doc.save(buffer)
                buffer.seek(0)
                file_content = buffer.read()
                filename = f"{client_name.replace(' ', '-')}-CostOptimizer360-{datetime.now().strftime('%Y%m%d')}.docx"
            
            return jsonify({
                'file': base64.b64encode(file_content).decode('utf-8'),
                'filename': filename,
                'totalMonthlySavings': round(total_savings, 2),
                'totalAnnualSavings': round(total_savings * 12, 2),
                'recommendationCounts': {k: len(v) for k, v in recommendations.items() if isinstance(v, list)},
                'riSpCoverage': ri_sp_summary
            })
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'message': str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    # Default to localhost only for security (handles AWS credentials)
    host = os.environ.get('HOST', '127.0.0.1')
    print(f"\n{'='*60}")
    print("CostOptimizer360 - Local Web Server")
    print(f"{'='*60}")
    print(f"\n✓ Server starting on http://localhost:{port}")
    print(f"✓ Frontend available at http://localhost:{port}")
    print(f"✓ API endpoint: http://localhost:{port}/api/generate")
    print(f"✓ Progress endpoint: http://localhost:{port}/api/progress/<scan_id>")
    print("\nPress Ctrl+C to stop the server\n")
    app.run(host=host, port=port, debug=False)
