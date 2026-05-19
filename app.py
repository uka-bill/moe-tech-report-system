from flask import Flask, render_template, request, jsonify, send_file
import os
from supabase import create_client
import uuid
from werkzeug.utils import secure_filename
import csv
import io
from datetime import datetime
import traceback
import json
import base64
import logging
from logging.handlers import RotatingFileHandler

# ============ INITIALIZATION ============

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'moe-tech-report-secret-key-change-in-production')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp'}

# ============ LOGGING SETUP ============

# Create logs directory if it doesn't exist
if not os.path.exists('logs'):
    os.makedirs('logs')

# Configure logging
file_handler = RotatingFileHandler('logs/app.log', maxBytes=10240, backupCount=10)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
file_handler.setLevel(logging.INFO)
app.logger.addHandler(file_handler)
app.logger.setLevel(logging.INFO)
app.logger.info('MOE Technical Report System startup')

# ============ SUPABASE CONFIGURATION ============

# Get Supabase credentials from environment variables
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
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def create_directories():
    """Create necessary directories for the application"""
    directories = ['uploads', 'logs']
    for directory in directories:
        try:
            os.makedirs(directory, exist_ok=True)
            app.logger.info(f"📁 Directory ready: {directory}")
        except Exception as e:
            app.logger.error(f"❌ Failed to create directory {directory}: {e}")

def test_supabase_connection():
    """Test Supabase connection and log result"""
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
    """Landing page"""
    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    """Main dashboard page"""
    return render_template('dashboard.html')

@app.route('/reports')
def reports_page():
    """All reports page"""
    return render_template('reports.html')

@app.route('/water-reports')
def water_reports():
    """Water reports page"""
    return render_template('water_reports.html')

@app.route('/electricity-reports')
def electricity_reports():
    """Electricity reports page"""
    return render_template('electricity_reports.html')

@app.route('/telephone-reports')
def telephone_reports():
    """Telephone reports page"""
    return render_template('telephone_reports.html')

@app.route('/new-report')
def new_report():
    """Create new report page"""
    return render_template('new_report.html')

@app.route('/schools')
def schools_page():
    """Schools management page"""
    return render_template('schools.html')

@app.route('/departments')
def departments_page():
    """Departments management page"""
    return render_template('departments.html')

@app.route('/technicians')
def technicians_page():
    """Technicians management page"""
    return render_template('technicians.html')

@app.route('/my-reports')
def my_reports():
    """Technician's own reports page"""
    return render_template('my_reports.html')

@app.route('/team-leader')
def team_leader():
    """Team leader dashboard page"""
    return render_template('team_leader.html')

# ============ TECHNICIAN API WITH AUTHORIZATION ============

@app.route('/api/technicians', methods=['GET'])
def get_technicians():
    """Get all technicians sorted by ID ascending (oldest first)"""
    try:
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        
        response = supabase.table("technicians").select("*").order("id", desc=False).execute()
        
        # Process the data to ensure specializations is always an array
        technicians = []
        if response.data:
            for tech in response.data:
                tech_dict = dict(tech)
                # Handle specializations
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
                # Ensure is_authorized is a boolean
                tech_dict['is_authorized'] = tech_dict.get('is_authorized', False)
                technicians.append(tech_dict)
        
        return jsonify(technicians)
    except Exception as e:
        app.logger.error(f"Error getting technicians: {e}")
        return jsonify([]), 500

@app.route('/api/technicians', methods=['POST'])
def create_technician():
    """Create a new technician with multiple specializations"""
    try:
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        
        data = request.get_json()
        
        # Get specializations as array
        specializations = data.get('specializations', [])
        
        technician_data = {
            "name": data.get('name'),
            "role": data.get('role', 'technician'),
            "employee_id": data.get('employee_id'),
            "phone": data.get('phone'),
            "email": data.get('email'),
            "specializations": json.dumps(specializations) if specializations else '[]',
            "is_authorized": data.get('is_authorized', False),
            "created_at": datetime.now().isoformat()
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
    """Update an existing technician with multiple specializations"""
    try:
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        
        data = request.get_json()
        update_data = {}
        
        allowed_fields = ['name', 'role', 'employee_id', 'phone', 'email', 'is_authorized']
        for field in allowed_fields:
            if field in data:
                update_data[field] = data[field]
        
        # Handle specializations separately
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
    """Delete a technician"""
    try:
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        
        # Check if technician has assigned reports
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
    """Check if a technician is authorized to acknowledge reports"""
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
    """Get all schools sorted by ID ascending (oldest first)"""
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
    """Create a new school"""
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
            "created_at": datetime.now().isoformat()
        }
        
        if not school_data['name']:
            return jsonify({'success': False, 'error': 'School name is required'}), 400
        
        response = supabase.table("schools").insert(school_data).execute()
        
        if response.data:
            app.logger.info(f"School created: {school_data['name']}")
            return jsonify({'success': True, 'data': response.data[0]})
        else:
            return jsonify({'success': False, 'error': 'Failed to create school'}), 500
            
    except Exception as e:
        app.logger.error(f"Error creating school: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/schools/<int:school_id>', methods=['PUT'])
def update_school(school_id):
    """Update an existing school"""
    try:
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        
        data = request.get_json()
        response = supabase.table("schools").update(data).eq("id", school_id).execute()
        
        if response.data:
            app.logger.info(f"School updated: ID {school_id}")
            return jsonify({'success': True, 'data': response.data[0]})
        else:
            return jsonify({'success': False, 'error': 'School not found'}), 404
            
    except Exception as e:
        app.logger.error(f"Error updating school: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/schools/<int:school_id>', methods=['DELETE'])
def delete_school(school_id):
    """Delete a school"""
    try:
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        
        # Check if school has reports
        reports = supabase.table("technical_reports").select("id").eq("entity_id", school_id).eq("entity_type", "school").limit(1).execute()
        if reports.data and len(reports.data) > 0:
            return jsonify({'success': False, 'error': 'Cannot delete school with existing reports'}), 400
        
        response = supabase.table("schools").delete().eq("id", school_id).execute()
        
        if response.data:
            app.logger.info(f"School deleted: ID {school_id}")
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'School not found'}), 404
            
    except Exception as e:
        app.logger.error(f"Error deleting school: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ============ DEPARTMENTS API ============

@app.route('/api/departments', methods=['GET'])
def get_departments():
    """Get all departments sorted by ID ascending (oldest first)"""
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
    """Create a new department"""
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
            "created_at": datetime.now().isoformat()
        }
        
        if not dept_data['unit_name']:
            dept_data['unit_name'] = dept_data['name']
        
        if not dept_data['name']:
            return jsonify({'success': False, 'error': 'Department name is required'}), 400
        
        response = supabase.table("departments").insert(dept_data).execute()
        
        if response.data:
            app.logger.info(f"Department created: {dept_data['name']}")
            return jsonify({'success': True, 'data': response.data[0]})
        else:
            return jsonify({'success': False, 'error': 'Failed to create department'}), 500
            
    except Exception as e:
        app.logger.error(f"Error creating department: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/departments/<int:dept_id>', methods=['PUT'])
def update_department(dept_id):
    """Update an existing department"""
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
            app.logger.info(f"Department updated: ID {dept_id}")
            return jsonify({'success': True, 'data': response.data[0]})
        else:
            return jsonify({'success': False, 'error': 'Department not found'}), 404
            
    except Exception as e:
        app.logger.error(f"Error updating department: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/departments/<int:dept_id>', methods=['DELETE'])
def delete_department(dept_id):
    """Delete a department"""
    try:
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        
        # Check if department has reports
        reports = supabase.table("technical_reports").select("id").eq("entity_id", dept_id).eq("entity_type", "department").limit(1).execute()
        if reports.data and len(reports.data) > 0:
            return jsonify({'success': False, 'error': 'Cannot delete department with existing reports'}), 400
        
        response = supabase.table("departments").delete().eq("id", dept_id).execute()
        
        if response.data:
            app.logger.info(f"Department deleted: ID {dept_id}")
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Department not found'}), 404
            
    except Exception as e:
        app.logger.error(f"Error deleting department: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ============ TECHNICAL REPORTS API ============

@app.route('/api/technical-reports', methods=['GET'])
def get_technical_reports():
    """Get technical reports with filters"""
    try:
        if not supabase:
            return jsonify([]), 500
        
        # Get query parameters
        report_type = request.args.get('type')
        entity_type = request.args.get('entity_type')
        entity_id = request.args.get('entity_id')
        status = request.args.get('status')
        priority = request.args.get('priority')
        technician_id = request.args.get('technician_id')
        team_leader_ack = request.args.get('team_leader_acknowledged')
        
        # Build query
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
        
        # Execute query with ordering by created_at descending (newest first for reports)
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
    """Create a new technical report"""
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
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
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
    """Update an existing technical report"""
    try:
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        
        data = request.get_json()
        
        allowed_fields = [
            'problem_type', 'complaint_details', 'priority', 'status',
            'technician_notes', 'action_taken', 'resolution_details',
            'team_leader_notes', 'images', 'account_number', 'meter_number',
            'phone_number', 'number_of_lines'
        ]
        
        update_data = {}
        for field in allowed_fields:
            if field in data:
                update_data[field] = data[field]
        
        update_data['updated_at'] = datetime.now().isoformat()
        
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
    """Acknowledge a report as team leader (only for authorized technicians)"""
    try:
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        
        data = request.get_json()
        team_leader_id = data.get('team_leader_id')
        
        # Check if the technician is authorized
        auth_response = supabase.table("technicians").select("is_authorized").eq("id", team_leader_id).execute()
        
        if not auth_response.data or not auth_response.data[0].get('is_authorized', False):
            return jsonify({
                'success': False, 
                'error': 'You are not authorized to acknowledge reports. Only designated team leaders can acknowledge.'
            }), 403
        
        update_data = {
            "team_leader_acknowledged": True,
            "team_leader_acknowledged_at": datetime.now().isoformat(),
            "team_leader_id": team_leader_id,
            "team_leader_notes": data.get('team_leader_notes', ''),
            "updated_at": datetime.now().isoformat()
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
    """Delete a technical report"""
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

# ============ IMAGE UPLOAD ============

@app.route('/api/upload-image', methods=['POST'])
def upload_image():
    """Upload an image for a report"""
    try:
        if 'image' not in request.files:
            return jsonify({'success': False, 'error': 'No image file provided'}), 400
        
        file = request.files['image']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No image selected'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'success': False, 'error': 'File type not allowed'}), 400
        
        ext = file.filename.rsplit('.', 1)[1].lower()
        filename = secure_filename(f"{uuid.uuid4().hex}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{ext}")
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
            "uploaded_at": datetime.now().isoformat()
        }
        
        if supabase:
            try:
                response = supabase.table("report_images").insert(image_record).execute()
                if response.data:
                    image_id = response.data[0]['id']
                    app.logger.info(f"Image record saved to Supabase: ID {image_id}")
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
    """Serve uploaded images"""
    try:
        from flask import send_from_directory
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
    except Exception as e:
        app.logger.error(f"Error serving image {filename}: {e}")
        return jsonify({'error': 'Image not found'}), 404

# ============ DASHBOARD STATISTICS ============

@app.route('/api/dashboard-stats')
def get_dashboard_stats():
    """Get statistics for dashboard"""
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
    """Export reports to CSV"""
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
            'Report ID', 'Type', 'Entity Type', 'Entity Name', 'Account Number',
            'Meter Number', 'Phone Number', 'Number of Lines', 'Problem Type',
            'Complaint Details', 'Priority', 'Status', 'Technician Name',
            'Technician Notes', 'Action Taken', 'Resolution Details',
            'Team Leader Acknowledged', 'Team Leader Notes', 'Created At', 'Updated At'
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
                report.get('status', ''),
                tech_name,
                report.get('technician_notes', ''),
                report.get('action_taken', ''),
                report.get('resolution_details', ''),
                'Yes' if report.get('team_leader_acknowledged') else 'No',
                report.get('team_leader_notes', ''),
                report.get('created_at', ''),
                report.get('updated_at', '')
            ])
        
        output.seek(0)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
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
    """Health check endpoint for monitoring"""
    supabase_status = test_supabase_connection()
    
    return jsonify({
        'status': 'healthy' if supabase_status else 'degraded',
        'timestamp': datetime.now().isoformat(),
        'version': '1.0.0',
        'supabase_connected': supabase_status,
        'service': 'MOE Technical Report System',
        'environment': os.environ.get('FLASK_ENV', 'production')
    })

@app.route('/api/health')
def api_health():
    """Simple API health check"""
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat()
    })

# ============ ERROR HANDLERS ============

@app.errorhandler(404)
def not_found_error(error):
    """Handle 404 errors"""
    app.logger.warning(f"404 error: {request.url}")
    return jsonify({'error': 'Resource not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    app.logger.error(f"500 error: {error}")
    return jsonify({'error': 'Internal server error'}), 500

# ============ APPLICATION STARTUP ============

def init_app():
    """Initialize application on startup"""
    create_directories()
    
    app.logger.info("=" * 60)
    app.logger.info("🏫 MOE Technical Report System Starting")
    app.logger.info("Ministry of Education - Brunei Darussalam")
    app.logger.info("=" * 60)
    app.logger.info("📋 System for Water, Electricity & Telephone Reports")
    app.logger.info("👥 Users: Senior Technicians & Technicians")
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

# Run initialization
init_app()

# ============ MAIN ENTRY POINT ============

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    
    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug_mode
    )
