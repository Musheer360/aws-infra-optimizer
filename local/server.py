#!/usr/bin/env python3
"""
CostOptimizer360 - Local Web Server
Flask-based backend server that mirrors the AWS Lambda functionality.
Runs on localhost:5000 by default.
"""

import os
import sys
import base64
import uuid
import threading
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

# Add lambda directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'lambda'))

# Get the directory where server.py is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(SCRIPT_DIR, 'web')
SHARED_ASSET_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), 'lambda', 'web')

app = Flask(__name__, static_folder=WEB_DIR)
CORS(app)

# Progress tracking for scans
SCAN_PROGRESS = {}


@app.route('/')
def serve_frontend():
    """Serve the main frontend page."""
    return send_from_directory(WEB_DIR, 'index.html')


@app.route('/assets/<path:filename>')
def serve_shared_asset(filename):
    """Serve the canonical UI assets shared with the cloud frontend."""
    return send_from_directory(SHARED_ASSET_DIR, filename)


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
    """Run the scan in a background thread with progress updates.

    Delegates to the shared lambda_function.run_full_scan so local mode has full
    parity with the Lambda backend (same scanners, pricing, enrichment, reports).
    """
    try:
        from lambda_function import run_full_scan, make_report, scan_result_summary

        client_name = body.get('clientName', 'Client')
        export_format = body.get('exportFormat', 'docx')

        def progress_cb(step, total, label):
            SCAN_PROGRESS[scan_id] = {
                'status': 'scanning',
                'current_service': label,
                'progress': min(97, round(step / max(total, 1) * 100)),
                'step': step,
                'total_steps': total,
            }

        result = run_full_scan(body, progress_cb=progress_cb)

        SCAN_PROGRESS[scan_id] = {
            'status': 'generating',
            'current_service': 'Generating report...',
            'progress': 98,
        }

        content, filename = make_report(result, client_name, export_format)
        summary = scan_result_summary(result)
        summary['file'] = base64.b64encode(content).decode('utf-8')
        summary['filename'] = filename

        SCAN_PROGRESS[scan_id] = {
            'status': 'complete',
            'current_service': 'Complete',
            'progress': 100,
            'result': summary,
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
            # Synchronous mode (backward compatible) - shared scan pipeline.
            from lambda_function import run_full_scan, make_report, scan_result_summary

            client_name = body.get('clientName', 'Client')
            export_format = body.get('exportFormat', 'docx')

            result = run_full_scan(body)
            content, filename = make_report(result, client_name, export_format)
            summary = scan_result_summary(result)
            summary['file'] = base64.b64encode(content).decode('utf-8')
            summary['filename'] = filename
            return jsonify(summary)
    
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
