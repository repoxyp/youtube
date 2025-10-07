import os
import json
import threading
import time
from flask import Flask, render_template, request, jsonify, send_file
from downloader import YouTubeDownloader
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)

# Disable Werkzeug startup messages
logging.getLogger('werkzeug').setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'fallback-secret-key')

# Global variable to store download progress
download_progress = {}
download_lock = threading.Lock()

def get_downloads_folder():
    """Get the system downloads folder with fallback"""
    try:
        if os.name == 'nt':  # Windows
            downloads = os.path.join(os.path.expanduser('~'), 'Downloads')
        else:  # Linux/macOS
            downloads = os.path.join(os.path.expanduser('~'), 'Downloads')
        
        # Create if doesn't exist
        os.makedirs(downloads, exist_ok=True)
        return downloads
    except Exception as e:
        logger.error(f"Error accessing downloads folder: {e}")
        # Fallback to current directory
        fallback = os.path.join(os.getcwd(), 'downloads')
        os.makedirs(fallback, exist_ok=True)
        return fallback

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/fetch_formats', methods=['POST'])
def fetch_formats():
    try:
        url = request.json.get('url')
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        logger.info(f"Fetching formats for URL: {url}")
        downloader = YouTubeDownloader()
        video_info = downloader.get_video_info(url)
        
        if not video_info:
            return jsonify({'error': 'Could not fetch video information. Please check the URL and try again.'}), 400
        
        logger.info(f"Successfully fetched info for: {video_info.get('title', 'Unknown')}")
        return jsonify(video_info)
    
    except Exception as e:
        logger.error(f"Error fetching formats: {str(e)}")
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500

@app.route('/download', methods=['POST'])
def download():
    try:
        data = request.json
        url = data.get('url')
        format_id = data.get('format_id')
        download_type = data.get('type', 'video')
        
        if not url or not format_id:
            return jsonify({'error': 'URL and format are required'}), 400
        
        # Generate a unique download ID
        import uuid
        download_id = str(uuid.uuid4())
        
        # Start download in background thread
        def download_thread():
            try:
                with download_lock:
                    download_progress[download_id] = {
                        'status': 'starting',
                        'percent': 0,
                        'speed': '0 MB/s',
                        'eta': 'Unknown',
                        'filesize': '0 MB',
                        'filename': '',
                        'message': 'Starting download...',
                        'start_time': time.time()
                    }
                
                logger.info(f"Starting download {download_id} for URL: {url}, Format: {format_id}, Type: {download_type}")
                downloader = YouTubeDownloader()
                
                downloads_folder = get_downloads_folder()
                filepath = downloader.download(
                    url=url,
                    format_id=format_id,
                    download_type=download_type,
                    downloads_folder=downloads_folder,
                    progress_callback=lambda info: update_progress(download_id, info)
                )
                
                if filepath and os.path.exists(filepath):
                    with download_lock:
                        download_progress[download_id]['status'] = 'completed'
                        download_progress[download_id]['filepath'] = filepath
                        download_progress[download_id]['filename'] = os.path.basename(filepath)
                        download_progress[download_id]['message'] = 'Download completed successfully!'
                        download_progress[download_id]['percent'] = 100
                    
                    logger.info(f"Download completed successfully: {filepath}")
                else:
                    with download_lock:
                        download_progress[download_id]['status'] = 'error'
                        download_progress[download_id]['message'] = 'Download failed - file not found'
                    
                    logger.error(f"Download failed - file not found: {filepath}")
                    
            except Exception as e:
                logger.error(f"Download error for {download_id}: {str(e)}")
                with download_lock:
                    download_progress[download_id]['status'] = 'error'
                    download_progress[download_id]['message'] = f'Error: {str(e)}'
        
        def update_progress(dl_id, progress_info):
            with download_lock:
                if dl_id in download_progress:
                    download_progress[dl_id].update(progress_info)
        
        thread = threading.Thread(target=download_thread)
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'download_id': download_id, 
            'message': 'Download started successfully',
            'downloads_folder': get_downloads_folder()
        })
    
    except Exception as e:
        logger.error(f"Error starting download: {str(e)}")
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500

@app.route('/progress/<download_id>')
def get_progress(download_id):
    with download_lock:
        progress = download_progress.get(download_id, {
            'status': 'unknown',
            'message': 'Download not found or expired'
        })
    return jsonify(progress)

@app.route('/download_file/<download_id>')
def download_file(download_id):
    try:
        with download_lock:
            progress = download_progress.get(download_id)
        
        if not progress or progress.get('status') != 'completed':
            return jsonify({'error': 'File not available or download not completed'}), 404
        
        filepath = progress.get('filepath')
        if not filepath or not os.path.exists(filepath):
            return jsonify({'error': 'File not found on server'}), 404
        
        filename = progress.get('filename', 'download')
        
        logger.info(f"Serving file: {filepath} as {filename}")
        return send_file(
            filepath, 
            as_attachment=True, 
            download_name=filename,
            mimetype='application/octet-stream'
        )
    
    except Exception as e:
        logger.error(f"Error serving file {download_id}: {str(e)}")
        return jsonify({'error': f'Error serving file: {str(e)}'}), 500

@app.route('/cleanup', methods=['POST'])
def cleanup():
    """Clean up old download entries"""
    try:
        current_time = time.time()
        with download_lock:
            # Remove entries older than 1 hour
            to_remove = []
            for dl_id, progress in download_progress.items():
                start_time = progress.get('start_time', 0)
                if current_time - start_time > 3600:  # 1 hour
                    to_remove.append(dl_id)
            
            for dl_id in to_remove:
                del download_progress[dl_id]
        
        return jsonify({'message': f'Cleaned up {len(to_remove)} old entries'})
    
    except Exception as e:
        logger.error(f"Cleanup error: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Create downloads folder if it doesn't exist
    downloads_folder = get_downloads_folder()
    logger.info(f"Downloads folder: {downloads_folder}")
    
    # Check if running in production
    if os.getenv('FLASK_ENV') == 'production':
        try:
            from waitress import serve
            print("🚀 Production server starting with Waitress...")
            serve(app, host='0.0.0.0', port=5000)
        except ImportError:
            print("⚠️ Waitress not installed, using development server")
            app.run(debug=False, host='0.0.0.0', port=5000)
    else:
        print("🔧 Development server starting...")
        app.run(debug=True, host='0.0.0.0', port=5000)