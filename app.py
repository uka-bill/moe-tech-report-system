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
from PIL import Image
import io as io_lib

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

# ============ UPDATED: Reduced file size limits to save bandwidth ============
app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024  # 1MB max (reduced from 16MB)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp'}

# Image compression settings
app.config['MAX_IMAGE_DIMENSION'] = 1200  # Max width or height in pixels
app.config['IMAGE_QUALITY'] = 75  # JPEG quality (1-100)
app.config['MAX_IMAGE_SIZE_KB'] = 500  # Max file size after compression (500KB)

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

def compress_image(file_content, filename):
    """Compress image to save bandwidth and storage"""
    try:
        # Open image from bytes
        img = Image.open(io_lib.BytesIO(file_content))
        
        # Convert RGBA to RGB (remove transparency)
        if img.mode in ('RGBA', 'LA', 'P'):
            rgb_img = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'RGBA':
                rgb_img.paste(img, mask=img.split()[-1])
            else:
                rgb_img.paste(img)
            img = rgb_img
        elif img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Resize if too large (maintain aspect ratio)
        max_dimension = app.config['MAX_IMAGE_DIMENSION']
        if img.width > max_dimension or img.height > max_dimension:
            ratio = min(max_dimension / img.width, max_dimension / img.height)
            new_size = (int(img.width * ratio), int(img.height * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
            app.logger.info(f"Resized image from {img.width}x{img.height} to {new_size[0]}x{new_size[1]}")
        
        # Save compressed image to bytes
        output = io_lib.BytesIO()
        img.save(output, format='JPEG', quality=app.config['IMAGE_QUALITY'], optimize=True)
        compressed_content = output.getvalue()
        
        app.logger.info(f"Image compressed: {len(file_content)/1024:.1f}KB → {len(compressed_content)/1024:.1f}KB")
        
        return compressed_content, 'jpg'
        
    except Exception as e:
        app.logger.error(f"Image compression error: {e}")
        return file_content, 'jpg'

# ============ ROUTES (keep all your existing routes) ============

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

# ============ TECHNICIAN API (keep all your existing technician routes) ============
# ... (your existing technician, schools, departments, reports APIs go here)
# I'm omitting them for brevity since they remain unchanged

# ============ UPDATED IMAGE UPLOAD with Compression ============

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
        
        # Read file content
        original_content = file.read()
        original_size_kb = len(original_content) / 1024
        
        # Check if file is too large (>1MB)
        if len(original_content) > app.config['MAX_CONTENT_LENGTH']:
            return jsonify({
                'success': False, 
                'error': f'Image too large ({original_size_kb:.1f}KB). Maximum allowed is 1MB.'
            }), 400
        
        # Compress the image
        compressed_content, ext = compress_image(original_content, file.filename)
        compressed_size_kb = len(compressed_content) / 1024
        
        # Check if compressed image is still too large
        max_size_bytes = app.config['MAX_IMAGE_SIZE_KB'] * 1024
        if len(compressed_content) > max_size_bytes:
            return jsonify({
                'success': False,
                'error': f'Image too large even after compression ({compressed_size_kb:.1f}KB). Please upload a smaller image.'
            }), 400
        
        # Generate unique filename
        filename = f"{uuid.uuid4().hex}_{get_brunei_time().strftime('%Y%m%d_%H%M%S')}.{ext}"
        
        image_url = None
        
        # Upload to Supabase Storage
        if supabase:
            try:
                init_supabase_storage()
                supabase.storage.from_('mapping-images').upload(
                    filename, 
                    compressed_content,
                    file_options={"content-type": "image/jpeg"}
                )
                image_url = supabase.storage.from_('mapping-images').get_public_url(filename)
                app.logger.info(f"✅ Image uploaded to Supabase Storage: {image_url} (Original: {original_size_kb:.1f}KB → Compressed: {compressed_size_kb:.1f}KB)")
            except Exception as e:
                app.logger.error(f"❌ Failed to upload to Supabase Storage: {e}")
                # Fallback to local storage
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                with open(filepath, 'wb') as f:
                    f.write(compressed_content)
                image_url = f"/api/images/{filename}"
                app.logger.info(f"📁 Image saved locally: {filepath}")
        else:
            # Fallback to local storage
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            with open(filepath, 'wb') as f:
                f.write(compressed_content)
            image_url = f"/api/images/{filename}"
            app.logger.info(f"📁 Image saved locally: {filepath}")
        
        return jsonify({
            'success': True, 
            'image_url': image_url, 
            'filename': filename, 
            'original_size_kb': round(original_size_kb, 1),
            'compressed_size_kb': round(compressed_size_kb, 1),
            'message': f'Image uploaded successfully (Compressed: {original_size_kb:.1f}KB → {compressed_size_kb:.1f}KB)'
        })
        
    except Exception as e:
        app.logger.error(f"Error uploading image: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/images/<filename>')
def get_image(filename):
    """Serve local images (fallback)"""
    try:
        from flask import send_from_directory
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
    except Exception as e:
        app.logger.error(f"Error serving image {filename}: {e}")
        return jsonify({'error': 'Image not found'}), 404

# ============ REST OF YOUR EXISTING CODE (keep everything else) ============
# ... (your backup, restore, dashboard stats, export, etc. endpoints remain unchanged)

# ============ APPLICATION STARTUP ============

def init_app():
    create_directories()
    init_supabase_storage()
    app.logger.info("=" * 60)
    app.logger.info("🏫 MOE Technical Report System Starting")
    app.logger.info("Ministry of Education - Brunei Darussalam")
    app.logger.info(f"📸 Image settings: Max {app.config['MAX_IMAGE_DIMENSION']}px, Quality {app.config['IMAGE_QUALITY']}%, Max size {app.config['MAX_IMAGE_SIZE_KB']}KB")
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
