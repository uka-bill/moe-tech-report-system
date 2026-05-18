from flask import Flask, render_template, request, jsonify, send_file
import os
from supabase import create_client, Client
import uuid
from werkzeug.utils import secure_filename
import csv
import io
from datetime import datetime, timedelta
import traceback
import json
import base64
from PIL import Image

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'moed-tech-report-secret-2026')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Configure upload folder
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Supabase configuration
SUPABASE_URL = 'https://megrxcfmcwrttiwujddh.supabase.co'
SUPABASE_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1lZ3J4Y2ZtY3dydHRpd3VqZGRoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzkwNDA4ODgsImV4cCI6MjA5NDYxNjg4OH0.fmwcV6fqqr-hO6hRPTzER6eODl6zffwud9heIchMNkw'

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def create_directories():
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

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
        response = supabase.table("technicians").select("*").order("name").execute()
        return jsonify(response.data if response.data else [])
    except Exception as e:
        print(f"Error getting technicians: {e}")
        return jsonify([]), 500

@app.route('/api/technicians', methods=['POST'])
def create_technician():
    try:
        data = request.get_json()
        technician_data = {
            "name": data.get('name'),
            "role": data.get('role', 'technician'),
            "employee_id": data.get('employee_id'),
            "phone": data.get('phone'),
            "email": data.get('email'),
            "specialization": data.get('specialization'),
            "created_at": datetime.now().isoformat()
        }
        response = supabase.table("technicians").insert(technician_data).execute()
        return jsonify({'success': True, 'data': response.data[0] if response.data else None})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============ SCHOOLS API ============

@app.route('/api/schools', methods=['GET'])
def get_schools():
    try:
        response = supabase.table("schools").select("*").order("name").execute()
        return jsonify(response.data if response.data else [])
    except Exception as e:
        return jsonify([]), 500

@app.route('/api/schools', methods=['POST'])
def create_school():
    try:
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
        response = supabase.table("schools").insert(school_data).execute()
        return jsonify({'success': True, 'data': response.data[0] if response.data else None})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/schools/<int:school_id>', methods=['PUT'])
def update_school(school_id):
    try:
        data = request.get_json()
        response = supabase.table("schools").update(data).eq("id", school_id).execute()
        return jsonify({'success': True, 'data': response.data[0] if response.data else None})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/schools/<int:school_id>', methods=['DELETE'])
def delete_school(school_id):
    try:
        # Check if there are reports associated
        reports = supabase.table("technical_reports").select("id").eq("entity_id", school_id).eq("entity_type", "school").execute()
        if reports.data and len(reports.data) > 0:
            return jsonify({'success': False, 'error': 'Cannot delete school with existing reports'}), 400
        
        supabase.table("schools").delete().eq("id", school_id).execute()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============ DEPARTMENTS API ============

@app.route('/api/departments', methods=['GET'])
def get_departments():
    try:
        response = supabase.table("departments").select("*").order("name").execute()
        return jsonify(response.data if response.data else [])
    except Exception as e:
        return jsonify([]), 500

@app.route('/api/departments', methods=['POST'])
def create_department():
    try:
        data = request.get_json()
        dept_data = {
            "name": data.get('name'),
            "division": data.get('division'),
            "department_code": data.get('department_code'),
            "address": data.get('address'),
            "contact_person": data.get('contact_person'),
            "contact_phone": data.get('contact_phone'),
            "created_at": datetime.now().isoformat()
        }
        response = supabase.table("departments").insert(dept_data).execute()
        return jsonify({'success': True, 'data': response.data[0] if response.data else None})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/departments/<int:dept_id>', methods=['PUT'])
def update_department(dept_id):
    try:
        data = request.get_json()
        response = supabase.table("departments").update(data).eq("id", dept_id).execute()
        return jsonify({'success': True, 'data': response.data[0] if response.data else None})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/departments/<int:dept_id>', methods=['DELETE'])
def delete_department(dept_id):
    try:
        reports = supabase.table("technical_reports").select("id").eq("entity_id", dept_id).eq("entity_type", "department").execute()
        if reports.data and len(reports.data) > 0:
            return jsonify({'success': False, 'error': 'Cannot delete department with existing reports'}), 400
        
        supabase.table("departments").delete().eq("id", dept_id).execute()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============ TECHNICAL REPORTS API ============

@app.route('/api/technical-reports', methods=['GET'])
def get_technical_reports():
    try:
        report_type = request.args.get('type')
        entity_type = request.args.get('entity_type')
        entity_id = request.args.get('entity_id')
        status = request.args.get('status')
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
        if technician_id:
            query = query.eq("technician_id", int(technician_id))
        if team_leader_ack is not None:
            query = query.eq("team_leader_acknowledged", team_leader_ack == 'true')
        
        response = query.order("created_at", desc=True).execute()
        
        reports = []
        if response.data:
            for report in response.data:
                report_data = dict(report)
                
                # Get entity name
                if report_data['entity_type'] == 'school':
                    entity = supabase.table("schools").select("name").eq("id", report_data['entity_id']).execute()
                    if entity.data:
                        report_data['entity_name'] = entity.data[0]['name']
                elif report_data['entity_type'] == 'department':
                    entity = supabase.table("departments").select("name").eq("id", report_data['entity_id']).execute()
                    if entity.data:
                        report_data['entity_name'] = entity.data[0]['name']
                
                # Get technician name
                if report_data.get('technician_id'):
                    tech = supabase.table("technicians").select("name, role").eq("id", report_data['technician_id']).execute()
                    if tech.data:
                        report_data['technician_name'] = tech.data[0]['name']
                        report_data['technician_role'] = tech.data[0]['role']
                
                reports.append(report_data)
        
        return jsonify(reports)
    except Exception as e:
        print(f"Error getting reports: {e}")
        return jsonify([]), 500

@app.route('/api/technical-reports', methods=['POST'])
def create_technical_report():
    try:
        data = request.get_json()
        
        report_data = {
            "report_type": data.get('report_type'),  # water, electricity, telephone
            "entity_type": data.get('entity_type'),  # school, department
            "entity_id": int(data.get('entity_id')),
            "account_number": data.get('account_number', ''),
            "meter_number": data.get('meter_number', ''),
            "phone_number": data.get('phone_number', ''),
            "number_of_lines": data.get('number_of_lines'),
            "problem_type": data.get('problem_type'),
            "complaint_details": data.get('complaint_details'),
            "priority": data.get('priority', 'medium'),  # high, medium, low
            "status": data.get('status', 'pending'),  # pending, in_progress, resolved, closed
            "technician_id": data.get('technician_id'),
            "technician_notes": data.get('technician_notes'),
            "action_taken": data.get('action_taken'),
            "resolution_details": data.get('resolution_details'),
            "team_leader_notes": data.get('team_leader_notes'),
            "team_leader_acknowledged": False,
            "team_leader_acknowledged_at": None,
            "team_leader_id": None,
            "images": data.get('images', []),  # JSON array of image URLs
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        
        response = supabase.table("technical_reports").insert(report_data).execute()
        
        if response.data:
            return jsonify({
                'success': True,
                'message': 'Report created successfully',
                'report': response.data[0]
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to create report'}), 500
            
    except Exception as e:
        print(f"Error creating report: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/technical-reports/<int:report_id>', methods=['PUT'])
def update_technical_report(report_id):
    try:
        data = request.get_json()
        
        update_data = {}
        allowed_fields = ['problem_type', 'complaint_details', 'priority', 'status', 
                         'technician_notes', 'action_taken', 'resolution_details', 
                         'team_leader_notes', 'images', 'account_number', 'meter_number',
                         'phone_number', 'number_of_lines']
        
        for field in allowed_fields:
            if field in data:
                update_data[field] = data[field]
        
        update_data['updated_at'] = datetime.now().isoformat()
        
        response = supabase.table("technical_reports").update(update_data).eq("id", report_id).execute()
        
        if response.data:
            return jsonify({
                'success': True,
                'message': 'Report updated successfully',
                'report': response.data[0]
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to update report'}), 500
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/technical-reports/<int:report_id>/acknowledge', methods=['POST'])
def acknowledge_report(report_id):
    try:
        data = request.get_json()
        
        update_data = {
            "team_leader_acknowledged": True,
            "team_leader_acknowledged_at": datetime.now().isoformat(),
            "team_leader_id": data.get('team_leader_id'),
            "team_leader_notes": data.get('team_leader_notes', '')
        }
        
        response = supabase.table("technical_reports").update(update_data).eq("id", report_id).execute()
        
        if response.data:
            return jsonify({
                'success': True,
                'message': 'Report acknowledged successfully',
                'report': response.data[0]
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to acknowledge report'}), 500
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/technical-reports/<int:report_id>', methods=['DELETE'])
def delete_technical_report(report_id):
    try:
        response = supabase.table("technical_reports").delete().eq("id", report_id).execute()
        
        if response.data:
            return jsonify({
                'success': True,
                'message': 'Report deleted successfully'
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to delete report'}), 500
            
    except Exception as e:
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
        
        if file and allowed_file(file.filename):
            filename = secure_filename(f"{uuid.uuid4().hex}_{file.filename}")
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # Convert to base64 for storage in Supabase
            with open(filepath, 'rb') as img_file:
                img_data = base64.b64encode(img_file.read()).decode('utf-8')
            
            # Store image info in supabase
            image_record = {
                "filename": filename,
                "original_name": file.filename,
                "filepath": filepath,
                "file_size": os.path.getsize(filepath),
                "image_data_base64": img_data,
                "uploaded_at": datetime.now().isoformat()
            }
            
            response = supabase.table("report_images").insert(image_record).execute()
            
            if response.data:
                return jsonify({
                    'success': True,
                    'image_url': f"/api/images/{filename}",
                    'image_id': response.data[0]['id'],
                    'message': 'Image uploaded successfully'
                })
            else:
                return jsonify({'success': False, 'error': 'Failed to save image record'}), 500
        else:
            return jsonify({'success': False, 'error': 'Invalid file type'}), 400
            
    except Exception as e:
        print(f"Error uploading image: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/images/<filename>')
def get_image(filename):
    try:
        from flask import send_from_directory
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
    except Exception as e:
        return jsonify({'error': 'Image not found'}), 404

# ============ DASHBOARD STATISTICS ============

@app.route('/api/dashboard-stats')
def get_dashboard_stats():
    try:
        # Get counts by report type
        water_reports = supabase.table("technical_reports").select("*", count="exact").eq("report_type", "water").execute()
        electricity_reports = supabase.table("technical_reports").select("*", count="exact").eq("report_type", "electricity").execute()
        telephone_reports = supabase.table("technical_reports").select("*", count="exact").eq("report_type", "telephone").execute()
        
        # Get counts by status
        pending_reports = supabase.table("technical_reports").select("*", count="exact").eq("status", "pending").execute()
        in_progress_reports = supabase.table("technical_reports").select("*", count="exact").eq("status", "in_progress").execute()
        resolved_reports = supabase.table("technical_reports").select("*", count="exact").eq("status", "resolved").execute()
        
        # Get acknowledged vs unacknowledged
        acknowledged_reports = supabase.table("technical_reports").select("*", count="exact").eq("team_leader_acknowledged", True).execute()
        
        # Get recent reports
        recent_reports = supabase.table("technical_reports").select("*").order("created_at", desc=True).limit(10).execute()
        
        # Enhance recent reports with entity names
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
        })
        
    except Exception as e:
        print(f"Error getting dashboard stats: {e}")
        return jsonify({'error': str(e)}), 500

# ============ EXPORT REPORTS ============

@app.route('/api/export-reports', methods=['GET'])
def export_reports():
    try:
        report_type = request.args.get('type')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        query = supabase.table("technical_reports").select("*")
        
        if report_type:
            query = query.eq("report_type", report_type)
        if start_date:
            query = query.gte("created_at", start_date)
        if end_date:
            query = query.lte("created_at", end_date)
        
        response = query.order("created_at", desc=True).execute()
        
        if not response.data:
            return jsonify({'success': False, 'error': 'No data to export'}), 404
        
        # Create CSV
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write headers
        headers = ['ID', 'Report Type', 'Entity Type', 'Entity Name', 'Account Number', 
                   'Meter Number', 'Phone Number', 'Problem Type', 'Complaint Details', 
                   'Priority', 'Status', 'Technician Name', 'Technician Notes', 
                   'Action Taken', 'Resolution', 'Team Leader Acknowledged', 
                   'Team Leader Notes', 'Created At', 'Updated At']
        writer.writerow(headers)
        
        for report in response.data:
            # Get entity name
            entity_name = ''
            if report['entity_type'] == 'school':
                entity = supabase.table("schools").select("name").eq("id", report['entity_id']).execute()
                if entity.data:
                    entity_name = entity.data[0]['name']
            else:
                entity = supabase.table("departments").select("name").eq("id", report['entity_id']).execute()
                if entity.data:
                    entity_name = entity.data[0]['name']
            
            # Get technician name
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
        
        filename = f"technical_reports_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        print(f"Error exporting reports: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ============ HEALTH CHECK ============

@app.route('/health')
def health_check():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'service': 'MOE Technical Report System'
    })

# ============ APPLICATION STARTUP ============

if __name__ == '__main__':
    create_directories()
    
    print("=" * 60)
    print("🏫 MOE Technical Report System")
    print("Ministry of Education - Brunei Darussalam")
    print("=" * 60)
    print("📋 System for Water, Electricity & Telephone Reports")
    print("👥 Users: Senior Technicians & Technicians")
    print("=" * 60)
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
