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
from urllib.parse import urlparse

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'uka-bill-utility-secret-2026')
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max file size

# Configure upload folder
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
        buckets = supabase.storage.list_buckets()
        print(f"✅ Supabase Storage connected! Found {len(buckets)} buckets")
        
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

# ============ SUPABASE STORAGE FUNCTIONS (ADDED) ============

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

# ============ UPDATED UPLOAD IMAGE API (MODIFIED) ============

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
            # Fallback to local storage if Supabase fails
            try:
                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                unique_id = str(uuid.uuid4())[:8]
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"{timestamp}_{unique_id}_{original_filename}"
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                local_url = f"/api/images/{filename}"
                print(f"⚠️ Using local storage fallback: {local_url}")
                return jsonify({
                    'success': True,
                    'image_url': local_url,
                    'message': 'Image uploaded to local storage (Supabase unavailable)'
                })
            except Exception as local_error:
                print(f"❌ Local storage fallback also failed: {local_error}")
                return jsonify({'error': 'Failed to upload image to both Supabase and local storage'}), 500
            
    except Exception as e:
        print(f"❌ Upload image error: {e}")
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

# ============ ADDED MAPPING IMAGE UPLOAD ROUTE ============

@app.route('/api/upload-mapping-image', methods=['POST'])
def upload_mapping_image():
    """Upload a mapping image to Supabase Storage and save metadata"""
    try:
        print("📸 POST /api/upload-mapping-image called")
        
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        
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
            # Fallback to local storage
            try:
                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                unique_id = str(uuid.uuid4())[:8]
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"mapping_{timestamp}_{unique_id}_{original_filename}"
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                image_url = f"/api/images/{filename}"
                print(f"⚠️ Using local storage fallback for mapping image: {image_url}")
            except Exception as local_error:
                print(f"❌ Local storage fallback failed: {local_error}")
                return jsonify({'error': 'Failed to upload image'}), 500
        
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

# ============ ADDED MAPPING IMAGES CRUD ROUTES ============

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
    """Delete a mapping image record and the actual file"""
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

# ============ SERVE LOCAL IMAGES (FALLBACK) ============

@app.route('/api/images/<path:filename>')
def serve_image(filename):
    """Serve locally stored images (fallback when Supabase is unavailable)"""
    try:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.exists(filepath):
            return send_file(filepath, mimetype='image/png')
        else:
            return jsonify({'error': 'Image not found'}), 404
    except Exception as e:
        print(f"❌ Serve image error: {e}")
        return jsonify({'error': str(e)}), 404

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
            try:
                abs_path = os.path.join(os.getcwd(), directory)
                if not os.path.exists(abs_path):
                    os.makedirs(abs_path, exist_ok=True)
                    print(f"📁 Created directory (absolute path): {abs_path}")
            except Exception as e2:
                print(f"❌ Failed to create directory {directory}: {e2}")

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
        
        tables = ['financial_years', 'schools', 'departments', 'utility_bills', 'utility_accounts', 'backup_metadata', 'sut_office_expenses', 'mapping_images']
        
        for table in tables:
            try:
                supabase.table(table).select("id").limit(1).execute()
                print(f"✅ {table.capitalize()} table exists")
            except Exception as e:
                print(f"⚠️ {table} table not found or error accessing it")
                print(f"ℹ️ Please create the '{table}' table manually in Supabase")
                
    except Exception as e:
        print(f"⚠️ Database check warning: {e}")

# ============ BACKUP FUNCTIONS ============

def get_all_data_with_order():
    """Fetch all data from Supabase tables preserving the correct order"""
    data = {}
    
    try:
        # Get financial years ordered by start_year descending
        response = supabase.table("financial_years").select("*").order("start_year", desc=True).execute()
        data['financial_years'] = response.data if response.data else []
        
        # Get schools ordered by cluster_number, then by display_order, then by id
        response = supabase.table("schools").select("*").order("cluster_number").order("display_order").order("id").execute()
        schools = response.data if response.data else []
        
        # Process schools to parse JSON accounts
        for school in schools:
            if school.get('water_accounts') and isinstance(school['water_accounts'], str):
                try:
                    school['water_accounts'] = json.loads(school['water_accounts'])
                except:
                    pass
            if school.get('electricity_accounts') and isinstance(school['electricity_accounts'], str):
                try:
                    school['electricity_accounts'] = json.loads(school['electricity_accounts'])
                except:
                    pass
            if school.get('telephone_accounts') and isinstance(school['telephone_accounts'], str):
                try:
                    school['telephone_accounts'] = json.loads(school['telephone_accounts'])
                except:
                    pass
        
        data['schools'] = schools
        
        # Get departments ordered by display_order, then by department_name, then by id
        response = supabase.table("departments").select("*").order("display_order").order("department_name").order("id").execute()
        departments = response.data if response.data else []
        
        # Process departments to parse JSON accounts
        for dept in departments:
            if dept.get('water_accounts') and isinstance(dept['water_accounts'], str):
                try:
                    dept['water_accounts'] = json.loads(dept['water_accounts'])
                except:
                    pass
            if dept.get('electricity_accounts') and isinstance(dept['electricity_accounts'], str):
                try:
                    dept['electricity_accounts'] = json.loads(dept['electricity_accounts'])
                except:
                    pass
            if dept.get('telephone_accounts') and isinstance(dept['telephone_accounts'], str):
                try:
                    dept['telephone_accounts'] = json.loads(dept['telephone_accounts'])
                except:
                    pass
        
        data['departments'] = departments
        
        # Get utility bills ordered by year, month, entity_type, entity_name
        response = supabase.table("utility_bills").select("*").order("year", desc=True).order("month", desc=True).order("entity_type").order("entity_name").execute()
        bills = response.data if response.data else []
        
        # Parse JSON fields in bills
        for bill in bills:
            if bill.get('bill_image') and isinstance(bill['bill_image'], str):
                try:
                    bill['bill_image'] = json.loads(bill['bill_image']) if bill['bill_image'] else None
                except:
                    pass
        
        data['utility_bills'] = bills
        
        # Get SUT Office expenses ordered by year, month
        try:
            response = supabase.table("sut_office_expenses").select("*").order("year", desc=True).order("month", desc=True).execute()
            data['sut_office_expenses'] = response.data if response.data else []
        except:
            data['sut_office_expenses'] = []
        
        return data
        
    except Exception as e:
        print(f"❌ Error fetching data for backup: {e}")
        raise

def restore_all_data(backup_data):
    """Restore all data from backup, preserving order"""
    errors = []
    
    try:
        # Clear existing data in correct order (delete bills first due to foreign keys)
        print("🗑️ Clearing existing data...")
        
        # Delete utility bills first
        try:
            supabase.table("utility_bills").delete().neq("id", 0).execute()
            print("✅ Cleared utility_bills")
        except Exception as e:
            errors.append(f"Failed to clear utility_bills: {str(e)}")
        
        # Delete SUT office expenses
        try:
            supabase.table("sut_office_expenses").delete().neq("id", 0).execute()
            print("✅ Cleared sut_office_expenses")
        except:
            pass
        
        # Delete departments
        try:
            supabase.table("departments").delete().neq("id", 0).execute()
            print("✅ Cleared departments")
        except Exception as e:
            errors.append(f"Failed to clear departments: {str(e)}")
        
        # Delete schools
        try:
            supabase.table("schools").delete().neq("id", 0).execute()
            print("✅ Cleared schools")
        except Exception as e:
            errors.append(f"Failed to clear schools: {str(e)}")
        
        # Delete financial years
        try:
            supabase.table("financial_years").delete().neq("id", 0).execute()
            print("✅ Cleared financial_years")
        except Exception as e:
            errors.append(f"Failed to clear financial_years: {str(e)}")
        
        # Restore financial years
        financial_years = backup_data.get('financial_years', [])
        for fy in financial_years:
            fy_copy = {k: v for k, v in fy.items() if k != 'id'}
            try:
                supabase.table("financial_years").insert(fy_copy).execute()
            except Exception as e:
                errors.append(f"Failed to restore financial year: {str(e)}")
        
        # Restore schools
        schools = backup_data.get('schools', [])
        for school in schools:
            school_copy = {k: v for k, v in school.items() if k != 'id'}
            # Convert account arrays back to JSON strings if needed
            if school_copy.get('water_accounts') and isinstance(school_copy['water_accounts'], (list, dict)):
                school_copy['water_accounts'] = json.dumps(school_copy['water_accounts'])
            if school_copy.get('electricity_accounts') and isinstance(school_copy['electricity_accounts'], (list, dict)):
                school_copy['electricity_accounts'] = json.dumps(school_copy['electricity_accounts'])
            if school_copy.get('telephone_accounts') and isinstance(school_copy['telephone_accounts'], (list, dict)):
                school_copy['telephone_accounts'] = json.dumps(school_copy['telephone_accounts'])
            try:
                supabase.table("schools").insert(school_copy).execute()
            except Exception as e:
                errors.append(f"Failed to restore school {school.get('name')}: {str(e)}")
        
        # Restore departments
        departments = backup_data.get('departments', [])
        for dept in departments:
            dept_copy = {k: v for k, v in dept.items() if k != 'id'}
            if dept_copy.get('water_accounts') and isinstance(dept_copy['water_accounts'], (list, dict)):
                dept_copy['water_accounts'] = json.dumps(dept_copy['water_accounts'])
            if dept_copy.get('electricity_accounts') and isinstance(dept_copy['electricity_accounts'], (list, dict)):
                dept_copy['electricity_accounts'] = json.dumps(dept_copy['electricity_accounts'])
            if dept_copy.get('telephone_accounts') and isinstance(dept_copy['telephone_accounts'], (list, dict)):
                dept_copy['telephone_accounts'] = json.dumps(dept_copy['telephone_accounts'])
            try:
                supabase.table("departments").insert(dept_copy).execute()
            except Exception as e:
                errors.append(f"Failed to restore department {dept.get('name')}: {str(e)}")
        
        # Restore utility bills
        bills = backup_data.get('utility_bills', [])
        for bill in bills:
            bill_copy = {k: v for k, v in bill.items() if k != 'id'}
            if bill_copy.get('bill_image') and isinstance(bill_copy['bill_image'], (list, dict)):
                bill_copy['bill_image'] = json.dumps(bill_copy['bill_image'])
            try:
                supabase.table("utility_bills").insert(bill_copy).execute()
            except Exception as e:
                errors.append(f"Failed to restore bill for {bill.get('entity_name')}: {str(e)}")
        
        # Restore SUT office expenses
        sut_expenses = backup_data.get('sut_office_expenses', [])
        for expense in sut_expenses:
            expense_copy = {k: v for k, v in expense.items() if k != 'id'}
            try:
                supabase.table("sut_office_expenses").insert(expense_copy).execute()
            except Exception as e:
                errors.append(f"Failed to restore SUT expense: {str(e)}")
        
        return {'success': len(errors) == 0, 'errors': errors}
        
    except Exception as e:
        return {'success': False, 'errors': [str(e)]}

# ============ BACKUP API ROUTES ============

@app.route('/api/backup/all', methods=['GET'])
def backup_all_data():
    """Create a complete backup of all data with preserved order"""
    try:
        print("💾 GET /api/backup/all called")
        
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        
        # Ensure backups directory exists
        backup_path = app.config['BACKUP_FOLDER']
        if not os.path.exists(backup_path):
            os.makedirs(backup_path, exist_ok=True)
            print(f"📁 Created backups directory: {backup_path}")
        
        # Fetch all data with preserved order
        data = get_all_data_with_order()
        
        # Create backup metadata
        backup_data = {
            'version': '1.0',
            'created_at': datetime.now().isoformat(),
            'description': 'UKA BILL System Backup',
            'order_preserved': True,
            'records_count': {
                'financial_years': len(data.get('financial_years', [])),
                'schools': len(data.get('schools', [])),
                'departments': len(data.get('departments', [])),
                'utility_bills': len(data.get('utility_bills', [])),
                'sut_office_expenses': len(data.get('sut_office_expenses', []))
            },
            'data': data
        }
        
        # Convert to JSON
        backup_json = json.dumps(backup_data, indent=2, default=str)
        
        # Generate filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"uka_bill_backup_{timestamp}.json"
        
        # Save to backups folder
        backup_filepath = os.path.join(backup_path, filename)
        with open(backup_filepath, 'w', encoding='utf-8') as f:
            f.write(backup_json)
        
        print(f"✅ Backup created and saved to: {backup_filepath}")
        
        return jsonify({
            'success': True,
            'message': 'Backup created successfully! Order preserved.',
            'backup_filename': filename,
            'backup_content': backup_json,
            'records_count': backup_data['records_count']
        })
        
    except Exception as e:
        print(f"❌ Backup error: {e}")
        print(traceback.format_exc())
        return jsonify({'error': f'Backup failed: {str(e)}'}), 500

@app.route('/api/backup/download-direct', methods=['GET'])
def download_backup_direct():
    """Direct download of backup without storing metadata"""
    try:
        print("💾 GET /api/backup/download-direct called")
        
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        
        data = get_all_data_with_order()
        
        backup_data = {
            'version': '1.0',
            'created_at': datetime.now().isoformat(),
            'description': 'UKA BILL System Backup',
            'order_preserved': True,
            'records_count': {
                'financial_years': len(data.get('financial_years', [])),
                'schools': len(data.get('schools', [])),
                'departments': len(data.get('departments', [])),
                'utility_bills': len(data.get('utility_bills', [])),
                'sut_office_expenses': len(data.get('sut_office_expenses', []))
            },
            'data': data
        }
        
        backup_json = json.dumps(backup_data, indent=2, default=str)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"uka_bill_backup_{timestamp}.json"
        
        response = make_response(backup_json)
        response.headers['Content-Type'] = 'application/json'
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'
        
        return response
        
    except Exception as e:
        print(f"❌ Direct download error: {e}")
        return jsonify({'error': f'Download failed: {str(e)}'}), 500

@app.route('/api/backup/list', methods=['GET'])
def list_backups():
    """List all available backup files"""
    try:
        print("💾 GET /api/backup/list called")
        
        backup_folder = app.config['BACKUP_FOLDER']
        backups = []
        
        # Ensure backup folder exists
        if not os.path.exists(backup_folder):
            os.makedirs(backup_folder, exist_ok=True)
            print(f"📁 Created backups directory: {backup_folder}")
        
        if os.path.exists(backup_folder):
            for filename in os.listdir(backup_folder):
                if filename.endswith('.json'):
                    filepath = os.path.join(backup_folder, filename)
                    stat = os.stat(filepath)
                    
                    # Try to read backup metadata
                    records_count = {}
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            backup_data = json.load(f)
                            records_count = backup_data.get('records_count', {})
                    except:
                        pass
                    
                    backups.append({
                        'filename': filename,
                        'created': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        'size': stat.st_size,
                        'size_formatted': format_file_size(stat.st_size),
                        'records_count': records_count
                    })
        
        # Sort by creation date (newest first)
        backups.sort(key=lambda x: x['created'], reverse=True)
        
        return jsonify({
            'success': True,
            'backups': backups,
            'count': len(backups)
        })
        
    except Exception as e:
        print(f"❌ List backups error: {e}")
        return jsonify({'error': f'Failed to list backups: {str(e)}'}), 500

@app.route('/api/backup/download/<path:filename>', methods=['GET'])
def download_backup(filename):
    """Download a specific backup file"""
    try:
        print(f"💾 GET /api/backup/download/{filename} called")
        
        # Security: prevent path traversal
        filename = secure_filename(filename)
        filepath = os.path.join(app.config['BACKUP_FOLDER'], filename)
        
        if not os.path.exists(filepath):
            return jsonify({'error': 'Backup file not found'}), 404
        
        return send_file(
            filepath,
            as_attachment=True,
            download_name=filename,
            mimetype='application/json'
        )
        
    except Exception as e:
        print(f"❌ Download backup error: {e}")
        return jsonify({'error': f'Download failed: {str(e)}'}), 500

@app.route('/api/backup/delete/<path:filename>', methods=['DELETE'])
def delete_backup(filename):
    """Delete a backup file"""
    try:
        print(f"💾 DELETE /api/backup/delete/{filename} called")
        
        filename = secure_filename(filename)
        filepath = os.path.join(app.config['BACKUP_FOLDER'], filename)
        
        if not os.path.exists(filepath):
            return jsonify({'error': 'Backup file not found'}), 404
        
        os.remove(filepath)
        
        return jsonify({
            'success': True,
            'message': f'Backup file {filename} deleted successfully'
        })
        
    except Exception as e:
        print(f"❌ Delete backup error: {e}")
        return jsonify({'error': f'Delete failed: {str(e)}'}), 500

@app.route('/api/backup/restore', methods=['POST'])
def restore_backup():
    """Restore data from a backup file"""
    try:
        print("💾 POST /api/backup/restore called")
        
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        
        if 'backup_file' not in request.files:
            return jsonify({'error': 'No backup file provided'}), 400
        
        file = request.files['backup_file']
        
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not file.filename.endswith('.json'):
            return jsonify({'error': 'Only JSON backup files are supported'}), 400
        
        # Read and parse the backup file
        backup_content = file.read().decode('utf-8')
        backup_data = json.loads(backup_content)
        
        # Extract data from backup
        data_to_restore = backup_data.get('data', backup_data)
        
        # Perform restore
        result = restore_all_data(data_to_restore)
        
        if result['success']:
            return jsonify({
                'success': True,
                'message': 'Data restored successfully! Order preserved.',
                'order_preserved': True
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Restore completed with errors',
                'errors': result['errors']
            }), 500
        
    except json.JSONDecodeError as e:
        print(f"❌ Restore JSON decode error: {e}")
        return jsonify({'error': 'Invalid backup file format'}), 400
    except Exception as e:
        print(f"❌ Restore backup error: {e}")
        print(traceback.format_exc())
        return jsonify({'error': f'Restore failed: {str(e)}'}), 500

# ============ EXPORT FUNCTIONS ============

@app.route('/api/export-data', methods=['GET'])
def export_data_single():
    """Export single data type as CSV"""
    try:
        export_type = request.args.get('type', '')
        format_type = request.args.get('format', 'csv')
        
        if not export_type:
            return jsonify({'error': 'No export type specified'}), 400
        
        if export_type == 'schools':
            return export_schools_csv()
        elif export_type == 'departments':
            return export_departments_csv()
        elif export_type == 'water_bills':
            return export_water_bills_csv()
        elif export_type == 'electricity_bills':
            return export_electricity_bills_csv()
        elif export_type == 'telephone_bills':
            return export_telephone_bills_csv()
        else:
            return jsonify({'error': 'Invalid export type'}), 400
            
    except Exception as e:
        print(f"❌ Export error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/export-multiple', methods=['POST'])
def export_multiple():
    """Export multiple data types as ZIP file"""
    try:
        data = request.get_json()
        exports = data.get('exports', [])
        format_type = data.get('format', 'csv')
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for export in exports:
                export_type = export.get('type')
                
                if export_type == 'schools':
                    csv_content = export_schools_csv_to_string()
                    zip_file.writestr(f"schools_{timestamp}.csv", csv_content)
                elif export_type == 'departments':
                    csv_content = export_departments_csv_to_string()
                    zip_file.writestr(f"departments_{timestamp}.csv", csv_content)
                elif export_type == 'water_bills':
                    csv_content = export_water_bills_csv_to_string()
                    zip_file.writestr(f"water_bills_{timestamp}.csv", csv_content)
                elif export_type == 'electricity_bills':
                    csv_content = export_electricity_bills_csv_to_string()
                    zip_file.writestr(f"electricity_bills_{timestamp}.csv", csv_content)
                elif export_type == 'telephone_bills':
                    csv_content = export_telephone_bills_csv_to_string()
                    zip_file.writestr(f"telephone_bills_{timestamp}.csv", csv_content)
        
        zip_buffer.seek(0)
        
        response = make_response(zip_buffer.getvalue())
        response.headers['Content-Type'] = 'application/zip'
        response.headers['Content-Disposition'] = f'attachment; filename=export_{timestamp}.zip'
        
        return response
        
    except Exception as e:
        print(f"❌ Multiple export error: {e}")
        return jsonify({'error': str(e)}), 500

def export_schools_csv():
    """Export schools as CSV"""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Name', 'Cluster Number', 'School Number', 'BMO Name', 'BMO Phone', 'Address', 
                     'Water Account', 'Water Meter', 'Electricity Account', 'Electricity Meter', 
                     'Telephone Account', 'Telephone Number', 'Notes'])
    
    response = supabase.table("schools").select("*").order("cluster_number").order("display_order").order("name").execute()
    schools = response.data if response.data else []
    
    for school in schools:
        writer.writerow([
            school.get('id', ''),
            school.get('name', ''),
            school.get('cluster_number', ''),
            school.get('school_number', ''),
            school.get('bmo_name', ''),
            school.get('bmo_phone', ''),
            school.get('address', ''),
            school.get('water_account', ''),
            school.get('water_meter', ''),
            school.get('electricity_account', ''),
            school.get('electricity_meter', ''),
            school.get('telephone_account', ''),
            school.get('telephone_number', ''),
            school.get('notes', '')
        ])
    
    output.seek(0)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"schools_export_{timestamp}.csv"
    
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    response.headers['Content-Disposition'] = f'attachment; filename={filename}'
    return response

def export_departments_csv():
    """Export departments as CSV"""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Unit Name', 'Division Name', 'Department Name', 'Hotline Numbers', 'Address', 
                     'Water Account', 'Water Meter', 'Electricity Account', 'Electricity Meter', 
                     'Telephone Account', 'Telephone Number', 'Notes'])
    
    response = supabase.table("departments").select("*").order("display_order").order("department_name").order("id").execute()
    departments = response.data if response.data else []
    
    for dept in departments:
        writer.writerow([
            dept.get('id', ''),
            dept.get('unit_name', ''),
            dept.get('division_name', ''),
            dept.get('department_name', ''),
            dept.get('hotline_numbers', ''),
            dept.get('address', ''),
            dept.get('water_account', ''),
            dept.get('water_meter', ''),
            dept.get('electricity_account', ''),
            dept.get('electricity_meter', ''),
            dept.get('telephone_account', ''),
            dept.get('telephone_number', ''),
            dept.get('notes', '')
        ])
    
    output.seek(0)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"departments_export_{timestamp}.csv"
    
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    response.headers['Content-Disposition'] = f'attachment; filename={filename}'
    return response

def export_water_bills_csv():
    """Export water bills as CSV"""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Entity Type', 'Entity Name', 'Account Number', 'Meter Number', 
                     'Consumption (m³)', 'Current Charges', 'Amount Paid', 'Month', 'Year', 'Notes'])
    
    response = supabase.table("utility_bills").select("*").eq("utility_type", "water").order("year", desc=True).order("month", desc=True).execute()
    bills = response.data if response.data else []
    
    for bill in bills:
        writer.writerow([
            bill.get('id', ''),
            bill.get('entity_type', ''),
            bill.get('entity_name', ''),
            bill.get('account_number', ''),
            bill.get('meter_number', ''),
            bill.get('consumption_m3', ''),
            bill.get('current_charges', 0),
            bill.get('amount_paid', 0),
            bill.get('month', ''),
            bill.get('year', ''),
            bill.get('notes', '')
        ])
    
    output.seek(0)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"water_bills_export_{timestamp}.csv"
    
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    response.headers['Content-Disposition'] = f'attachment; filename={filename}'
    return response

def export_electricity_bills_csv():
    """Export electricity bills as CSV"""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Entity Type', 'Entity Name', 'Account Number', 'Meter Number', 
                     'Consumption (kWh)', 'Current Charges', 'Amount Paid', 'Month', 'Year', 'Notes'])
    
    response = supabase.table("utility_bills").select("*").eq("utility_type", "electricity").order("year", desc=True).order("month", desc=True).execute()
    bills = response.data if response.data else []
    
    for bill in bills:
        writer.writerow([
            bill.get('id', ''),
            bill.get('entity_type', ''),
            bill.get('entity_name', ''),
            bill.get('account_number', ''),
            bill.get('meter_number', ''),
            bill.get('consumption_kwh', ''),
            bill.get('current_charges', 0),
            bill.get('amount_paid', 0),
            bill.get('month', ''),
            bill.get('year', ''),
            bill.get('notes', '')
        ])
    
    output.seek(0)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"electricity_bills_export_{timestamp}.csv"
    
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    response.headers['Content-Disposition'] = f'attachment; filename={filename}'
    return response

def export_telephone_bills_csv():
    """Export telephone bills as CSV"""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Entity Type', 'Entity Name', 'Account Number', 'Phone Number', 
                     'Bill Number', 'Current Charges', 'Amount Paid', 'Month', 'Year', 'Notes'])
    
    response = supabase.table("utility_bills").select("*").eq("utility_type", "telephone").order("year", desc=True).order("month", desc=True).execute()
    bills = response.data if response.data else []
    
    for bill in bills:
        writer.writerow([
            bill.get('id', ''),
            bill.get('entity_type', ''),
            bill.get('entity_name', ''),
            bill.get('account_number', ''),
            bill.get('phone_number', ''),
            bill.get('meter_number', ''),
            bill.get('current_charges', 0),
            bill.get('amount_paid', 0),
            bill.get('month', ''),
            bill.get('year', ''),
            bill.get('notes', '')
        ])
    
    output.seek(0)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"telephone_bills_export_{timestamp}.csv"
    
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    response.headers['Content-Disposition'] = f'attachment; filename={filename}'
    return response

def export_schools_csv_to_string():
    """Export schools to CSV string"""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Name', 'Cluster Number', 'School Number', 'BMO Name', 'BMO Phone', 'Address', 
                     'Water Account', 'Water Meter', 'Electricity Account', 'Electricity Meter', 
                     'Telephone Account', 'Telephone Number', 'Notes'])
    
    response = supabase.table("schools").select("*").order("cluster_number").order("display_order").order("name").execute()
    schools = response.data if response.data else []
    
    for school in schools:
        writer.writerow([
            school.get('id', ''),
            school.get('name', ''),
            school.get('cluster_number', ''),
            school.get('school_number', ''),
            school.get('bmo_name', ''),
            school.get('bmo_phone', ''),
            school.get('address', ''),
            school.get('water_account', ''),
            school.get('water_meter', ''),
            school.get('electricity_account', ''),
            school.get('electricity_meter', ''),
            school.get('telephone_account', ''),
            school.get('telephone_number', ''),
            school.get('notes', '')
        ])
    
    return output.getvalue()

def export_departments_csv_to_string():
    """Export departments to CSV string"""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Unit Name', 'Division Name', 'Department Name', 'Hotline Numbers', 'Address', 
                     'Water Account', 'Water Meter', 'Electricity Account', 'Electricity Meter', 
                     'Telephone Account', 'Telephone Number', 'Notes'])
    
    response = supabase.table("departments").select("*").order("display_order").order("department_name").order("id").execute()
    departments = response.data if response.data else []
    
    for dept in departments:
        writer.writerow([
            dept.get('id', ''),
            dept.get('unit_name', ''),
            dept.get('division_name', ''),
            dept.get('department_name', ''),
            dept.get('hotline_numbers', ''),
            dept.get('address', ''),
            dept.get('water_account', ''),
            dept.get('water_meter', ''),
            dept.get('electricity_account', ''),
            dept.get('electricity_meter', ''),
            dept.get('telephone_account', ''),
            dept.get('telephone_number', ''),
            dept.get('notes', '')
        ])
    
    return output.getvalue()

def export_water_bills_csv_to_string():
    """Export water bills to CSV string"""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Entity Type', 'Entity Name', 'Account Number', 'Meter Number', 
                     'Consumption (m³)', 'Current Charges', 'Amount Paid', 'Month', 'Year', 'Notes'])
    
    response = supabase.table("utility_bills").select("*").eq("utility_type", "water").order("year", desc=True).order("month", desc=True).execute()
    bills = response.data if response.data else []
    
    for bill in bills:
        writer.writerow([
            bill.get('id', ''),
            bill.get('entity_type', ''),
            bill.get('entity_name', ''),
            bill.get('account_number', ''),
            bill.get('meter_number', ''),
            bill.get('consumption_m3', ''),
            bill.get('current_charges', 0),
            bill.get('amount_paid', 0),
            bill.get('month', ''),
            bill.get('year', ''),
            bill.get('notes', '')
        ])
    
    return output.getvalue()

def export_electricity_bills_csv_to_string():
    """Export electricity bills to CSV string"""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Entity Type', 'Entity Name', 'Account Number', 'Meter Number', 
                     'Consumption (kWh)', 'Current Charges', 'Amount Paid', 'Month', 'Year', 'Notes'])
    
    response = supabase.table("utility_bills").select("*").eq("utility_type", "electricity").order("year", desc=True).order("month", desc=True).execute()
    bills = response.data if response.data else []
    
    for bill in bills:
        writer.writerow([
            bill.get('id', ''),
            bill.get('entity_type', ''),
            bill.get('entity_name', ''),
            bill.get('account_number', ''),
            bill.get('meter_number', ''),
            bill.get('consumption_kwh', ''),
            bill.get('current_charges', 0),
            bill.get('amount_paid', 0),
            bill.get('month', ''),
            bill.get('year', ''),
            bill.get('notes', '')
        ])
    
    return output.getvalue()

def export_telephone_bills_csv_to_string():
    """Export telephone bills to CSV string"""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Entity Type', 'Entity Name', 'Account Number', 'Phone Number', 
                     'Bill Number', 'Current Charges', 'Amount Paid', 'Month', 'Year', 'Notes'])
    
    response = supabase.table("utility_bills").select("*").eq("utility_type", "telephone").order("year", desc=True).order("month", desc=True).execute()
    bills = response.data if response.data else []
    
    for bill in bills:
        writer.writerow([
            bill.get('id', ''),
            bill.get('entity_type', ''),
            bill.get('entity_name', ''),
            bill.get('account_number', ''),
            bill.get('phone_number', ''),
            bill.get('meter_number', ''),
            bill.get('current_charges', 0),
            bill.get('amount_paid', 0),
            bill.get('month', ''),
            bill.get('year', ''),
            bill.get('notes', '')
        ])
    
    return output.getvalue()

def format_file_size(size):
    """Format file size in human readable format"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"

# ============ BATCH UPDATE API (FAST PARALLEL SAVING) ============

@app.route('/api/utility-bills/batch-update', methods=['POST'])
def batch_update_utility_bills():
    """Update multiple utility bills in parallel for faster saving"""
    try:
        print("💡 POST /api/utility-bills/batch-update called")
        
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        
        data = request.get_json()
        bills = data.get('bills', [])
        
        if not bills:
            return jsonify({'error': 'No bills provided'}), 400
        
        print(f"📦 Batch updating {len(bills)} bills")
        
        success_count = 0
        error_count = 0
        
        for bill_data in bills:
            try:
                # Check if bill exists
                query = supabase.table("utility_bills").select("*")\
                    .eq("utility_type", bill_data.get('utility_type'))\
                    .eq("entity_type", bill_data.get('entity_type'))\
                    .eq("entity_id", int(bill_data.get('entity_id')))\
                    .eq("month", int(bill_data.get('month')))\
                    .eq("year", int(bill_data.get('year')))
                
                account_number = bill_data.get('account_number', '')
                if account_number and account_number != '—' and account_number != '':
                    query = query.eq("account_number", account_number)
                
                meter_number = bill_data.get('meter_number', '')
                if meter_number and meter_number != '—' and meter_number != '':
                    query = query.eq("meter_number", meter_number)
                
                phone_number = bill_data.get('phone_number', '')
                if phone_number and phone_number != '—' and phone_number != '':
                    query = query.eq("phone_number", phone_number)
                
                existing = query.execute()
                
                update_data = {
                    "current_charges": float(bill_data.get('current_charges', 0)),
                    "unsettled_charges": float(bill_data.get('unsettled_charges', 0)),
                    "amount_paid": float(bill_data.get('amount_paid', 0))
                }
                
                if bill_data.get('consumption_m3') is not None:
                    update_data["consumption_m3"] = float(bill_data.get('consumption_m3'))
                if bill_data.get('consumption_kwh') is not None:
                    update_data["consumption_kwh"] = float(bill_data.get('consumption_kwh'))
                if bill_data.get('notes') is not None:
                    update_data["notes"] = bill_data.get('notes')
                if bill_data.get('meter_number') is not None and bill_data.get('meter_number') != '—':
                    update_data["meter_number"] = bill_data.get('meter_number')
                
                if existing.data and len(existing.data) > 0:
                    # Update existing bill
                    bill_id = existing.data[0]['id']
                    response = supabase.table("utility_bills").update(update_data).eq("id", bill_id).execute()
                    if response.data:
                        success_count += 1
                    else:
                        error_count += 1
                else:
                    # Get entity name
                    entity_name = ""
                    if bill_data.get('entity_type') == 'school':
                        school_resp = supabase.table("schools").select("name").eq("id", bill_data.get('entity_id')).execute()
                        if school_resp.data:
                            entity_name = school_resp.data[0]['name']
                    elif bill_data.get('entity_type') == 'department':
                        dept_resp = supabase.table("departments").select("unit_name").eq("id", bill_data.get('entity_id')).execute()
                        if dept_resp.data:
                            entity_name = dept_resp.data[0].get('unit_name', '')
                    
                    # Create new bill
                    new_bill = {
                        "utility_type": bill_data.get('utility_type'),
                        "entity_type": bill_data.get('entity_type'),
                        "entity_id": int(bill_data.get('entity_id')),
                        "entity_name": entity_name,
                        "account_number": bill_data.get('account_number', ''),
                        "meter_number": bill_data.get('meter_number', ''),
                        "phone_number": bill_data.get('phone_number', ''),
                        "current_charges": float(bill_data.get('current_charges', 0)),
                        "unsettled_charges": float(bill_data.get('unsettled_charges', 0)),
                        "amount_paid": float(bill_data.get('amount_paid', 0)),
                        "month": int(bill_data.get('month')),
                        "year": int(bill_data.get('year')),
                        "notes": bill_data.get('notes', ''),
                        "created_at": datetime.now().isoformat()
                    }
                    
                    if bill_data.get('consumption_m3') is not None:
                        new_bill["consumption_m3"] = float(bill_data.get('consumption_m3'))
                    if bill_data.get('consumption_kwh') is not None:
                        new_bill["consumption_kwh"] = float(bill_data.get('consumption_kwh'))
                    
                    response = supabase.table("utility_bills").insert(new_bill).execute()
                    if response.data:
                        success_count += 1
                    else:
                        error_count += 1
                        
            except Exception as e:
                error_count += 1
                print(f"Error processing bill: {e}")
        
        print(f"📊 Batch update result: {success_count} success, {error_count} failed")
        
        return jsonify({
            'success': error_count == 0,
            'success_count': success_count,
            'error_count': error_count
        })
        
    except Exception as e:
        print(f"❌ Batch update error: {e}")
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

# ============ BUDGET MANAGEMENT API ============

@app.route('/api/budgets', methods=['GET'])
def get_budgets():
    """Get all financial years/budgets"""
    try:
        print("📅 GET /api/budgets called")
        
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        
        response = supabase.table("financial_years").select("*").order("start_year", desc=True).execute()
        return jsonify(response.data if response.data else [])
        
    except Exception as e:
        print(f"❌ Budgets GET error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/budgets', methods=['POST'])
def create_budget():
    """Create a new financial year budget"""
    try:
        print("📅 POST /api/budgets called")
        
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        
        data = request.get_json()
        print(f"📅 Received budget data: {data}")
        
        # Validate required fields
        required_fields = ['financial_year', 'start_year', 'end_year']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        budget_data = {
            "financial_year": data.get('financial_year'),
            "start_year": int(data.get('start_year')),
            "end_year": int(data.get('end_year')),
            "total_allocated": float(data.get('total_allocated', 0)),
            "water_allocated": float(data.get('water_allocated', 0)),
            "electricity_allocated": float(data.get('electricity_allocated', 0)),
            "telephone_allocated": float(data.get('telephone_allocated', 0)),
            "sut_office_allocated": float(data.get('sut_office_allocated', 0)),
            "created_at": datetime.now().isoformat()
        }
        
        response = supabase.table("financial_years").insert(budget_data).execute()
        
        if response.data:
            print("✅ Budget created successfully")
            return jsonify({
                'success': True,
                'message': 'Budget created successfully',
                'budget': response.data[0]
            })
        else:
            return jsonify({'error': 'Failed to create budget'}), 500
            
    except Exception as e:
        print(f"❌ Budget POST error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/budgets/<int:budget_id>', methods=['PUT'])
def update_budget(budget_id):
    """Update an existing budget"""
    try:
        print(f"📅 PUT /api/budgets/{budget_id} called")
        
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        
        data = request.get_json()
        
        budget_data = {}
        
        if 'financial_year' in data:
            budget_data['financial_year'] = data['financial_year']
        if 'start_year' in data:
            budget_data['start_year'] = int(data['start_year'])
        if 'end_year' in data:
            budget_data['end_year'] = int(data['end_year'])
        if 'total_allocated' in data:
            budget_data['total_allocated'] = float(data['total_allocated'])
        if 'water_allocated' in data:
            budget_data['water_allocated'] = float(data['water_allocated'])
        if 'electricity_allocated' in data:
            budget_data['electricity_allocated'] = float(data['electricity_allocated'])
        if 'telephone_allocated' in data:
            budget_data['telephone_allocated'] = float(data['telephone_allocated'])
        if 'sut_office_allocated' in data:
            budget_data['sut_office_allocated'] = float(data['sut_office_allocated'])
        
        response = supabase.table("financial_years").update(budget_data).eq("id", budget_id).execute()
        
        if response.data:
            print("✅ Budget updated successfully")
            return jsonify({
                'success': True,
                'message': 'Budget updated successfully',
                'budget': response.data[0]
            })
        else:
            return jsonify({'error': 'Failed to update budget'}), 500
            
    except Exception as e:
        print(f"❌ Budget PUT error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/budgets/<int:budget_id>', methods=['DELETE'])
def delete_budget(budget_id):
    """Delete a budget"""
    try:
        print(f"📅 DELETE /api/budgets/{budget_id} called")
        
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        
        # Check if there are any bills associated with this financial year
        budget = supabase.table("financial_years").select("*").eq("id", budget_id).execute()
        
        if budget.data and len(budget.data) > 0:
            start_year = budget.data[0].get('start_year')
            end_year = budget.data[0].get('end_year')
            
            # Check for bills in this financial year
            bills = supabase.table("utility_bills").select("*").eq("year", start_year).execute()
            if bills.data and len(bills.data) > 0:
                return jsonify({
                    'error': f'Cannot delete budget for {start_year}-{end_year} because there are utility bills associated with it.'
                }), 400
        
        response = supabase.table("financial_years").delete().eq("id", budget_id).execute()
        
        if response.data:
            return jsonify({
                'success': True,
                'message': 'Budget deleted successfully'
            })
        else:
            return jsonify({'error': 'Failed to delete budget'}), 500
            
    except Exception as e:
        print(f"❌ Budget DELETE error: {e}")
        return jsonify({'error': str(e)}), 500

# ============ PAYMENT SUMMARY API ============

@app.route('/api/payment-summary', methods=['GET'])
def get_payment_summary():
    """Get payment summary for current financial year"""
    try:
        print("💰 GET /api/payment-summary called")
        
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        
        # Get current financial year
        current_date = datetime.now()
        current_year = current_date.year
        current_month = current_date.month
        
        if current_month >= 4:
            start_year = current_year
            end_year = current_year + 1
        else:
            start_year = current_year - 1
            end_year = current_year
        
        # Get budget for current financial year
        budget_response = supabase.table("financial_years").select("*").eq("start_year", start_year).eq("end_year", end_year).execute()
        budget = budget_response.data[0] if budget_response.data else None
        
        # Calculate total payments made (amount_paid from utility_bills)
        payments_response = supabase.table("utility_bills").select("*").execute()
        total_paid_water = 0
        total_paid_electricity = 0
        total_paid_telephone = 0
        
        if payments_response.data:
            for bill in payments_response.data:
                bill_year = bill.get('year')
                if bill_year == start_year or bill_year == end_year:
                    if bill.get('utility_type') == 'water':
                        total_paid_water += float(bill.get('amount_paid', 0) or 0)
                    elif bill.get('utility_type') == 'electricity':
                        total_paid_electricity += float(bill.get('amount_paid', 0) or 0)
                    elif bill.get('utility_type') == 'telephone':
                        total_paid_telephone += float(bill.get('amount_paid', 0) or 0)
        
        # Get SUT Office expenses
        sut_response = supabase.table("sut_office_expenses").select("*").eq("year", start_year).execute()
        sut_total = 0
        if sut_response.data:
            for expense in sut_response.data:
                sut_total += float(expense.get('amount_spent', 0) or 0)
        
        total_paid = total_paid_water + total_paid_electricity + total_paid_telephone + sut_total
        
        return jsonify({
            'success': True,
            'financial_year': f"{start_year}-{end_year}",
            'start_year': start_year,
            'end_year': end_year,
            'budget': budget,
            'payments': {
                'water': total_paid_water,
                'electricity': total_paid_electricity,
                'telephone': total_paid_telephone,
                'sut_office': sut_total,
                'total': total_paid
            }
        })
        
    except Exception as e:
        print(f"❌ Payment summary error: {e}")
        return jsonify({'error': str(e)}), 500

# ============ REMAINING ROUTES ============

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

# ============ ENTITIES API FOR REPORTS ============

@app.route('/api/entities', methods=['GET'])
def get_entities():
    """Get schools or departments for report selection"""
    try:
        print("🔍 GET /api/entities called")
        entity_type = request.args.get('type', 'school')
        
        if not supabase:
            return jsonify([]), 500
        
        if entity_type == 'school':
            response = supabase.table("schools").select("id, name, cluster_number").order("cluster_number").order("display_order").order("name").execute()
            entities = []
            for school in (response.data or []):
                entities.append({
                    'id': school['id'],
                    'name': school['name'],
                    'cluster': school.get('cluster_number', '')
                })
            return jsonify(entities)
        elif entity_type == 'department':
            response = supabase.table("departments").select("id, name, department_name, unit_name").order("display_order").order("department_name").order("id").execute()
            entities = []
            for dept in (response.data or []):
                display_name = dept.get('unit_name') or dept.get('name') or f"Department #{dept['id']}"
                entities.append({
                    'id': dept['id'],
                    'name': display_name,
                    'department_name': dept.get('department_name', '')
                })
            return jsonify(entities)
        else:
            return jsonify([])
            
    except Exception as e:
        print(f"❌ Entities GET error: {e}")
        return jsonify([]), 500

# ============ GENERATE REPORT API ============

@app.route('/api/generate-report', methods=['POST'])
def generate_report():
    """Generate report based on filters"""
    try:
        print("📊 POST /api/generate-report called")
        
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        
        data = request.get_json()
        print(f"📊 Report request data: {data}")
        
        selection_type = data.get('selection_type', 'entityType')
        utility_type = data.get('utility_type', 'all')
        month = data.get('month', 'all')
        year = data.get('year')
        
        # Build query
        query = supabase.table("utility_bills").select("*")
        
        # Filter by utility type
        if utility_type != 'all':
            query = query.eq("utility_type", utility_type)
        
        # Filter by month
        if month != 'all' and month:
            query = query.eq("month", int(month))
        
        # Filter by year
        if year and year != 'all':
            query = query.eq("year", int(year))
        
        # Filter by entity selection
        if selection_type == 'entityType':
            entity_type_filter = data.get('entity_type', 'all')
            if entity_type_filter != 'all':
                query = query.eq("entity_type", entity_type_filter)
        else:
            # Specific entities selected - will filter after fetch
            pass
        
        response = query.execute()
        bills = response.data if response.data else []
        
        # Apply specific entity filtering if needed
        if selection_type == 'specificEntities':
            school_ids = [int(sid) for sid in data.get('school_ids', [])]
            department_ids = [int(did) for did in data.get('department_ids', [])]
            
            filtered_bills = []
            for bill in bills:
                if bill['entity_type'] == 'school' and bill['entity_id'] in school_ids:
                    filtered_bills.append(bill)
                elif bill['entity_type'] == 'department' and bill['entity_id'] in department_ids:
                    filtered_bills.append(bill)
            bills = filtered_bills
        
        # Enrich bills with entity names
        enriched_bills = []
        for bill in bills:
            bill_data = dict(bill)
            
            # Get entity name
            if bill_data['entity_type'] == 'school':
                school_response = supabase.table("schools").select("name").eq("id", bill_data['entity_id']).execute()
                if school_response.data and len(school_response.data) > 0:
                    bill_data['entity_name'] = school_response.data[0]['name']
                else:
                    bill_data['entity_name'] = 'Unknown School'
            elif bill_data['entity_type'] == 'department':
                dept_response = supabase.table("departments").select("name", "unit_name").eq("id", bill_data['entity_id']).execute()
                if dept_response.data and len(dept_response.data) > 0:
                    bill_data['entity_name'] = dept_response.data[0].get('unit_name') or dept_response.data[0]['name'] or 'Unknown Department'
                else:
                    bill_data['entity_name'] = 'Unknown Department'
            else:
                bill_data['entity_name'] = 'Unknown'
            
            # Add telephone number if telephone utility
            if bill_data['utility_type'] == 'telephone' and not bill_data.get('phone_number'):
                bill_data['phone_number'] = bill_data.get('meter_number', '')
            
            # Ensure numeric values are floats
            bill_data['current_charges'] = float(bill_data.get('current_charges') or 0)
            bill_data['late_charges'] = float(bill_data.get('late_charges') or 0)
            bill_data['unsettled_charges'] = float(bill_data.get('unsettled_charges') or 0)
            bill_data['amount_paid'] = float(bill_data.get('amount_paid') or 0)
            
            enriched_bills.append(bill_data)
        
        # Sort by entity name
        enriched_bills.sort(key=lambda x: x.get('entity_name', ''))
        
        print(f"📊 Report generated with {len(enriched_bills)} bills")
        return jsonify(enriched_bills)
        
    except Exception as e:
        print(f"❌ Generate report error: {e}")
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

# ============ FINANCIAL YEARS API ============

@app.route('/api/financial-years', methods=['GET'])
def get_financial_years():
    try:
        print("📅 GET /api/financial-years called")
        
        if not supabase:
            return jsonify({'data': []}), 500
        
        response = supabase.table("financial_years").select("*").order("start_year", desc=True).execute()
        return jsonify(response.data if response.data else [])
        
    except Exception as e:
        print(f"❌ Financial years GET error: {e}")
        return jsonify({'data': []}), 500

@app.route('/api/financial-years', methods=['POST'])
def create_financial_year():
    try:
        print("📅 POST /api/financial-years called")
        
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        
        data = request.get_json()
        print(f"📅 Received financial year data: {data}")
        
        financial_year_data = {
            "financial_year": data.get('financialYear'),
            "start_year": int(data.get('startYear')),
            "end_year": int(data.get('endYear')),
            "total_allocated": float(data.get('totalAllocated', 60000)),
            "water_allocated": float(data.get('waterAllocated', 15000)),
            "electricity_allocated": float(data.get('electricityAllocated', 35000)),
            "telephone_allocated": float(data.get('telephoneAllocated', 10000)),
            "sut_office_allocated": float(data.get('sutOfficeAllocated', 0)),
            "created_at": datetime.now().isoformat()
        }
        
        response = supabase.table("financial_years").insert(financial_year_data).execute()
        
        if response.data:
            print("✅ Financial year created successfully")
            return jsonify({
                'message': 'Financial year created successfully',
                'financial_year': response.data[0]
            })
        else:
            print("❌ Financial year creation failed")
            return jsonify({'error': 'Failed to create financial year'}), 500
            
    except Exception as e:
        print(f"❌ Financial year POST error: {e}")
        print(traceback.format_exc())
        return jsonify({'error': f'Failed to create financial year: {str(e)}'}), 500

@app.route('/api/financial-years/<int:fy_id>', methods=['PUT'])
def update_financial_year(fy_id):
    try:
        print(f"📅 PUT /api/financial-years/{fy_id} called")
        
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        
        data = request.get_json()
        print(f"📅 Update financial year data: {data}")
        
        financial_year_data = {}
        
        if data.get('financialYear'):
            financial_year_data["financial_year"] = data.get('financialYear')
        
        if data.get('startYear') is not None:
            financial_year_data["start_year"] = int(data.get('startYear'))
        
        if data.get('endYear') is not None:
            financial_year_data["end_year"] = int(data.get('endYear'))
        
        if data.get('totalAllocated') is not None:
            financial_year_data["total_allocated"] = float(data.get('totalAllocated', 60000))
        
        if data.get('waterAllocated') is not None:
            financial_year_data["water_allocated"] = float(data.get('waterAllocated', 15000))
        
        if data.get('electricityAllocated') is not None:
            financial_year_data["electricity_allocated"] = float(data.get('electricityAllocated', 35000))
        
        if data.get('telephoneAllocated') is not None:
            financial_year_data["telephone_allocated"] = float(data.get('telephoneAllocated', 10000))
        
        if data.get('sutOfficeAllocated') is not None:
            financial_year_data["sut_office_allocated"] = float(data.get('sutOfficeAllocated', 0))
        
        print(f"📅 Final update data: {financial_year_data}")
        
        response = supabase.table("financial_years").update(financial_year_data).eq("id", fy_id).execute()
        
        if response.data:
            print("✅ Financial year updated successfully")
            return jsonify({
                'message': 'Financial year updated successfully',
                'financial_year': response.data[0]
            })
        else:
            print("❌ Financial year update failed")
            return jsonify({'error': 'Failed to update financial year'}), 500
            
    except Exception as e:
        print(f"❌ Financial year PUT error: {e}")
        print(traceback.format_exc())
        return jsonify({'error': f'Failed to update financial year: {str(e)}'}), 500

@app.route('/api/financial-years/current')
def get_current_financial_year():
    try:
        print("📅 GET /api/financial-years/current called")
        
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        
        current_date = datetime.now()
        current_year = current_date.year
        current_month = current_date.month
        
        if current_month >= 4:
            start_year = current_year
            end_year = current_year + 1
        else:
            start_year = current_year - 1
            end_year = current_year
        
        response = supabase.table("financial_years").select("*").eq("start_year", start_year).eq("end_year", end_year).execute()
        
        if response.data and len(response.data) > 0:
            return jsonify(response.data[0])
        else:
            default_financial_year = {
                "financial_year": f"{start_year}-{end_year}",
                "start_year": start_year,
                "end_year": end_year,
                "total_allocated": 60000.00,
                "water_allocated": 15000.00,
                "electricity_allocated": 35000.00,
                "telephone_allocated": 10000.00,
                "sut_office_allocated": 0.00,
                "created_at": datetime.now().isoformat()
            }
            
            create_response = supabase.table("financial_years").insert(default_financial_year).execute()
            if create_response.data:
                return jsonify(create_response.data[0])
            else:
                return jsonify({'error': 'Failed to create default financial year'}), 500
        
    except Exception as e:
        print(f"❌ Current financial year error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/financial-years/<int:fy_id>', methods=['DELETE'])
def delete_financial_year(fy_id):
    try:
        print(f"📅 DELETE /api/financial-years/{fy_id} called")
        
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        
        response = supabase.table("financial_years").delete().eq("id", fy_id).execute()
        
        if response.data:
            return jsonify({
                'success': True,
                'message': 'Financial year deleted successfully'
            })
        else:
            return jsonify({'error': 'Failed to delete financial year'}), 500
            
    except Exception as e:
        print(f"❌ Financial year DELETE error: {e}")
        return jsonify({'error': f'Failed to delete financial year: {str(e)}'}), 500

# ============ SUT OFFICE API ROUTES ============

@app.route('/api/sut-office-expenses', methods=['GET'])
def get_sut_office_expenses():
    """Get all SUT Office expenses"""
    try:
        print("💰 GET /api/sut-office-expenses called")
        
        if not supabase:
            return jsonify({'data': []}), 500
        
        response = supabase.table("sut_office_expenses").select("*").order("expense_date", desc=True).execute()
        return jsonify(response.data if response.data else [])
        
    except Exception as e:
        print(f"❌ SUT Office expenses GET error: {e}")
        return jsonify({'data': []}), 500

@app.route('/api/sut-office-expenses', methods=['POST'])
def create_sut_office_expense():
    """Create a new SUT Office expense"""
    try:
        print("💰 POST /api/sut-office-expenses called")
        
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        
        data = request.get_json()
        print(f"💰 Received expense data: {data}")
        
        expense_date = data.get('expenseDate')
        if expense_date:
            date_obj = datetime.strptime(expense_date, '%Y-%m-%d')
            month = date_obj.month
            year = date_obj.year
        else:
            month = datetime.now().month
            year = datetime.now().year
            expense_date = datetime.now().strftime('%Y-%m-%d')
        
        expense_data = {
            "expense_date": expense_date,
            "month": month,
            "year": year,
            "amount_spent": float(data.get('amountSpent', 0)),
            "description": data.get('description', ''),
            "remarks": data.get('remarks', ''),
            "created_at": datetime.now().isoformat()
        }
        
        response = supabase.table("sut_office_expenses").insert(expense_data).execute()
        
        if response.data:
            print("✅ SUT Office expense created successfully")
            return jsonify({
                'success': True,
                'message': 'Expense recorded successfully',
                'expense': response.data[0]
            })
        else:
            print("❌ Expense creation failed")
            return jsonify({'error': 'Failed to create expense'}), 500
            
    except Exception as e:
        print(f"❌ SUT Office expense POST error: {e}")
        print(traceback.format_exc())
        return jsonify({'error': f'Failed to create expense: {str(e)}'}), 500

@app.route('/api/sut-office-expenses/<int:expense_id>', methods=['PUT'])
def update_sut_office_expense(expense_id):
    """Update a SUT Office expense"""
    try:
        print(f"💰 PUT /api/sut-office-expenses/{expense_id} called")
        
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        
        data = request.get_json()
        print(f"💰 Update expense data: {data}")
        
        expense_date = data.get('expenseDate')
        if expense_date:
            date_obj = datetime.strptime(expense_date, '%Y-%m-%d')
            month = date_obj.month
            year = date_obj.year
        else:
            month = datetime.now().month
            year = datetime.now().year
        
        expense_data = {
            "expense_date": expense_date,
            "month": month,
            "year": year,
            "amount_spent": float(data.get('amountSpent', 0)),
            "description": data.get('description', ''),
            "remarks": data.get('remarks', '')
        }
        
        response = supabase.table("sut_office_expenses").update(expense_data).eq("id", expense_id).execute()
        
        if response.data:
            print("✅ SUT Office expense updated successfully")
            return jsonify({
                'success': True,
                'message': 'Expense updated successfully',
                'expense': response.data[0]
            })
        else:
            print("❌ Expense update failed")
            return jsonify({'error': 'Failed to update expense'}), 500
            
    except Exception as e:
        print(f"❌ SUT Office expense PUT error: {e}")
        print(traceback.format_exc())
        return jsonify({'error': f'Failed to update expense: {str(e)}'}), 500

@app.route('/api/sut-office-expenses/<int:expense_id>', methods=['DELETE'])
def delete_sut_office_expense(expense_id):
    """Delete a SUT Office expense"""
    try:
        print(f"💰 DELETE /api/sut-office-expenses/{expense_id} called")
        
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        
        response = supabase.table("sut_office_expenses").delete().eq("id", expense_id).execute()
        
        if response.data:
            return jsonify({
                'success': True,
                'message': 'Expense deleted successfully'
            })
        else:
            return jsonify({'error': 'Failed to delete expense'}), 500
            
    except Exception as e:
        print(f"❌ SUT Office expense DELETE error: {e}")
        return jsonify({'error': f'Failed to delete expense: {str(e)}'}), 500

# ============ DASHBOARD DATA ============

@app.route('/api/dashboard-data')
def dashboard_data():
    """Get dashboard data with financial year budget and current usage"""
    try:
        print("📈 GET /api/dashboard-data called")
        
        fy_response = supabase.table("financial_years").select("*").order("start_year", desc=True).limit(1).execute()
        
        if not fy_response.data or len(fy_response.data) == 0:
            current_date = datetime.now()
            current_year = current_date.year
            current_month = current_date.month
            
            if current_month >= 4:
                start_year = current_year
                end_year = current_year + 1
            else:
                start_year = current_year - 1
                end_year = current_year
            
            default_fy = {
                "financial_year": f"{start_year}-{end_year}",
                "start_year": start_year,
                "end_year": end_year,
                "total_allocated": 60000.00,
                "water_allocated": 15000.00,
                "electricity_allocated": 35000.00,
                "telephone_allocated": 10000.00,
                "sut_office_allocated": 0.00,
                "created_at": datetime.now().isoformat()
            }
            
            fy_create_response = supabase.table("financial_years").insert(default_fy).execute()
            if fy_create_response.data:
                current_fy = fy_create_response.data[0]
            else:
                current_fy = {
                    'financial_year': f'{start_year}-{end_year}',
                    'start_year': start_year,
                    'end_year': end_year,
                    'total_allocated': 60000.00,
                    'water_allocated': 15000.00,
                    'electricity_allocated': 35000.00,
                    'telephone_allocated': 10000.00,
                    'sut_office_allocated': 0.00
                }
        else:
            current_fy = fy_response.data[0]
        
        print(f"📈 Current financial year: {current_fy['financial_year']}")
        
        start_year = current_fy['start_year']
        end_year = current_fy['end_year']
        
        query = supabase.table("utility_bills").select("*")
        response = query.execute()
        
        water_total = 0
        electricity_total = 0
        telephone_total = 0
        total_current = 0
        total_unsettled = 0
        total_paid = 0
        
        if response.data:
            for bill in response.data:
                bill_year = bill['year']
                bill_month = bill['month']
                
                if bill_year == start_year and bill_month >= 4:
                    include_bill = True
                elif bill_year == end_year and bill_month <= 3:
                    include_bill = True
                else:
                    include_bill = False
                
                if include_bill:
                    if bill['utility_type'] == 'water':
                        water_total += float(bill['current_charges'] or 0)
                    elif bill['utility_type'] == 'electricity':
                        electricity_total += float(bill['current_charges'] or 0)
                    elif bill['utility_type'] == 'telephone':
                        telephone_total += float(bill['current_charges'] or 0)
                    
                    total_current += float(bill['current_charges'] or 0)
                    total_unsettled += float(bill['unsettled_charges'] or 0)
                    total_paid += float(bill.get('amount_paid') or 0)
        
        # Get SUT Office expenses for current financial year
        sut_office_used = 0
        try:
            sut_expenses_response = supabase.table("sut_office_expenses").select("*").eq("year", start_year).execute()
            if sut_expenses_response.data:
                for expense in sut_expenses_response.data:
                    sut_office_used += float(expense.get('amount_spent', 0) or 0)
        except Exception as e:
            print(f"⚠️ Could not get SUT Office expenses: {e}")
        
        budget_calculations = {
            'financial_year': current_fy['financial_year'],
            'start_year': start_year,
            'end_year': end_year,
            'total_allocated': float(current_fy.get('total_allocated', 60000)),
            'water_allocated': float(current_fy.get('water_allocated', 15000)),
            'electricity_allocated': float(current_fy.get('electricity_allocated', 35000)),
            'telephone_allocated': float(current_fy.get('telephone_allocated', 10000)),
            'sut_office_allocated': float(current_fy.get('sut_office_allocated', 0)),
            'water_used': water_total,
            'electricity_used': electricity_total,
            'telephone_used': telephone_total,
            'sut_office_used': sut_office_used,
            'total_used': total_current,
            'water_balance': float(current_fy.get('water_allocated', 15000)) - water_total,
            'electricity_balance': float(current_fy.get('electricity_allocated', 35000)) - electricity_total,
            'telephone_balance': float(current_fy.get('telephone_allocated', 10000)) - telephone_total,
            'sut_office_balance': float(current_fy.get('sut_office_allocated', 0)) - sut_office_used,
            'total_balance': float(current_fy.get('total_allocated', 60000)) - total_current,
            'water_percentage': (water_total / float(current_fy.get('water_allocated', 15000))) * 100 if float(current_fy.get('water_allocated', 15000)) > 0 else 0,
            'electricity_percentage': (electricity_total / float(current_fy.get('electricity_allocated', 35000))) * 100 if float(current_fy.get('electricity_allocated', 35000)) > 0 else 0,
            'telephone_percentage': (telephone_total / float(current_fy.get('telephone_allocated', 10000))) * 100 if float(current_fy.get('telephone_allocated', 10000)) > 0 else 0,
            'sut_office_percentage': (sut_office_used / float(current_fy.get('sut_office_allocated', 0))) * 100 if float(current_fy.get('sut_office_allocated', 0)) > 0 else 0,
            'total_percentage': (total_current / float(current_fy.get('total_allocated', 60000))) * 100 if float(current_fy.get('total_allocated', 60000)) > 0 else 0
        }
        
        formatted_budget = {}
        for key, value in budget_calculations.items():
            if isinstance(value, (int, float)):
                if 'percentage' in key:
                    formatted_budget[key] = f"{value:.1f}%"
                elif 'start_year' in key or 'end_year' in key:
                    formatted_budget[key] = format_year(value)
                else:
                    formatted_budget[key] = format_currency(value)
            else:
                formatted_budget[key] = value
        
        formatted_current = {
            'water': format_currency(water_total),
            'electricity': format_currency(electricity_total),
            'telephone': format_currency(telephone_total),
            'total': format_currency(total_current),
            'unsettled': format_currency(total_unsettled),
            'paid': format_currency(total_paid)
        }
        
        return jsonify({
            'budget_data': formatted_budget,
            'current_totals': formatted_current,
            'raw_data': {
                'budget': budget_calculations,
                'current': {
                    'water': water_total,
                    'electricity': electricity_total,
                    'telephone': telephone_total,
                    'total': total_current,
                    'unsettled': total_unsettled,
                    'paid': total_paid
                }
            }
        })
        
    except Exception as e:
        print(f"❌ Dashboard data error: {e}")
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

# ============ SCHOOLS API ============

@app.route('/api/schools', methods=['GET'])
def api_schools():
    try:
        print("🏫 GET /api/schools called")
        
        if not supabase:
            return jsonify([]), 500
        
        # Order by cluster_number, then display_order, then id
        response = supabase.table("schools").select("*").order("cluster_number").order("display_order").order("id").execute()
        return jsonify(response.data if response.data else [])
        
    except Exception as e:
        print(f"❌ Schools GET error: {e}")
        return jsonify([]), 500

@app.route('/api/schools', methods=['POST'])
def create_school():
    try:
        print("🏫 POST /api/schools called")
        data = request.get_json()
        
        if not data.get('name'):
            return jsonify({'success': False, 'error': 'School name is required'}), 400
        if not data.get('clusterNumber'):
            return jsonify({'success': False, 'error': 'Cluster number is required'}), 400
        if not data.get('schoolNumber'):
            return jsonify({'success': False, 'error': 'School number is required'}), 400
        
        water_accounts = data.get('waterAccounts', [])
        electricity_accounts = data.get('electricityAccounts', [])
        telephone_accounts = data.get('telephoneAccounts', [])
        
        school_data = {
            "name": data.get('name'),
            "cluster_number": data.get('clusterNumber'),
            "school_number": data.get('schoolNumber'),
            "bmo_name": data.get('bmoName', ''),
            "bmo_phone": data.get('bmoPhone', ''),
            "address": data.get('address', ''),
            "notes": data.get('notes', ''),
            "water_accounts": json.dumps(water_accounts) if water_accounts else '[]',
            "electricity_accounts": json.dumps(electricity_accounts) if electricity_accounts else '[]',
            "telephone_accounts": json.dumps(telephone_accounts) if telephone_accounts else '[]',
            "water_account": water_accounts[0].get('accountNumber', '') if water_accounts and len(water_accounts) > 0 else '',
            "water_meter": water_accounts[0].get('meters', [{}])[0].get('meterNumber', '') if water_accounts and len(water_accounts) > 0 and water_accounts[0].get('meters') and len(water_accounts[0]['meters']) > 0 else '',
            "electricity_account": electricity_accounts[0].get('accountNumber', '') if electricity_accounts and len(electricity_accounts) > 0 else '',
            "electricity_meter": electricity_accounts[0].get('meters', [{}])[0].get('meterNumber', '') if electricity_accounts and len(electricity_accounts) > 0 and electricity_accounts[0].get('meters') and len(electricity_accounts[0]['meters']) > 0 else '',
            "telephone_account": telephone_accounts[0].get('accountNumber', '') if telephone_accounts and len(telephone_accounts) > 0 else '',
            "telephone_number": telephone_accounts[0].get('numbers', [{}])[0].get('phoneNumber', '') if telephone_accounts and len(telephone_accounts) > 0 and telephone_accounts[0].get('numbers') and len(telephone_accounts[0]['numbers']) > 0 else '',
            "display_order": data.get('displayOrder', 0),
            "created_at": datetime.now().isoformat()
        }
        
        response = supabase.table("schools").insert(school_data).execute()
        
        if hasattr(response, 'data') and response.data:
            return jsonify({
                'success': True,
                'message': 'School created successfully',
                'school': response.data[0]
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to create school'}), 500
        
    except Exception as e:
        print(f"❌ Create school error: {e}")
        return jsonify({'success': False, 'error': f'Failed to create school: {str(e)}'}), 500

@app.route('/api/schools/<int:school_id>', methods=['PUT'])
def update_school(school_id):
    try:
        data = request.get_json()
        
        water_accounts = data.get('waterAccounts', [])
        electricity_accounts = data.get('electricityAccounts', [])
        telephone_accounts = data.get('telephoneAccounts', [])
        
        school_data = {
            "name": data.get('name'),
            "cluster_number": data.get('clusterNumber', ''),
            "school_number": data.get('schoolNumber', ''),
            "bmo_name": data.get('bmoName', ''),
            "bmo_phone": data.get('bmoPhone', ''),
            "address": data.get('address', ''),
            "notes": data.get('notes', ''),
            "water_accounts": json.dumps(water_accounts) if water_accounts else '[]',
            "electricity_accounts": json.dumps(electricity_accounts) if electricity_accounts else '[]',
            "telephone_accounts": json.dumps(telephone_accounts) if telephone_accounts else '[]',
            "water_account": water_accounts[0].get('accountNumber', '') if water_accounts and len(water_accounts) > 0 else '',
            "water_meter": water_accounts[0].get('meters', [{}])[0].get('meterNumber', '') if water_accounts and len(water_accounts) > 0 and water_accounts[0].get('meters') and len(water_accounts[0]['meters']) > 0 else '',
            "electricity_account": electricity_accounts[0].get('accountNumber', '') if electricity_accounts and len(electricity_accounts) > 0 else '',
            "electricity_meter": electricity_accounts[0].get('meters', [{}])[0].get('meterNumber', '') if electricity_accounts and len(electricity_accounts) > 0 and electricity_accounts[0].get('meters') and len(electricity_accounts[0]['meters']) > 0 else '',
            "telephone_account": telephone_accounts[0].get('accountNumber', '') if telephone_accounts and len(telephone_accounts) > 0 else '',
            "telephone_number": telephone_accounts[0].get('numbers', [{}])[0].get('phoneNumber', '') if telephone_accounts and len(telephone_accounts) > 0 and telephone_accounts[0].get('numbers') and len(telephone_accounts[0]['numbers']) > 0 else '',
            "display_order": data.get('displayOrder', 0)
        }
        
        response = supabase.table("schools").update(school_data).eq("id", school_id).execute()
        
        if hasattr(response, 'data') and response.data:
            return jsonify({
                'success': True,
                'message': 'School updated successfully',
                'school': response.data[0]
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to update school'}), 500
        
    except Exception as e:
        print(f"❌ Update school error: {e}")
        return jsonify({'success': False, 'error': f'Failed to update school: {str(e)}'}), 500

@app.route('/api/schools/<int:school_id>', methods=['DELETE'])
def delete_school(school_id):
    try:
        bills_response = supabase.table("utility_bills").select("*").eq("entity_type", "school").eq("entity_id", school_id).execute()
        
        if bills_response.data and len(bills_response.data) > 0:
            return jsonify({
                'success': False, 
                'error': 'Cannot delete school because it has utility bills associated with it.'
            }), 400
        
        response = supabase.table("schools").delete().eq("id", school_id).execute()
        
        if hasattr(response, 'data') and response.data:
            return jsonify({
                'success': True,
                'message': 'School deleted successfully'
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to delete school'}), 500
        
    except Exception as e:
        return jsonify({'success': False, 'error': f'Failed to delete school: {str(e)}'}), 500

# ============ DEPARTMENTS API ============

@app.route('/api/departments', methods=['GET'])
def api_departments():
    try:
        print("🏢 GET /api/departments called")
        
        if not supabase:
            return jsonify([]), 500
        
        # Order by display_order first, then by department_name, then by id
        response = supabase.table("departments").select("*").order("display_order").order("department_name").order("id").execute()
        return jsonify(response.data if response.data else [])
        
    except Exception as e:
        print(f"❌ Departments GET error: {e}")
        return jsonify([]), 500

@app.route('/api/departments', methods=['POST'])
def create_department():
    try:
        print("🏢 POST /api/departments called")
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        unit_name = data.get('unitName')
        division_name = data.get('divisionName')
        department_name = data.get('departmentName')
        
        if not unit_name:
            return jsonify({'success': False, 'error': 'Unit Name is required'}), 400
        if not division_name:
            return jsonify({'success': False, 'error': 'Division Name is required'}), 400
        if not department_name:
            return jsonify({'success': False, 'error': 'Department Name is required'}), 400
        
        water_accounts = data.get('waterAccounts', [])
        electricity_accounts = data.get('electricityAccounts', [])
        telephone_accounts = data.get('telephoneAccounts', [])
        
        department_data = {
            "name": unit_name,
            "unit_name": unit_name,
            "division_name": division_name,
            "department_name": department_name,
            "hotline_numbers": data.get('hotlineNumbers', ''),
            "address": data.get('address', ''),
            "notes": data.get('notes', ''),
            "water_accounts": json.dumps(water_accounts) if water_accounts else '[]',
            "electricity_accounts": json.dumps(electricity_accounts) if electricity_accounts else '[]',
            "telephone_accounts": json.dumps(telephone_accounts) if telephone_accounts else '[]',
            "water_account": water_accounts[0].get('accountNumber', '') if water_accounts and len(water_accounts) > 0 else '',
            "water_meter": water_accounts[0].get('meters', [{}])[0].get('meterNumber', '') if water_accounts and len(water_accounts) > 0 and water_accounts[0].get('meters') and len(water_accounts[0]['meters']) > 0 else '',
            "electricity_account": electricity_accounts[0].get('accountNumber', '') if electricity_accounts and len(electricity_accounts) > 0 else '',
            "electricity_meter": electricity_accounts[0].get('meters', [{}])[0].get('meterNumber', '') if electricity_accounts and len(electricity_accounts) > 0 and electricity_accounts[0].get('meters') and len(electricity_accounts[0]['meters']) > 0 else '',
            "telephone_account": telephone_accounts[0].get('accountNumber', '') if telephone_accounts and len(telephone_accounts) > 0 else '',
            "telephone_number": telephone_accounts[0].get('numbers', [{}])[0].get('phoneNumber', '') if telephone_accounts and len(telephone_accounts) > 0 and telephone_accounts[0].get('numbers') and len(telephone_accounts[0]['numbers']) > 0 else '',
            "display_order": data.get('displayOrder', 0),
            "created_at": datetime.now().isoformat()
        }
        
        response = supabase.table("departments").insert(department_data).execute()
        
        if hasattr(response, 'data') and response.data:
            return jsonify({
                'success': True,
                'message': 'Department created successfully',
                'department': response.data[0]
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to create department'}), 500
        
    except Exception as e:
        print(f"❌ Create department error: {e}")
        return jsonify({'success': False, 'error': f'Failed to create department: {str(e)}'}), 500

@app.route('/api/departments/<int:department_id>', methods=['PUT'])
def update_department(department_id):
    try:
        data = request.get_json()
        
        water_accounts = data.get('waterAccounts', [])
        electricity_accounts = data.get('electricityAccounts', [])
        telephone_accounts = data.get('telephoneAccounts', [])
        
        department_data = {
            "name": data.get('unitName'),
            "unit_name": data.get('unitName', ''),
            "division_name": data.get('divisionName', ''),
            "department_name": data.get('departmentName', ''),
            "hotline_numbers": data.get('hotlineNumbers', ''),
            "address": data.get('address', ''),
            "notes": data.get('notes', ''),
            "water_accounts": json.dumps(water_accounts) if water_accounts else '[]',
            "electricity_accounts": json.dumps(electricity_accounts) if electricity_accounts else '[]',
            "telephone_accounts": json.dumps(telephone_accounts) if telephone_accounts else '[]',
            "water_account": water_accounts[0].get('accountNumber', '') if water_accounts and len(water_accounts) > 0 else '',
            "water_meter": water_accounts[0].get('meters', [{}])[0].get('meterNumber', '') if water_accounts and len(water_accounts) > 0 and water_accounts[0].get('meters') and len(water_accounts[0]['meters']) > 0 else '',
            "electricity_account": electricity_accounts[0].get('accountNumber', '') if electricity_accounts and len(electricity_accounts) > 0 else '',
            "electricity_meter": electricity_accounts[0].get('meters', [{}])[0].get('meterNumber', '') if electricity_accounts and len(electricity_accounts) > 0 and electricity_accounts[0].get('meters') and len(electricity_accounts[0]['meters']) > 0 else '',
            "telephone_account": telephone_accounts[0].get('accountNumber', '') if telephone_accounts and len(telephone_accounts) > 0 else '',
            "telephone_number": telephone_accounts[0].get('numbers', [{}])[0].get('phoneNumber', '') if telephone_accounts and len(telephone_accounts) > 0 and telephone_accounts[0].get('numbers') and len(telephone_accounts[0]['numbers']) > 0 else '',
            "display_order": data.get('displayOrder', 0)
        }
        
        response = supabase.table("departments").update(department_data).eq("id", department_id).execute()
        
        if hasattr(response, 'data') and response.data:
            return jsonify({
                'success': True,
                'message': 'Department updated successfully',
                'department': response.data[0]
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to update department'}), 500
        
    except Exception as e:
        print(f"❌ Update department error: {e}")
        return jsonify({'success': False, 'error': f'Failed to update department: {str(e)}'}), 500

@app.route('/api/departments/<int:department_id>', methods=['DELETE'])
def delete_department(department_id):
    try:
        bills_response = supabase.table("utility_bills").select("*").eq("entity_type", "department").eq("entity_id", department_id).execute()
        
        if bills_response.data and len(bills_response.data) > 0:
            return jsonify({
                'success': False, 
                'error': 'Cannot delete department because it has utility bills associated with it.'
            }), 400
        
        response = supabase.table("departments").delete().eq("id", department_id).execute()
        
        if hasattr(response, 'data') and response.data:
            return jsonify({
                'success': True,
                'message': 'Department deleted successfully'
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to delete department'}), 500
        
    except Exception as e:
        return jsonify({'success': False, 'error': f'Failed to delete department: {str(e)}'}), 500

# ============ UTILITY BILLS API ============

@app.route('/api/utility-bills', methods=['GET'])
def api_utility_bills():
    try:
        print("💡 GET /api/utility-bills called")
        
        if not supabase:
            return jsonify([]), 500
        
        utility_type = request.args.get('utility_type')
        entity_type = request.args.get('entity_type')
        entity_id = request.args.get('entity_id')
        month = request.args.get('month')
        year = request.args.get('year')
        
        query = supabase.table("utility_bills").select("*")
        
        if utility_type:
            query = query.eq("utility_type", utility_type)
        if entity_type:
            query = query.eq("entity_type", entity_type)
        if entity_id:
            query = query.eq("entity_id", int(entity_id))
        if month:
            query = query.eq("month", int(month))
        if year:
            query = query.eq("year", int(year))
        
        response = query.execute()
        
        bills = []
        if response.data:
            for bill in response.data:
                bill_data = dict(bill)
                
                if bill_data['entity_type'] == 'school':
                    school_response = supabase.table("schools").select("name").eq("id", bill_data['entity_id']).execute()
                    if school_response.data and len(school_response.data) > 0:
                        bill_data['entity_name'] = school_response.data[0]['name']
                    else:
                        bill_data['entity_name'] = 'Unknown School'
                elif bill_data['entity_type'] == 'department':
                    dept_response = supabase.table("departments").select("name").eq("id", bill_data['entity_id']).execute()
                    if dept_response.data and len(dept_response.data) > 0:
                        bill_data['entity_name'] = dept_response.data[0]['name']
                    else:
                        bill_data['entity_name'] = 'Unknown Department'
                else:
                    bill_data['entity_name'] = 'Unknown'
                
                bills.append(bill_data)
        
        return jsonify(bills)
        
    except Exception as e:
        print(f"❌ Utility bills GET error: {e}")
        return jsonify([]), 500

@app.route('/api/utility-bills', methods=['POST'])
def create_utility_bill():
    try:
        print("💡 POST /api/utility-bills called")
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        entity_name = ""
        
        if data.get('entity_type') == 'school':
            school_response = supabase.table("schools").select("name").eq("id", data.get('entity_id')).execute()
            if school_response.data and len(school_response.data) > 0:
                entity_name = school_response.data[0]['name']
        elif data.get('entity_type') == 'department':
            dept_response = supabase.table("departments").select("name").eq("id", data.get('entity_id')).execute()
            if dept_response.data and len(dept_response.data) > 0:
                entity_name = dept_response.data[0]['name']
        
        current_date = datetime.now()
        
        # Check if a bill already exists for this combination
        query = supabase.table("utility_bills").select("*")\
            .eq("utility_type", data.get('utility_type'))\
            .eq("entity_type", data.get('entity_type'))\
            .eq("entity_id", int(data.get('entity_id')))\
            .eq("month", int(data.get('month', current_date.month)))\
            .eq("year", int(data.get('year', current_date.year)))
        
        # Only filter by account number if provided and not placeholder
        account_number = data.get('account_number', '')
        if account_number and account_number != '—':
            query = query.eq("account_number", account_number)
        
        existing_bill = query.execute()
        
        if existing_bill.data and len(existing_bill.data) > 0:
            # Update existing bill instead of creating new one
            bill_id = existing_bill.data[0]['id']
            bill_data = {
                "current_charges": float(data.get('current_charges', 0)),
                "late_charges": float(data.get('late_charges', 0)),
                "unsettled_charges": float(data.get('unsettled_charges', 0)),
                "amount_paid": float(data.get('amount_paid', 0))
            }
            
            # Add consumption if provided
            if data.get('consumption_m3') is not None:
                bill_data["consumption_m3"] = float(data.get('consumption_m3'))
            if data.get('consumption_kwh') is not None:
                bill_data["consumption_kwh"] = float(data.get('consumption_kwh'))
            
            # Update meter number if provided
            if data.get('meter_number') and data.get('meter_number') != '—':
                bill_data["meter_number"] = data.get('meter_number')
            
            # Update notes if provided
            if data.get('notes') is not None:
                bill_data["notes"] = data.get('notes')
            
            response = supabase.table("utility_bills").update(bill_data).eq("id", bill_id).execute()
            
            if response.data:
                return jsonify({
                    'message': 'Utility bill updated successfully',
                    'bill': response.data[0],
                    'updated': True
                })
            else:
                return jsonify({'error': 'Failed to update utility bill'}), 500
        
        # Create new bill
        bill_data = {
            "utility_type": data.get('utility_type'),
            "entity_type": data.get('entity_type'),
            "entity_id": int(data.get('entity_id')),
            "entity_name": entity_name,
            "account_id": data.get('account_id') if data.get('account_id') else None,
            "account_number": data.get('account_number', '') if data.get('account_number', '') != '—' else '',
            "meter_number": data.get('meter_number', '') if data.get('meter_number', '') != '—' else '',
            "phone_number": data.get('phone_number', ''),
            "current_charges": float(data.get('current_charges', 0)),
            "late_charges": float(data.get('late_charges', 0)),
            "unsettled_charges": float(data.get('unsettled_charges', 0)),
            "amount_paid": float(data.get('amount_paid', 0)),
            "consumption_m3": float(data.get('consumption_m3', 0)) if data.get('consumption_m3') else None,
            "consumption_kwh": float(data.get('consumption_kwh', 0)) if data.get('consumption_kwh') else None,
            "month": int(data.get('month', current_date.month)),
            "year": int(data.get('year', current_date.year)),
            "bill_month": int(data.get('bill_month', current_date.month)),
            "bill_year": int(data.get('bill_year', current_date.year)),
            "bill_image": data.get('bill_image'),
            "notes": data.get('notes', ''),
            "created_at": datetime.now().isoformat()
        }
        
        response = supabase.table("utility_bills").insert(bill_data).execute()
        if response.data:
            return jsonify({
                'message': 'Utility bill created successfully',
                'bill': response.data[0]
            })
        else:
            return jsonify({'error': 'Failed to create utility bill'}), 500
        
    except Exception as e:
        print(f"❌ Create utility bill error: {e}")
        print(traceback.format_exc())
        return jsonify({'error': f'Failed to create utility bill: {str(e)}'}), 500

# ============ UPDATE UTILITY BILL (PUT) ============

@app.route('/api/utility-bills/<int:bill_id>', methods=['PUT'])
def update_utility_bill(bill_id):
    try:
        print(f"💡 PUT /api/utility-bills/{bill_id} called")
        
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        
        data = request.get_json()
        print(f"💡 Update bill data: {data}")
        
        bill_data = {
            "current_charges": float(data.get('current_charges', 0)),
            "late_charges": float(data.get('late_charges', 0)),
            "unsettled_charges": float(data.get('unsettled_charges', 0)),
            "amount_paid": float(data.get('amount_paid', 0))
        }
        
        # Add consumption if provided
        if data.get('consumption_m3') is not None:
            bill_data["consumption_m3"] = float(data.get('consumption_m3'))
        if data.get('consumption_kwh') is not None:
            bill_data["consumption_kwh"] = float(data.get('consumption_kwh'))
        
        # Update account/meter information if provided
        if data.get('account_number') is not None and data.get('account_number') != '—':
            bill_data["account_number"] = data.get('account_number')
        if data.get('meter_number') is not None and data.get('meter_number') != '—':
            bill_data["meter_number"] = data.get('meter_number')
        if data.get('phone_number') is not None:
            bill_data["phone_number"] = data.get('phone_number')
        
        # Update notes if provided
        if data.get('notes') is not None:
            bill_data["notes"] = data.get('notes')
        
        response = supabase.table("utility_bills").update(bill_data).eq("id", bill_id).execute()
        
        if response.data:
            print("✅ Utility bill updated successfully")
            return jsonify({
                'success': True,
                'message': 'Bill updated successfully',
                'bill': response.data[0]
            })
        else:
            print("❌ Bill update failed")
            return jsonify({'error': 'Failed to update bill'}), 500
            
    except Exception as e:
        print(f"❌ Utility bill PUT error: {e}")
        print(traceback.format_exc())
        return jsonify({'error': f'Failed to update bill: {str(e)}'}), 500

# ============ DELETE UTILITY BILL ============

@app.route('/api/utility-bills/<int:bill_id>', methods=['DELETE'])
def delete_utility_bill(bill_id):
    try:
        print(f"💡 DELETE /api/utility-bills/{bill_id} called")
        
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        
        # First, check if the bill exists
        check_response = supabase.table("utility_bills").select("id").eq("id", bill_id).execute()
        
        if not check_response.data or len(check_response.data) == 0:
            print(f"❌ Bill with ID {bill_id} not found")
            return jsonify({'error': 'Bill not found'}), 404
        
        # Delete the bill
        response = supabase.table("utility_bills").delete().eq("id", bill_id).execute()
        
        if response.data:
            print(f"✅ Bill with ID {bill_id} deleted successfully")
            return jsonify({
                'success': True,
                'message': 'Bill deleted successfully',
                'deleted_id': bill_id
            })
        else:
            print(f"❌ Failed to delete bill with ID {bill_id}")
            return jsonify({'error': 'Failed to delete bill'}), 500
            
    except Exception as e:
        print(f"❌ Utility bill DELETE error: {e}")
        print(traceback.format_exc())
        return jsonify({'error': f'Failed to delete bill: {str(e)}'}), 500

# ============ STATISTICS API ============

@app.route('/api/statistics/overview')
def overview_statistics():
    try:
        if not supabase:
            return jsonify({'error': 'Database not connected'}), 500
        
        dept_response = supabase.table("departments").select("*").execute()
        departments = dept_response.data if dept_response.data else []
        
        school_response = supabase.table("schools").select("*").execute()
        schools = school_response.data if school_response.data else []
        
        bills_response = supabase.table("utility_bills").select("*").execute()
        bills = bills_response.data if bills_response.data else []
        
        dept_names = set()
        divisions = set()
        for dept in departments:
            dept_names.add(dept.get('department_name', 'Uncategorized'))
            divisions.add(dept.get('division_name', 'Unknown'))
        
        clusters = set()
        primary_count = 0
        secondary_count = 0
        college_count = 0
        other_count = 0
        
        for school in schools:
            school_name = school.get('name', '').lower()
            clusters.add(school.get('cluster_number', 'Unknown'))
            
            if 'primary' in school_name:
                primary_count += 1
            elif 'secondary' in school_name or 'high' in school_name:
                secondary_count += 1
            elif 'college' in school_name or 'university' in school_name or 'institute' in school_name:
                college_count += 1
            else:
                other_count += 1
        
        water_bills = [b for b in bills if b.get('utility_type') == 'water']
        electricity_bills = [b for b in bills if b.get('utility_type') == 'electricity']
        telephone_bills = [b for b in bills if b.get('utility_type') == 'telephone']
        
        total_amount = sum(float(b.get('current_charges', 0) or 0) for b in bills)
        
        return jsonify({
            'departments': {
                'total_departments': len(dept_names),
                'total_units': len(departments),
                'total_divisions': len(divisions),
                'unique_departments': list(dept_names)[:10]
            },
            'schools': {
                'total_schools': len(schools),
                'total_clusters': len(clusters),
                'by_type': {
                    'primary': primary_count,
                    'secondary': secondary_count,
                    'college': college_count,
                    'other': other_count
                },
                'unique_clusters': list(clusters)[:10]
            },
            'utility_bills': {
                'total_bills': len(bills),
                'water_bills': len(water_bills),
                'electricity_bills': len(electricity_bills),
                'telephone_bills': len(telephone_bills),
                'total_amount': total_amount
            }
        })
        
    except Exception as e:
        print(f"❌ Overview statistics error: {e}")
        return jsonify({'error': str(e)}), 500

# ============ HEALTH CHECK ============

@app.route('/health')
def health_check():
    connection_status = test_supabase_connection()
    
    return jsonify({
        'status': 'healthy' if connection_status else 'degraded',
        'timestamp': datetime.now().isoformat(),
        'supabase_connected': connection_status,
        'service': 'UKA-BILL Utility System'
    })

@app.route('/api/test')
def api_test():
    return jsonify({'message': 'API is working'})

# ============ TECHNICIAN API ROUTES ============

@app.route('/api/technicians', methods=['GET'])
def get_technicians():
    """Get all technicians"""
    try:
        print("👤 GET /api/technicians called")
        
        if not supabase:
            # Return default technicians if Supabase is not connected
            return jsonify([
                {'id': 1, 'name': 'Admin User', 'role': 'admin', 'isAuthorized': True},
                {'id': 2, 'name': 'Technician User', 'role': 'technician', 'isAuthorized': False}
            ]), 200
        
        response = supabase.table("technicians").select("*").execute()
        technicians = response.data if response.data else []
        
        # If no technicians in database, return default
        if not technicians:
            return jsonify([
                {'id': 1, 'name': 'Admin User', 'role': 'admin', 'isAuthorized': True},
                {'id': 2, 'name': 'Technician User', 'role': 'technician', 'isAuthorized': False}
            ]), 200
        
        return jsonify(technicians)
        
    except Exception as e:
        print(f"❌ Get technicians error: {e}")
        # Return default technicians on error
        return jsonify([
            {'id': 1, 'name': 'Admin User', 'role': 'admin', 'isAuthorized': True},
            {'id': 2, 'name': 'Technician User', 'role': 'technician', 'isAuthorized': False}
        ]), 200

# ============ TECHNICAL REPORTS API (ADDITIONAL) ============

@app.route('/api/technical-reports/<int:report_id>/track-print', methods=['POST'])
def track_report_print(report_id):
    """Track when a report is printed"""
    try:
        print(f"📄 POST /api/technical-reports/{report_id}/track-print called")
        # Just log the print action - no database tracking needed
        print(f"Report {report_id} was printed/viewed")
        return jsonify({'success': True})
    except Exception as e:
        print(f"❌ Track print error: {e}")
        return jsonify({'success': False}), 500

# ============ APPLICATION STARTUP ============

if __name__ == '__main__':
    create_directories()
    
    print("\n" + "="*60)
    print("🚀 UKA-BILL Utility System Starting")
    print("👤 Contact: aka.sazali@gmail.com")
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
