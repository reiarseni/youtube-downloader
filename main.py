import sys
import os
import json
import logging
import subprocess  # For opening folders
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QLineEdit, QPushButton, QListWidget, QListWidgetItem, QLabel, QFileDialog,
                             QProgressBar, QMessageBox, QTextEdit, QComboBox)
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtGui import QIcon
import yt_dlp

logging.basicConfig(level=logging.DEBUG)

def get_cookie_file_path():
    """Returns the absolute path of the cookies.txt file located in the Downloads folder."""
    return os.path.join(os.path.expanduser("~"), "Downloads", "cookies.txt")

class DownloadThread(QThread):
    progress_signal = pyqtSignal(dict)
    finished_signal = pyqtSignal()
    error_signal = pyqtSignal(str)

    def __init__(self, url, quality_format, output_path):
        super().__init__()
        self.url = url
        self.quality_format = quality_format  # Selected quality format from the user
        self.output_path = output_path
        self.cancelled = False  # Cancellation flag

    def cancel(self):
        """Set the cancellation flag to True to cooperatively stop the download."""
        self.cancelled = True

    def run(self):
        ydl_opts = {
            'format': self.quality_format,  # Now linked to the selected quality option
            'merge_output_format': True,
            'outtmpl': f'{self.output_path}/%(title)s_%(height)sp.%(ext)s',
            'progress_hooks': [self.my_hook],
            # 'noplaylist': True,
            'cookiefile': get_cookie_file_path(),
            # 'http_headers': {'User-Agent': 'Mozilla/5.0 ...'},
            # 'fragment_retries': 'infinite',
            # 'retries': 3,
            'verbose': True,
            'extractor_args': "youtube:player_client=android"  # ios / tv / web_safari / web / android / tv_embedded
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([self.url])
            self.finished_signal.emit()
        except Exception as e:
            logging.exception("Error during download:")
            self.error_signal.emit(str(e))

    def my_hook(self, d):
        # Check cancellation flag in the progress hook
        if self.cancelled:
            raise Exception("Download cancelled by user")
        if d.get('status') == 'downloading':
            self.progress_signal.emit(d)
        elif d.get('status') == 'finished':
            self.progress_signal.emit(d)

class InfoFetchThread(QThread):
    """
    Thread that performs a single request to fetch video or playlist information:
    formats, description, and other metadata.
    """
    info_signal = pyqtSignal(dict)
    error_signal = pyqtSignal(str)

    def __init__(self, url, flat=True):
        super().__init__()
        self.url = url
        self.flat = flat  # If True, perform flat extraction (for playlists); if False, full extraction
        self.cancelled = False  # Cancellation flag

    def cancel(self):
        """Set the cancellation flag to True to cooperatively stop fetching."""
        self.cancelled = True

    def run(self):
        if self.cancelled:
            return  # Exit if cancellation was requested before starting
        ydl_opts = {
            'skip_download': True,
            'quiet': True,
            'cookiefile': get_cookie_file_path(),
            'http_headers': {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                                           'AppleWebKit/537.36 (KHTML, like Gecko) '
                                           'Chrome/91.0.4472.124 Safari/537.36'},
        }
        if self.flat and "list=" in self.url:
            ydl_opts["extract_flat"] = True
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
            self.info_signal.emit(info)
        except Exception as e:
            logging.exception("Error fetching information:")
            self.error_signal.emit(str(e))

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("YouTube Downloader with yt-dlp")
        self.setWindowIcon(QIcon("icon.png"))
        self.last_formats = None      # Will store the array of formats obtained
        self.last_metadata = {}       # Will store metadata (title, description, uploader, etc.)
        self.output_folder = None
        self.download_thread = None
        self.info_thread = None       # Thread to fetch complete info in a single request
        self.download_in_progress = False  # Flag to track active download
        self.last_downloaded_file = None   # Stores the last downloaded file path
        self.playlist_videos = []          # List to store playlist video objects (each with title and url)
        self.current_playlist_index = 0    # Current index in the playlist
        self.full_info_thread = None       # Stores the thread for full metadata fetch
        self.setup_ui()
        self.load_config()

    def setup_ui(self):
        layout = QVBoxLayout()

        # URL input field
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Enter the YouTube video or playlist URL")
        layout.addWidget(self.url_input)

        # Button to fetch complete information (formats and metadata)
        self.fetch_button = QPushButton("Get Information")
        self.fetch_button.clicked.connect(self.fetch_info)
        layout.addWidget(self.fetch_button)

        self.videolist_label = QLabel("Video list:")
        layout.addWidget(self.videolist_label)

        # Playlist listbox added below Get Information
        self.playlist_list = QListWidget()
        #self.playlist_list.setPlaceholderText("Playlist videos will appear here...")
        self.playlist_list.itemDoubleClicked.connect(self.on_playlist_item_double_clicked)
        layout.addWidget(self.playlist_list)

        # Text area to display description and metadata
        self.metadata_label = QLabel("Metadata and description:")
        layout.addWidget(self.metadata_label)
        self.metadata_text = QTextEdit()
        self.metadata_text.setReadOnly(True)
        self.metadata_text.setPlaceholderText("Video description and metadata will appear here...")
        layout.addWidget(self.metadata_text)

        self.videolist_label = QLabel("Formats:")
        layout.addWidget(self.videolist_label)

        # List to display available formats (retained for legacy purposes)
        self.format_list = QListWidget()
        layout.addWidget(self.format_list)

        # Output folder selection with additional Open Folder button
        folder_layout = QHBoxLayout()
        self.folder_label = QLabel("Output folder: (Not selected)")
        self.folder_button = QPushButton("Select Folder")
        self.folder_button.clicked.connect(self.select_folder)
        folder_layout.addWidget(self.folder_label)
        folder_layout.addWidget(self.folder_button)
        self.open_folder_button = QPushButton("Open Folder")
        self.open_folder_button.clicked.connect(self.open_folder)
        folder_layout.addWidget(self.open_folder_button)
        layout.addLayout(folder_layout)

        # Quality selection dropdown
        quality_layout = QHBoxLayout()
        self.quality_label = QLabel("Select Quality:")
        self.quality_combo = QComboBox()
        self.quality_combo.addItem("Low 144p", "bestvideo[ext=mp4][height<=144]+bestaudio[ext=m4a]")
        self.quality_combo.addItem("Low 240p", "bestvideo[ext=mp4][height<=240]+bestaudio[ext=m4a]")
        self.quality_combo.addItem("Medium 360p", "bestvideo[ext=mp4][height<=360]+bestaudio[ext=m4a]")
        self.quality_combo.addItem("Medium 480p", "bestvideo[ext=mp4][height<=480]+bestaudio[ext=m4a]")
        self.quality_combo.addItem("Higth 720p", "bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]")
        self.quality_combo.addItem("Higth 1080p", "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]")
        self.quality_combo.addItem("Audio Only", "bestaudio[ext=m4a]")
        quality_layout.addWidget(self.quality_label)
        quality_layout.addWidget(self.quality_combo)
        layout.addLayout(quality_layout)

        # Download and Stop buttons
        buttons_layout = QHBoxLayout()
        self.download_button = QPushButton("Download")
        self.download_button.clicked.connect(self.start_download)
        buttons_layout.addWidget(self.download_button)
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop_operation)
        buttons_layout.addWidget(self.stop_button)
        layout.addLayout(buttons_layout)

        # Progress bar and status label
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        self.setLayout(layout)

    def load_config(self):
        """Loads configuration from config.json, if it exists."""
        try:
            with open("config.json", "r") as f:
                config = json.load(f)
            self.url_input.setText(config.get("last_video", ""))
            self.output_folder = config.get("last_output_folder", None)
            if self.output_folder:
                self.folder_label.setText(f"Output folder: {self.output_folder}")
            formats = config.get("formats", [])
            if formats:
                self.populate_formats_from_config(formats)
                self.last_formats = formats
            metadata = config.get("metadata", {})
            if metadata:
                self.last_metadata = metadata
                self.update_metadata_text(metadata)
            # Load playlist from config if available
            playlist = config.get("playlist", [])
            if playlist:
                self.playlist_videos = playlist
                self.playlist_list.clear()
                for video in playlist:
                    title = video.get("title", "Unknown Title")
                    item = QListWidgetItem(title)
                    item.setData(Qt.UserRole, video.get("url", ""))
                    self.playlist_list.addItem(item)
                self.current_playlist_index = config.get("current_playlist_index", 0)
                self.playlist_list.setCurrentRow(self.current_playlist_index)
            # Load last selected quality from config, default to 720p if not found
            quality = config.get("quality", "bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]")
            index = self.quality_combo.findData(quality)
            if index != -1:
                self.quality_combo.setCurrentIndex(index)
            else:
                index = self.quality_combo.findData("bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]")
                self.quality_combo.setCurrentIndex(index)
        except Exception as e:
            logging.info("Could not load config.json, using default configuration.")

    def save_config(self):
        """Saves current configuration to config.json, including metadata and playlist."""
        config = {
            "last_video": self.url_input.text().strip(),
            "last_output_folder": self.output_folder,
            "formats": self.last_formats if self.last_formats else [],
            "metadata": self.last_metadata if self.last_metadata else {},
            "quality": self.quality_combo.currentData(),
            "playlist": self.playlist_videos if self.playlist_videos else [],
            "current_playlist_index": self.current_playlist_index
        }
        try:
            with open("config.json", "w") as f:
                json.dump(config, f, indent=4)
        except Exception as e:
            logging.error("Error saving configuration: %s", e)

    def populate_formats(self, formats):
        """Populates the format list in the QListWidget."""
        self.format_list.clear()
        self.last_formats = formats
        for f in formats:
            format_id = f.get('format_id')
            ext = f.get('ext')
            resolution = f.get('resolution') or (str(f.get('height')) if f.get('height') else 'N/A')
            filesize = f.get('filesize') or 0
            filesize_str = f"{filesize/1024/1024:.2f} MB" if filesize else "Unknown"
            item_text = f"Ext: {ext} | Resolution: {resolution} | Size: {filesize_str}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, format_id)
            self.format_list.addItem(item)

    def populate_formats_from_config(self, formats):
        """Populates the QListWidget with formats saved in config."""
        self.format_list.clear()
        for f in formats:
            format_id = f.get('format_id')
            ext = f.get('ext')
            resolution = f.get('resolution') or (str(f.get('height')) if f.get('height') else 'N/A')
            filesize = f.get('filesize') or 0
            filesize_str = f"{filesize/1024/1024:.2f} MB" if filesize else "Unknown"
            item_text = f"Ext: {ext} | Resolution: {resolution} | Size: {filesize_str}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, format_id)
            self.format_list.addItem(item)

    def update_metadata_text(self, metadata):
        """Updates the QTextEdit with formatted metadata and description."""
        text = (
            f"Title: {metadata.get('title', '')}\n"
            f"Uploader: {metadata.get('uploader', '')}\n"
            f"Upload Date: {metadata.get('upload_date', '')}\n\n"
            f"Description:\n{metadata.get('description', '')}"
        )
        self.metadata_text.setPlainText(text)

    def fetch_info(self):
        """Fetches all video information (formats/metadata or playlist entries) in a single request."""
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Error", "Please enter a valid URL.")
            return

        # Clear the playlist, format list, and metadata area
        self.playlist_list.clear()
        self.format_list.clear()
        self.metadata_text.clear()
        self.status_label.setText("Fetching video information...")
        self.toggle_buttons(False)

        self.info_thread = InfoFetchThread(url, flat=True)
        self.info_thread.info_signal.connect(self.process_info)
        self.info_thread.error_signal.connect(self.info_error)
        self.info_thread.finished.connect(lambda: self.toggle_buttons(True))
        self.info_thread.start()

    def process_info(self, info):
        # Check if the info represents a playlist
        if 'entries' in info:
            self.playlist_videos = []
            self.playlist_list.clear()
            for entry in info.get('entries', []):
                if entry is None:
                    continue
                title = entry.get('title', 'Unknown Title')
                video_url = entry.get('webpage_url')
                # If extract_flat was used, webpage_url may be missing; build it from video id
                if not video_url:
                    video_id = entry.get('id')
                    if video_id:
                        video_url = f"https://www.youtube.com/watch?v={video_id}"
                    else:
                        video_url = self.url_input.text()
                self.playlist_videos.append({"title": title, "url": video_url})
                item = QListWidgetItem(title)
                item.setData(Qt.UserRole, video_url)
                self.playlist_list.addItem(item)
            self.current_playlist_index = 0
            self.playlist_list.setCurrentRow(self.current_playlist_index)
            # Automatically fetch full metadata for the first video in the playlist
            if self.playlist_videos:
                first_video_url = self.playlist_videos[0].get("url")
                self.load_video_info(first_video_url)
            self.status_label.setText("Playlist loaded. Select a quality and press 'Download'.")
        else:
            # Single video case
            video_title = info.get("title", "Unknown Title")
            video_url = info.get("webpage_url", self.url_input.text())
            self.playlist_videos = [{"title": video_title, "url": video_url}]
            self.playlist_list.clear()
            item = QListWidgetItem(video_title)
            item.setData(Qt.UserRole, video_url)
            self.playlist_list.addItem(item)
            self.current_playlist_index = 0
            self.populate_formats(info.get('formats', []))
            metadata = {
                "title": info.get("title", ""),
                "description": info.get("description", ""),
                "uploader": info.get("uploader", ""),
                "upload_date": info.get("upload_date", "")
            }
            self.last_metadata = metadata
            self.update_metadata_text(metadata)
            self.status_label.setText("Information loaded. Select a quality and press 'Download'.")
        self.save_config()

    def load_video_info(self, video_url):
        """Fetch full metadata/description/formats for a given video URL."""
        self.status_label.setText("Fetching full video information...")
        # Store the thread in a member variable to prevent it from being destroyed prematurely
        self.full_info_thread = InfoFetchThread(video_url, flat=False)
        self.full_info_thread.info_signal.connect(self.update_video_info)
        self.full_info_thread.error_signal.connect(self.info_error)
        self.full_info_thread.finished.connect(lambda: setattr(self, 'full_info_thread', None))
        self.full_info_thread.start()

    def update_video_info(self, info):
        """Update metadata, formats, and description based on full video info."""
        self.populate_formats(info.get('formats', []))
        metadata = {
            "title": info.get("title", ""),
            "description": info.get("description", ""),
            "uploader": info.get("uploader", ""),
            "upload_date": info.get("upload_date", "")
        }
        self.last_metadata = metadata
        self.update_metadata_text(metadata)
        self.status_label.setText("Full video information loaded.")

    def on_playlist_item_double_clicked(self, item):
        """When a playlist video is double-clicked, fetch its full metadata and update UI."""
        video_url = item.data(Qt.UserRole)
        self.current_playlist_index = self.playlist_list.currentRow()
        self.url_input.setText(video_url)
        self.load_video_info(video_url)

    def info_error(self, error_msg):
        QMessageBox.critical(self, "Error", f"Error fetching information: {error_msg}")
        self.status_label.setText("Error fetching information.")
        self.toggle_buttons(True)

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select output folder")
        if folder:
            self.folder_label.setText(f"Output folder: {folder}")
            self.output_folder = folder
            self.save_config()
        else:
            self.output_folder = None

    def open_folder(self):
        """Opens the download folder. On Windows, if the last downloaded file is known, highlight it."""
        if not self.output_folder:
            QMessageBox.warning(self, "Error", "No folder selected.")
            return
        if os.name == 'nt' and self.last_downloaded_file:
            try:
                subprocess.Popen(['explorer', '/select,', self.last_downloaded_file])
                return
            except Exception as e:
                pass  # Fallback if error occurs
        if sys.platform.startswith('darwin'):
            subprocess.Popen(["open", self.output_folder])
        elif os.name == 'nt':
            os.startfile(self.output_folder)
        elif os.name == 'posix':
            subprocess.Popen(["xdg-open", self.output_folder])
        else:
            QMessageBox.warning(self, "Error", "Platform not supported for opening folder.")

    def start_download(self):
        # Determine the URL to download: if playlist exists, use current playlist video
        if self.playlist_videos:
            video = self.playlist_videos[self.current_playlist_index]
            url = video.get("url")
        else:
            url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Error", "Enter a valid URL.")
            return

        if not self.output_folder:
            QMessageBox.warning(self, "Error", "Select an output folder.")
            return

        quality_format = self.quality_combo.currentData()
        if not quality_format:
            QMessageBox.warning(self, "Error", "Select a download quality.")
            return

        self.toggle_buttons(False)
        self.status_label.setText("Downloading...")

        self.download_thread = DownloadThread(url, quality_format, self.output_folder)
        self.download_thread.progress_signal.connect(self.update_progress)
        self.download_thread.finished_signal.connect(self.download_finished)
        self.download_thread.error_signal.connect(self.download_error)
        self.download_thread.start()
        self.download_in_progress = True  # Set flag on download start

    def format_eta(self, seconds):
        """Formats the ETA in a user-friendly format (hours, minutes, seconds)."""
        try:
            seconds = int(seconds)
        except (ValueError, TypeError):
            return "N/A"
        if seconds <= 0:
            return "0s"
        hours, remainder = divmod(seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        parts = []
        if hours:
            parts.append(f"{hours}h")
        if minutes:
            parts.append(f"{minutes}m")
        parts.append(f"{secs}s")
        return " ".join(parts)

    def update_progress(self, data):
        if data.get('status') == 'downloading':
            total_bytes = data.get('total_bytes') or data.get('total_bytes_estimate')
            downloaded = data.get('downloaded_bytes', 0)
            speed = data.get('speed', 0)  # bytes per second
            eta = data.get('eta', 0)      # seconds
            if total_bytes:
                progress = int(downloaded * 100 / total_bytes)
                self.progress_bar.setValue(progress)
                # Convert speed to MB/s if available
                speed_mb = speed / (1024 * 1024) if speed else 0
                eta_formatted = self.format_eta(eta)
                self.status_label.setText(
                    f"Downloading: {progress}% "
                    f"({downloaded/1024/1024:.2f} MB of {total_bytes/1024/1024:.2f} MB) | "
                    f"Speed: {speed_mb:.2f} MB/s | ETA: {eta_formatted}"
                )
        elif data.get('status') == 'finished':
            self.progress_bar.setValue(100)
            self.status_label.setText("Download finished.")
            if data.get('filename'):
                self.last_downloaded_file = data.get('filename')

    def download_finished(self):
        # If a playlist is loaded and there are more videos, auto-advance to the next video.
        if self.playlist_videos and self.current_playlist_index < len(self.playlist_videos) - 1:
            self.current_playlist_index += 1
            self.playlist_list.setCurrentRow(self.current_playlist_index)
            next_video = self.playlist_videos[self.current_playlist_index]
            self.url_input.setText(next_video.get("url"))
            self.download_in_progress = False
            # Automatically start download for the next video
            self.start_download()
            return
        self.download_in_progress = False  # Reset flag on download finish
        QMessageBox.information(self, "Download complete", "The video(s) were downloaded successfully.")
        self.toggle_buttons(True)
        self.progress_bar.setValue(0)
        self.save_config()

    def download_error(self, error_msg):
        self.download_in_progress = False  # Reset flag on download error
        QMessageBox.critical(self, "Download error", f"An error occurred during download:\n{error_msg}")
        self.toggle_buttons(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("Download error.")

    def stop_operation(self):
        """Stops any ongoing operation (download or information fetch) cooperatively."""
        threads_stopped = False
        if self.download_thread is not None and self.download_thread.isRunning():
            self.download_thread.cancel()  # Use cooperative cancellation instead of terminate()
            self.download_thread.wait()
            self.download_thread = None
            self.download_in_progress = False
            threads_stopped = True
        if self.info_thread is not None and self.info_thread.isRunning():
            self.info_thread.cancel()
            self.info_thread.wait()
            self.info_thread = None
            threads_stopped = True
        if threads_stopped:
            self.status_label.setText("Operation stopped.")
            self.progress_bar.setValue(0)
            self.toggle_buttons(True)

    def toggle_buttons(self, enable):
        """Enables or disables the main interface buttons."""
        self.download_button.setEnabled(enable)
        self.fetch_button.setEnabled(enable)
        self.folder_button.setEnabled(enable)
        self.stop_button.setEnabled(not enable)

    def closeEvent(self, event):
        # If a download is in progress, show a confirmation dialog.
        if self.download_in_progress:
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Confirmation")
            msg_box.setText("A video is currently downloading.\nAre you sure you want to exit?")
            accept_button = msg_box.addButton("Accept", QMessageBox.AcceptRole)
            cancel_button = msg_box.addButton("Cancel", QMessageBox.RejectRole)
            msg_box.setDefaultButton(cancel_button)
            msg_box.exec_()
            if msg_box.clickedButton() == accept_button:
                self.save_config()
                event.accept()
            else:
                event.ignore()
        else:
            self.save_config()
            event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.resize(600, 600)
    window.show()
    sys.exit(app.exec_())
