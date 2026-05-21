from flask import Flask, render_template, request, jsonify, send_file
import os
from supabase import create_client
import uuid
from werkzeug.utils import secure_filename
import csv
import io
from datetime import datetime, timezone, timedelta
import traceback
import json
import base64
import logging
from logging.handlers import RotatingFileHandler

# ============ TIMEZONE HELPER FUNCTIONS ============

def get_brunei_time():
    """Get current time in Brunei (UTC+8)"""
    utc_now = datetime.now(timezone.utc)
    brunei_time = utc_now + timedelta(hours=8)
    return brunei_time

def get_brunei_time_iso():
    """Get current time in Brunei as ISO string"""
    return get_brunei_time().isoformat()

def format_brunei_time(date_string):
    """Format a date string to Brunei time display"""
    if not date_string:
        return '-'
    try:
        if isinstance(date_string, str):
            dt = datetime.fromisoformat(date_string.replace('Z', '+00:00'))
        else:
            dt = date_string
        
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        
        brunei_dt = dt.astimezone(timezone(timedelta(hours=8)))
        return brunei_dt.strftime('%d/%m/%Y %H:%M:%S')
    except Exception as e:
        return date_string

# ============ INITIALIZATION ============

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'moe-tech-report-secret-key-change-in-production')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp'}

app.jinja_env.globals.update(format_brunei_time=format_brunei_time)

# ============ LOGGING SETUP ============

if not os.path.exists('logs'):
    os.makedirs('logs')

file_handler = RotatingFileHandler('logs/app.log', maxBytes=10240, backupCount=10)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
file_handler.setLevel(logging.INFO)
app.logger.addHandler(file_handler)
app.logger.setLevel(logging.INFO)
app.logger.info('MOE Technical Report System startup')

# ============ SUPABASE CONFIGURATION ============

SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://megrxcfmcwrttiwujddh.supabase.co')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1lZ3J4Y2ZtY3dydHRpd3VqZGRoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzkwNDA4ODgsImV4cCI6MjA5NDYxNjg4OH0.fmwcV6fqqr-hO6hRPTzER6eODl6zffwud9heIchMNkw')

try:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    app.logger.info("✅ Supabase client initialized successfully")
except Exception as e:
    app.logger.error(f"❌ Failed to initialize Supabase client: {e}")
    supabase = None

# ============ HELPER FUNCTIONS ============

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def create_directories():
    directories = ['uploads', 'logs']
    for directory in directories:
        try:
            os.makedirs(directory, exist_ok=True)
            app.logger.info(f"📁 Directory ready: {directory}")
        except Exception as e:
            app.logger.error(f"❌ Failed to create directory {directory}: {e}")

def test_supabase_connection():
    if not supabase:
        app.logger.warning("⚠️ Supabase client not initialized")
        return False
    
    try:
        response = supabase.table("technicians").select("id").limit(1).execute()
        app.logger.info("✅ Supabase connection test successful")
        return True
    except Exception as e:
        app.logger.error(f"❌ Supabase connection test failed: {e}")
        return False

# ============ ROUTES ============

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/reports')
def reports_page():
    return render_template('reports.html')

@app.route('/water-reports')
def water_reports():
    return render_template('water_reports.html')

@app.route('/electricity-reports')
def electricity_reports():
    return render_template('electricity_reports.html')

@app.route('/telephone-reports')
def telephone_reports():
    return render_template('telephone_reports.html')

@app.route('/new-report')
def new_report():
    return render_template('new_report.html')

@app.route('/schools')
def schools_page():
    return render_template('schools.html')

@app.route('/departments')
def departments_page():
    return render_template('departments.html')

@app.route('/technicians')
def technicians_page():
    return render_template('technicians.html')

@app.route('/my-reports')
def my_reports():
    return render_template('my_reports.html')

@app.route('/team-leader')
def team_leader():
    return render_template('team_leader.html')

# ============ TECHNICIAN API ============

@app.route('/api/technicians', methods=['GET'])
def get_technicians():
    try:
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        
        response = supabase.table("technicians").select("*").order("id", desc=False).execute()
        
        technicians = []
        if response.data:
            for tech in response.data:
                tech_dict = dict(tech)
                if 'specializations' in tech_dict and tech_dict['specializations']:
                    if isinstance(tech_dict['specializations'], str):
                        try:
                            tech_dict['specializations'] = json.loads(tech_dict['specializations'])
                        except:
                            tech_dict['specializations'] = []
                    elif isinstance(tech_dict['specializations'], list):
                        pass
                    else:
                        tech_dict['specializations'] = []
                else:
                    tech_dict['specializations'] = []
                tech_dict['is_authorized'] = tech_dict.get('is_authorized', False)
                technicians.append(tech_dict)
        
        return jsonify(technicians)
    except Exception as e:
        app.logger.error(f"Error getting technicians: {e}")
        return jsonify([]), 500

@app.route('/api/technicians', methods=['POST'])
def create_technician():
    try:
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        
        data = request.get_json()
        specializations = data.get('specializations', [])
        
        technician_data = {
            "name": data.get('name'),
            "role": data.get('role', 'technician'),
            "employee_id": data.get('employee_id'),
            "phone": data.get('phone'),
            "email": data.get('email'),
            "specializations": json.dumps(specializations) if specializations else '[]',
            "is_authorized": data.get('is_authorized', False),
            "created_at": get_brunei_time_iso()
        }
        
        if not technician_data['name']:
            return jsonify({'success': False, 'error': 'Name is required'}), 400
        
        if not specializations or len(specializations) == 0:
            return jsonify({'success': False, 'error': 'At least one specialization is required'}), 400
        
        response = supabase.table("technicians").insert(technician_data).execute()
        
        if response.data:
            app.logger.info(f"Technician created: {technician_data['name']}")
            return jsonify({'success': True, 'data': response.data[0]})
        else:
            return jsonify({'success': False, 'error': 'Failed to create technician'}), 500
            
    except Exception as e:
        app.logger.error(f"Error creating technician: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/technicians/<int:tech_id>', methods=['PUT'])
def update_technician(tech_id):
    try:
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        
        data = request.get_json()
        update_data = {}
        
        allowed_fields = ['name', 'role', 'employee_id', 'phone', 'email', 'is_authorized']
        for field in allowed_fields:
            if field in data:
                update_data[field] = data[field]
        
        if 'specializations' in data:
            update_data['specializations'] = json.dumps(data['specializations'])
        
        if not update_data:
            return jsonify({'success': False, 'error': 'No data to update'}), 400
        
        response = supabase.table("technicians").update(update_data).eq("id", tech_id).execute()
        
        if response.data:
            app.logger.info(f"Technician updated: ID {tech_id}")
            return jsonify({'success': True, 'data': response.data[0]})
        else:
            return jsonify({'success': False, 'error': 'Technician not found'}), 404
            
    except Exception as e:
        app.logger.error(f"Error updating technician: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/technicians/<int:tech_id>', methods=['DELETE'])
def delete_technician(tech_id):
    try:
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        
        reports = supabase.table("technical_reports").select("id").eq("technician_id", tech_id).limit(1).execute()
        if reports.data and len(reports.data) > 0:
            return jsonify({'success': False, 'error': 'Cannot delete technician with assigned reports'}), 400
        
        response = supabase.table("technicians").delete().eq("id", tech_id).execute()
        
        if response.data:
            app.logger.info(f"Technician deleted: ID {tech_id}")
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Technician not found'}), 404
            
    except Exception as e:
        app.logger.error(f"Error deleting technician: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/technicians/<int:tech_id>/authorization', methods=['GET'])
def check_technician_authorization(tech_id):
    try:
        if not supabase:
            return jsonify({'authorized': False}), 500
        
        response = supabase.table("technicians").select("is_authorized").eq("id", tech_id).execute()
        
        if response.data and len(response.data) > 0:
            is_authorized = response.data[0].get('is_authorized', False)
            return jsonify({'authorized': is_authorized})
        else:
            return jsonify({'authorized': False}), 404
            
    except Exception as e:
        app.logger.error(f"Error checking authorization: {e}")
        return jsonify({'authorized': False}), 500

# ============ SCHOOLS API ============

@app.route('/api/schools', methods=['GET'])
def get_schools():
    try:
        if not supabase:
            return jsonify([]), 500
        
        response = supabase.table("schools").select("*").order("name", desc=False).execute()
        return jsonify(response.data if response.data else [])
    except Exception as e:
        app.logger.error(f"Error getting schools: {e}")
        return jsonify([]), 500

@app.route('/api/departments', methods=['GET'])
def get_departments():
    try:
        if not supabase:
            return jsonify([]), 500
        
        response = supabase.table("departments").select("*").order("name", desc=False).execute()
        return jsonify(response.data if response.data else [])
    except Exception as e:
        app.logger.error(f"Error getting departments: {e}")
        return jsonify([]), 500

# ============ TECHNICAL REPORTS API ============

@app.route('/api/technical-reports', methods=['GET'])
def get_technical_reports():
    try:
        if not supabase:
            return jsonify([]), 500
        
        report_type = request.args.get('type')
        entity_type = request.args.get('entity_type')
        entity_id = request.args.get('entity_id')
        status = request.args.get('status')
        priority = request.args.get('priority')
        technician_id = request.args.get('technician_id')
        team_leader_ack = request.args.get('team_leader_acknowledged')
        
        query = supabase.table("technical_reports").select("*")
        
        if report_type:
            query = query.eq("report_type", report_type)
        if entity_type:
            query = query.eq("entity_type", entity_type)
        if entity_id:
            query = query.eq("entity_id", int(entity_id))
        if status:
            query = query.eq("status", status)
        if priority:
            query = query.eq("priority", priority)
        if technician_id:
            query = query.eq("technician_id", int(technician_id))
        if team_leader_ack is not None:
            query = query.eq("team_leader_acknowledged", team_leader_ack.lower() == 'true')
        
        response = query.order("created_at", desc=True).execute()
        
        reports = []
        if response.data:
            for report in response.data:
                report_data = dict(report)
                
                if report_data['entity_type'] == 'school':
                    entity = supabase.table("schools").select("name").eq("id", report_data['entity_id']).execute()
                    if entity.data:
                        report_data['entity_name'] = entity.data[0]['name']
                elif report_data['entity_type'] == 'department':
                    entity = supabase.table("departments").select("name").eq("id", report_data['entity_id']).execute()
                    if entity.data:
                        report_data['entity_name'] = entity.data[0]['name']
                
                if report_data.get('technician_id'):
                    tech = supabase.table("technicians").select("name, role").eq("id", report_data['technician_id']).execute()
                    if tech.data:
                        report_data['technician_name'] = tech.data[0]['name']
                        report_data['technician_role'] = tech.data[0]['role']
                
                reports.append(report_data)
        
        return jsonify(reports)
        
    except Exception as e:
        app.logger.error(f"Error getting technical reports: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/technical-reports', methods=['POST'])
def create_technical_report():
    try:
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        
        data = request.get_json()
        
        required_fields = ['report_type', 'entity_type', 'entity_id', 'problem_type', 'complaint_details']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'error': f'{field} is required'}), 400
        
        reference_date = data.get('reference_date')
        if reference_date:
            try:
                reference_date = datetime.strptime(reference_date, '%Y-%m-%d').date().isoformat()
            except:
                reference_date = None
        
        report_data = {
            "report_type": data.get('report_type'),
            "entity_type": data.get('entity_type'),
            "entity_id": int(data.get('entity_id')),
            "account_number": data.get('account_number', ''),
            "meter_number": data.get('meter_number', ''),
            "phone_number": data.get('phone_number', ''),
            "number_of_lines": data.get('number_of_lines'),
            "problem_type": data.get('problem_type'),
            "complaint_details": data.get('complaint_details'),
            "priority": data.get('priority', 'medium'),
            "priority_with_tender": data.get('priority_with_tender', False),
            "status": data.get('status', 'pending'),
            "technician_id": data.get('technician_id'),
            "technician_notes": data.get('technician_notes', ''),
            "action_taken": data.get('action_taken', ''),
            "resolution_details": data.get('resolution_details', ''),
            "team_leader_notes": data.get('team_leader_notes', ''),
            "team_leader_acknowledged": False,
            "team_leader_acknowledged_at": None,
            "team_leader_id": None,
            "images": data.get('images', []),
            "reference_type": data.get('reference_type', ''),
            "reference_number": data.get('reference_number', ''),
            "reference_date": reference_date,
            "created_at": get_brunei_time_iso(),
            "updated_at": get_brunei_time_iso(),
            "print_count": 0,
            "last_printed_at": None
        }
        
        response = supabase.table("technical_reports").insert(report_data).execute()
        
        if response.data:
            app.logger.info(f"Technical report created: ID {response.data[0]['id']}")
            return jsonify({
                'success': True,
                'message': 'Report created successfully',
                'report': response.data[0]
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to create report'}), 500
            
    except Exception as e:
        app.logger.error(f"Error creating technical report: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/technical-reports/<int:report_id>', methods=['PUT'])
def update_technical_report(report_id):
    try:
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        
        data = request.get_json()
        
        allowed_fields = [
            'problem_type', 'complaint_details', 'priority', 'priority_with_tender', 'status',
            'technician_notes', 'action_taken', 'resolution_details',
            'team_leader_notes', 'images', 'account_number', 'meter_number',
            'phone_number', 'number_of_lines',
            'reference_type', 'reference_number', 'reference_date'
        ]
        
        update_data = {}
        for field in allowed_fields:
            if field in data:
                if field == 'reference_date' and data[field]:
                    try:
                        update_data[field] = datetime.strptime(data[field], '%Y-%m-%d').date().isoformat()
                    except:
                        update_data[field] = None
                else:
                    update_data[field] = data[field]
        
        update_data['updated_at'] = get_brunei_time_iso()
        
        if not update_data:
            return jsonify({'success': False, 'error': 'No data to update'}), 400
        
        response = supabase.table("technical_reports").update(update_data).eq("id", report_id).execute()
        
        if response.data:
            app.logger.info(f"Technical report updated: ID {report_id}")
            return jsonify({
                'success': True,
                'message': 'Report updated successfully',
                'report': response.data[0]
            })
        else:
            return jsonify({'success': False, 'error': 'Report not found'}), 404
            
    except Exception as e:
        app.logger.error(f"Error updating technical report: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/technical-reports/<int:report_id>/acknowledge', methods=['POST'])
def acknowledge_report(report_id):
    try:
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        
        data = request.get_json()
        team_leader_id = data.get('team_leader_id')
        
        auth_response = supabase.table("technicians").select("is_authorized").eq("id", team_leader_id).execute()
        
        if not auth_response.data or not auth_response.data[0].get('is_authorized', False):
            return jsonify({
                'success': False, 
                'error': 'You are not authorized to acknowledge reports. Only designated team leaders can acknowledge.'
            }), 403
        
        update_data = {
            "team_leader_acknowledged": True,
            "team_leader_acknowledged_at": get_brunei_time_iso(),
            "team_leader_id": team_leader_id,
            "team_leader_notes": data.get('team_leader_notes', ''),
            "updated_at": get_brunei_time_iso()
        }
        
        response = supabase.table("technical_reports").update(update_data).eq("id", report_id).execute()
        
        if response.data:
            app.logger.info(f"Report acknowledged by authorized user ID {team_leader_id}: {report_id}")
            return jsonify({
                'success': True,
                'message': 'Report acknowledged successfully',
                'report': response.data[0]
            })
        else:
            return jsonify({'success': False, 'error': 'Report not found'}), 404
            
    except Exception as e:
        app.logger.error(f"Error acknowledging report: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/technical-reports/<int:report_id>', methods=['DELETE'])
def delete_technical_report(report_id):
    try:
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        
        response = supabase.table("technical_reports").delete().eq("id", report_id).execute()
        
        if response.data:
            app.logger.info(f"Technical report deleted: ID {report_id}")
            return jsonify({
                'success': True,
                'message': 'Report deleted successfully'
            })
        else:
            return jsonify({'success': False, 'error': 'Report not found'}), 404
            
    except Exception as e:
        app.logger.error(f"Error deleting technical report: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/technical-reports/<int:report_id>/track-print', methods=['POST'])
def track_print(report_id):
    try:
        if not supabase:
            return jsonify({'success': False}), 500
        
        current = supabase.table("technical_reports").select("print_count").eq("id", report_id).execute()
        current_count = current.data[0].get('print_count', 0) if current.data else 0
        
        response = supabase.table("technical_reports").update({
            "print_count": current_count + 1,
            "last_printed_at": get_brunei_time_iso()
        }).eq("id", report_id).execute()
        
        return jsonify({'success': True})
    except Exception as e:
        app.logger.error(f"Error tracking print: {e}")
        return jsonify({'success': False}), 500

# ============ IMAGE UPLOAD ============

@app.route('/api/upload-image', methods=['POST'])
def upload_image():
    try:
        if 'image' not in request.files:
            return jsonify({'success': False, 'error': 'No image file provided'}), 400
        
        file = request.files['image']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No image selected'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'success': False, 'error': 'File type not allowed'}), 400
        
        ext = file.filename.rsplit('.', 1)[1].lower()
        filename = secure_filename(f"{uuid.uuid4().hex}_{get_brunei_time().strftime('%Y%m%d_%H%M%S')}.{ext}")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        file.save(filepath)
        app.logger.info(f"Image saved: {filepath}")
        
        with open(filepath, 'rb') as img_file:
            img_data = base64.b64encode(img_file.read()).decode('utf-8')
        
        image_record = {
            "filename": filename,
            "original_name": file.filename,
            "filepath": filepath,
            "file_size": os.path.getsize(filepath),
            "image_data_base64": img_data,
            "uploaded_at": get_brunei_time_iso()
        }
        
        if supabase:
            try:
                response = supabase.table("report_images").insert(image_record).execute()
                if response.data:
                    app.logger.info(f"Image record saved to Supabase: ID {response.data[0]['id']}")
            except Exception as e:
                app.logger.warning(f"Could not save image to Supabase: {e}")
        
        image_url = f"/api/images/{filename}"
        
        return jsonify({
            'success': True,
            'image_url': image_url,
            'filename': filename,
            'message': 'Image uploaded successfully'
        })
        
    except Exception as e:
        app.logger.error(f"Error uploading image: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/images/<filename>')
def get_image(filename):
    try:
        from flask import send_from_directory
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
    except Exception as e:
        app.logger.error(f"Error serving image {filename}: {e}")
        return jsonify({'error': 'Image not found'}), 404

# ============ DASHBOARD STATISTICS ============

@app.route('/api/dashboard-stats')
def get_dashboard_stats():
    try:
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        
        water_reports = supabase.table("technical_reports").select("*", count="exact").eq("report_type", "water").execute()
        electricity_reports = supabase.table("technical_reports").select("*", count="exact").eq("report_type", "electricity").execute()
        telephone_reports = supabase.table("technical_reports").select("*", count="exact").eq("report_type", "telephone").execute()
        
        pending_reports = supabase.table("technical_reports").select("*", count="exact").eq("status", "pending").execute()
        in_progress_reports = supabase.table("technical_reports").select("*", count="exact").eq("status", "in_progress").execute()
        resolved_reports = supabase.table("technical_reports").select("*", count="exact").eq("status", "resolved").execute()
        
        acknowledged_reports = supabase.table("technical_reports").select("*", count="exact").eq("team_leader_acknowledged", True).execute()
        
        recent_reports = supabase.table("technical_reports").select("*").order("created_at", desc=True).limit(10).execute()
        
        recent_list = []
        if recent_reports.data:
            for report in recent_reports.data:
                report_dict = dict(report)
                
                if report_dict['entity_type'] == 'school':
                    entity = supabase.table("schools").select("name").eq("id", report_dict['entity_id']).execute()
                    if entity.data:
                        report_dict['entity_name'] = entity.data[0]['name']
                else:
                    entity = supabase.table("departments").select("name").eq("id", report_dict['entity_id']).execute()
                    if entity.data:
                        report_dict['entity_name'] = entity.data[0]['name']
                
                if report_dict.get('technician_id'):
                    tech = supabase.table("technicians").select("name").eq("id", report_dict['technician_id']).execute()
                    if tech.data:
                        report_dict['technician_name'] = tech.data[0]['name']
                
                recent_list.append(report_dict)
        
        stats = {
            'total_reports': (water_reports.count or 0) + (electricity_reports.count or 0) + (telephone_reports.count or 0),
            'by_type': {
                'water': water_reports.count or 0,
                'electricity': electricity_reports.count or 0,
                'telephone': telephone_reports.count or 0
            },
            'by_status': {
                'pending': pending_reports.count or 0,
                'in_progress': in_progress_reports.count or 0,
                'resolved': resolved_reports.count or 0
            },
            'acknowledged_count': acknowledged_reports.count or 0,
            'recent_reports': recent_list
        }
        
        return jsonify(stats)
        
    except Exception as e:
        app.logger.error(f"Error getting dashboard stats: {e}")
        return jsonify({'error': str(e)}), 500

# ============ EXPORT REPORTS ============

@app.route('/api/export-reports', methods=['GET'])
def export_reports():
    try:
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        
        report_type = request.args.get('type')
        status = request.args.get('status')
        
        query = supabase.table("technical_reports").select("*")
        
        if report_type:
            query = query.eq("report_type", report_type)
        if status:
            query = query.eq("status", status)
        
        response = query.order("created_at", desc=True).execute()
        
        if not response.data:
            return jsonify({'success': False, 'error': 'No data to export'}), 404
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        headers = [
            'Utility #', 'Report ID', 'Type', 'Entity Type', 'Entity Name', 'Account Number',
            'Meter Number', 'Phone Number', 'Number of Lines', 'Problem Type',
            'Complaint Details', 'Priority', 'Priority with Tender', 'Status', 'Technician Name',
            'Technician Notes', 'Action Taken', 'Resolution Details',
            'Team Leader Acknowledged', 'Team Leader Notes', 'Reference Type',
            'Reference Number', 'Reference Date', 'Print Count', 'Last Printed',
            'Created At', 'Updated At'
        ]
        writer.writerow(headers)
        
        for report in response.data:
            entity_name = ''
            if report['entity_type'] == 'school':
                entity = supabase.table("schools").select("name").eq("id", report['entity_id']).execute()
                if entity.data:
                    entity_name = entity.data[0]['name']
            else:
                entity = supabase.table("departments").select("name").eq("id", report['entity_id']).execute()
                if entity.data:
                    entity_name = entity.data[0]['name']
            
            tech_name = ''
            if report.get('technician_id'):
                tech = supabase.table("technicians").select("name").eq("id", report['technician_id']).execute()
                if tech.data:
                    tech_name = tech.data[0]['name']
            
            writer.writerow([
                report.get('utility_number', ''),
                report.get('id', ''),
                report.get('report_type', ''),
                report.get('entity_type', ''),
                entity_name,
                report.get('account_number', ''),
                report.get('meter_number', ''),
                report.get('phone_number', ''),
                report.get('number_of_lines', ''),
                report.get('problem_type', ''),
                report.get('complaint_details', ''),
                report.get('priority', ''),
                'Yes' if report.get('priority_with_tender') else 'No',
                report.get('status', ''),
                tech_name,
                report.get('technician_notes', ''),
                report.get('action_taken', ''),
                report.get('resolution_details', ''),
                'Yes' if report.get('team_leader_acknowledged') else 'No',
                report.get('team_leader_notes', ''),
                report.get('reference_type', ''),
                report.get('reference_number', ''),
                report.get('reference_date', ''),
                report.get('print_count', 0),
                report.get('last_printed_at', ''),
                report.get('created_at', ''),
                report.get('updated_at', '')
            ])
        
        output.seek(0)
        
        timestamp = get_brunei_time().strftime('%Y%m%d_%H%M%S')
        filename = f"technical_reports_{timestamp}.csv"
        
        app.logger.info(f"Reports exported: {filename}")
        
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8-sig')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        app.logger.error(f"Error exporting reports: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ============ HEALTH CHECK ============

@app.route('/health')
def health_check():
    supabase_status = test_supabase_connection()
    
    return jsonify({
        'status': 'healthy' if supabase_status else 'degraded',
        'timestamp': get_brunei_time_iso(),
        'version': '1.0.0',
        'supabase_connected': supabase_status,
        'service': 'MOE Technical Report System',
        'environment': os.environ.get('FLASK_ENV', 'production')
    })

@app.route('/api/health')
def api_health():
    return jsonify({
        'status': 'ok',
        'timestamp': get_brunei_time_iso()
    })

# ============ ERROR HANDLERS ============

@app.errorhandler(404)
def not_found_error(error):
    app.logger.warning(f"404 error: {request.url}")
    return jsonify({'error': 'Resource not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    app.logger.error(f"500 error: {error}")
    return jsonify({'error': 'Internal server error'}), 500

# ============ APPLICATION STARTUP ============

def init_app():
    create_directories()
    
    app.logger.info("=" * 60)
    app.logger.info("🏫 MOE Technical Report System Starting")
    app.logger.info("Ministry of Education - Brunei Darussalam")
    app.logger.info("=" * 60)
    app.logger.info("📋 System for Water, Electricity & Telephone Reports")
    app.logger.info("👥 Users: Senior Technicians & Technicians")
    app.logger.info(f"🌍 Timezone: UTC+8 (Brunei Time)")
    app.logger.info("=" * 60)
    
    if test_supabase_connection():
        app.logger.info("✅ Supabase connection established")
    else:
        app.logger.warning("⚠️ Supabase connection failed - check credentials")
    
    env = os.environ.get('FLASK_ENV', 'production')
    app.logger.info(f"🌍 Running in {env} mode")
    
    port = int(os.environ.get('PORT', 5000))
    app.logger.info(f"🚀 Server will run on port: {port}")
    
    app.logger.info("✅ Application initialization complete")

init_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    
    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug_mode
    )
