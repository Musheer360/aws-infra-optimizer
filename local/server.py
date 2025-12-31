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


@app.route('/')
def serve_frontend():
    """Serve the main frontend page."""
    return send_from_directory(WEB_DIR, 'index.html')


@app.route('/<path:filename>')
def serve_static(filename):
    """Serve static files from web directory."""
    return send_from_directory(WEB_DIR, filename)


@app.route('/api/generate', methods=['POST', 'OPTIONS'])
def generate_report():
    """Generate optimization report - uses credentials provided in request body only."""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        import boto3
        from lambda_function import (
            scan_ec2_instances, scan_ebs_volumes, scan_rds_instances,
            scan_lambda_functions, scan_elastic_ips, generate_word_report
        )
        
        body = request.get_json()
        if not body:
            return jsonify({'message': 'Request body is required'}), 400
        
        client_name = body.get('clientName', 'Client')
        region = body.get('region', 'us-east-1')
        services = body.get('services', ['ec2', 'ebs', 'rds', 'lambda', 'eip'])
        
        # Require credentials from request body - no CLI or role-based auth
        if 'accessKeyId' not in body or 'secretAccessKey' not in body:
            return jsonify({'message': 'AWS credentials (accessKeyId and secretAccessKey) are required'}), 400
        
        if not body['accessKeyId'].strip() or not body['secretAccessKey'].strip():
            return jsonify({'message': 'AWS credentials cannot be empty'}), 400
        
        # Create AWS session using provided credentials
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
        
        # Collect recommendations
        recommendations = {}
        total_savings = 0.0
        
        if 'ec2' in services:
            recs = scan_ec2_instances(session)
            recommendations['ec2'] = recs
            total_savings += sum(r['monthly_savings'] for r in recs)
        
        if 'ebs' in services:
            recs = scan_ebs_volumes(session)
            recommendations['ebs'] = recs
            total_savings += sum(r['monthly_savings'] for r in recs)
        
        if 'rds' in services:
            recs = scan_rds_instances(session)
            recommendations['rds'] = recs
            total_savings += sum(r['monthly_savings'] for r in recs)
        
        if 'lambda' in services:
            recs = scan_lambda_functions(session)
            recommendations['lambda'] = recs
            total_savings += sum(r['monthly_savings'] for r in recs)
        
        if 'eip' in services:
            recs = scan_elastic_ips(session)
            recommendations['eip'] = recs
            total_savings += sum(r['monthly_savings'] for r in recs)
        
        # Generate Word document
        doc = generate_word_report(recommendations, total_savings, client_name)
        
        # Save to bytes
        buffer = BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        file_content = buffer.read()
        
        # Format filename
        client_name_formatted = client_name.replace(' ', '-')
        filename = f"{client_name_formatted}-CostOptimizer360-{datetime.now().strftime('%Y%m%d')}.docx"
        
        return jsonify({
            'file': base64.b64encode(file_content).decode('utf-8'),
            'filename': filename
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
    print("\nPress Ctrl+C to stop the server\n")
    app.run(host=host, port=port, debug=False)
