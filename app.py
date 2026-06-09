from flask import Flask, render_template, request, jsonify, send_file
import os
from supabase import create_client
import uuid
import csv
import io
from datetime import datetime, timezone, timedelta
import json
import logging
from logging.handlers import RotatingFileHandler
from PIL import Image
import io as io_lib
import requests
import base64

# ============ TIMEZONE HELPER FUNCTIONS ============

def get_brunei_time():
    utc_now = datetime.now(timezone.utc)
    brunei_time = utc_now + timedelta(hours=8)
    return brunei_time

def get_brunei_time_iso():
    return get_brunei_time().isoformat()

def format_brunei_time(date_string):
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

app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

app.config['MAX_IMAGE_DIMENSION'] = 1200
app.config['IMAGE_QUALITY'] = 75

app.jinja_env.globals.update(format_brunei_time=format_brunei_time)

# ============ LOGGING SETUP ============

if not os.path.exists('logs'):
    os.makedirs('logs')

file_handler = RotatingFileHandler('logs/app.log', maxBytes=10240, backupCount=10)
file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s: %(message)s'))
file_handler.setLevel(logging.INFO)
app.logger.addHandler(file_handler)
app.logger.setLevel(logging.INFO)

# ============ SUPABASE CONFIGURATION ============

SUPABASE_URL = 'https://megrxcfmcwrttiwujddh.supabase.co'
SUPABASE_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1lZ3J4Y2ZtY3dydHRpd3VqZGRoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzkwNDA4ODgsImV4cCI6MjA5NDYxNjg4OH0.fmwcV6fqqr-hO6hRPTzER6eODl6zffwud9heIchMNkw'
SUPABASE_STORAGE_BUCKET = 'mapping-images'

try:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    app.logger.info("Supabase client initialized successfully")
except Exception as e:
    app.logger.error(f"Failed to initialize Supabase client: {e}")
    supabase = None

# ============ HELPER FUNCTIONS ============

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def create_directories():
    directories = ['uploads', 'logs']
    for directory in directories:
        try:
            os.makedirs(directory, exist_ok=True)
        except Exception as e:
            app.logger.error(f"Failed to create directory {directory}: {e}")

def init_supabase_storage():
    """Initialize Supabase storage bucket"""
    if not supabase:
        return False
    try:
        supabase.storage.create_bucket(SUPABASE_STORAGE_BUCKET, {'public': True})
        app.logger.info(f"Created storage bucket: {SUPABASE_STORAGE_BUCKET}")
    except Exception as e:
        app.logger.info(f"Storage bucket already exists: {e}")
    return True

def compress_image(file_content, filename):
    try:
        img = Image.open(io_lib.BytesIO(file_content))
        if img.mode in ('RGBA', 'LA', 'P'):
            rgb_img = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'RGBA':
                rgb_img.paste(img, mask=img.split()[-1])
            else:
                rgb_img.paste(img)
            img = rgb_img
        elif img.mode != 'RGB':
            img = img.convert('RGB')
        
        max_dimension = app.config['MAX_IMAGE_DIMENSION']
        if img.width > max_dimension or img.height > max_dimension:
            ratio = min(max_dimension / img.width, max_dimension / img.height)
            new_size = (int(img.width * ratio), int(img.height * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
        
        output = io_lib.BytesIO()
        img.save(output, format='JPEG', quality=app.config['IMAGE_QUALITY'], optimize=True)
        compressed_content = output.getvalue()
        app.logger.info(f"Image compressed: {len(file_content)/1024:.1f}KB -> {len(compressed_content)/1024:.1f}KB")
        return compressed_content, 'jpg'
    except Exception as e:
        app.logger.error(f"Image compression error: {e}")
        return file_content, 'jpg'

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

@app.route('/mapping')
def mapping_page():
    return render_template('mapping.html')

# ============ TECHNICIAN API ============

@app.route('/api/technicians', methods=['GET'])
def get_technicians():
    try:
        if not supabase:
            return jsonify([]), 500
        response = supabase.table("technicians").select("*").order("id", desc=False).execute()
        technicians = []
        if response.data:
            for tech in response.data:
                tech_dict = dict(tech)
                tech_dict.pop('password', None)
                if 'specializations' in tech_dict and isinstance(tech_dict['specializations'], str):
                    try:
                        tech_dict['specializations'] = json.loads(tech_dict['specializations'])
                    except:
                        tech_dict['specializations'] = []
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
        password = data.get('password') or data.get('employee_id')
        technician_data = {
            "name": data.get('name'),
            "role": data.get('role', 'technician'),
            "employee_id": data.get('employee_id'),
            "phone": data.get('phone'),
            "email": data.get('email'),
            "specializations": json.dumps(specializations) if specializations else '[]',
            "is_authorized": data.get('is_authorized', False),
            "can_edit_technicians": data.get('can_edit_technicians', False),
            "password": password,
            "created_at": get_brunei_time_iso()
        }
        if not technician_data['name']:
            return jsonify({'success': False, 'error': 'Name is required'}), 400
        if not specializations or len(specializations) == 0:
            return jsonify({'success': False, 'error': 'At least one specialization is required'}), 400
        response = supabase.table("technicians").insert(technician_data).execute()
        if response.data:
            response.data[0].pop('password', None)
            return jsonify({'success': True, 'data': response.data[0]})
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
        allowed_fields = ['name', 'role', 'employee_id', 'phone', 'email', 'is_authorized', 'can_edit_technicians', 'password']
        for field in allowed_fields:
            if field in data and data[field] is not None:
                update_data[field] = data[field]
        if 'specializations' in data:
            update_data['specializations'] = json.dumps(data['specializations'])
        if not update_data:
            return jsonify({'success': False, 'error': 'No data to update'}), 400
        response = supabase.table("technicians").update(update_data).eq("id", tech_id).execute()
        if response.data:
            response.data[0].pop('password', None)
            return jsonify({'success': True, 'data': response.data[0]})
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
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Technician not found'}), 404
    except Exception as e:
        app.logger.error(f"Error deleting technician: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/technicians/verify-password', methods=['POST'])
def verify_technician_password():
    try:
        if not supabase:
            return jsonify({'success': False, 'error': 'Database not connected'}), 500
        data = request.get_json()
        technician_id = data.get('technician_id')
        password = data.get('password')
        if not technician_id or not password:
            return jsonify({'success': False, 'error': 'Technician ID and password required'}), 400
        response = supabase.table("technicians").select("password, employee_id").eq("id", technician_id).execute()
        if not response.data:
            return jsonify({'success': False, 'error': 'Technician not found'}), 404
        tech = response.data[0]
        stored_password = tech.get('password', '')
        employee_id = tech.get('employee_id', '')
        if stored_password and password == stored_password:
            return jsonify({'success': True, 'message': 'Password verified'})
        if not stored_password and password == employee_id:
            return jsonify({'success': True, 'message': 'Password verified'})
        return jsonify({'success': False, 'error': 'Invalid password'}), 401
    except Exception as e:
        app.logger.error(f"Error verifying password: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/technicians/change-password', methods=['POST'])
def change_technician_password():
    try:
        if not supabase:
            return jsonify({'success': False, 'error': 'Database not connected'}), 500
        data = request.get_json()
        technician_id = data.get('technician_id')
        current_password = data.get('current_password')
        new_password = data.get('new_password')
        if not technician_id or not current_password or not new_password:
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400
        response = supabase.table("technicians").select("password, employee_id").eq("id", technician_id).execute()
        if not response.data:
            return jsonify({'success': False, 'error': 'Technician not found'}), 404
        tech = response.data[0]
        stored_password = tech.get('password', '')
        employee_id = tech.get('employee_id', '')
        password_valid = (stored_password and current_password == stored_password) or (not stored_password and current_password == employee_id)
        if not password_valid:
            return jsonify({'success': False, 'error': 'Current password is incorrect'}), 401
        update_response = supabase.table("technicians").update({"password": new_password}).eq("id", technician_id).execute()
        if update_response.data:
            return jsonify({'success': True, 'message': 'Password changed successfully'})
        return jsonify({'success': False, 'error': 'Failed to update password'}), 500
    except Exception as e:
        app.logger.error(f"Error changing password: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ============ SCHOOLS API ============

@app.route('/api/schools', methods=['GET'])
def get_schools():
    try:
        if not supabase:
            return jsonify([]), 500
        response = supabase.table("schools").select("*").order("id", desc=False).execute()
        return jsonify(response.data if response.data else [])
    except Exception as e:
        app.logger.error(f"Error getting schools: {e}")
        return jsonify([]), 500

@app.route('/api/schools', methods=['POST'])
def create_school():
    try:
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        data = request.get_json()
        school_data = {
            "name": data.get('name'),
            "cluster_number": data.get('cluster_number'),
            "school_number": data.get('school_number'),
            "address": data.get('address'),
            "contact_person": data.get('contact_person'),
            "contact_phone": data.get('contact_phone'),
            "created_at": get_brunei_time_iso()
        }
        if not school_data['name']:
            return jsonify({'success': False, 'error': 'School name is required'}), 400
        response = supabase.table("schools").insert(school_data).execute()
        if response.data:
            return jsonify({'success': True, 'data': response.data[0]})
        return jsonify({'success': False, 'error': 'Failed to create school'}), 500
    except Exception as e:
        app.logger.error(f"Error creating school: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/schools/<int:school_id>', methods=['PUT'])
def update_school(school_id):
    try:
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        data = request.get_json()
        response = supabase.table("schools").update(data).eq("id", school_id).execute()
        if response.data:
            return jsonify({'success': True, 'data': response.data[0]})
        return jsonify({'success': False, 'error': 'School not found'}), 404
    except Exception as e:
        app.logger.error(f"Error updating school: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/schools/<int:school_id>', methods=['DELETE'])
def delete_school(school_id):
    try:
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        reports = supabase.table("technical_reports").select("id").eq("entity_id", school_id).eq("entity_type", "school").limit(1).execute()
        if reports.data:
            return jsonify({'success': False, 'error': 'Cannot delete school with existing reports'}), 400
        response = supabase.table("schools").delete().eq("id", school_id).execute()
        if response.data:
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'School not found'}), 404
    except Exception as e:
        app.logger.error(f"Error deleting school: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ============ DEPARTMENTS API ============

@app.route('/api/departments', methods=['GET'])
def get_departments():
    try:
        if not supabase:
            return jsonify([]), 500
        response = supabase.table("departments").select("*").order("id", desc=False).execute()
        return jsonify(response.data if response.data else [])
    except Exception as e:
        app.logger.error(f"Error getting departments: {e}")
        return jsonify([]), 500

@app.route('/api/departments', methods=['POST'])
def create_department():
    try:
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        data = request.get_json()
        dept_data = {
            "name": data.get('name'),
            "unit_name": data.get('unit_name') or data.get('name'),
            "address": data.get('address'),
            "contact_person": data.get('contact_person'),
            "contact_phone": data.get('contact_phone'),
            "created_at": get_brunei_time_iso()
        }
        if not dept_data['name']:
            return jsonify({'success': False, 'error': 'Department name is required'}), 400
        response = supabase.table("departments").insert(dept_data).execute()
        if response.data:
            return jsonify({'success': True, 'data': response.data[0]})
        return jsonify({'success': False, 'error': 'Failed to create department'}), 500
    except Exception as e:
        app.logger.error(f"Error creating department: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/departments/<int:dept_id>', methods=['PUT'])
def update_department(dept_id):
    try:
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        data = request.get_json()
        update_data = {}
        allowed_fields = ['name', 'unit_name', 'address', 'contact_person', 'contact_phone']
        for field in allowed_fields:
            if field in data and data[field] is not None:
                update_data[field] = data[field]
        if not update_data:
            return jsonify({'success': False, 'error': 'No data to update'}), 400
        response = supabase.table("departments").update(update_data).eq("id", dept_id).execute()
        if response.data:
            return jsonify({'success': True, 'data': response.data[0]})
        return jsonify({'success': False, 'error': 'Department not found'}), 404
    except Exception as e:
        app.logger.error(f"Error updating department: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/departments/<int:dept_id>', methods=['DELETE'])
def delete_department(dept_id):
    try:
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        reports = supabase.table("technical_reports").select("id").eq("entity_id", dept_id).eq("entity_type", "department").limit(1).execute()
        if reports.data:
            return jsonify({'success': False, 'error': 'Cannot delete department with existing reports'}), 400
        response = supabase.table("departments").delete().eq("id", dept_id).execute()
        if response.data:
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Department not found'}), 404
    except Exception as e:
        app.logger.error(f"Error deleting department: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ============ TECHNICAL REPORTS API ============

@app.route('/api/technical-reports', methods=['GET'])
def get_technical_reports():
    try:
        if not supabase:
            return jsonify([]), 500
        query = supabase.table("technical_reports").select("*")
        if request.args.get('type'):
            query = query.eq("report_type", request.args.get('type'))
        if request.args.get('entity_type'):
            query = query.eq("entity_type", request.args.get('entity_type'))
        if request.args.get('entity_id'):
            query = query.eq("entity_id", int(request.args.get('entity_id')))
        if request.args.get('status'):
            query = query.eq("status", request.args.get('status'))
        if request.args.get('technician_id'):
            query = query.eq("technician_id", int(request.args.get('technician_id')))
        response = query.order("created_at", desc=True).execute()
        reports = []
        if response.data:
            for report in response.data:
                report_data = dict(report)
                if report_data['entity_type'] == 'school':
                    entity = supabase.table("schools").select("name").eq("id", report_data['entity_id']).execute()
                    if entity.data:
                        report_data['entity_name'] = entity.data[0]['name']
                else:
                    entity = supabase.table("departments").select("name").eq("id", report_data['entity_id']).execute()
                    if entity.data:
                        report_data['entity_name'] = entity.data[0]['name']
                if report_data.get('technician_id'):
                    tech = supabase.table("technicians").select("name, role").eq("id", report_data['technician_id']).execute()
                    if tech.data:
                        report_data['technician_name'] = tech.data[0]['name']
                reports.append(report_data)
        return jsonify(reports)
    except Exception as e:
        app.logger.error(f"Error getting technical reports: {e}")
        return jsonify([]), 500

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
            "images": data.get('images', []),
            "reference_type": data.get('reference_type', ''),
            "reference_number": data.get('reference_number', ''),
            "reference_date": data.get('reference_date'),
            "created_at": get_brunei_time_iso(),
            "updated_at": get_brunei_time_iso()
        }
        response = supabase.table("technical_reports").insert(report_data).execute()
        if response.data:
            return jsonify({'success': True, 'message': 'Report created successfully', 'report': response.data[0]})
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
        allowed_fields = ['problem_type', 'complaint_details', 'priority', 'priority_with_tender', 'status',
                         'technician_notes', 'action_taken', 'images', 'account_number', 'meter_number',
                         'phone_number', 'number_of_lines', 'reference_type', 'reference_number', 'reference_date']
        update_data = {}
        for field in allowed_fields:
            if field in data:
                update_data[field] = data[field]
        update_data['updated_at'] = get_brunei_time_iso()
        if not update_data:
            return jsonify({'success': False, 'error': 'No data to update'}), 400
        response = supabase.table("technical_reports").update(update_data).eq("id", report_id).execute()
        if response.data:
            return jsonify({'success': True, 'message': 'Report updated successfully', 'report': response.data[0]})
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
            return jsonify({'success': False, 'error': 'You are not authorized to acknowledge reports.'}), 403
        update_data = {
            "team_leader_acknowledged": True,
            "team_leader_acknowledged_at": get_brunei_time_iso(),
            "team_leader_id": team_leader_id,
            "team_leader_notes": data.get('team_leader_notes', ''),
            "updated_at": get_brunei_time_iso()
        }
        response = supabase.table("technical_reports").update(update_data).eq("id", report_id).execute()
        if response.data:
            return jsonify({'success': True, 'message': 'Report acknowledged successfully'})
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
            return jsonify({'success': True, 'message': 'Report deleted successfully'})
        return jsonify({'success': False, 'error': 'Report not found'}), 404
    except Exception as e:
        app.logger.error(f"Error deleting technical report: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ============ MAPPING AND PROFILING API ============

@app.route('/api/mapping/images', methods=['GET'])
def get_mapping_images():
    try:
        if not supabase:
            return jsonify([]), 500
        entity_type = request.args.get('entity_type')
        entity_id = request.args.get('entity_id')
        query = supabase.table("mapping_images").select("*")
        if entity_type:
            query = query.eq("entity_type", entity_type)
        if entity_id:
            query = query.eq("entity_id", int(entity_id))
        response = query.order("uploaded_at", desc=True).execute()
        return jsonify(response.data if response.data else [])
    except Exception as e:
        app.logger.error(f"Error getting mapping images: {e}")
        return jsonify([]), 500

@app.route('/api/mapping/images', methods=['POST'])
def create_mapping_image():
    try:
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        data = request.get_json()
        image_data = {
            "entity_type": data.get('entity_type'),
            "entity_id": int(data.get('entity_id')),
            "image_url": data.get('image_url'),
            "description": data.get('description', ''),
            "notes": data.get('notes', ''),
            "water_account_number": data.get('water_account_number', ''),
            "water_meter_number": data.get('water_meter_number', ''),
            "electricity_account_number": data.get('electricity_account_number', ''),
            "electricity_meter_number": data.get('electricity_meter_number', ''),
            "telephone_account_number": data.get('telephone_account_number', ''),
            "telephone_number": data.get('telephone_number', ''),
            "canteen_water_account_number": data.get('canteen_water_account_number', ''),
            "canteen_water_meter_number": data.get('canteen_water_meter_number', ''),
            "canteen_electricity_account_number": data.get('canteen_electricity_account_number', ''),
            "canteen_electricity_meter_number": data.get('canteen_electricity_meter_number', ''),
            "uploaded_by": data.get('uploaded_by'),
            "uploaded_at": get_brunei_time_iso()
        }
        response = supabase.table("mapping_images").insert(image_data).execute()
        if response.data:
            app.logger.info(f"Mapping image created: {response.data[0]['id']}")
            return jsonify({'success': True, 'data': response.data[0]})
        return jsonify({'success': False, 'error': 'Failed to save image record'}), 500
    except Exception as e:
        app.logger.error(f"Error creating mapping image: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/mapping/images/<int:image_id>', methods=['PUT'])
def update_mapping_image(image_id):
    try:
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        data = request.get_json()
        allowed_fields = ['description', 'notes', 'water_account_number', 'water_meter_number',
                         'electricity_account_number', 'electricity_meter_number',
                         'telephone_account_number', 'telephone_number',
                         'canteen_water_account_number', 'canteen_water_meter_number',
                         'canteen_electricity_account_number', 'canteen_electricity_meter_number']
        update_data = {}
        for field in allowed_fields:
            if field in data:
                update_data[field] = data[field]
        if not update_data:
            return jsonify({'success': False, 'error': 'No data to update'}), 400
        response = supabase.table("mapping_images").update(update_data).eq("id", image_id).execute()
        if response.data:
            return jsonify({'success': True, 'data': response.data[0]})
        return jsonify({'success': False, 'error': 'Image not found'}), 404
    except Exception as e:
        app.logger.error(f"Error updating mapping image: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/mapping/images/<int:image_id>', methods=['DELETE'])
def delete_mapping_image(image_id):
    try:
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        response = supabase.table("mapping_images").delete().eq("id", image_id).execute()
        if response.data:
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Image not found'}), 404
    except Exception as e:
        app.logger.error(f"Error deleting mapping image: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

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
        
        original_content = file.read()
        compressed_content, ext = compress_image(original_content, file.filename)
        
        timestamp = get_brunei_time().strftime('%Y%m%d_%H%M%S')
        unique_id = uuid.uuid4().hex[:8]
        filename = f"{timestamp}_{unique_id}.{ext}"
        
        # Initialize storage and upload
        init_supabase_storage()
        
        # Use supabase client to upload
        try:
            supabase.storage.from_(SUPABASE_STORAGE_BUCKET).upload(
                filename, 
                compressed_content,
                file_options={"content-type": "image/jpeg"}
            )
            image_url = supabase.storage.from_(SUPABASE_STORAGE_BUCKET).get_public_url(filename)
            app.logger.info(f"Image uploaded to Supabase: {image_url}")
            
            return jsonify({
                'success': True, 
                'image_url': image_url, 
                'filename': filename
            })
        except Exception as e:
            app.logger.error(f"Supabase upload error: {e}")
            return jsonify({'success': False, 'error': f'Upload failed: {str(e)}'}), 500
        
    except Exception as e:
        app.logger.error(f"Error uploading image: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ============ DASHBOARD STATISTICS ============

@app.route('/api/dashboard-stats')
def get_dashboard_stats():
    try:
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        water = supabase.table("technical_reports").select("*", count="exact").eq("report_type", "water").execute()
        electricity = supabase.table("technical_reports").select("*", count="exact").eq("report_type", "electricity").execute()
        telephone = supabase.table("technical_reports").select("*", count="exact").eq("report_type", "telephone").execute()
        pending = supabase.table("technical_reports").select("*", count="exact").eq("status", "pending").execute()
        in_progress = supabase.table("technical_reports").select("*", count="exact").eq("status", "in_progress").execute()
        resolved = supabase.table("technical_reports").select("*", count="exact").eq("status", "resolved").execute()
        return jsonify({
            'total_reports': (water.count or 0) + (electricity.count or 0) + (telephone.count or 0),
            'by_type': {'water': water.count or 0, 'electricity': electricity.count or 0, 'telephone': telephone.count or 0},
            'by_status': {'pending': pending.count or 0, 'in_progress': in_progress.count or 0, 'resolved': resolved.count or 0}
        })
    except Exception as e:
        app.logger.error(f"Error getting dashboard stats: {e}")
        return jsonify({'error': str(e)}), 500

# ============ HEALTH CHECK ============

@app.route('/health')
def health_check():
    return jsonify({'status': 'healthy', 'timestamp': get_brunei_time_iso()})

# ============ APPLICATION STARTUP ============

def init_app():
    create_directories()
    init_supabase_storage()
    app.logger.info("MOE Technical Report System Starting")

init_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
