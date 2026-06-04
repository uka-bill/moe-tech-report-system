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

def init_supabase_storage():
    """Initialize Supabase storage bucket for images"""
    if not supabase:
        return False
    
    try:
        supabase.storage.create_bucket('mapping-images', {'public': True})
        app.logger.info("✅ Created storage bucket: mapping-images")
    except Exception as e:
        app.logger.info(f"Storage bucket ready (or already exists): {e}")
    
    return True

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
    """Mapping and Profiling page"""
    return render_template('mapping.html')

# ============ TECHNICIAN API ============

@app.route('/api/technicians', methods=['GET'])
def get_technicians():
    try:
        if not supabase:
            app.logger.error("Supabase client not initialized")
            return jsonify({'error': 'Database not connected'}), 500
        
        response = supabase.table("technicians").select("*").order("id", desc=False).execute()
        
        app.logger.info(f"Fetched {len(response.data) if response.data else 0} technicians from database")
        
        technicians = []
        if response.data:
            for tech in response.data:
                tech_dict = dict(tech)
                tech_dict.pop('password', None)
                
                if 'specializations' in tech_dict and tech_dict['specializations']:
                    if isinstance(tech_dict['specializations'], str):
                        try:
                            tech_dict['specializations'] = json.loads(tech_dict['specializations'])
                        except json.JSONDecodeError:
                            tech_dict['specializations'] = []
                    elif not isinstance(tech_dict['specializations'], list):
                        tech_dict['specializations'] = []
                else:
                    tech_dict['specializations'] = []
                
                tech_dict['is_authorized'] = tech_dict.get('is_authorized', False)
                tech_dict['can_edit_technicians'] = tech_dict.get('can_edit_technicians', False)
                technicians.append(tech_dict)
        
        return jsonify(technicians)
        
    except Exception as e:
        app.logger.error(f"Error getting technicians: {str(e)}")
        return jsonify([]), 500

@app.route('/api/technicians', methods=['POST'])
def create_technician():
    try:
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        
        data = request.get_json()
        specializations = data.get('specializations', [])
        
        password = data.get('password')
        employee_id = data.get('employee_id')
        if not password:
            password = employee_id
        
        technician_data = {
            "name": data.get('name'),
            "role": data.get('role', 'technician'),
            "employee_id": employee_id,
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
            app.logger.info(f"Technician created: {technician_data['name']}")
            response.data[0].pop('password', None)
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
            app.logger.info(f"Technician updated: ID {tech_id}")
            response.data[0].pop('password', None)
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
            return jsonify({'authorized': response.data[0].get('is_authorized', False)})
        else:
            return jsonify({'authorized': False}), 404
            
    except Exception as e:
        app.logger.error(f"Error checking authorization: {e}")
        return jsonify({'authorized': False}), 500

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
        
        if not response.data or len(response.data) == 0:
            return jsonify({'success': False, 'error': 'Technician not found'}), 404
        
        tech = response.data[0]
        stored_password = tech.get('password', '')
        employee_id = tech.get('employee_id', '')
        
        if stored_password and password == stored_password:
            return jsonify({'success': True, 'message': 'Password verified'})
        elif not stored_password and password == employee_id:
            return jsonify({'success': True, 'message': 'Password verified'})
        else:
            return jsonify({'success': False, 'error': 'Invalid password'}), 401
            
    except Exception as e:
        app.logger.error(f"Error verifying password: {e}")
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
        else:
            return jsonify({'success': False, 'error': 'Failed to reset password'}), 500
            
    except Exception as e:
        app.logger.error(f"Error resetting password: {e}")
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
        
        if not response.data or len(response.data) == 0:
            return jsonify({'success': False, 'error': 'Technician not found'}), 404
        
        tech = response.data[0]
        stored_password = tech.get('password', '')
        employee_id = tech.get('employee_id', '')
        
        password_valid = False
        if stored_password and current_password == stored_password:
            password_valid = True
        elif not stored_password and current_password == employee_id:
            password_valid = True
        
        if not password_valid:
            return jsonify({'success': False, 'error': 'Current password is incorrect'}), 401
        
        update_response = supabase.table("technicians").update({"password": new_password}).eq("id", technician_id).execute()
        
        if update_response.data:
            app.logger.info(f"Password changed for technician ID {technician_id}")
            return jsonify({'success': True, 'message': 'Password changed successfully'})
        else:
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
        else:
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
        else:
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
        if reports.data and len(reports.data) > 0:
            return jsonify({'success': False, 'error': 'Cannot delete school with existing reports'}), 400
        
        response = supabase.table("schools").delete().eq("id", school_id).execute()
        
        if response.data:
            return jsonify({'success': True})
        else:
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
            "unit_name": data.get('unit_name'),
            "address": data.get('address'),
            "contact_person": data.get('contact_person'),
            "contact_phone": data.get('contact_phone'),
            "created_at": get_brunei_time_iso()
        }
        
        if not dept_data['unit_name']:
            dept_data['unit_name'] = dept_data['name']
        
        if not dept_data['name']:
            return jsonify({'success': False, 'error': 'Department name is required'}), 400
        
        response = supabase.table("departments").insert(dept_data).execute()
        
        if response.data:
            return jsonify({'success': True, 'data': response.data[0]})
        else:
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
        else:
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
        if reports.data and len(reports.data) > 0:
            return jsonify({'success': False, 'error': 'Cannot delete department with existing reports'}), 400
        
        response = supabase.table("departments").delete().eq("id", dept_id).execute()
        
        if response.data:
            return jsonify({'success': True})
        else:
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
        
        report_type = request.args.get('type')
        entity_type = request.args.get('entity_type')
        entity_id = request.args.get('entity_id')
        status = request.args.get('status')
        priority = request.args.get('priority')
        technician_id = request.args.get('technician_id')
        team_leader_ack = request.args.get('team_leader_acknowledged')
        priority_with_tender = request.args.get('priority_with_tender')
        
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
        if priority_with_tender is not None:
            query = query.eq("priority_with_tender", priority_with_tender.lower() == 'true')
        
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
                
                if 'comments' not in report_data or report_data['comments'] is None:
                    report_data['comments'] = []
                elif isinstance(report_data['comments'], str):
                    try:
                        report_data['comments'] = json.loads(report_data['comments'])
                    except:
                        report_data['comments'] = []
                
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
            "comments": data.get('comments', []),
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
            return jsonify({'success': True, 'message': 'Report created successfully', 'report': response.data[0]})
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
            'phone_number', 'number_of_lines', 'comments',
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
            return jsonify({'success': True, 'message': 'Report updated successfully', 'report': response.data[0]})
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
            return jsonify({'success': False, 'error': 'You are not authorized to acknowledge reports.'}), 403
        
        tech_response = supabase.table("technicians").select("name").eq("id", team_leader_id).execute()
        team_leader_name = tech_response.data[0]['name'] if tech_response.data else 'Team Leader'
        
        update_data = {
            "team_leader_acknowledged": True,
            "team_leader_acknowledged_at": get_brunei_time_iso(),
            "team_leader_id": team_leader_id,
            "team_leader_name": team_leader_name,
            "team_leader_notes": data.get('team_leader_notes', ''),
            "updated_at": get_brunei_time_iso()
        }
        
        response = supabase.table("technical_reports").update(update_data).eq("id", report_id).execute()
        
        if response.data:
            return jsonify({'success': True, 'message': 'Report acknowledged successfully', 'report': response.data[0]})
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
            return jsonify({'success': True, 'message': 'Report deleted successfully'})
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

# ============ MAPPING AND PROFILING API ============

@app.route('/api/mapping/locations', methods=['GET'])
def get_mapping_locations():
    """Get all mapping locations for an entity"""
    try:
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        
        entity_type = request.args.get('entity_type')
        entity_id = request.args.get('entity_id')
        
        query = supabase.table("mapping_locations").select("*")
        
        if entity_type:
            query = query.eq("entity_type", entity_type)
        if entity_id:
            query = query.eq("entity_id", int(entity_id))
        
        response = query.order("location_type", desc=False).execute()
        
        locations = []
        if response.data:
            for loc in response.data:
                loc_dict = dict(loc)
                if loc_dict['entity_type'] == 'school':
                    entity = supabase.table("schools").select("name").eq("id", loc_dict['entity_id']).execute()
                    if entity.data:
                        loc_dict['entity_name'] = entity.data[0]['name']
                else:
                    entity = supabase.table("departments").select("name").eq("id", loc_dict['entity_id']).execute()
                    if entity.data:
                        loc_dict['entity_name'] = entity.data[0]['name']
                locations.append(loc_dict)
        
        return jsonify(locations)
    except Exception as e:
        app.logger.error(f"Error getting mapping locations: {e}")
        return jsonify([]), 500

@app.route('/api/mapping/locations', methods=['POST'])
def create_mapping_location():
    """Create a new mapping location"""
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
            app.logger.info(f"Mapping location created: {response.data[0]['id']}")
            return jsonify({'success': True, 'data': response.data[0]})
        else:
            return jsonify({'success': False, 'error': 'Failed to create location'}), 500
            
    except Exception as e:
        app.logger.error(f"Error creating mapping location: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/mapping/locations/<int:location_id>', methods=['PUT'])
def update_mapping_location(location_id):
    """Update a mapping location"""
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
        else:
            return jsonify({'success': False, 'error': 'Location not found'}), 404
            
    except Exception as e:
        app.logger.error(f"Error updating mapping location: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/mapping/locations/<int:location_id>', methods=['DELETE'])
def delete_mapping_location(location_id):
    """Delete a mapping location"""
    try:
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        
        response = supabase.table("mapping_locations").delete().eq("id", location_id).execute()
        
        if response.data:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Location not found'}), 404
            
    except Exception as e:
        app.logger.error(f"Error deleting mapping location: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/mapping/images', methods=['GET'])
def get_mapping_images():
    """Get all mapping images for an entity"""
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
        if response.data:
            for img in response.data:
                img_dict = dict(img)
                if img_dict.get('image_data_base64'):
                    img_dict['image_data_base64'] = None
                images.append(img_dict)
        
        return jsonify(images)
    except Exception as e:
        app.logger.error(f"Error getting mapping images: {e}")
        return jsonify([]), 500

@app.route('/api/mapping/images', methods=['POST'])
def create_mapping_image():
    """Create a new mapping image record"""
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
            "canteen_account_number": data.get('canteen_account_number', ''),
            "canteen_meter_number": data.get('canteen_meter_number', ''),
            "uploaded_by": data.get('uploaded_by'),
            "uploaded_at": get_brunei_time_iso()
        }
        
        response = supabase.table("mapping_images").insert(image_data).execute()
        
        if response.data:
            app.logger.info(f"Mapping image created: {response.data[0]['id']}")
            return jsonify({'success': True, 'data': response.data[0]})
        else:
            return jsonify({'success': False, 'error': 'Failed to save image record'}), 500
            
    except Exception as e:
        app.logger.error(f"Error creating mapping image: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/mapping/images/<int:image_id>', methods=['PUT'])
def update_mapping_image(image_id):
    """Update a mapping image (description, notes, and account details)"""
    try:
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        
        data = request.get_json()
        update_data = {}
        
        allowed_fields = ['description', 'notes', 
                          'water_account_number', 'water_meter_number',
                          'electricity_account_number', 'electricity_meter_number',
                          'telephone_account_number', 'telephone_number',
                          'canteen_account_number', 'canteen_meter_number']
        
        for field in allowed_fields:
            if field in data:
                update_data[field] = data[field]
        
        if not update_data:
            return jsonify({'success': False, 'error': 'No data to update'}), 400
        
        response = supabase.table("mapping_images").update(update_data).eq("id", image_id).execute()
        
        if response.data:
            app.logger.info(f"Mapping image updated: ID {image_id}")
            return jsonify({'success': True, 'data': response.data[0]})
        else:
            return jsonify({'success': False, 'error': 'Image not found'}), 404
            
    except Exception as e:
        app.logger.error(f"Error updating mapping image: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/mapping/images/<int:image_id>', methods=['DELETE'])
def delete_mapping_image(image_id):
    """Delete a mapping image"""
    try:
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        
        image_response = supabase.table("mapping_images").select("image_url").eq("id", image_id).execute()
        
        if image_response.data and image_response.data[0].get('image_url'):
            image_url = image_response.data[0]['image_url']
            
            if supabase and 'supabase.co' in image_url:
                try:
                    filename = image_url.split('/')[-1].split('?')[0]
                    supabase.storage.from_('mapping-images').remove([filename])
                    app.logger.info(f"Deleted image from Supabase Storage: {filename}")
                except Exception as e:
                    app.logger.warning(f"Could not delete from Supabase Storage: {e}")
            else:
                filename = image_url.replace('/api/images/', '')
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                if os.path.exists(filepath):
                    os.remove(filepath)
                    app.logger.info(f"Deleted local image file: {filepath}")
        
        response = supabase.table("mapping_images").delete().eq("id", image_id).execute()
        
        if response.data:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Image not found'}), 404
            
    except Exception as e:
        app.logger.error(f"Error deleting mapping image: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ============ DEBUG ENDPOINTS ============

@app.route('/api/debug/mapping-tables', methods=['GET'])
def debug_mapping_tables():
    """Debug endpoint to check if mapping tables exist"""
    try:
        if not supabase:
            return jsonify({'error': 'Supabase not connected'}), 500
        
        try:
            locations_response = supabase.table("mapping_locations").select("id").limit(1).execute()
            locations_exists = True
            locations_error = None
        except Exception as e:
            locations_exists = False
            locations_error = str(e)
        
        try:
            images_response = supabase.table("mapping_images").select("id").limit(1).execute()
            images_exists = True
            images_error = None
        except Exception as e:
            images_exists = False
            images_error = str(e)
        
        return jsonify({
            'mapping_locations_exists': locations_exists,
            'mapping_images_exists': images_exists,
            'locations_error': locations_error,
            'images_error': images_error
        })
    except Exception as e:
        app.logger.error(f"Debug endpoint error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/debug/mapping-images', methods=['GET'])
def debug_mapping_images():
    """Debug endpoint to check all mapping images in database"""
    try:
        if not supabase:
            return jsonify({'error': 'Supabase not connected'}), 500
        
        response = supabase.table("mapping_images").select("*").execute()
        
        return jsonify({
            'count': len(response.data) if response.data else 0,
            'images': response.data if response.data else []
        })
    except Exception as e:
        app.logger.error(f"Debug endpoint error: {e}")
        return jsonify({'error': str(e)}), 500

# ============ BACKUP AND RESTORE API ============

@app.route('/api/backup', methods=['GET'])
def backup_data():
    """Export all data to JSON file"""
    try:
        if not supabase:
            return jsonify({'success': False, 'error': 'Database not connected'}), 500
        
        user_id = request.args.get('user_id')
        if user_id:
            auth_response = supabase.table("technicians").select("can_edit_technicians").eq("id", int(user_id)).execute()
            if not auth_response.data or not auth_response.data[0].get('can_edit_technicians', False):
                return jsonify({'success': False, 'error': 'Unauthorized: Only administrators can perform backup'}), 403
        
        backup_data = {}
        
        # Technical reports
        reports_response = supabase.table("technical_reports").select("*").execute()
        backup_data['technical_reports'] = reports_response.data if reports_response.data else []
        
        # Schools
        schools_response = supabase.table("schools").select("*").execute()
        backup_data['schools'] = schools_response.data if schools_response.data else []
        
        # Departments
        departments_response = supabase.table("departments").select("*").execute()
        backup_data['departments'] = departments_response.data if departments_response.data else []
        
        # Technicians (remove passwords for security)
        technicians_response = supabase.table("technicians").select("*").execute()
        technicians = []
        if technicians_response.data:
            for tech in technicians_response.data:
                tech_copy = dict(tech)
                tech_copy.pop('password', None)
                technicians.append(tech_copy)
        backup_data['technicians'] = technicians
        
        # Mapping images
        images_response = supabase.table("mapping_images").select("*").execute()
        backup_data['mapping_images'] = images_response.data if images_response.data else []
        
        # Mapping locations
        locations_response = supabase.table("mapping_locations").select("*").execute()
        backup_data['mapping_locations'] = locations_response.data if locations_response.data else []
        
        backup_data['_backup_info'] = {
            'created_at': get_brunei_time_iso(),
            'version': '1.0',
            'record_counts': {
                'technical_reports': len(backup_data['technical_reports']),
                'schools': len(backup_data['schools']),
                'departments': len(backup_data['departments']),
                'technicians': len(backup_data['technicians']),
                'mapping_images': len(backup_data['mapping_images']),
                'mapping_locations': len(backup_data['mapping_locations'])
            }
        }
        
        app.logger.info(f"Backup created with {backup_data['_backup_info']['record_counts']}")
        
        return jsonify({'success': True, 'data': backup_data})
        
    except Exception as e:
        app.logger.error(f"Error creating backup: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/restore', methods=['POST'])
def restore_data():
    """Restore data from backup JSON"""
    try:
        if not supabase:
            return jsonify({'success': False, 'error': 'Database not connected'}), 500
        
        data = request.get_json()
        backup_data = data.get('backup_data')
        user_id = data.get('user_id')
        
        if not backup_data:
            return jsonify({'success': False, 'error': 'No backup data provided'}), 400
        
        if user_id:
            auth_response = supabase.table("technicians").select("can_edit_technicians").eq("id", int(user_id)).execute()
            if not auth_response.data or not auth_response.data[0].get('can_edit_technicians', False):
                return jsonify({'success': False, 'error': 'Unauthorized: Only administrators can perform restore'}), 403
        
        # Clear existing data
        try:
            supabase.table("mapping_images").delete().neq("id", 0).execute()
        except:
            pass
        try:
            supabase.table("mapping_locations").delete().neq("id", 0).execute()
        except:
            pass
        try:
            supabase.table("technical_reports").delete().neq("id", 0).execute()
        except:
            pass
        try:
            supabase.table("departments").delete().neq("id", 0).execute()
        except:
            pass
        try:
            supabase.table("schools").delete().neq("id", 0).execute()
        except:
            pass
        try:
            supabase.table("technicians").delete().neq("id", 0).execute()
        except:
            pass
        
        restored_counts = {}
        
        # Restore schools
        if 'schools' in backup_data and backup_data['schools']:
            for item in backup_data['schools']:
                item_copy = {k: v for k, v in item.items() if k != 'id'}
                supabase.table("schools").insert(item_copy).execute()
            restored_counts['schools'] = len(backup_data['schools'])
        
        # Restore departments
        if 'departments' in backup_data and backup_data['departments']:
            for item in backup_data['departments']:
                item_copy = {k: v for k, v in item.items() if k != 'id'}
                supabase.table("departments").insert(item_copy).execute()
            restored_counts['departments'] = len(backup_data['departments'])
        
        # Restore technicians
        if 'technicians' in backup_data and backup_data['technicians']:
            for item in backup_data['technicians']:
                item_copy = {k: v for k, v in item.items() if k != 'id'}
                if 'password' not in item_copy or not item_copy.get('password'):
                    item_copy['password'] = item_copy.get('employee_id', 'default123')
                supabase.table("technicians").insert(item_copy).execute()
            restored_counts['technicians'] = len(backup_data['technicians'])
        
        # Restore technical reports
        if 'technical_reports' in backup_data and backup_data['technical_reports']:
            for item in backup_data['technical_reports']:
                item_copy = {k: v for k, v in item.items() if k != 'id'}
                supabase.table("technical_reports").insert(item_copy).execute()
            restored_counts['technical_reports'] = len(backup_data['technical_reports'])
        
        # Restore mapping images
        if 'mapping_images' in backup_data and backup_data['mapping_images']:
            for item in backup_data['mapping_images']:
                item_copy = {k: v for k, v in item.items() if k != 'id'}
                supabase.table("mapping_images").insert(item_copy).execute()
            restored_counts['mapping_images'] = len(backup_data['mapping_images'])
        
        # Restore mapping locations
        if 'mapping_locations' in backup_data and backup_data['mapping_locations']:
            for item in backup_data['mapping_locations']:
                item_copy = {k: v for k, v in item.items() if k != 'id'}
                supabase.table("mapping_locations").insert(item_copy).execute()
            restored_counts['mapping_locations'] = len(backup_data['mapping_locations'])
        
        app.logger.info(f"Restore completed: {restored_counts}")
        
        return jsonify({
            'success': True, 
            'message': 'Data restored successfully',
            'restored_counts': restored_counts
        })
        
    except Exception as e:
        app.logger.error(f"Error restoring data: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/backup/last', methods=['GET'])
def get_last_backup_info():
    """Get information about the last backup"""
    try:
        return jsonify({'success': True, 'last_backup': None})
    except Exception as e:
        return jsonify({'success': True, 'last_backup': None})

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
        filename = f"{uuid.uuid4().hex}_{get_brunei_time().strftime('%Y%m%d_%H%M%S')}.{ext}"
        file_content = file.read()
        
        image_url = None
        
        if supabase:
            try:
                init_supabase_storage()
                supabase.storage.from_('mapping-images').upload(
                    filename, 
                    file_content,
                    file_options={"content-type": f"image/{ext}"}
                )
                image_url = supabase.storage.from_('mapping-images').get_public_url(filename)
                app.logger.info(f"✅ Image uploaded to Supabase Storage: {image_url}")
            except Exception as e:
                app.logger.error(f"❌ Failed to upload to Supabase Storage: {e}")
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                with open(filepath, 'wb') as f:
                    f.write(file_content)
                image_url = f"/api/images/{filename}"
                app.logger.info(f"📁 Image saved locally: {filepath}")
        else:
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            with open(filepath, 'wb') as f:
                f.write(file_content)
            image_url = f"/api/images/{filename}"
            app.logger.info(f"📁 Image saved locally: {filepath}")
        
        return jsonify({'success': True, 'image_url': image_url, 'filename': filename, 'message': 'Image uploaded successfully'})
        
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
        
        return jsonify({
            'total_reports': (water_reports.count or 0) + (electricity_reports.count or 0) + (telephone_reports.count or 0),
            'by_type': {'water': water_reports.count or 0, 'electricity': electricity_reports.count or 0, 'telephone': telephone_reports.count or 0},
            'by_status': {'pending': pending_reports.count or 0, 'in_progress': in_progress_reports.count or 0, 'resolved': resolved_reports.count or 0},
            'acknowledged_count': acknowledged_reports.count or 0,
            'recent_reports': recent_list
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
        
        headers = ['Report ID', 'Type', 'Entity Type', 'Entity Name', 'Problem Type', 'Complaint Details', 'Priority', 'Status', 'Technician Name', 'Created At']
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
                report.get('id', ''), report.get('report_type', ''), report.get('entity_type', ''),
                entity_name, report.get('problem_type', ''), report.get('complaint_details', ''),
                report.get('priority', ''), report.get('status', ''), tech_name, report.get('created_at', '')
            ])
        
        output.seek(0)
        timestamp = get_brunei_time().strftime('%Y%m%d_%H%M%S')
        filename = f"technical_reports_{timestamp}.csv"
        
        return send_file(io.BytesIO(output.getvalue().encode('utf-8-sig')), mimetype='text/csv', as_attachment=True, download_name=filename)
        
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
        'service': 'MOE Technical Report System'
    })

@app.route('/api/health')
def api_health():
    return jsonify({'status': 'ok', 'timestamp': get_brunei_time_iso()})

# ============ ERROR HANDLERS ============

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
    app.logger.info("🏫 MOE Technical Report System Starting")
    app.logger.info("Ministry of Education - Brunei Darussalam")
    app.logger.info("=" * 60)
    
    if test_supabase_connection():
        app.logger.info("✅ Supabase connection established")
    else:
        app.logger.warning("⚠️ Supabase connection failed")
    
    port = int(os.environ.get('PORT', 5000))
    app.logger.info(f"🚀 Server will run on port: {port}")

init_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
