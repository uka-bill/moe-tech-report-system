from flask import Flask, render_template, request, jsonify, redirect, url_for, send_file, make_response
import os
from supabase import create_client, Client
import uuid
from werkzeug.utils import secure_filename
import csv
import io
from datetime import datetime, timedelta
import traceback
import json
import sys
import zipfile
import base64
import requests
from urllib.parse import urlparse

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'uka-bill-utility-secret-2026')
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max file size

# Configure upload folder (for temporary storage only)
UPLOAD_FOLDER = 'uploads'
BACKUP_FOLDER = 'backups'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['BACKUP_FOLDER'] = BACKUP_FOLDER

# Supabase Storage bucket name
SUPABASE_BUCKET = 'moe-images'  # You need to create this bucket in Supabase Storage

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Number formatting functions
def format_currency(amount):
    try:
        if amount is None:
            return "0.00"
        return "${:,.2f}".format(float(amount))
    except (ValueError, TypeError):
        return "$0.00"

def format_number(number):
    try:
        if number is None:
            return "0"
        return "{:,.0f}".format(float(number))
    except (ValueError, TypeError):
        return "0"

def format_year(year_value):
    """Format year values without currency symbols"""
    try:
        if year_value is None:
            return ""
        year_str = str(year_value)
        year_str = year_str.replace('$', '').replace(',', '').strip()
        year_int = int(float(year_str))
        return f"{year_int}"
    except (ValueError, TypeError):
        return ""

# Initialize Supabase
print("=" * 60)
print("Ministry of Education Brunei - Utility Bills System")
print("Starting up...")
print("=" * 60)

try:
    SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://skzhqbynrpdsxersdxnp.supabase.co')
    SUPABASE_KEY = os.environ.get('SUPABASE_KEY', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNremhxYnlucnBkc3hlcnNkeG5wIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjgyNjU3MDksImV4cCI6MjA4Mzg0MTcwOX0.xXfYc5O-Oua_Lug8kq-L-Pysq4r1C2mZtysosldzTKc')
    
    print(f"Supabase URL: {SUPABASE_URL}")
    
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("✅ Supabase connected successfully!")
    
    # Test storage connection
    try:
        # Try to list buckets to verify storage access
        buckets = supabase.storage.list_buckets()
        print(f"✅ Supabase Storage connected! Found {len(buckets)} buckets")
        
        # Check if our bucket exists, if not, try to create it
        bucket_exists = False
        for bucket in buckets:
            if bucket.name == SUPABASE_BUCKET:
                bucket_exists = True
                print(f"✅ Bucket '{SUPABASE_BUCKET}' exists")
                break
        
        if not bucket_exists:
            try:
                supabase.storage.create_bucket(SUPABASE_BUCKET, {'public': True})
                print(f"✅ Created bucket '{SUPABASE_BUCKET}'")
            except Exception as e:
                print(f"⚠️ Could not create bucket: {e}")
                print(f"ℹ️ Please create bucket '{SUPABASE_BUCKET}' manually in Supabase Storage")
    except Exception as e:
        print(f"⚠️ Supabase Storage connection warning: {e}")
        print(f"ℹ️ Please ensure storage is enabled in Supabase")
        
except Exception as e:
    print(f"❌ Supabase connection error: {e}")
    supabase = None

def upload_file_to_supabase(file_data, filename, folder='reports'):
    """Upload a file to Supabase Storage and return the public URL"""
    if not supabase:
        return None
    
    try:
        # Generate a unique filename to avoid collisions
        unique_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_filename = f"{folder}/{timestamp}_{unique_id}_{filename}"
        
        # Upload to Supabase Storage
        result = supabase.storage.from_(SUPABASE_BUCKET).upload(
            safe_filename,
            file_data,
            {'content-type': 'image/png'}
        )
        
        # Get public URL
        public_url = supabase.storage.from_(SUPABASE_BUCKET).get_public_url(safe_filename)
        
        print(f"✅ File uploaded to Supabase: {public_url}")
        return public_url
        
    except Exception as e:
        print(f"❌ Supabase upload error: {e}")
        return None

def delete_file_from_supabase(file_url):
    """Delete a file from Supabase Storage"""
    if not supabase or not file_url:
        return False
    
    try:
        # Extract file path from URL
        # URL format: https://[project].supabase.co/storage/v1/object/public/[bucket]/[path]
        parsed = urlparse(file_url)
        path_parts = parsed.path.split('/')
        
        # Find the bucket name and file path
        bucket_index = -1
        for i, part in enumerate(path_parts):
            if part == 'public' and i + 1 < len(path_parts):
                bucket_index = i + 1
                break
        
        if bucket_index > 0 and bucket_index < len(path_parts):
            bucket = path_parts[bucket_index]
            file_path = '/'.join(path_parts[bucket_index + 1:])
            
            if bucket == SUPABASE_BUCKET:
                supabase.storage.from_(SUPABASE_BUCKET).remove([file_path])
                print(f"✅ Deleted file from Supabase: {file_path}")
                return True
        
        return False
        
    except Exception as e:
        print(f"❌ Supabase delete error: {e}")
        return False

def create_directories():
    """Create required directories if they don't exist"""
    directories = [UPLOAD_FOLDER, BACKUP_FOLDER]
    for directory in directories:
        try:
            if not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)
                print(f"📁 Created directory: {directory}")
            else:
                print(f"📁 Directory already exists: {directory}")
        except Exception as e:
            print(f"❌ Error creating directory {directory}: {e}")

def test_supabase_connection():
    if supabase:
        try:
            response = supabase.table("financial_years").select("*").limit(1).execute()
            print(f"✅ Supabase test query successful: {len(response.data)} budgets found")
            return True
        except Exception as e:
            print(f"❌ Supabase test query failed: {e}")
            return False
    return False

def initialize_database_tables():
    """Check if required tables exist"""
    try:
        if not supabase:
            return
        
        print("🗄️ Checking required database tables...")
        
        tables = ['financial_years', 'schools', 'departments', 'utility_bills', 'utility_accounts', 'backup_metadata', 'sut_office_expenses', 'technical_reports', 'mapping_images']
        
        for table in tables:
            try:
                supabase.table(table).select("id").limit(1).execute()
                print(f"✅ {table.capitalize()} table exists")
            except Exception as e:
                print(f"⚠️ {table} table not found or error accessing it")
                print(f"ℹ️ Please create the '{table}' table manually in Supabase")
                
    except Exception as e:
        print(f"⚠️ Database check warning: {e}")

# ============ UPLOAD IMAGE API ============

@app.route('/api/upload-image', methods=['POST'])
def upload_image():
    """Upload an image to Supabase Storage"""
    try:
        print("📸 POST /api/upload-image called")
        
        if 'image' not in request.files:
            return jsonify({'error': 'No image file provided'}), 400
        
        file = request.files['image']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Get folder from request (reports or mapping)
        folder = request.form.get('folder', 'reports')
        
        # Read file data
        file_data = file.read()
        
        # Get original filename
        original_filename = secure_filename(file.filename)
        
        # Upload to Supabase
        image_url = upload_file_to_supabase(file_data, original_filename, folder)
        
        if image_url:
            return jsonify({
                'success': True,
                'image_url': image_url,
                'message': 'Image uploaded successfully'
            })
        else:
            return jsonify({'error': 'Failed to upload image to storage'}), 500
            
    except Exception as e:
        print(f"❌ Upload image error: {e}")
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

@app.route('/api/upload-mapping-image', methods=['POST'])
def upload_mapping_image():
    """Upload a mapping image to Supabase Storage and save metadata"""
    try:
        print("📸 POST /api/upload-mapping-image called")
        
        if 'image' not in request.files:
            return jsonify({'error': 'No image file provided'}), 400
        
        file = request.files['image']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Get form data
        entity_type = request.form.get('entity_type')
        entity_id = request.form.get('entity_id')
        description = request.form.get('description', '')
        notes = request.form.get('notes', '')
        water_account_number = request.form.get('water_account_number', '')
        water_meter_number = request.form.get('water_meter_number', '')
        electricity_account_number = request.form.get('electricity_account_number', '')
        electricity_meter_number = request.form.get('electricity_meter_number', '')
        telephone_account_number = request.form.get('telephone_account_number', '')
        telephone_number = request.form.get('telephone_number', '')
        canteen_account_number = request.form.get('canteen_account_number', '')
        canteen_meter_number = request.form.get('canteen_meter_number', '')
        
        if not entity_type or not entity_id:
            return jsonify({'error': 'Entity type and ID are required'}), 400
        
        # Read file data
        file_data = file.read()
        original_filename = secure_filename(file.filename)
        
        # Upload to Supabase in mapping folder
        image_url = upload_file_to_supabase(file_data, original_filename, 'mapping')
        
        if not image_url:
            return jsonify({'error': 'Failed to upload image to storage'}), 500
        
        # Save metadata to database
        image_data = {
            'entity_type': entity_type,
            'entity_id': int(entity_id),
            'image_url': image_url,
            'description': description,
            'notes': notes,
            'water_account_number': water_account_number,
            'water_meter_number': water_meter_number,
            'electricity_account_number': electricity_account_number,
            'electricity_meter_number': electricity_meter_number,
            'telephone_account_number': telephone_account_number,
            'telephone_number': telephone_number,
            'canteen_account_number': canteen_account_number,
            'canteen_meter_number': canteen_meter_number,
            'uploaded_at': datetime.now().isoformat()
        }
        
        result = supabase.table("mapping_images").insert(image_data).execute()
        
        if result.data:
            return jsonify({
                'success': True,
                'image': result.data[0],
                'image_url': image_url,
                'message': 'Image uploaded successfully'
            })
        else:
            # If database insert fails, delete the uploaded file
            delete_file_from_supabase(image_url)
            return jsonify({'error': 'Failed to save image metadata'}), 500
            
    except Exception as e:
        print(f"❌ Upload mapping image error: {e}")
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

@app.route('/api/technical-reports', methods=['POST'])
def create_technical_report():
    """Create a new technical report with images stored in Supabase"""
    try:
        print("📋 POST /api/technical-reports called")
        
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        
        data = request.get_json()
        
        # Generate utility number
        utility_number = f"TR-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:4].upper()}"
        
        report_data = {
            'utility_number': utility_number,
            'report_type': data.get('report_type'),
            'entity_type': data.get('entity_type'),
            'entity_id': data.get('entity_id'),
            'entity_name': data.get('entity_name', ''),
            'account_number': data.get('account_number', ''),
            'meter_number': data.get('meter_number', ''),
            'phone_number': data.get('phone_number', ''),
            'number_of_lines': data.get('number_of_lines'),
            'problem_type': data.get('problem_type'),
            'complaint_details': data.get('complaint_details'),
            'action_taken': data.get('action_taken', ''),
            'priority': data.get('priority', 'medium'),
            'priority_with_tender': data.get('priority_with_tender', False),
            'technician_id': data.get('technician_id'),
            'technician_name': data.get('technician_name', ''),
            'technician_notes': data.get('technician_notes', ''),
            'images': data.get('images', []),  # List of image URLs from Supabase
            'reference_type': data.get('reference_type', ''),
            'reference_number': data.get('reference_number', ''),
            'reference_date': data.get('reference_date'),
            'status': 'pending',
            'team_leader_acknowledged': False,
            'created_at': datetime.now().isoformat()
        }
        
        result = supabase.table("technical_reports").insert(report_data).execute()
        
        if result.data:
            return jsonify({
                'success': True,
                'report': result.data[0],
                'message': 'Report created successfully'
            })
        else:
            return jsonify({'error': 'Failed to create report'}), 500
            
    except Exception as e:
        print(f"❌ Create technical report error: {e}")
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

@app.route('/api/technical-reports/<int:report_id>', methods=['PUT'])
def update_technical_report(report_id):
    """Update a technical report"""
    try:
        print(f"📋 PUT /api/technical-reports/{report_id} called")
        
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        
        data = request.get_json()
        
        # Check if report is already acknowledged
        check = supabase.table("technical_reports").select("team_leader_acknowledged").eq("id", report_id).execute()
        if check.data and check.data[0].get('team_leader_acknowledged'):
            return jsonify({'error': 'Cannot edit acknowledged report'}), 400
        
        report_data = {
            'report_type': data.get('report_type'),
            'entity_type': data.get('entity_type'),
            'entity_id': data.get('entity_id'),
            'entity_name': data.get('entity_name', ''),
            'account_number': data.get('account_number', ''),
            'meter_number': data.get('meter_number', ''),
            'phone_number': data.get('phone_number', ''),
            'number_of_lines': data.get('number_of_lines'),
            'problem_type': data.get('problem_type'),
            'complaint_details': data.get('complaint_details'),
            'action_taken': data.get('action_taken', ''),
            'priority': data.get('priority', 'medium'),
            'priority_with_tender': data.get('priority_with_tender', False),
            'technician_notes': data.get('technician_notes', ''),
            'images': data.get('images', []),
            'reference_type': data.get('reference_type', ''),
            'reference_number': data.get('reference_number', ''),
            'reference_date': data.get('reference_date'),
            'updated_at': datetime.now().isoformat()
        }
        
        result = supabase.table("technical_reports").update(report_data).eq("id", report_id).execute()
        
        if result.data:
            return jsonify({
                'success': True,
                'report': result.data[0],
                'message': 'Report updated successfully'
            })
        else:
            return jsonify({'error': 'Failed to update report'}), 500
            
    except Exception as e:
        print(f"❌ Update technical report error: {e}")
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

@app.route('/api/mapping/images', methods=['GET'])
def get_mapping_images():
    """Get mapping images for an entity"""
    try:
        print("📍 GET /api/mapping/images called")
        
        if not supabase:
            return jsonify([]), 500
        
        entity_type = request.args.get('entity_type')
        entity_id = request.args.get('entity_id')
        
        query = supabase.table("mapping_images").select("*")
        
        if entity_type:
            query = query.eq("entity_type", entity_type)
        if entity_id:
            query = query.eq("entity_id", int(entity_id))
        
        query = query.order("uploaded_at", desc=True)
        result = query.execute()
        
        images = result.data if result.data else []
        return jsonify(images)
        
    except Exception as e:
        print(f"❌ Get mapping images error: {e}")
        return jsonify([]), 500

@app.route('/api/mapping/images', methods=['POST'])
def create_mapping_image():
    """Create a mapping image record (image already uploaded to Supabase)"""
    try:
        print("📍 POST /api/mapping/images called")
        
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        
        data = request.get_json()
        
        image_data = {
            'entity_type': data.get('entity_type'),
            'entity_id': data.get('entity_id'),
            'image_url': data.get('image_url'),
            'description': data.get('description', ''),
            'notes': data.get('notes', ''),
            'water_account_number': data.get('water_account_number', ''),
            'water_meter_number': data.get('water_meter_number', ''),
            'electricity_account_number': data.get('electricity_account_number', ''),
            'electricity_meter_number': data.get('electricity_meter_number', ''),
            'telephone_account_number': data.get('telephone_account_number', ''),
            'telephone_number': data.get('telephone_number', ''),
            'canteen_account_number': data.get('canteen_account_number', ''),
            'canteen_meter_number': data.get('canteen_meter_number', ''),
            'uploaded_by': data.get('uploaded_by'),
            'uploaded_at': datetime.now().isoformat()
        }
        
        result = supabase.table("mapping_images").insert(image_data).execute()
        
        if result.data:
            return jsonify({
                'success': True,
                'image': result.data[0],
                'message': 'Image saved successfully'
            })
        else:
            return jsonify({'error': 'Failed to save image'}), 500
            
    except Exception as e:
        print(f"❌ Create mapping image error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/mapping/images/<int:image_id>', methods=['PUT'])
def update_mapping_image(image_id):
    """Update a mapping image record"""
    try:
        print(f"📍 PUT /api/mapping/images/{image_id} called")
        
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        
        data = request.get_json()
        
        update_data = {
            'description': data.get('description', ''),
            'notes': data.get('notes', ''),
            'water_account_number': data.get('water_account_number', ''),
            'water_meter_number': data.get('water_meter_number', ''),
            'electricity_account_number': data.get('electricity_account_number', ''),
            'electricity_meter_number': data.get('electricity_meter_number', ''),
            'telephone_account_number': data.get('telephone_account_number', ''),
            'telephone_number': data.get('telephone_number', ''),
            'canteen_account_number': data.get('canteen_account_number', ''),
            'canteen_meter_number': data.get('canteen_meter_number', ''),
            'updated_at': datetime.now().isoformat()
        }
        
        result = supabase.table("mapping_images").update(update_data).eq("id", image_id).execute()
        
        if result.data:
            return jsonify({
                'success': True,
                'image': result.data[0],
                'message': 'Image updated successfully'
            })
        else:
            return jsonify({'error': 'Failed to update image'}), 500
            
    except Exception as e:
        print(f"❌ Update mapping image error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/mapping/images/<int:image_id>', methods=['DELETE'])
def delete_mapping_image(image_id):
    """Delete a mapping image record and the actual file from Supabase"""
    try:
        print(f"📍 DELETE /api/mapping/images/{image_id} called")
        
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        
        # Get the image record first to get the URL
        get_result = supabase.table("mapping_images").select("image_url").eq("id", image_id).execute()
        
        if get_result.data:
            image_url = get_result.data[0].get('image_url')
            # Delete from Supabase Storage
            if image_url:
                delete_file_from_supabase(image_url)
        
        # Delete from database
        result = supabase.table("mapping_images").delete().eq("id", image_id).execute()
        
        if result.data:
            return jsonify({
                'success': True,
                'message': 'Image deleted successfully'
            })
        else:
            return jsonify({'error': 'Failed to delete image'}), 500
            
    except Exception as e:
        print(f"❌ Delete mapping image error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/technical-reports', methods=['GET'])
def get_technical_reports():
    """Get all technical reports"""
    try:
        print("📋 GET /api/technical-reports called")
        
        if not supabase:
            return jsonify([]), 500
        
        result = supabase.table("technical_reports").select("*").order("created_at", desc=True).execute()
        reports = result.data if result.data else []
        
        # Ensure images are properly formatted
        for report in reports:
            if report.get('images') and isinstance(report.get('images'), str):
                try:
                    report['images'] = json.loads(report['images'])
                except:
                    report['images'] = []
            elif not report.get('images'):
                report['images'] = []
        
        return jsonify(reports)
        
    except Exception as e:
        print(f"❌ Get technical reports error: {e}")
        return jsonify([]), 500

@app.route('/api/technical-reports/<int:report_id>/acknowledge', methods=['POST'])
def acknowledge_technical_report(report_id):
    """Acknowledge a technical report"""
    try:
        print(f"📋 POST /api/technical-reports/{report_id}/acknowledge called")
        
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        
        data = request.get_json()
        
        update_data = {
            'team_leader_acknowledged': True,
            'team_leader_id': data.get('team_leader_id'),
            'team_leader_name': data.get('team_leader_name', 'Team Leader'),
            'team_leader_notes': data.get('team_leader_notes', ''),
            'team_leader_acknowledged_at': datetime.now().isoformat(),
            'status': 'acknowledged'
        }
        
        result = supabase.table("technical_reports").update(update_data).eq("id", report_id).execute()
        
        if result.data:
            return jsonify({
                'success': True,
                'report': result.data[0],
                'message': 'Report acknowledged successfully'
            })
        else:
            return jsonify({'error': 'Failed to acknowledge report'}), 500
            
    except Exception as e:
        print(f"❌ Acknowledge technical report error: {e}")
        return jsonify({'error': str(e)}), 500

# ============ REST OF YOUR EXISTING CODE ============
# (Include all your other routes here - backup, budgets, schools, departments, etc.)
# I'm omitting them for brevity but they should remain as is

@app.route('/')
def splash():
    return render_template('splash.html')

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/water')
def water_utility():
    return render_template('water.html')

@app.route('/electricity')
def electricity_utility():
    return render_template('electricity.html')

@app.route('/telephone')
def telephone_utility():
    return render_template('telephone.html')

@app.route('/schools')
def schools():
    return render_template('schools.html')

@app.route('/departments')
def departments():
    return render_template('departments.html')

@app.route('/reports')
def reports_page():
    return render_template('reports.html')

@app.route('/export')
def export_page():
    return render_template('export.html')

@app.route('/backup')
def backup_page():
    return render_template('backup.html')

@app.route('/sut-office')
def sut_office():
    return render_template('sut_office.html')

@app.route('/new-report')
def new_report():
    return render_template('new_reports.html')

@app.route('/mapping')
def mapping():
    return render_template('mapping.html')

@app.route('/my-reports')
def my_reports():
    return render_template('my_reports.html')

@app.route('/health')
def health_check():
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

# ============ APPLICATION STARTUP ============

if __name__ == '__main__':
    create_directories()
    
    print("\n" + "="*60)
    print("🚀 UKA-BILL Utility System Starting")
    print("="*60 + "\n")
    
    print("🔗 Testing Supabase connection...")
    if test_supabase_connection():
        print("✅ All systems ready!")
    else:
        print("⚠️  Warning: Supabase connection failed")
    
    initialize_database_tables()
    
    port = int(os.environ.get('PORT', 5000))
    print(f"🌐 Server will run on port: {port}")
    
    app.run(host='0.0.0.0', port=port, debug=False)
