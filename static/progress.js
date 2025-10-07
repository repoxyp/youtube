class VideoDownloader {
    constructor() {
        this.currentDownloadId = null;
        this.progressInterval = null;
        this.initializeEventListeners();
    }

    initializeEventListeners() {
        // URL form submission
        document.getElementById('urlForm').addEventListener('submit', (e) => {
            e.preventDefault();
            this.fetchFormats();
        });

        // Download button click
        document.getElementById('downloadBtn').addEventListener('click', () => {
            this.startDownload();
        });

        // Download file button
        document.getElementById('downloadFileBtn').addEventListener('click', () => {
            if (this.currentDownloadId) {
                window.open(`/download_file/${this.currentDownloadId}`, '_blank');
            }
        });
    }

    async fetchFormats() {
        const url = document.getElementById('videoUrl').value.trim();
        const fetchBtn = document.getElementById('fetchBtn');
        
        if (!url) {
            this.showError('Please enter a video URL');
            return;
        }

        // Reset previous state
        this.resetUI();

        fetchBtn.disabled = true;
        fetchBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Fetching...';

        try {
            const response = await fetch('/fetch_formats', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ url: url })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Failed to fetch video information');
            }

            this.displayVideoInfo(data);
            this.displayFormats(data.formats);

        } catch (error) {
            this.showError(error.message);
        } finally {
            fetchBtn.disabled = false;
            fetchBtn.innerHTML = '<i class="fas fa-search me-2"></i>Fetch Formats';
        }
    }

    resetUI() {
        // Hide all dynamic sections
        document.getElementById('videoInfoCard').classList.add('d-none');
        document.getElementById('formatsCard').classList.add('d-none');
        document.getElementById('progressCard').classList.add('d-none');
        document.getElementById('downloadComplete').classList.add('d-none');
        document.getElementById('downloadError').classList.add('d-none');
        document.getElementById('progressContent').classList.remove('d-none');
    }

    displayVideoInfo(videoInfo) {
        // Show video info card
        const videoCard = document.getElementById('videoInfoCard');
        videoCard.classList.remove('d-none');
        
        // Set video information
        document.getElementById('videoTitle').textContent = videoInfo.title;
        document.getElementById('videoUploader').textContent = videoInfo.uploader;
        document.getElementById('videoDuration').textContent = videoInfo.duration;
        
        // Set thumbnail
        const thumbnail = document.getElementById('videoThumbnail');
        if (videoInfo.thumbnail) {
            thumbnail.src = videoInfo.thumbnail;
            thumbnail.alt = videoInfo.title;
        } else {
            thumbnail.src = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="200" height="150" viewBox="0 0 200 150"><rect width="200" height="150" fill="%23ddd"/><text x="100" y="75" text-anchor="middle" dy=".3em" fill="%23999">No Thumbnail</text></svg>';
        }
    }

    displayFormats(formats) {
        const formatsList = document.getElementById('formatsList');
        formatsList.innerHTML = '';

        if (!formats || formats.length === 0) {
            formatsList.innerHTML = '<div class="alert alert-warning">No formats available for this video.</div>';
            // Hide download button if no formats
            document.getElementById('downloadBtn').style.display = 'none';
            return;
        }

        // Show download button
        document.getElementById('downloadBtn').style.display = 'block';

        formats.forEach(format => {
            const formatElement = this.createFormatElement(format);
            formatsList.appendChild(formatElement);
        });

        // Auto-select first format
        const firstFormat = document.querySelector('.format-option');
        if (firstFormat) {
            firstFormat.click();
        }

        // Show formats card
        document.getElementById('formatsCard').classList.remove('d-none');
    }

    createFormatElement(format) {
        const formatElement = document.createElement('div');
        formatElement.className = 'format-option';
        
        const typeBadge = this.getTypeBadge(format.type);
        const qualityClass = this.getQualityClass(format.quality);
        
        formatElement.innerHTML = `
            <div class="form-check">
                <input class="form-check-input" type="radio" name="format" 
                       id="format-${format.format_id}" value="${format.format_id}" 
                       data-type="${format.type}">
                <label class="form-check-label w-100" for="format-${format.format_id}">
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <strong class="${qualityClass}">${format.resolution}</strong>
                            ${typeBadge}
                            <span class="badge bg-secondary quality-badge ms-2">
                                ${format.ext.toUpperCase()}
                            </span>
                        </div>
                        <div class="text-muted text-end">
                            <div>${format.filesize}</div>
                            <small>${this.getFormatDescription(format)}</small>
                        </div>
                    </div>
                </label>
            </div>
        `;

        formatElement.addEventListener('click', () => {
            document.querySelectorAll('.format-option').forEach(opt => {
                opt.classList.remove('selected');
            });
            formatElement.classList.add('selected');
            const radio = formatElement.querySelector('input[type="radio"]');
            radio.checked = true;
        });

        return formatElement;
    }

    getTypeBadge(type) {
        const badges = {
            'video': 'bg-primary',
            'audio': 'bg-success',
            'video+audio': 'bg-info'
        };
        
        const badgeClass = badges[type] || 'bg-secondary';
        return `<span class="badge ${badgeClass} format-type-badge ms-2">${type.toUpperCase()}</span>`;
    }

    getQualityClass(quality) {
        if (quality >= 1080) return 'text-success';
        if (quality >= 720) return 'text-info';
        if (quality >= 480) return 'text-warning';
        return 'text-muted';
    }

    getFormatDescription(format) {
        if (format.type === 'audio') {
            return 'Audio Only';
        } else if (format.type === 'video') {
            return 'Video Only';
        } else if (format.type === 'video+audio') {
            return 'Video + Audio';
        }
        return '';
    }

    async startDownload() {
        const selectedFormat = document.querySelector('input[name="format"]:checked');
        if (!selectedFormat) {
            this.showError('Please select a format');
            return;
        }

        const url = document.getElementById('videoUrl').value.trim();
        const formatId = selectedFormat.value;
        const downloadType = this.getDownloadType(selectedFormat.getAttribute('data-type'));

        // Show progress card
        document.getElementById('progressCard').classList.remove('d-none');
        document.getElementById('progressContent').classList.remove('d-none');
        document.getElementById('downloadComplete').classList.add('d-none');
        document.getElementById('downloadError').classList.add('d-none');

        // Disable download button during download
        document.getElementById('downloadBtn').disabled = true;

        try {
            const response = await fetch('/download', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    url: url,
                    format_id: formatId,
                    type: downloadType
                })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Failed to start download');
            }

            this.currentDownloadId = data.download_id;
            this.startProgressTracking();

        } catch (error) {
            this.showProgressError(error.message);
            // Re-enable download button on error
            document.getElementById('downloadBtn').disabled = false;
        }
    }

    getDownloadType(formatType) {
        if (formatType === 'audio' || formatType.includes('mp3')) {
            return 'audio';
        }
        return 'video';
    }

    startProgressTracking() {
        if (this.progressInterval) {
            clearInterval(this.progressInterval);
        }

        this.progressInterval = setInterval(async () => {
            if (!this.currentDownloadId) return;

            try {
                const response = await fetch(`/progress/${this.currentDownloadId}`);
                const progress = await response.json();

                this.updateProgressUI(progress);

                if (progress.status === 'completed') {
                    clearInterval(this.progressInterval);
                    this.showDownloadComplete(progress);
                    // Re-enable download button
                    document.getElementById('downloadBtn').disabled = false;
                } else if (progress.status === 'error') {
                    clearInterval(this.progressInterval);
                    this.showProgressError(progress.message);
                    // Re-enable download button
                    document.getElementById('downloadBtn').disabled = false;
                }

            } catch (error) {
                console.error('Error fetching progress:', error);
            }
        }, 1000);
    }

    updateProgressUI(progress) {
        // Update progress bar
        const progressBar = document.getElementById('progressBar');
        const progressPercent = document.getElementById('progressPercent');
        
        progressBar.style.width = `${progress.percent}%`;
        progressPercent.textContent = `${progress.percent}%`;

        // Update other progress info
        document.getElementById('progressSpeed').textContent = progress.speed;
        document.getElementById('fileSize').textContent = progress.filesize;
        document.getElementById('eta').textContent = progress.eta;
        document.getElementById('statusMessage').textContent = progress.message;
        document.getElementById('currentFilename').textContent = progress.filename || '-';

        // Update progress bar color based on status
        progressBar.classList.remove('bg-success', 'bg-danger', 'bg-warning', 'bg-primary');
        if (progress.status === 'downloading') {
            progressBar.classList.add('bg-primary');
        } else if (progress.status === 'processing') {
            progressBar.classList.add('bg-warning');
        } else if (progress.status === 'error') {
            progressBar.classList.add('bg-danger');
        } else if (progress.status === 'completed') {
            progressBar.classList.add('bg-success');
        }
    }

    showDownloadComplete(progress) {
        document.getElementById('progressContent').classList.add('d-none');
        document.getElementById('downloadComplete').classList.remove('d-none');
        document.getElementById('completedFilename').textContent = progress.filename;
    }

    showProgressError(message) {
        document.getElementById('progressContent').classList.add('d-none');
        document.getElementById('downloadError').classList.remove('d-none');
        document.getElementById('errorMessage').textContent = message;
    }

    showError(message) {
        // Simple error display
        alert(`Error: ${message}`);
    }
}

// Global functions
function toggleDarkMode() {
    const html = document.documentElement;
    const currentTheme = html.getAttribute('data-bs-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    const icon = document.querySelector('.dark-mode-toggle i');
    
    html.setAttribute('data-bs-theme', newTheme);
    icon.className = newTheme === 'dark' ? 'fas fa-moon' : 'fas fa-sun';
}

function resetDownload() {
    document.getElementById('progressCard').classList.add('d-none');
    document.getElementById('downloadError').classList.add('d-none');
    document.getElementById('downloadBtn').disabled = false;
}

// Initialize the application when the page loads
document.addEventListener('DOMContentLoaded', () => {
    window.downloader = new VideoDownloader();
});