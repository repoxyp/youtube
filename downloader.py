import os
import json
import yt_dlp
import ffmpeg
from urllib.parse import urlparse
import re
import logging

logger = logging.getLogger(__name__)

class YouTubeDownloader:
    def __init__(self):
        self.supported_domains = [
            'youtube.com', 'youtu.be', 'tiktok.com', 'vm.tiktok.com',
            'instagram.com', 'fb.com', 'facebook.com', 'www.tiktok.com',
            'www.instagram.com', 'www.facebook.com'
        ]
    
    def sanitize_filename(self, filename):
        """Remove invalid characters from filename"""
        filename = re.sub(r'[<>:"/\\|?*]', '', filename)
        if len(filename) > 100:
            filename = filename[:100]
        return filename.strip()
    
    def get_video_info(self, url):
        """Get video information and available formats"""
        try:
            # Special handling for Facebook and Instagram
            ydl_opts = self.get_extractor_opts(url)
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Validate URL first
                try:
                    ie_result = ydl.extract_info(url, download=False, process=False)
                    if not ie_result:
                        return None
                except Exception as e:
                    logger.warning(f"URL validation warning: {e}")
                    # Continue anyway, some platforms might still work
                
                # Get full info with processing
                info = ydl.extract_info(url, download=False)
                
                if not info:
                    return None
                
                # Extract basic video info
                video_info = {
                    'title': self.sanitize_filename(info.get('title', 'Unknown Title')),
                    'thumbnail': info.get('thumbnail', ''),
                    'duration': self.format_duration(info.get('duration', 0)),
                    'uploader': info.get('uploader', 'Unknown Uploader'),
                    'webpage_url': info.get('webpage_url', url),
                    'formats': []
                }
                
                # Extract available formats
                formats = self.extract_formats(info)
                video_info['formats'] = formats
                
                logger.info(f"Found {len(formats)} formats for: {video_info['title']}")
                return video_info
                
        except Exception as e:
            logger.error(f"Error getting video info: {str(e)}")
            return None
    
    def get_extractor_opts(self, url):
        """Get extractor options based on platform"""
        opts = {
            'quiet': True,
            'no_warnings': False,
        }
        
        # Facebook specific options
        if 'facebook.com' in url or 'fb.com' in url:
            opts.update({
                'cookiefile': 'cookies.txt',  # Optional: for private videos
                'extractor_args': {
                    'facebook': {
                        'credentials': {
                            'email': os.getenv('FB_EMAIL', ''),
                            'password': os.getenv('FB_PASSWORD', '')
                        }
                    }
                }
            })
        
        # Instagram specific options  
        elif 'instagram.com' in url:
            opts.update({
                'extractor_args': {
                    'instagram': {
                        'shortcode_match': True
                    }
                }
            })
        
        return opts
    
    def extract_formats(self, info):
        """Extract and organize all available formats"""
        formats = []
        
        # Process each format
        for f in info.get('formats', []):
            format_info = self.create_format_info(f)
            if format_info and self.is_valid_format(format_info):
                formats.append(format_info)
        
        # Add combined formats for high quality videos
        combined_formats = self.create_combined_formats(formats)
        formats.extend(combined_formats)
        
        # Add best audio format
        formats.append({
            'format_id': 'bestaudio/best',
            'ext': 'mp3',
            'resolution': 'MP3 (Best Quality)',
            'filesize': 'Unknown',
            'type': 'audio',
            'quality': 1
        })
        
        # Add best video format
        formats.append({
            'format_id': 'best',
            'ext': 'mp4',
            'resolution': 'BEST (Auto Select)',
            'filesize': 'Unknown',
            'type': 'video+audio',
            'quality': 10000
        })
        
        # Remove duplicates and sort
        return self.deduplicate_and_sort_formats(formats)
    
    def create_format_info(self, format_dict):
        """Create standardized format info"""
        format_note = format_dict.get('format_note', 'unknown')
        if format_note == 'unknown' and format_dict.get('height'):
            format_note = f"{format_dict['height']}p"
        
        # Skip storyboard formats
        if format_dict.get('format_id', '').startswith('sb'):
            return None
        
        return {
            'format_id': format_dict['format_id'],
            'ext': format_dict.get('ext', 'mp4'),
            'resolution': format_note.upper() if format_note != 'unknown' else 'N/A',
            'filesize': self.format_filesize(format_dict.get('filesize')),
            'type': self.get_format_type(format_dict),
            'quality': self.get_quality_value(format_note, format_dict),
            'has_audio': format_dict.get('acodec') != 'none',
            'has_video': format_dict.get('vcodec') != 'none',
        }
    
    def get_format_type(self, format_dict):
        """Determine format type"""
        has_video = format_dict.get('vcodec') != 'none'
        has_audio = format_dict.get('acodec') != 'none'
        
        if has_video and has_audio:
            return 'video+audio'
        elif has_video:
            return 'video'
        elif has_audio:
            return 'audio'
        else:
            return 'unknown'
    
    def is_valid_format(self, format_info):
        """Check if format should be included"""
        # Skip formats without video or audio
        if not format_info['has_video'] and not format_info['has_audio']:
            return False
        
        # Skip very low quality audio
        if format_info['type'] == 'audio' and format_info.get('abr', 0) < 50:
            return False
            
        return True
    
    def create_combined_formats(self, formats):
        """Create combined formats for high quality video+audio"""
        combined = []
        
        # Find best video-only and audio-only formats
        video_formats = [f for f in formats if f['type'] == 'video' and f['quality'] >= 720]
        audio_formats = [f for f in formats if f['type'] == 'audio']
        
        for video_fmt in video_formats[:3]:  # Top 3 video formats
            if video_fmt['quality'] >= 720:
                combined.append({
                    'format_id': f"{video_fmt['format_id']}+bestaudio",
                    'ext': 'mp4',
                    'resolution': f"{video_fmt['resolution']} (+AUDIO)",
                    'filesize': 'Unknown',
                    'type': 'video+audio',
                    'quality': video_fmt['quality'] + 1000
                })
        
        return combined
    
    def deduplicate_and_sort_formats(self, formats):
        """Remove duplicates and sort formats by quality"""
        seen = set()
        unique_formats = []
        
        for f in formats:
            key = (f['resolution'], f['type'], f['quality'])
            if key not in seen:
                seen.add(key)
                unique_formats.append(f)
        
        # Sort by type and quality
        unique_formats.sort(key=lambda x: (
            0 if 'video' in x['type'] else 1,
            x['quality']
        ), reverse=True)
        
        return unique_formats
    
    def get_quality_value(self, resolution, format_dict=None):
        """Convert resolution to numeric value for sorting"""
        resolution_map = {
            '144P': 144, '240P': 240, '360P': 360, '480P': 480,
            '720P': 720, '1080P': 1080, '1440P': 1440, '2160P': 2160,
            '4320P': 4320, 'BEST': 10000, 'N/A': 0
        }
        
        # Try to get from resolution map
        quality = resolution_map.get(resolution.upper(), 0)
        
        # If not found, try to extract from height
        if quality == 0 and format_dict and format_dict.get('height'):
            quality = format_dict['height']
        
        return quality
    
    def format_duration(self, seconds):
        """Format duration in seconds to HH:MM:SS"""
        if not seconds:
            return "Unknown"
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        seconds = seconds % 60
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes:02d}:{seconds:02d}"
    
    def format_filesize(self, size_bytes):
        """Format file size in human readable format"""
        if not size_bytes:
            return "Unknown"
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"
    
    def progress_hook(self, d, progress_callback=None):
        """Progress hook for yt-dlp"""
        if d['status'] == 'downloading':
            total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            downloaded_bytes = d.get('downloaded_bytes', 0)
            
            percent = 0
            if total_bytes > 0:
                percent = (downloaded_bytes / total_bytes) * 100
            
            speed = d.get('speed', 0)
            eta = d.get('eta', 0)
            
            progress_info = {
                'status': 'downloading',
                'percent': round(percent, 1),
                'speed': f"{speed / 1024 / 1024:.1f} MB/s" if speed else "0 MB/s",
                'eta': f"{eta} seconds" if eta else "Unknown",
                'filesize': self.format_filesize(total_bytes),
                'filename': os.path.basename(d.get('filename', '')),
                'message': 'Downloading...'
            }
            
            if progress_callback:
                progress_callback(progress_info)
                
        elif d['status'] == 'finished':
            progress_info = {
                'status': 'processing',
                'percent': 100,
                'speed': '0 MB/s',
                'eta': '0 seconds',
                'filesize': self.format_filesize(d.get('total_bytes', 0)),
                'filename': os.path.basename(d.get('filename', '')),
                'message': 'Processing file...'
            }
            
            if progress_callback:
                progress_callback(progress_info)
    
    def download(self, url, format_id, download_type, downloads_folder, progress_callback=None):
        """Download video or audio"""
        try:
            # Create downloads folder if it doesn't exist
            os.makedirs(downloads_folder, exist_ok=True)
            
            # Configure download options
            ydl_opts = self.get_download_options(download_type, format_id, downloads_folder, progress_callback)
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                
                # Handle MP3 conversion
                if download_type == 'audio' or 'mp3' in format_id.lower():
                    filename = self.convert_to_mp3(filename, downloads_folder, progress_callback)
                
                logger.info(f"Download completed: {filename}")
                return filename
                
        except Exception as e:
            logger.error(f"Download error: {str(e)}")
            if progress_callback:
                progress_callback({
                    'status': 'error',
                    'message': f'Download failed: {str(e)}'
                })
            return None
    
    def get_download_options(self, download_type, format_id, downloads_folder, progress_callback):
        """Get appropriate download options"""
        base_opts = {
            'outtmpl': os.path.join(downloads_folder, '%(title)s.%(ext)s'),
            'progress_hooks': [lambda d: self.progress_hook(d, progress_callback)],
            'quiet': True,
            'no_warnings': False,
        }
        
        # Add platform-specific options
        base_opts.update(self.get_extractor_opts(''))
        
        if download_type == 'audio' or 'mp3' in format_id.lower():
            # Audio download with MP3 conversion
            base_opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            })
        elif '+' in format_id:
            # Combined format (video + audio)
            base_opts.update({
                'format': format_id,
                'merge_output_format': 'mp4',
            })
        else:
            # Specific format
            base_opts.update({
                'format': format_id,
            })
        
        return base_opts
    
    def convert_to_mp3(self, input_file, downloads_folder, progress_callback):
        """Convert downloaded file to MP3 using ffmpeg"""
        try:
            if not input_file or not os.path.exists(input_file):
                return input_file
            
            # If already MP3, return as is
            if input_file.lower().endswith('.mp3'):
                return input_file
            
            if progress_callback:
                progress_callback({
                    'status': 'processing',
                    'message': 'Converting to MP3...'
                })
            
            output_file = os.path.splitext(input_file)[0] + '.mp3'
            
            # Use ffmpeg to convert to MP3
            (
                ffmpeg
                .input(input_file)
                .output(output_file, audio_bitrate='192k', acodec='libmp3lame')
                .overwrite_output()
                .run(quiet=True, overwrite_output=True)
            )
            
            # Remove original file if conversion successful
            if os.path.exists(output_file):
                os.remove(input_file)
                return output_file
            else:
                return input_file
                
        except Exception as e:
            logger.error(f"MP3 conversion error: {str(e)}")
            if progress_callback:
                progress_callback({
                    'status': 'error',
                    'message': f'MP3 conversion failed: {str(e)}'
                })
            return input_file