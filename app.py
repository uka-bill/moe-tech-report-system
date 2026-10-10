from flask import Flask, render_template, request, jsonify, send_file, send_from_directory
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
import traceback
import zipfile
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed

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

app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024  # 20 MB per request
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

app.config['MAX_IMAGE_DIMENSION'] = 1024
app.config['IMAGE_QUALITY'] = 60

app.jinja_env.globals.update(format_brunei_time=format_brunei_time)

# ============ NO-CACHE HEADERS FOR API RESPONSES ============
@app.after_request
def add_no_cache_headers(response):
    if request.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response

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
SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1lZ3J4Y2ZtY3dydHRpd3VqZGRoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzkwNDA4ODgsImV4cCI6MjA5NDYxNjg4OH0.fmwcV6fqqr-hO6hRPTzER6eODl6zffwud9heIchMNkw'
SUPABASE_SERVICE_KEY = os.environ.get('SUPABASE_SERVICE_KEY', SUPABASE_ANON_KEY)
SUPABASE_STORAGE_BUCKET = 'mapping-images'

try:
    supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
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
    if not supabase:
        app.logger.error("Supabase client not available")
        return False
    try:
        supabase.storage.create_bucket(SUPABASE_STORAGE_BUCKET, {'public': True})
        app.logger.info(f"Storage bucket created/verified: {SUPABASE_STORAGE_BUCKET}")
    except Exception as e:
        app.logger.info(f"Storage bucket already exists or error: {e}")
    return True

def compress_image(file_content, filename):
    try:
        original_size_kb = len(file_content) / 1024
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
        if img.width > 1024 or img.height > 1024:
            ratio = min(1024 / img.width, 1024 / img.height)
            new_size = (int(img.width * ratio), int(img.height * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
        output = io_lib.BytesIO()
        img.save(output, format='JPEG', quality=app.config['IMAGE_QUALITY'], optimize=True, progressive=True)
        compressed_content = output.getvalue()
        compressed_size_kb = len(compressed_content) / 1024
        compression_ratio = (1 - compressed_size_kb / original_size_kb) * 100
        app.logger.info(f"Image compressed: {original_size_kb:.1f}KB -> {compressed_size_kb:.1f}KB ({compression_ratio:.1f}% saved)")
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

@app.route('/budget-tracking')
def budget_tracking_page():
    return render_template('budget_tracking.html')

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
            "is_assistant_leader": data.get('is_assistant_leader', False),
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
        allowed_fields = ['name', 'role', 'employee_id', 'phone', 'email', 'is_authorized', 'can_edit_technicians', 'is_assistant_leader', 'password']
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

@app.route('/api/technicians/reset-password', methods=['POST'])
def reset_technician_password():
    try:
        if not supabase:
            return jsonify({'success': False, 'error': 'Database not connected'}), 500
        data = request.get_json()
        technician_id = data.get('technician_id')
        new_password = data.get('new_password')
        if not technician_id or not new_password:
            return jsonify({'success': False, 'error': 'Technician ID and new password required'}), 400
        response = supabase.table("technicians").update({"password": new_password}).eq("id", technician_id).execute()
        if response.data:
            app.logger.info(f"Password reset for technician ID {technician_id}")
            return jsonify({'success': True, 'message': 'Password reset successfully'})
        return jsonify({'success': False, 'error': 'Failed to reset password'}), 500
    except Exception as e:
        app.logger.error(f"Error resetting password: {e}")
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

        # ============ BATCH PREFETCH (fixes N+1 slowness) ============
        schools_map = {}
        departments_map = {}
        technicians_map = {}
        slips_by_report = {}

        try:
            schools_resp = supabase.table("schools").select("id, name").execute()
            if schools_resp.data:
                for s in schools_resp.data:
                    schools_map[s['id']] = s.get('name') or ''
        except Exception as e:
            app.logger.warning(f"Could not prefetch schools: {e}")

        try:
            depts_resp = supabase.table("departments").select("id, name, unit_name").execute()
            if depts_resp.data:
                for d in depts_resp.data:
                    departments_map[d['id']] = {
                        'name': d.get('name') or '',
                        'unit_name': d.get('unit_name') or ''
                    }
        except Exception as e:
            app.logger.warning(f"Could not prefetch departments: {e}")

        try:
            techs_resp = supabase.table("technicians").select("id, name, role").execute()
            if techs_resp.data:
                for t in techs_resp.data:
                    technicians_map[t['id']] = {
                        'name': t.get('name') or '',
                        'role': t.get('role') or ''
                    }
        except Exception as e:
            app.logger.warning(f"Could not prefetch technicians: {e}")

        try:
            slips_resp = supabase.table("task_slips").select("*").not_.is_("report_id", "null").execute()
            if slips_resp.data:
                for slip in slips_resp.data:
                    slips_by_report[slip['report_id']] = slip
        except Exception as se:
            app.logger.warning(f"Could not fetch task slips map: {se}")
        # ============ END BATCH PREFETCH ============

        reports = []
        if response.data:
            for report in response.data:
                report_data = dict(report)
                entity_id = report_data['entity_id']

                if report_data['entity_type'] == 'school':
                    report_data['entity_name'] = schools_map.get(entity_id, '')
                    report_data['entity_unit_name'] = ''
                else:
                    dept = departments_map.get(entity_id) or {}
                    report_data['entity_name'] = dept.get('name') or ''
                    report_data['entity_unit_name'] = dept.get('unit_name') or ''

                if report_data.get('technician_id'):
                    tech = technicians_map.get(report_data['technician_id']) or {}
                    if tech.get('name'):
                        report_data['technician_name'] = tech['name']

                if report_data['id'] in slips_by_report:
                    slip = slips_by_report[report_data['id']]
                    report_data['slip_id'] = slip['id']
                    report_data['slip_number'] = slip.get('slip_number', '')
                    report_data['slip_complaint_number'] = slip.get('complaint_number', '')
                    report_data['slip_kpi_number'] = slip.get('kpi_number', '')
                    report_data['slip_notes'] = slip.get('notes', '')
                    report_data['slip_status'] = slip.get('status', '')
                    report_data['slip_issue_date'] = slip.get('issue_date')
                    report_data['slip_due_date'] = slip.get('due_date')
                    if slip.get('issued_by'):
                        issuer = technicians_map.get(slip['issued_by']) or {}
                        if issuer.get('name'):
                            report_data['slip_issued_by_name'] = issuer['name']

                reports.append(report_data)
        return jsonify(reports)
    except Exception as e:
        app.logger.error(f"Error getting technical reports: {e}")
        return jsonify([]), 500

@app.route('/api/technical-reports/<int:report_id>', methods=['GET'])
def get_single_technical_report(report_id):
    try:
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        response = supabase.table("technical_reports").select("*").eq("id", report_id).execute()
        if not response.data:
            return jsonify({'success': False, 'error': 'Report not found'}), 404
        report_data = dict(response.data[0])
        # ---- ENTITY LOOKUP ----
        if report_data['entity_type'] == 'school':
            entity = supabase.table("schools").select("name").eq("id", report_data['entity_id']).execute()
            if entity.data:
                report_data['entity_name'] = entity.data[0]['name']
                report_data['entity_unit_name'] = ''
            else:
                report_data['entity_unit_name'] = ''
        else:
            entity = supabase.table("departments").select("name, unit_name").eq("id", report_data['entity_id']).execute()
            if entity.data:
                dept = entity.data[0]
                report_data['entity_name'] = dept.get('name') or ''
                report_data['entity_unit_name'] = dept.get('unit_name') or ''
            else:
                report_data['entity_unit_name'] = ''
        # ---- END ----
        if report_data.get('technician_id'):
            tech = supabase.table("technicians").select("name, role").eq("id", report_data['technician_id']).execute()
            if tech.data:
                report_data['technician_name'] = tech.data[0]['name']

        try:
            slip_resp = supabase.table("task_slips").select("*").eq("report_id", report_id).limit(1).execute()
            if slip_resp.data:
                slip = slip_resp.data[0]
                report_data['slip_id'] = slip['id']
                report_data['slip_number'] = slip.get('slip_number', '')
                report_data['slip_complaint_number'] = slip.get('complaint_number', '')
                report_data['slip_kpi_number'] = slip.get('kpi_number', '')
                report_data['slip_notes'] = slip.get('notes', '')
                report_data['slip_status'] = slip.get('status', '')
                report_data['slip_issue_date'] = slip.get('issue_date')
                report_data['slip_due_date'] = slip.get('due_date')
                if slip.get('issued_by'):
                    issuer = supabase.table("technicians").select("name").eq("id", slip['issued_by']).execute()
                    if issuer.data:
                        report_data['slip_issued_by_name'] = issuer.data[0]['name']
        except Exception as se:
            app.logger.warning(f"Could not fetch slip for report {report_id}: {se}")

        return jsonify({'success': True, 'report': report_data})
    except Exception as e:
        app.logger.error(f"Error getting single report: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

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
            "resolution_status": data.get('resolution_status', 'pending_action'),
            "technician_id": data.get('technician_id'),
            "technician_notes": data.get('technician_notes', ''),
            "action_taken": data.get('action_taken', ''),
            "images": data.get('images', []),
            "reference_type": data.get('reference_type', ''),
            "reference_number": data.get('reference_number', ''),
            "reference_date": data.get('reference_date'),
            "account_details": data.get('account_details') if isinstance(data.get('account_details'), str) else (json.dumps(data.get('account_details')) if data.get('account_details') else None),
            "created_at": get_brunei_time_iso(),
            "updated_at": get_brunei_time_iso()
        }

        # Auto-initialize budget tracking + stage timer if this is a Need Budget report
        if report_data['resolution_status'] == 'need_budget':
            now_iso = get_brunei_time_iso()
            report_data['budget_status'] = 'waiting_quote'
            report_data['budget_updated_at'] = now_iso
            report_data['budget_status_changed_at'] = now_iso

        response = supabase.table("technical_reports").insert(report_data).execute()
        if response.data:
            new_report = response.data[0]
            slip_id = data.get('slip_id')
            if slip_id:
                try:
                    supabase.table("task_slips").update({
                        "report_id": new_report['id'],
                        "updated_at": get_brunei_time_iso()
                    }).eq("id", int(slip_id)).execute()
                    app.logger.info(f"Slip {slip_id} linked to report {new_report['id']}")
                except Exception as le:
                    app.logger.warning(f"Could not link slip to report: {le}")
            return jsonify({'success': True, 'message': 'Report created successfully', 'report': new_report})
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
        allowed_fields = ['report_type', 'entity_type', 'entity_id', 'problem_type', 'complaint_details',
                         'priority', 'priority_with_tender', 'status', 'resolution_status', 'technician_notes', 'action_taken',
                         'images', 'account_number', 'meter_number', 'phone_number', 'number_of_lines',
                         'reference_type', 'reference_number', 'reference_date', 'account_details']
        update_data = {}
        for field in allowed_fields:
            if field in data and data[field] is not None:
                if field == 'entity_id':
                    update_data[field] = int(data[field])
                else:
                    update_data[field] = data[field]

        # Handle resolution_status <-> budget_status transition + stage timer reset
        if 'resolution_status' in data:
            new_rs = data.get('resolution_status')
            current = supabase.table("technical_reports").select("budget_status").eq("id", report_id).execute()
            if current.data:
                curr_bs = current.data[0].get('budget_status')
                if new_rs == 'need_budget':
                    if not curr_bs:
                        now_iso = get_brunei_time_iso()
                        update_data['budget_status'] = 'waiting_quote'
                        update_data['budget_updated_at'] = now_iso
                        update_data['budget_status_changed_at'] = now_iso
                else:
                    if curr_bs and curr_bs != 'completed':
                        now_iso = get_brunei_time_iso()
                        update_data['budget_status'] = 'completed'
                        update_data['budget_updated_at'] = now_iso
                        update_data['budget_status_changed_at'] = now_iso
                        if 'budget_notes' not in data:
                            existing_notes = ""
                            try:
                                row = supabase.table("technical_reports").select("budget_notes").eq("id", report_id).execute()
                                if row.data:
                                    existing_notes = row.data[0].get('budget_notes') or ""
                            except Exception:
                                pass
                            auto_note = f"[Auto-completed: resolution changed to {new_rs}]"
                            update_data['budget_notes'] = (existing_notes + "\n" + auto_note).strip() if existing_notes else auto_note

        if not update_data:
            return jsonify({'success': False, 'error': 'No data to update'}), 400
        update_data['updated_at'] = get_brunei_time_iso()
        response = supabase.table("technical_reports").update(update_data).eq("id", report_id).execute()
        if response.data:
            return jsonify({'success': True, 'message': 'Report updated successfully', 'report': response.data[0]})
        return jsonify({'success': False, 'error': 'Report not found'}), 404
    except Exception as e:
        app.logger.error(f"Error updating technical report: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/technical-reports/<int:report_id>', methods=['DELETE'])
def delete_technical_report(report_id):
    try:
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        report = supabase.table("technical_reports").select("id, technician_id, team_leader_acknowledged").eq("id", report_id).execute()
        if not report.data:
            return jsonify({'success': False, 'error': 'Report not found'}), 404
        if report.data[0].get('team_leader_acknowledged', False):
            return jsonify({'success': False, 'error': 'Cannot delete an acknowledged report'}), 400
        response = supabase.table("technical_reports").delete().eq("id", report_id).execute()
        if response.data:
            app.logger.info(f"Report {report_id} deleted")
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Failed to delete report'}), 500
    except Exception as e:
        app.logger.error(f"Error deleting report: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/technical-reports/<int:report_id>/acknowledge', methods=['POST'])
def acknowledge_report(report_id):
    try:
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        data = request.get_json()
        team_leader_id = data.get('team_leader_id')
        team_leader_notes = data.get('team_leader_notes', '')
        acknowledgment_status = data.get('acknowledgment_status', 'done_reviewed')
        if not team_leader_id:
            return jsonify({'success': False, 'error': 'Team Leader ID required'}), 400
        auth_response = supabase.table("technicians").select("is_authorized, name").eq("id", team_leader_id).execute()
        if not auth_response.data:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        if not auth_response.data[0].get('is_authorized', False):
            return jsonify({'success': False, 'error': 'You are not authorized to acknowledge reports'}), 403
        team_leader_name = auth_response.data[0].get('name', 'Team Leader')
        report_response = supabase.table("technical_reports").select("team_leader_acknowledged").eq("id", report_id).execute()
        if not report_response.data:
            return jsonify({'success': False, 'error': 'Report not found'}), 404
        if report_response.data[0].get('team_leader_acknowledged', False):
            return jsonify({'success': False, 'error': 'Report already acknowledged'}), 400
        update_data = {
            "team_leader_acknowledged": True,
            "team_leader_acknowledged_at": get_brunei_time_iso(),
            "team_leader_id": team_leader_id,
            "team_leader_name": team_leader_name,
            "team_leader_notes": team_leader_notes,
            "acknowledgment_status": acknowledgment_status,
            "updated_at": get_brunei_time_iso()
        }
        response = supabase.table("technical_reports").update(update_data).eq("id", report_id).execute()
        if response.data:
            app.logger.info(f"Report {report_id} acknowledged by {team_leader_name} - status: {acknowledgment_status}")
            return jsonify({'success': True, 'message': 'Report acknowledged successfully'})
        return jsonify({'success': False, 'error': 'Failed to acknowledge report'}), 500
    except Exception as e:
        app.logger.error(f"Error acknowledging report: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/technical-reports/<int:report_id>/check', methods=['POST'])
def check_report_by_assistant(report_id):
    try:
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        data = request.get_json()
        assistant_id = data.get('assistant_id')
        if not assistant_id:
            return jsonify({'success': False, 'error': 'Assistant ID required'}), 400
        user_response = supabase.table("technicians").select("is_assistant_leader, name").eq("id", assistant_id).execute()
        if not user_response.data:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        if not user_response.data[0].get('is_assistant_leader', False):
            return jsonify({'success': False, 'error': 'You are not authorized as Assistant Team Leader'}), 403
        assistant_name = user_response.data[0].get('name', 'Assistant Leader')
        report_response = supabase.table("technical_reports").select("checked_by_assistant").eq("id", report_id).execute()
        if report_response.data and report_response.data[0].get('checked_by_assistant', False):
            return jsonify({'success': False, 'error': 'Report already checked by assistant'}), 400
        update_data = {
            "checked_by_assistant": True,
            "checked_by_assistant_id": assistant_id,
            "checked_by_assistant_name": assistant_name,
            "checked_by_assistant_at": get_brunei_time_iso(),
            "updated_at": get_brunei_time_iso()
        }
        response = supabase.table("technical_reports").update(update_data).eq("id", report_id).execute()
        if response.data:
            app.logger.info(f"Report {report_id} checked by Assistant Team Leader: {assistant_name}")
            return jsonify({'success': True, 'message': 'Report marked as checked', 'report': response.data[0]})
        else:
            return jsonify({'success': False, 'error': 'Report not found'}), 404
    except Exception as e:
        app.logger.error(f"Error checking report: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ============ BUDGET TRACKING API ============

@app.route('/api/budget-reports', methods=['GET'])
def get_budget_reports():
    """Returns all reports that are or have been budget items."""
    try:
        if not supabase:
            return jsonify([]), 500
        include_completed = request.args.get('include_completed', 'false').lower() == 'true'

        response = supabase.table("technical_reports").select("*").order("created_at", desc=True).execute()

        # ============ BATCH PREFETCH ============
        schools_map = {}
        departments_map = {}
        technicians_map = {}

        try:
            schools_resp = supabase.table("schools").select("id, name").execute()
            if schools_resp.data:
                for s in schools_resp.data:
                    schools_map[s['id']] = s.get('name') or ''
        except Exception as e:
            app.logger.warning(f"Could not prefetch schools: {e}")

        try:
            depts_resp = supabase.table("departments").select("id, name, unit_name").execute()
            if depts_resp.data:
                for d in depts_resp.data:
                    departments_map[d['id']] = {
                        'name': d.get('name') or '',
                        'unit_name': d.get('unit_name') or ''
                    }
        except Exception as e:
            app.logger.warning(f"Could not prefetch departments: {e}")

        try:
            techs_resp = supabase.table("technicians").select("id, name").execute()
            if techs_resp.data:
                for t in techs_resp.data:
                    technicians_map[t['id']] = t.get('name') or ''
        except Exception as e:
            app.logger.warning(f"Could not prefetch technicians: {e}")
        # ============ END BATCH PREFETCH ============

        reports = []
        if response.data:
            for report in response.data:
                r = dict(report)
                is_currently_need_budget = r.get('resolution_status') == 'need_budget'
                has_budget_status = bool(r.get('budget_status'))

                if not (is_currently_need_budget or has_budget_status):
                    continue

                is_completed = (r.get('budget_status') == 'completed')
                if is_completed and not include_completed:
                    continue

                entity_id = r['entity_id']
                if r['entity_type'] == 'school':
                    r['entity_name'] = schools_map.get(entity_id, '')
                    r['entity_unit_name'] = ''
                else:
                    dept = departments_map.get(entity_id) or {}
                    r['entity_name'] = dept.get('name') or ''
                    r['entity_unit_name'] = dept.get('unit_name') or ''

                if r.get('technician_id'):
                    name = technicians_map.get(r['technician_id'])
                    if name:
                        r['technician_name'] = name

                if r.get('budget_updated_by'):
                    name = technicians_map.get(r['budget_updated_by'])
                    if name:
                        r['budget_updated_by_name'] = name

                reports.append(r)
        return jsonify(reports)
    except Exception as e:
        app.logger.error(f"Error getting budget reports: {e}")
        return jsonify([]), 500


@app.route('/api/budget-reports/<int:report_id>', methods=['PUT'])
def update_budget_report(report_id):
    """Update the budget tracking fields for a report. Anyone logged in can use this."""
    try:
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        data = request.get_json()

        update_data = {}
        if 'budget_status' in data and data['budget_status'] is not None:
            update_data['budget_status'] = data['budget_status']
        if 'budget_amount' in data:
            amt = data['budget_amount']
            if amt is None or amt == '':
                update_data['budget_amount'] = None
            else:
                try:
                    update_data['budget_amount'] = float(amt)
                except (ValueError, TypeError):
                    return jsonify({'success': False, 'error': 'Invalid amount'}), 400
        if 'budget_notes' in data:
            update_data['budget_notes'] = data['budget_notes'] or ''
        if 'updated_by' in data and data['updated_by']:
            try:
                update_data['budget_updated_by'] = int(data['updated_by'])
            except (ValueError, TypeError):
                pass

        if not update_data:
            return jsonify({'success': False, 'error': 'No data to update'}), 400

        # If the budget_status is actually CHANGING, reset the stage timer
        if 'budget_status' in update_data:
            try:
                current_row = supabase.table("technical_reports").select("budget_status").eq("id", report_id).execute()
                if current_row.data:
                    current_status = current_row.data[0].get('budget_status')
                    if current_status != update_data['budget_status']:
                        update_data['budget_status_changed_at'] = get_brunei_time_iso()
                        app.logger.info(f"Budget status for report {report_id} changed: {current_status} -> {update_data['budget_status']}")
            except Exception as ex:
                app.logger.warning(f"Could not check previous status for timer reset: {ex}")

        update_data['budget_updated_at'] = get_brunei_time_iso()
        update_data['updated_at'] = get_brunei_time_iso()

        response = supabase.table("technical_reports").update(update_data).eq("id", report_id).execute()
        if response.data:
            app.logger.info(f"Budget info updated for report {report_id}")
            return jsonify({'success': True, 'data': response.data[0]})
        return jsonify({'success': False, 'error': 'Report not found'}), 404
    except Exception as e:
        app.logger.error(f"Error updating budget report: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/budget-stats', methods=['GET'])
def get_budget_stats():
    """Returns counts by budget status for the dashboard tile and page header."""
    try:
        if not supabase:
            return jsonify({}), 500
        response = supabase.table("technical_reports").select("budget_status, resolution_status").execute()
        stats = {
            'waiting_quote': 0,
            'quote_received': 0,
            'submitted_approval': 0,
            'approved': 0,
            'rejected': 0,
            'work_in_progress': 0,
            'completed': 0,
            'total_active': 0
        }
        if response.data:
            for r in response.data:
                bs = r.get('budget_status')
                rs = r.get('resolution_status')
                is_need = (rs == 'need_budget')
                has_bs = bool(bs)
                if not (is_need or has_bs):
                    continue
                if bs and bs in stats:
                    stats[bs] += 1
                if bs != 'completed':
                    stats['total_active'] += 1
        return jsonify(stats)
    except Exception as e:
        app.logger.error(f"Error getting budget stats: {e}")
        return jsonify({}), 500

# ============ MAPPING API ============

@app.route('/api/mapping/locations', methods=['GET'])
def get_mapping_locations():
    try:
        if not supabase:
            return jsonify([]), 500
        entity_type = request.args.get('entity_type')
        entity_id = request.args.get('entity_id')
        query = supabase.table("mapping_locations").select("*")
        if entity_type:
            query = query.eq("entity_type", entity_type)
        if entity_id:
            query = query.eq("entity_id", int(entity_id))
        response = query.order("location_type", desc=False).execute()
        return jsonify(response.data if response.data else [])
    except Exception as e:
        app.logger.error(f"Error getting mapping locations: {e}")
        return jsonify([]), 500

@app.route('/api/mapping/locations', methods=['POST'])
def create_mapping_location():
    try:
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        data = request.get_json()
        location_data = {
            "entity_type": data.get('entity_type'),
            "entity_id": int(data.get('entity_id')),
            "location_type": data.get('location_type'),
            "account_number": data.get('account_number', ''),
            "meter_number": data.get('meter_number', ''),
            "phone_number": data.get('phone_number', ''),
            "description": data.get('description', ''),
            "latitude": data.get('latitude'),
            "longitude": data.get('longitude'),
            "address": data.get('address', ''),
            "image_url": data.get('image_url', ''),
            "created_by": data.get('created_by'),
            "created_at": get_brunei_time_iso(),
            "updated_at": get_brunei_time_iso()
        }
        response = supabase.table("mapping_locations").insert(location_data).execute()
        if response.data:
            return jsonify({'success': True, 'data': response.data[0]})
        return jsonify({'success': False, 'error': 'Failed to create location'}), 500
    except Exception as e:
        app.logger.error(f"Error creating mapping location: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/mapping/locations/<int:location_id>', methods=['PUT'])
def update_mapping_location(location_id):
    try:
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        data = request.get_json()
        update_data = {}
        allowed_fields = ['account_number', 'meter_number', 'phone_number', 'description', 
                         'latitude', 'longitude', 'address', 'image_url']
        for field in allowed_fields:
            if field in data:
                update_data[field] = data[field]
        update_data['updated_at'] = get_brunei_time_iso()
        if not update_data:
            return jsonify({'success': False, 'error': 'No data to update'}), 400
        response = supabase.table("mapping_locations").update(update_data).eq("id", location_id).execute()
        if response.data:
            return jsonify({'success': True, 'data': response.data[0]})
        return jsonify({'success': False, 'error': 'Location not found'}), 404
    except Exception as e:
        app.logger.error(f"Error updating mapping location: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/mapping/locations/<int:location_id>', methods=['DELETE'])
def delete_mapping_location(location_id):
    try:
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        response = supabase.table("mapping_locations").delete().eq("id", location_id).execute()
        if response.data:
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Location not found'}), 404
    except Exception as e:
        app.logger.error(f"Error deleting mapping location: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

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
        images = []
        for img in response.data if response.data else []:
            img_dict = dict(img)
            if 'uploaded_by_name' not in img_dict or img_dict['uploaded_by_name'] is None:
                img_dict['uploaded_by_name'] = ''
            if 'last_edited_by' not in img_dict:
                img_dict['last_edited_by'] = None
            if 'last_edited_at' not in img_dict:
                img_dict['last_edited_at'] = None
            if 'pabx_name' not in img_dict or img_dict['pabx_name'] is None:
                img_dict['pabx_name'] = ''
            if 'pabx_pilot_no' not in img_dict or img_dict['pabx_pilot_no'] is None:
                img_dict['pabx_pilot_no'] = ''
            if 'pabx_trailing_no' not in img_dict or img_dict['pabx_trailing_no'] is None:
                img_dict['pabx_trailing_no'] = []
            if 'pabx_extension_no' not in img_dict or img_dict['pabx_extension_no'] is None:
                img_dict['pabx_extension_no'] = []
            images.append(img_dict)
        return jsonify(images)
    except Exception as e:
        app.logger.error(f"Error getting mapping images: {e}")
        return jsonify([]), 500

@app.route('/api/mapping/images', methods=['POST'])
def create_mapping_image():
    try:
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        data = request.get_json()
        app.logger.info(f"Creating mapping image with data keys: {list(data.keys()) if data else 'None'}")
        pabx_trailing_no = data.get('pabx_trailing_no', [])
        pabx_extension_no = data.get('pabx_extension_no', [])
        if isinstance(pabx_trailing_no, str):
            pabx_trailing_no = [pabx_trailing_no] if pabx_trailing_no else []
        if isinstance(pabx_extension_no, str):
            pabx_extension_no = [pabx_extension_no] if pabx_extension_no else []
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
            "pabx_name": data.get('pabx_name', ''),
            "pabx_pilot_no": data.get('pabx_pilot_no', ''),
            "pabx_trailing_no": pabx_trailing_no,
            "pabx_extension_no": pabx_extension_no,
            "water_accounts_json": data.get('water_accounts_json', '[]'),
            "electricity_accounts_json": data.get('electricity_accounts_json', '[]'),
            "telephone_accounts_json": data.get('telephone_accounts_json', '[]'),
            "canteen_water_accounts_json": data.get('canteen_water_accounts_json', '[]'),
            "canteen_electricity_accounts_json": data.get('canteen_electricity_accounts_json', '[]'),
            "uploaded_by": data.get('uploaded_by'),
            "last_edited_by": data.get('last_edited_by'),
            "last_edited_at": data.get('last_edited_at'),
            "uploaded_at": get_brunei_time_iso()
        }
        response = supabase.table("mapping_images").insert(image_data).execute()
        if response.data:
            app.logger.info(f"Mapping image created: ID {response.data[0]['id']}")
            return jsonify({'success': True, 'data': response.data[0]})
        return jsonify({'success': False, 'error': 'Failed to save image record'}), 500
    except Exception as e:
        app.logger.error(f"Error creating mapping image: {e}")
        app.logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/mapping/images/<int:image_id>', methods=['PUT'])
def update_mapping_image(image_id):
    try:
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        data = request.get_json()
        pabx_trailing_no = data.get('pabx_trailing_no', [])
        pabx_extension_no = data.get('pabx_extension_no', [])
        if isinstance(pabx_trailing_no, str):
            pabx_trailing_no = [pabx_trailing_no] if pabx_trailing_no else []
        if isinstance(pabx_extension_no, str):
            pabx_extension_no = [pabx_extension_no] if pabx_extension_no else []
        allowed_fields = [
            'description', 'notes', 
            'water_account_number', 'water_meter_number',
            'electricity_account_number', 'electricity_meter_number',
            'telephone_account_number', 'telephone_number',
            'canteen_water_account_number', 'canteen_water_meter_number',
            'canteen_electricity_account_number', 'canteen_electricity_meter_number',
            'pabx_name', 'pabx_pilot_no',
            'water_accounts_json', 'electricity_accounts_json', 'telephone_accounts_json',
            'canteen_water_accounts_json', 'canteen_electricity_accounts_json',
            'last_edited_by', 'last_edited_at'
        ]
        update_data = {}
        for field in allowed_fields:
            if field in data:
                update_data[field] = data[field]
        if 'pabx_trailing_no' in data:
            update_data['pabx_trailing_no'] = pabx_trailing_no
        if 'pabx_extension_no' in data:
            update_data['pabx_extension_no'] = pabx_extension_no
        if not update_data:
            return jsonify({'success': False, 'error': 'No data to update'}), 400
        response = supabase.table("mapping_images").update(update_data).eq("id", image_id).execute()
        if response.data:
            app.logger.info(f"Mapping image updated: ID {image_id}")
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
        init_supabase_storage()
        if not supabase:
            return jsonify({'success': False, 'error': 'Supabase client not initialized'}), 500
        supabase.storage.from_(SUPABASE_STORAGE_BUCKET).upload(
            filename, 
            compressed_content,
            file_options={"content-type": "image/jpeg"}
        )
        image_url = supabase.storage.from_(SUPABASE_STORAGE_BUCKET).get_public_url(filename)
        app.logger.info(f"Image uploaded: {image_url}")
        return jsonify({
            'success': True, 
            'image_url': image_url, 
            'filename': filename
        })
    except Exception as e:
        app.logger.error(f"Error uploading image: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/images/<filename>')
def get_image(filename):
    try:
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
    except Exception as e:
        return jsonify({'error': 'Image not found'}), 404

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

# ============ EXPORT REPORTS ============

@app.route('/api/export-reports', methods=['GET'])
def export_reports():
    try:
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        report_type = request.args.get('type')
        query = supabase.table("technical_reports").select("*")
        if report_type:
            query = query.eq("report_type", report_type)
        response = query.order("created_at", desc=True).execute()
        if not response.data:
            return jsonify({'success': False, 'error': 'No data to export'}), 404
        output = io.StringIO()
        writer = csv.writer(output)
        headers = ['Report ID', 'Type', 'Entity Type', 'Entity Name', 'Unit Name', 'Problem Type', 'Complaint Details', 'Priority', 'Status', 'Technician Name', 'Created At']
        writer.writerow(headers)
        for report in response.data:
            entity_name = ''
            entity_unit_name = ''
            if report['entity_type'] == 'school':
                entity = supabase.table("schools").select("name").eq("id", report['entity_id']).execute()
                if entity.data:
                    entity_name = entity.data[0]['name']
            else:
                entity = supabase.table("departments").select("name, unit_name").eq("id", report['entity_id']).execute()
                if entity.data:
                    dept = entity.data[0]
                    entity_name = dept.get('name') or ''
                    entity_unit_name = dept.get('unit_name') or ''
            tech_name = ''
            if report.get('technician_id'):
                tech = supabase.table("technicians").select("name").eq("id", report['technician_id']).execute()
                if tech.data:
                    tech_name = tech.data[0]['name']
            writer.writerow([
                report.get('id', ''), report.get('report_type', ''), report.get('entity_type', ''),
                entity_name, entity_unit_name, report.get('problem_type', ''), report.get('complaint_details', ''),
                report.get('priority', ''), report.get('status', ''), tech_name, report.get('created_at', '')
            ])
        output.seek(0)
        timestamp = get_brunei_time().strftime('%Y%m%d_%H%M%S')
        filename = f"technical_reports_{timestamp}.csv"
        return send_file(io.BytesIO(output.getvalue().encode('utf-8-sig')), mimetype='text/csv', as_attachment=True, download_name=filename)
    except Exception as e:
        app.logger.error(f"Error exporting reports: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ============ BACKUP & RESTORE ============

@app.route('/api/backup', methods=['GET'])
def backup_data():
    try:
        if not supabase:
            return jsonify({'success': False, 'error': 'Database not connected'}), 500
        user_id = request.args.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'error': 'User ID required'}), 400
        auth_response = supabase.table("technicians").select("is_authorized, role, can_edit_technicians").eq("id", int(user_id)).execute()
        if not auth_response.data:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        user = auth_response.data[0]
        is_authorized = user.get('is_authorized', False)
        is_senior = user.get('role') == 'senior_technician'
        can_edit = user.get('can_edit_technicians', False)
        if not (is_authorized or is_senior or can_edit):
            return jsonify({'success': False, 'error': 'You are not authorized to perform backup'}), 403
        tables = ['technicians', 'schools', 'departments', 'technical_reports',
                  'mapping_images', 'mapping_locations', 'task_slips']
        backup_data = {}
        for table in tables:
            try:
                response = supabase.table(table).select("*").execute()
                backup_data[table] = response.data if response.data else []
            except Exception as tex:
                app.logger.warning(f"Could not back up table {table}: {tex}")
                backup_data[table] = []
        backup_data['_backup_info'] = {
            'version': '2.0',
            'timestamp': get_brunei_time_iso(),
            'user_id': int(user_id),
            'total_records': sum(len(backup_data[t]) for t in tables),
            'tables_included': tables
        }
        app.logger.info(f"Backup created by user {user_id} with {backup_data['_backup_info']['total_records']} records")
        return jsonify({'success': True, 'data': backup_data})
    except Exception as e:
        app.logger.error(f"Backup error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/restore', methods=['POST'])
def restore_data():
    try:
        if not supabase:
            return jsonify({'success': False, 'error': 'Database not connected'}), 500
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        backup_data = data.get('backup_data')
        user_id = data.get('user_id')
        if not backup_data or not user_id:
            return jsonify({'success': False, 'error': 'Missing backup data or user ID'}), 400
        auth_response = supabase.table("technicians").select("is_authorized, role, can_edit_technicians").eq("id", int(user_id)).execute()
        if not auth_response.data:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        user = auth_response.data[0]
        is_authorized = user.get('is_authorized', False)
        is_senior = user.get('role') == 'senior_technician'
        can_edit = user.get('can_edit_technicians', False)
        if not (is_authorized or is_senior or can_edit):
            return jsonify({'success': False, 'error': 'You are not authorized to perform restore'}), 403
        if '_backup_info' not in backup_data:
            return jsonify({'success': False, 'error': 'Invalid backup file: missing metadata'}), 400

        delete_order = ['task_slips', 'mapping_locations', 'mapping_images',
                        'technical_reports', 'technicians', 'schools', 'departments']
        insert_order = ['technicians', 'schools', 'departments', 'technical_reports',
                        'mapping_images', 'mapping_locations', 'task_slips']

        restored_count = 0
        for table in delete_order:
            if table not in backup_data:
                continue
            try:
                supabase.table(table).delete().neq('id', 0).execute()
                app.logger.info(f"Cleared table: {table}")
            except Exception as e:
                app.logger.error(f"Error clearing table {table}: {e}")
                return jsonify({'success': False, 'error': f'Failed to clear table {table}: {str(e)}'}), 500

        for table in insert_order:
            if table not in backup_data:
                continue
            records = backup_data[table]
            if not records:
                continue
            for record in records:
                try:
                    insert_record = {k: v for k, v in record.items() if k not in ['created_at', 'updated_at']}
                    supabase.table(table).insert(insert_record).execute()
                    restored_count += 1
                except Exception as e:
                    app.logger.error(f"Error restoring record in {table}: {e} (record: {record.get('id', 'unknown')})")
                    if table == 'technicians':
                        return jsonify({'success': False, 'error': f'Failed to restore critical table {table}: {str(e)}'}), 500
        app.logger.info(f"Restore completed by user {user_id}, restored {restored_count} records")
        return jsonify({'success': True, 'message': f'Restore successful, {restored_count} records restored'})
    except Exception as e:
        app.logger.error(f"Restore error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/backup-images', methods=['GET'])
def backup_images():
    tmp_path = None
    try:
        if not supabase:
            return jsonify({'success': False, 'error': 'Database not connected'}), 500

        user_id = request.args.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'error': 'User ID required'}), 400

        year = request.args.get('year')
        month = request.args.get('month')

        auth_response = supabase.table("technicians").select("is_authorized, role, can_edit_technicians").eq("id", int(user_id)).execute()
        if not auth_response.data:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        user = auth_response.data[0]
        is_authorized = user.get('is_authorized', False)
        is_senior = user.get('role') == 'senior_technician'
        can_edit = user.get('can_edit_technicians', False)
        if not (is_authorized or is_senior or can_edit):
            return jsonify({'success': False, 'error': 'You are not authorized to perform backup'}), 403

        valid_files = []

        if year:
            try:
                y = int(year)
                if month and month != 'all':
                    m = int(month)
                    if m < 1 or m > 12:
                        return jsonify({'success': False, 'error': 'Invalid month'}), 400
                    start_date = f"{y:04d}-{m:02d}-01T00:00:00"
                    if m == 12:
                        end_date = f"{y+1:04d}-01-01T00:00:00"
                    else:
                        end_date = f"{y:04d}-{m+1:02d}-01T00:00:00"
                    label = f"{y}-{m:02d}"
                else:
                    start_date = f"{y:04d}-01-01T00:00:00"
                    end_date = f"{y+1:04d}-01-01T00:00:00"
                    label = f"{y}"
            except ValueError:
                return jsonify({'success': False, 'error': 'Invalid year/month'}), 400

            try:
                response = supabase.table("mapping_images").select("image_url, uploaded_at").gte("uploaded_at", start_date).lt("uploaded_at", end_date).execute()
            except Exception as qe:
                app.logger.error(f"Query failed: {qe}")
                return jsonify({'success': False, 'error': f'Query failed: {str(qe)}'}), 500

            records = response.data or []
            for rec in records:
                url = rec.get('image_url', '')
                if not url:
                    continue
                fname = url.split('?')[0].rstrip('/').split('/')[-1]
                if fname and fname.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                    valid_files.append(fname)
        else:
            try:
                files = supabase.storage.from_(SUPABASE_STORAGE_BUCKET).list()
            except Exception as e:
                app.logger.error(f"Error listing storage files: {e}")
                return jsonify({'success': False, 'error': f'Could not list storage files: {str(e)}'}), 500

            for f in files:
                name = f.get('name')
                if not name:
                    continue
                if f.get('id') is None and not name.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                    continue
                valid_files.append(name)
            label = "all"

        if not valid_files:
            return jsonify({'success': False, 'error': f'No images found for period: {label}'}), 404

        tmp_fd, tmp_path = tempfile.mkstemp(suffix='.zip')
        os.close(tmp_fd)

        def download_one(filename):
            try:
                file_bytes = supabase.storage.from_(SUPABASE_STORAGE_BUCKET).download(filename)
                return (filename, file_bytes, None)
            except Exception as e:
                return (filename, None, str(e))

        downloaded = 0
        skipped = 0

        with zipfile.ZipFile(tmp_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = {executor.submit(download_one, name): name for name in valid_files}
                for future in as_completed(futures):
                    name, data, err = future.result()
                    if err or not data:
                        skipped += 1
                        continue
                    try:
                        zf.writestr(name, data)
                        downloaded += 1
                    except Exception:
                        skipped += 1

        if downloaded == 0:
            try:
                os.remove(tmp_path)
            except Exception:
                pass
            return jsonify({'success': False, 'error': 'Could not download any images'}), 500

        timestamp = get_brunei_time().strftime('%Y%m%d_%H%M%S')
        filename = f"moe_images_backup_{label}_{timestamp}.zip"

        response = send_file(
            tmp_path,
            mimetype='application/zip',
            as_attachment=True,
            download_name=filename
        )

        @response.call_on_close
        def cleanup():
            try:
                if tmp_path and os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

        return response

    except Exception as e:
        app.logger.error(f"Image backup error: {e}")
        app.logger.error(traceback.format_exc())
        if tmp_path:
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        return jsonify({'success': False, 'error': str(e)}), 500

# ============ TASK SLIPS API ============

@app.route('/task-slips')
def task_slips_page():
    return render_template('task_slips.html')

@app.route('/api/task-slips', methods=['GET'])
def get_task_slips():
    try:
        if not supabase:
            return jsonify([]), 500
        query = supabase.table("task_slips").select("*")
        if request.args.get('assigned_to'):
            query = query.eq("assigned_to", int(request.args.get('assigned_to')))
        if request.args.get('status'):
            query = query.eq("status", request.args.get('status'))
        if request.args.get('entity_type'):
            query = query.eq("entity_type", request.args.get('entity_type'))
        if request.args.get('entity_id'):
            query = query.eq("entity_id", int(request.args.get('entity_id')))
        response = query.order("created_at", desc=True).execute()

        # ============ BATCH PREFETCH ============
        schools_map = {}
        departments_map = {}
        technicians_map = {}
        reports_map = {}

        try:
            schools_resp = supabase.table("schools").select("id, name").execute()
            if schools_resp.data:
                for s in schools_resp.data:
                    schools_map[s['id']] = s.get('name') or ''
        except Exception as e:
            app.logger.warning(f"Could not prefetch schools: {e}")

        try:
            depts_resp = supabase.table("departments").select("id, name, unit_name").execute()
            if depts_resp.data:
                for d in depts_resp.data:
                    departments_map[d['id']] = {
                        'name': d.get('name') or '',
                        'unit_name': d.get('unit_name') or ''
                    }
        except Exception as e:
            app.logger.warning(f"Could not prefetch departments: {e}")

        try:
            techs_resp = supabase.table("technicians").select("id, name").execute()
            if techs_resp.data:
                for t in techs_resp.data:
                    technicians_map[t['id']] = t.get('name') or ''
        except Exception as e:
            app.logger.warning(f"Could not prefetch technicians: {e}")

        try:
            if response.data:
                report_ids = [s['report_id'] for s in response.data if s.get('report_id')]
                if report_ids:
                    reports_resp = supabase.table("technical_reports").select(
                        "id, team_leader_acknowledged, acknowledgment_status, team_leader_notes, team_leader_acknowledged_at, team_leader_name, report_type"
                    ).in_("id", report_ids).execute()
                    if reports_resp.data:
                        for r in reports_resp.data:
                            reports_map[r['id']] = r
        except Exception as re:
            app.logger.warning(f"Could not fetch linked reports: {re}")
        # ============ END BATCH PREFETCH ============

        slips = []
        if response.data:
            for slip in response.data:
                s = dict(slip)
                entity_id = s['entity_id']
                if s['entity_type'] == 'school':
                    s['entity_name'] = schools_map.get(entity_id, '')
                    s['entity_unit_name'] = ''
                else:
                    dept = departments_map.get(entity_id) or {}
                    s['entity_name'] = dept.get('name') or ''
                    s['entity_unit_name'] = dept.get('unit_name') or ''

                if s.get('assigned_to'):
                    name = technicians_map.get(s['assigned_to'])
                    if name:
                        s['assigned_to_name'] = name
                if s.get('issued_by'):
                    name = technicians_map.get(s['issued_by'])
                    if name:
                        s['issued_by_name'] = name

                if s.get('report_id') and s['report_id'] in reports_map:
                    rpt = reports_map[s['report_id']]
                    s['has_report'] = True
                    s['report_acknowledged'] = rpt.get('team_leader_acknowledged', False)
                    s['report_acknowledgment_status'] = rpt.get('acknowledgment_status', '')
                    s['report_team_leader_name'] = rpt.get('team_leader_name', '')
                    s['report_team_leader_notes'] = rpt.get('team_leader_notes', '')
                    s['report_acknowledged_at'] = rpt.get('team_leader_acknowledged_at', '')
                else:
                    s['has_report'] = bool(s.get('report_id'))
                    s['report_acknowledged'] = False
                    s['report_acknowledgment_status'] = ''

                slips.append(s)
        return jsonify(slips)
    except Exception as e:
        app.logger.error(f"Error getting task slips: {e}")
        return jsonify([]), 500


@app.route('/api/task-slips/available/<int:technician_id>', methods=['GET'])
def get_available_task_slips(technician_id):
    try:
        if not supabase:
            return jsonify([]), 500
        response = supabase.table("task_slips").select("*").eq("assigned_to", technician_id).is_("report_id", "null").execute()

        # ============ BATCH PREFETCH ============
        schools_map = {}
        departments_map = {}

        try:
            schools_resp = supabase.table("schools").select("id, name").execute()
            if schools_resp.data:
                for s in schools_resp.data:
                    schools_map[s['id']] = s.get('name') or ''
        except Exception as e:
            app.logger.warning(f"Could not prefetch schools: {e}")

        try:
            depts_resp = supabase.table("departments").select("id, name, unit_name").execute()
            if depts_resp.data:
                for d in depts_resp.data:
                    departments_map[d['id']] = {
                        'name': d.get('name') or '',
                        'unit_name': d.get('unit_name') or ''
                    }
        except Exception as e:
            app.logger.warning(f"Could not prefetch departments: {e}")
        # ============ END BATCH PREFETCH ============

        slips = []
        if response.data:
            for slip in response.data:
                s = dict(slip)
                if s.get('status') not in ('issued', 'accepted', 'in_progress'):
                    continue
                entity_id = s['entity_id']
                if s['entity_type'] == 'school':
                    s['entity_name'] = schools_map.get(entity_id, '')
                    s['entity_unit_name'] = ''
                else:
                    dept = departments_map.get(entity_id) or {}
                    s['entity_name'] = dept.get('name') or ''
                    s['entity_unit_name'] = dept.get('unit_name') or ''
                slips.append(s)
        slips.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        return jsonify(slips)
    except Exception as e:
        app.logger.error(f"Error getting available task slips: {e}")
        return jsonify([]), 500


@app.route('/api/task-slips', methods=['POST'])
def create_task_slip():
    try:
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        data = request.get_json()
        required = ['slip_number', 'entity_type', 'entity_id', 'assigned_to', 'issued_by']
        for field in required:
            if not data.get(field):
                return jsonify({'success': False, 'error': f'{field} is required'}), 400

        slip_data = {
            "slip_number": data.get('slip_number'),
            "complaint_number": data.get('complaint_number', ''),
            "kpi_number": data.get('kpi_number', ''),
            "entity_type": data.get('entity_type'),
            "entity_id": int(data.get('entity_id')),
            "problem_type": data.get('problem_type', ''),
            "assigned_to": int(data.get('assigned_to')),
            "issued_by": int(data.get('issued_by')),
            "issue_date": get_brunei_time_iso(),
            "due_date": data.get('due_date'),
            "notes": data.get('notes', ''),
            "status": data.get('status', 'issued'),
            "created_at": get_brunei_time_iso(),
            "updated_at": get_brunei_time_iso()
        }
        response = supabase.table("task_slips").insert(slip_data).execute()
        if response.data:
            return jsonify({'success': True, 'data': response.data[0]})
        return jsonify({'success': False, 'error': 'Failed to create slip'}), 500
    except Exception as e:
        app.logger.error(f"Error creating task slip: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/task-slips/<int:slip_id>', methods=['GET'])
def get_single_task_slip(slip_id):
    try:
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        response = supabase.table("task_slips").select("*").eq("id", slip_id).execute()
        if not response.data:
            return jsonify({'success': False, 'error': 'Slip not found'}), 404
        s = dict(response.data[0])
        # ---- ENTITY LOOKUP ----
        if s['entity_type'] == 'school':
            entity = supabase.table("schools").select("name, address, contact_person, contact_phone").eq("id", s['entity_id']).execute()
            if entity.data:
                s['entity_name'] = entity.data[0]['name']
                s['entity_unit_name'] = ''
                s['entity_address'] = entity.data[0].get('address', '')
                s['entity_contact'] = entity.data[0].get('contact_person', '')
                s['entity_phone'] = entity.data[0].get('contact_phone', '')
            else:
                s['entity_unit_name'] = ''
        else:
            entity = supabase.table("departments").select("name, unit_name, address, contact_person, contact_phone").eq("id", s['entity_id']).execute()
            if entity.data:
                dept = entity.data[0]
                s['entity_name'] = dept.get('name') or ''
                s['entity_unit_name'] = dept.get('unit_name') or ''
                s['entity_address'] = dept.get('address', '')
                s['entity_contact'] = dept.get('contact_person', '')
                s['entity_phone'] = dept.get('contact_phone', '')
            else:
                s['entity_unit_name'] = ''
        # ---- END ----
        if s.get('assigned_to'):
            tech = supabase.table("technicians").select("name, employee_id").eq("id", s['assigned_to']).execute()
            if tech.data:
                s['assigned_to_name'] = tech.data[0]['name']
                s['assigned_to_employee_id'] = tech.data[0].get('employee_id', '')
        if s.get('issued_by'):
            issuer = supabase.table("technicians").select("name, employee_id").eq("id", s['issued_by']).execute()
            if issuer.data:
                s['issued_by_name'] = issuer.data[0]['name']
                s['issued_by_employee_id'] = issuer.data[0].get('employee_id', '')
        return jsonify({'success': True, 'data': s})
    except Exception as e:
        app.logger.error(f"Error getting task slip: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/task-slips/<int:slip_id>', methods=['PUT'])
def update_task_slip(slip_id):
    try:
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        data = request.get_json()
        allowed = ['slip_number', 'complaint_number', 'kpi_number', 'entity_type', 'entity_id',
                   'problem_type', 'assigned_to', 'due_date', 'notes', 'status', 'report_id']
        update_data = {}
        for f in allowed:
            if f in data:
                if f in ['entity_id', 'assigned_to', 'report_id'] and data[f] is not None:
                    update_data[f] = int(data[f])
                else:
                    update_data[f] = data[f]
        if not update_data:
            return jsonify({'success': False, 'error': 'No data to update'}), 400
        update_data['updated_at'] = get_brunei_time_iso()
        response = supabase.table("task_slips").update(update_data).eq("id", slip_id).execute()
        if response.data:
            return jsonify({'success': True, 'data': response.data[0]})
        return jsonify({'success': False, 'error': 'Slip not found'}), 404
    except Exception as e:
        app.logger.error(f"Error updating task slip: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/task-slips/<int:slip_id>', methods=['DELETE'])
def delete_task_slip(slip_id):
    try:
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        response = supabase.table("task_slips").delete().eq("id", slip_id).execute()
        if response.data:
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Slip not found'}), 404
    except Exception as e:
        app.logger.error(f"Error deleting task slip: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ============ HISTORY API (read-only storybook view) ============

@app.route('/history')
def history_page():
    return render_template('history.html')


@app.route('/api/history-entities', methods=['GET'])
def get_history_entities():
    """Returns list of all schools + departments with activity counts."""
    try:
        if not supabase:
            return jsonify([]), 500

        schools_resp = supabase.table("schools").select("*").order("name", desc=False).execute()
        depts_resp = supabase.table("departments").select("*").order("name", desc=False).execute()
        reports_resp = supabase.table("technical_reports").select("id, entity_type, entity_id, created_at").execute()
        images_resp = supabase.table("mapping_images").select("id, entity_type, entity_id, uploaded_at").execute()
        slips_resp = supabase.table("task_slips").select("id, entity_type, entity_id, created_at").execute()

        schools = schools_resp.data or []
        departments = depts_resp.data or []
        reports = reports_resp.data or []
        images = images_resp.data or []
        slips = slips_resp.data or []

        def build_maps(rows, date_field):
            counts = {}
            latest = {}
            for r in rows:
                k = (r.get('entity_type'), r.get('entity_id'))
                counts[k] = counts.get(k, 0) + 1
                d = r.get(date_field)
                if d and (k not in latest or d > latest[k]):
                    latest[k] = d
            return counts, latest

        r_counts, r_latest = build_maps(reports, 'created_at')
        i_counts, i_latest = build_maps(images, 'uploaded_at')
        s_counts, s_latest = build_maps(slips, 'created_at')

        entities = []

        for s in schools:
            k = ('school', s['id'])
            last_dates = [d for d in [r_latest.get(k), i_latest.get(k), s_latest.get(k)] if d]
            entities.append({
                'id': s['id'],
                'type': 'school',
                'name': s.get('name', ''),
                'cluster_number': s.get('cluster_number', ''),
                'school_number': s.get('school_number', ''),
                'address': s.get('address', ''),
                'contact_person': s.get('contact_person', ''),
                'contact_phone': s.get('contact_phone', ''),
                'report_count': r_counts.get(k, 0),
                'image_count': i_counts.get(k, 0),
                'slip_count': s_counts.get(k, 0),
                'total_count': r_counts.get(k, 0) + i_counts.get(k, 0) + s_counts.get(k, 0),
                'last_activity': max(last_dates) if last_dates else None
            })

        for d in departments:
            k = ('department', d['id'])
            last_dates = [dt for dt in [r_latest.get(k), i_latest.get(k), s_latest.get(k)] if dt]
            entities.append({
                'id': d['id'],
                'type': 'department',
                'name': d.get('name', ''),
                'unit_name': d.get('unit_name', ''),
                'address': d.get('address', ''),
                'contact_person': d.get('contact_person', ''),
                'contact_phone': d.get('contact_phone', ''),
                'report_count': r_counts.get(k, 0),
                'image_count': i_counts.get(k, 0),
                'slip_count': s_counts.get(k, 0),
                'total_count': r_counts.get(k, 0) + i_counts.get(k, 0) + s_counts.get(k, 0),
                'last_activity': max(last_dates) if last_dates else None
            })

        # Sort: schools first (by id ascending), then departments (by id ascending)
        # This matches the ordering in the Management tabs
        entities.sort(key=lambda x: (0 if x['type'] == 'school' else 1, x['id']))

        return jsonify(entities)
    except Exception as e:
        app.logger.error(f"Error getting history entities: {e}")
        return jsonify([]), 500


@app.route('/api/history/<entity_type>/<int:entity_id>', methods=['GET'])
def get_entity_history(entity_type, entity_id):
    """Returns the full story timeline for a single entity (school or department)."""
    try:
        if not supabase:
            return jsonify({'success': False, 'error': 'Database not connected'}), 500

        if entity_type not in ('school', 'department'):
            return jsonify({'success': False, 'error': 'Invalid entity type'}), 400

        if entity_type == 'school':
            ent_resp = supabase.table("schools").select("*").eq("id", entity_id).execute()
        else:
            ent_resp = supabase.table("departments").select("*").eq("id", entity_id).execute()

        if not ent_resp.data:
            return jsonify({'success': False, 'error': 'Entity not found'}), 404

        ent = dict(ent_resp.data[0])
        entity = {
            'id': ent.get('id'),
            'type': entity_type,
            'name': ent.get('name', ''),
            'address': ent.get('address', ''),
            'contact_person': ent.get('contact_person', ''),
            'contact_phone': ent.get('contact_phone', ''),
            'cluster_number': ent.get('cluster_number', ''),
            'school_number': ent.get('school_number', ''),
            'unit_name': ent.get('unit_name', '')
        }

        reports_resp = supabase.table("technical_reports").select("*").eq("entity_type", entity_type).eq("entity_id", entity_id).order("created_at", desc=True).execute()
        reports = reports_resp.data or []

        images_resp = supabase.table("mapping_images").select("*").eq("entity_type", entity_type).eq("entity_id", entity_id).order("uploaded_at", desc=True).execute()
        images = images_resp.data or []

        slips_resp = supabase.table("task_slips").select("*").eq("entity_type", entity_type).eq("entity_id", entity_id).order("created_at", desc=True).execute()
        slips = slips_resp.data or []

        tech_ids = set()
        for r in reports:
            if r.get('technician_id'): tech_ids.add(r['technician_id'])
        for im in images:
            if im.get('uploaded_by'): tech_ids.add(im['uploaded_by'])
            if im.get('last_edited_by'): tech_ids.add(im['last_edited_by'])
        for sl in slips:
            if sl.get('assigned_to'): tech_ids.add(sl['assigned_to'])
            if sl.get('issued_by'): tech_ids.add(sl['issued_by'])

        tech_name_map = {}
        if tech_ids:
            try:
                tr = supabase.table("technicians").select("id, name").in_("id", list(tech_ids)).execute()
                if tr.data:
                    for t in tr.data:
                        tech_name_map[t['id']] = t['name']
            except Exception as te:
                app.logger.warning(f"Could not fetch technician names: {te}")

        timeline = []

        for r in reports:
            timeline.append({
                'type': 'report',
                'date': r.get('created_at'),
                'id': r.get('id'),
                'report_type': r.get('report_type'),
                'problem_type': r.get('problem_type'),
                'priority': r.get('priority', 'medium'),
                'priority_with_tender': r.get('priority_with_tender', False),
                'resolution_status': r.get('resolution_status', 'pending_action'),
                'status': r.get('status', ''),
                'complaint_details': r.get('complaint_details', ''),
                'action_taken': r.get('action_taken', ''),
                'technician_notes': r.get('technician_notes', ''),
                'reference_number': r.get('reference_number', ''),
                'reference_type': r.get('reference_type', ''),
                'reference_date': r.get('reference_date'),
                'account_number': r.get('account_number', ''),
                'meter_number': r.get('meter_number', ''),
                'phone_number': r.get('phone_number', ''),
                'technician_name': tech_name_map.get(r.get('technician_id'), 'Unknown'),
                'team_leader_acknowledged': r.get('team_leader_acknowledged', False),
                'team_leader_name': r.get('team_leader_name', ''),
                'team_leader_notes': r.get('team_leader_notes', ''),
                'team_leader_acknowledged_at': r.get('team_leader_acknowledged_at'),
                'acknowledgment_status': r.get('acknowledgment_status', ''),
                'images': r.get('images', []) or []
            })

        for im in images:
            timeline.append({
                'type': 'image',
                'date': im.get('uploaded_at'),
                'id': im.get('id'),
                'image_url': im.get('image_url', ''),
                'description': im.get('description', ''),
                'notes': im.get('notes', ''),
                'uploaded_by_name': tech_name_map.get(im.get('uploaded_by'), ''),
                'last_edited_at': im.get('last_edited_at'),
                'last_edited_by_name': tech_name_map.get(im.get('last_edited_by'), '')
            })

        for sl in slips:
            timeline.append({
                'type': 'slip',
                'date': sl.get('created_at'),
                'id': sl.get('id'),
                'slip_number': sl.get('slip_number', ''),
                'complaint_number': sl.get('complaint_number', ''),
                'kpi_number': sl.get('kpi_number', ''),
                'problem_type': sl.get('problem_type', ''),
                'assigned_to_name': tech_name_map.get(sl.get('assigned_to'), ''),
                'issued_by_name': tech_name_map.get(sl.get('issued_by'), ''),
                'status': sl.get('status', 'issued'),
                'notes': sl.get('notes', ''),
                'due_date': sl.get('due_date'),
                'report_id': sl.get('report_id')
            })

        timeline.sort(key=lambda x: x.get('date') or '', reverse=True)

        water_count = sum(1 for r in reports if r.get('report_type') == 'water')
        elec_count = sum(1 for r in reports if r.get('report_type') == 'electricity')
        tel_count = sum(1 for r in reports if r.get('report_type') == 'telephone')
        total_budget = sum(float(r.get('budget_amount') or 0) for r in reports)

        summary = {
            'total_reports': len(reports),
            'total_images': len(images),
            'total_slips': len(slips),
            'water_reports': water_count,
            'electricity_reports': elec_count,
            'telephone_reports': tel_count,
            'last_activity': timeline[0]['date'] if timeline else None,
            'total_budget': total_budget
        }

        return jsonify({
            'success': True,
            'entity': entity,
            'summary': summary,
            'timeline': timeline
        })
    except Exception as e:
        app.logger.error(f"Error getting entity history: {e}")
        app.logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500

# ============ HEALTH CHECK ============

@app.route('/health')
def health_check():
    supabase_status = supabase is not None
    return jsonify({
        'status': 'healthy' if supabase_status else 'degraded',
        'timestamp': get_brunei_time_iso(),
        'supabase_connected': supabase_status
    })

@app.route('/api/health')
def api_health():
    return jsonify({'status': 'ok', 'timestamp': get_brunei_time_iso()})

# ============ DEBUG ENDPOINTS ============

@app.route('/api/debug/supabase', methods=['GET'])
def debug_supabase():
    return jsonify({
        'has_service_key': SUPABASE_SERVICE_KEY != SUPABASE_ANON_KEY,
        'service_key_length': len(SUPABASE_SERVICE_KEY) if SUPABASE_SERVICE_KEY else 0,
        'storage_client_exists': supabase is not None,
        'storage_bucket': SUPABASE_STORAGE_BUCKET
    })

# ============ ERROR HANDLERS ============

@app.errorhandler(413)
def request_entity_too_large(error):
    app.logger.warning(f"413 Payload Too Large — request exceeded size limit")
    return jsonify({
        'success': False,
        'error': 'Image too large. Please use an image under 20 MB, or resize it first.'
    }), 413

@app.errorhandler(404)
def not_found_error(error):
    return jsonify({'error': 'Resource not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    app.logger.error(f"500 error: {error}")
    return jsonify({'error': 'Internal server error'}), 500

# ============ APPLICATION STARTUP ============

def init_app():
    create_directories()
    init_supabase_storage()
    app.logger.info("=" * 60)
    app.logger.info("UKA Technical Report System Starting")
    app.logger.info("Unit Kemudahan Asas, Ministry of Education - Brunei Darussalam")
    app.logger.info(f"Compression Settings: Max {app.config['MAX_IMAGE_DIMENSION']}px, Quality {app.config['IMAGE_QUALITY']}%")
    app.logger.info("=" * 60)

init_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
