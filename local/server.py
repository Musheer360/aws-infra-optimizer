#!/usr/bin/env python3
"""
AWS Infrastructure Optimizer - Local Server
Full web interface running on localhost using AWS CLI credentials
"""
import os
import sys
import json
from datetime import datetime, timedelta
from io import BytesIO
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS

# Add lambda directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'lambda'))

app = Flask(__name__)
CORS(app)

# Default port and host
PORT = int(os.environ.get('PORT', 5000))
HOST = os.environ.get('HOST', '127.0.0.1')

@app.route('/')
def index():
    """Serve the local web interface"""
    return send_from_directory(os.path.join(os.path.dirname(__file__), 'web'), 'index.html')

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({'status': 'ok', 'timestamp': datetime.utcnow().isoformat()})

@app.route('/api/profiles')
def list_profiles():
    """List available AWS CLI profiles"""
    import configparser
    profiles = []
    
    # Check ~/.aws/credentials
    creds_file = os.path.expanduser('~/.aws/credentials')
    if os.path.exists(creds_file):
        config = configparser.ConfigParser()
        config.read(creds_file)
        profiles = list(config.sections())
    
    # Also check ~/.aws/config for SSO profiles
    config_file = os.path.expanduser('~/.aws/config')
    if os.path.exists(config_file):
        config = configparser.ConfigParser()
        config.read(config_file)
        for section in config.sections():
            if section.startswith('profile '):
                profile_name = section.replace('profile ', '')
                if profile_name not in profiles:
                    profiles.append(profile_name)
    
    # Add default if not already present
    if 'default' not in profiles:
        profiles.insert(0, 'default')
    
    return jsonify({'profiles': profiles})

@app.route('/api/verify', methods=['POST'])
def verify_credentials():
    """Verify AWS credentials are working"""
    try:
        import boto3
        data = request.json or {}
        profile = data.get('profile', 'default')
        region = data.get('region', 'us-east-1')
        
        # If credentials are provided directly, use them
        if data.get('accessKeyId') and data.get('secretAccessKey'):
            session_kwargs = {
                'aws_access_key_id': data['accessKeyId'],
                'aws_secret_access_key': data['secretAccessKey'],
                'region_name': region
            }
            if data.get('sessionToken'):
                session_kwargs['aws_session_token'] = data['sessionToken']
            session = boto3.Session(**session_kwargs)
        else:
            # Use AWS CLI profile
            session = boto3.Session(profile_name=profile, region_name=region)
        
        sts = session.client('sts')
        identity = sts.get_caller_identity()
        
        return jsonify({
            'valid': True,
            'account': identity['Account'],
            'arn': identity['Arn'],
            'user_id': identity['UserId']
        })
    except Exception as e:
        return jsonify({
            'valid': False,
            'error': str(e)
        }), 400

@app.route('/api/generate', methods=['POST', 'OPTIONS'])
def generate_report():
    """Generate optimization report"""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        import boto3
        from lambda_function import (
            scan_ec2_instances, scan_ebs_volumes, scan_rds_instances,
            scan_lambda_functions, scan_elastic_ips, generate_word_report
        )
        
        data = request.json
        if not data:
            return jsonify({'error': 'Request body required'}), 400
        
        client_name = data.get('clientName', 'Client')
        region = data.get('region', 'us-east-1')
        services = data.get('services', ['ec2', 'ebs', 'rds', 'lambda', 'eip'])
        
        # Create boto3 session based on auth method
        if data.get('accessKeyId') and data.get('secretAccessKey'):
            # Direct credentials
            session_kwargs = {
                'aws_access_key_id': data['accessKeyId'],
                'aws_secret_access_key': data['secretAccessKey'],
                'region_name': region
            }
            if data.get('sessionToken'):
                session_kwargs['aws_session_token'] = data['sessionToken']
            session = boto3.Session(**session_kwargs)
        else:
            # AWS CLI profile
            profile = data.get('profile', 'default')
            session = boto3.Session(profile_name=profile, region_name=region)
        
        # Verify credentials before proceeding
        try:
            sts = session.client('sts')
            sts.get_caller_identity()
        except Exception as e:
            return jsonify({
                'error': f'AWS credentials error: {str(e)}. Please run "aws configure" or check your credentials.'
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
        
        # Save to buffer
        buffer = BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        
        filename = f"{client_name.replace(' ', '-')}-InfraOptimization-{datetime.now().strftime('%Y%m%d')}.docx"
        
        return send_file(
            buffer,
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print()
    print("=" * 60)
    print("  AWS Infrastructure Optimizer - Local Server")
    print("=" * 60)
    print()
    print(f"  Frontend: http://{HOST}:{PORT}")
    print(f"  API:      http://{HOST}:{PORT}/api/generate")
    print()
    print("  Press Ctrl+C to stop")
    print()
    app.run(host=HOST, port=PORT, debug=False)
