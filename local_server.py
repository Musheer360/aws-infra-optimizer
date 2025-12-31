#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'lambda'))

from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
import json
from datetime import datetime
from io import BytesIO

app = Flask(__name__)
CORS(app)

@app.route('/')
def index():
    return send_from_directory('frontend', 'index-local.html')

@app.route('/optimize', methods=['POST', 'OPTIONS'])
def optimize():
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.json
        
        from lambda_function import (
            scan_ec2_instances, scan_ebs_volumes, scan_rds_instances,
            scan_lambda_functions, scan_elastic_ips, generate_word_report
        )
        import boto3
        
        # Use provided credentials (support session token for temporary credentials)
        session_kwargs = {
            'aws_access_key_id': data.get('accessKeyId'),
            'aws_secret_access_key': data.get('secretAccessKey'),
            'region_name': data.get('region', 'us-east-1')
        }
        # Add session token if provided
        if data.get('sessionToken'):
            session_kwargs['aws_session_token'] = data['sessionToken']
        session = boto3.Session(**session_kwargs)
        
        recommendations = {}
        total_savings = 0.0
        
        services = data.get('services', ['ec2', 'ebs', 'rds', 'lambda', 'eip'])
        
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
        
        doc = generate_word_report(
            recommendations,
            total_savings,
            data.get('clientName', 'Client')
        )
        
        buffer = BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        
        filename = f"{data.get('clientName', 'Client').replace(' ', '-')}-InfraOptimization-{datetime.now().strftime('%Y%m%d')}.docx"
        
        return send_file(
            buffer,
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("\n" + "="*60)
    print("AWS Infrastructure Optimizer - Local Server")
    print("="*60)
    print("\nServer running at: http://localhost:5000")
    print("\nPress Ctrl+C to stop\n")
    app.run(host='127.0.0.1', port=5000, debug=False)
