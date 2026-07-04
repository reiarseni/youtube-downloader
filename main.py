import sys
import os
import json
import logging
import shutil
import subprocess  # For opening folders
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QLabel,
    QFileDialog,
    QProgressBar,
    QMessageBox,
    QTextEdit,
    QComboBox,
)
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtGui import QIcon
import yt_dlp

logging.basicConfig(level=logging.DEBUG)


def get_cookie_file_path():
    """Returns the absolute path of the cookies.txt file located in the Downloads folder."""
    return os.path.join(os.path.expanduser("~"), "Downloads", "cookies.txt")


def get_js_runtimes():
    """Returns js_runtimes config for yt-dlp, detecting available runtimes."""
    runtimes = {}
    node_path = shutil.which("node")
    if node_path:
        runtimes["node"] = {"path": node_path}
    deno_path = shutil.which("deno")
    if deno_path:
        runtimes["deno"] = {"path": deno_path}
    return runtimes if runtimes else {"node": {}}


def check_cookies_exist():
    """Check if cookies.txt file exists and warn the user if it doesn't."""
    cookie_path = get_cookie_file_path()
    if not os.path.exists(cookie_path):
        logging.warning(f"Cookies file not found at: {cookie_path}")
        return False
    logging.debug(f"Cookies file found at: {cookie_path}")
    return True


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
            "format": self.quality_format,
            "merge_output_format": "mp4",
            "outtmpl": f"{self.output_path}/%(title)s_%(height)sp.%(ext)s",
            "progress_hooks": [self.my_hook],
            "cookiefile": get_cookie_file_path(),
            "verbose": False,
            "ignoreerrors": True,
            "nocheckcertificate": True,
            "retries": 10,
            "js_runtimes": get_js_runtimes(),
            # Download the Spanish subtitle only if available, preferring the
            # official one and falling back to the auto-generated (yt-dlp's
            # process_subtitles merges them with manual subs taking precedence).
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["es"],
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
        if d.get("status") == "downloading":
            self.progress_signal.emit(d)
        elif d.get("status") == "finished":
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
            "skip_download": True,
            "quiet": True,
            "cookiefile": get_cookie_file_path(),
            "ignoreerrors": True,
            "nocheckcertificate": True,
            "js_runtimes": get_js_runtimes(),
        }
        if self.flat and "list=" in self.url:
            ydl_opts["extract_flat"] = True
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
            if info is None:
                raise Exception(
                    "No information could be extracted. The video may be unavailable, private, or requires authentication."
                )
            if info.get("_type") == "playlist" or "entries" in info:
                pass
            elif not info.get("formats"):
                raise Exception(
                    "No formats available for this video. It may be unavailable or requires authentication."
                )
            self.info_signal.emit(info)
        except Exception as e:
            logging.exception("Error fetching information:")
            self.error_signal.emit(str(e))


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("YouTube Downloader with yt-dlp")
        self.setWindowIcon(QIcon("icon.png"))
        self.last_formats = None  # Will store the array of formats obtained
        self.last_metadata = {}  # Will store metadata (title, description, uploader, etc.)
        self.output_folder = None
        self.download_thread = None
        self.info_thread = None  # Thread to fetch complete info in a single request
        self.download_in_progress = False  # Flag to track active download
        self.last_downloaded_file = None  # Stores the last downloaded file path
        self.playlist_videos = []  # List to store playlist video objects (each with title and url)
        self.current_playlist_index = 0  # Current index in the playlist
        self.download_queue = []  # URLs (one per memo line) to download sequentially
        self.queue_index = 0  # Current position within download_queue
        self.full_info_thread = None  # Stores the thread for full metadata fetch
        self.setup_ui()
        self.load_config()

    def setup_ui(self):
        layout = QVBoxLayout()

        # URL input field (multi-line: one video or playlist URL per line)
        self.url_input = QTextEdit()
        self.url_input.setPlaceholderText(
            "Enter one YouTube video or playlist URL per line.\n"
            "All of them will be downloaded sequentially."
        )
        self.url_input.setMaximumHeight(110)
        layout.addWidget(self.url_input)

        # Button to fetch complete information (formats and metadata)
        self.fetch_button = QPushButton("Get Information")
        self.fetch_button.clicked.connect(self.fetch_info)
        layout.addWidget(self.fetch_button)

        self.videolist_label = QLabel("Video list:")
        layout.addWidget(self.videolist_label)

        # Playlist listbox added below Get Information
        self.playlist_list = QListWidget()
        # self.playlist_list.setPlaceholderText("Playlist videos will appear here...")
        self.playlist_list.itemDoubleClicked.connect(
            self.on_playlist_item_double_clicked
        )
        layout.addWidget(self.playlist_list)

        # Text area to display description and metadata
        self.metadata_label = QLabel("Metadata and description:")
        layout.addWidget(self.metadata_label)
        self.metadata_text = QTextEdit()
        self.metadata_text.setReadOnly(True)
        self.metadata_text.setPlaceholderText(
            "Video description and metadata will appear here..."
        )
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
        self.set_generic_quality_options()
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
            self.url_input.setPlainText(config.get("last_video", ""))
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
            # Rebuild quality options matching the saved context before restoring
            # the selection: video-specific for a single video, generic otherwise.
            if len(playlist) <= 1 and formats:
                self.set_video_quality_options(formats)
            else:
                self.set_generic_quality_options()
            # Load last selected quality from config, default to 720p if not found
            default_quality = self._video_format(720)
            quality = config.get("quality", default_quality)
            index = self.quality_combo.findData(quality)
            if index == -1:
                index = self.quality_combo.findData(default_quality)
            if index != -1:
                self.quality_combo.setCurrentIndex(index)
        except Exception as e:
            logging.info("Could not load config.json, using default configuration.")

    def save_config(self):
        """Saves current configuration to config.json, including metadata and playlist."""
        config = {
            "last_video": self.url_input.toPlainText().strip(),
            "last_output_folder": self.output_folder,
            "formats": self.last_formats if self.last_formats else [],
            "metadata": self.last_metadata if self.last_metadata else {},
            "quality": self.quality_combo.currentData(),
            "playlist": self.playlist_videos if self.playlist_videos else [],
            "current_playlist_index": self.current_playlist_index,
        }
        try:
            with open("config.json", "w") as f:
                json.dump(config, f, indent=4)
        except Exception as e:
            logging.error("Error saving configuration: %s", e)

    def get_urls(self):
        """Returns the list of non-empty, stripped URLs entered in the memo (one per line)."""
        return [
            line.strip()
            for line in self.url_input.toPlainText().splitlines()
            if line.strip()
        ]

    # Format selectors prefer the Spanish audio track when the video offers it,
    # falling back gracefully to the default audio (and to progressive formats).
    AUDIO_ONLY_FORMAT = "ba[language^=es]/ba"
    BEST_FORMAT = "bv*+ba[language^=es]/bv*+ba/b"

    @staticmethod
    def _video_format(height):
        """Format selector for a height cap, preferring Spanish audio if available."""
        return (
            f"bv*[height<={height}]+ba[language^=es]/"
            f"bv*[height<={height}]+ba/b[height<={height}]"
        )

    def set_generic_quality_options(self):
        """Loads the fixed, video-agnostic quality list (used for playlists)."""
        current = self.quality_combo.currentData()
        self.quality_combo.clear()
        for label, height in [
            ("Low 144p", 144),
            ("Low 240p", 240),
            ("Medium 360p", 360),
            ("Medium 480p", 480),
            ("High 720p", 720),
            ("High 1080p", 1080),
        ]:
            self.quality_combo.addItem(label, self._video_format(height))
        self.quality_combo.addItem("Audio Only", self.AUDIO_ONLY_FORMAT)
        self.quality_combo.addItem("Best Quality", self.BEST_FORMAT)
        self._restore_quality_selection(current)

    def set_video_quality_options(self, formats):
        """Builds the quality list from the resolutions actually available for a single video."""
        current = self.quality_combo.currentData()
        heights = sorted(
            {f.get("height") for f in formats if f.get("height")}
        )
        if not heights:
            # No video resolutions found (e.g. audio-only source); fall back to generic.
            self.set_generic_quality_options()
            return
        self.quality_combo.clear()
        for height in heights:
            self.quality_combo.addItem(f"{height}p", self._video_format(height))
        self.quality_combo.addItem("Audio Only", self.AUDIO_ONLY_FORMAT)
        self.quality_combo.addItem("Best Quality", self.BEST_FORMAT)
        self._restore_quality_selection(current)

    def _restore_quality_selection(self, quality_data):
        """Reselects a previously chosen quality if it is still available."""
        if quality_data is None:
            return
        index = self.quality_combo.findData(quality_data)
        if index != -1:
            self.quality_combo.setCurrentIndex(index)

    def populate_formats(self, formats):
        """Populates the format list in the QListWidget."""
        self.format_list.clear()
        self.last_formats = formats
        for f in formats:
            format_id = f.get("format_id")
            ext = f.get("ext")
            resolution = f.get("resolution") or (
                str(f.get("height")) if f.get("height") else "N/A"
            )
            filesize = f.get("filesize") or 0
            filesize_str = f"{filesize / 1024 / 1024:.2f} MB" if filesize else "Unknown"
            item_text = f"Ext: {ext} | Resolution: {resolution} | Size: {filesize_str}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, format_id)
            self.format_list.addItem(item)

    def populate_formats_from_config(self, formats):
        """Populates the QListWidget with formats saved in config."""
        self.format_list.clear()
        for f in formats:
            format_id = f.get("format_id")
            ext = f.get("ext")
            resolution = f.get("resolution") or (
                str(f.get("height")) if f.get("height") else "N/A"
            )
            filesize = f.get("filesize") or 0
            filesize_str = f"{filesize / 1024 / 1024:.2f} MB" if filesize else "Unknown"
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
        """Fetches information for the first URL in the memo (preview/metadata/quality)."""
        urls = self.get_urls()
        if not urls:
            QMessageBox.warning(self, "Error", "Please enter a valid URL.")
            return
        url = urls[0]

        # Check if cookies file exists
        if not check_cookies_exist():
            cookie_path = get_cookie_file_path()
            reply = QMessageBox.question(
                self,
                "Cookies Not Found",
                f"The cookies file was not found at:\n{cookie_path}\n\n"
                "Without cookies, you may encounter errors or be unable to download some videos.\n\n"
                "Do you want to continue anyway?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply == QMessageBox.No:
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
        if "entries" in info:
            self.playlist_videos = []
            self.playlist_list.clear()
            for entry in info.get("entries", []):
                if entry is None:
                    continue
                title = entry.get("title", "Unknown Title")
                video_url = entry.get("webpage_url")
                # If extract_flat was used, webpage_url may be missing; build it from video id
                if not video_url:
                    video_id = entry.get("id")
                    if video_id:
                        video_url = f"https://www.youtube.com/watch?v={video_id}"
                    else:
                        video_url = (self.get_urls() or [""])[0]
                self.playlist_videos.append({"title": title, "url": video_url})
                item = QListWidgetItem(title)
                item.setData(Qt.UserRole, video_url)
                self.playlist_list.addItem(item)
            self.current_playlist_index = 0
            self.playlist_list.setCurrentRow(self.current_playlist_index)
            # Playlists keep a single, general quality applied to every video
            self.set_generic_quality_options()
            # Automatically fetch full metadata for the first video in the playlist
            if self.playlist_videos:
                first_video_url = self.playlist_videos[0].get("url")
                self.load_video_info(first_video_url)
            self.status_label.setText(
                "Playlist loaded. Select a quality and press 'Download'."
            )
        else:
            # Single video case
            video_title = info.get("title", "Unknown Title")
            video_url = info.get("webpage_url", (self.get_urls() or [""])[0])
            self.playlist_videos = [{"title": video_title, "url": video_url}]
            self.playlist_list.clear()
            item = QListWidgetItem(video_title)
            item.setData(Qt.UserRole, video_url)
            self.playlist_list.addItem(item)
            self.current_playlist_index = 0
            self.populate_formats(info.get("formats", []))
            # Several URLs in the memo are a batch: keep one general quality.
            # A single video offers only the resolutions it actually has.
            if len(self.get_urls()) > 1:
                self.set_generic_quality_options()
            else:
                self.set_video_quality_options(info.get("formats", []))
            metadata = {
                "title": info.get("title", ""),
                "description": info.get("description", ""),
                "uploader": info.get("uploader", ""),
                "upload_date": info.get("upload_date", ""),
            }
            self.last_metadata = metadata
            self.update_metadata_text(metadata)
            self.status_label.setText(
                "Information loaded. Select a quality and press 'Download'."
            )
        self.save_config()

    def load_video_info(self, video_url):
        """Fetch full metadata/description/formats for a given video URL."""
        self.status_label.setText("Fetching full video information...")
        # Store the thread in a member variable to prevent it from being destroyed prematurely
        self.full_info_thread = InfoFetchThread(video_url, flat=False)
        self.full_info_thread.info_signal.connect(self.update_video_info)
        self.full_info_thread.error_signal.connect(self.info_error)
        self.full_info_thread.finished.connect(
            lambda: setattr(self, "full_info_thread", None)
        )
        self.full_info_thread.start()

    def update_video_info(self, info):
        """Update metadata, formats, and description based on full video info."""
        self.populate_formats(info.get("formats", []))
        metadata = {
            "title": info.get("title", ""),
            "description": info.get("description", ""),
            "uploader": info.get("uploader", ""),
            "upload_date": info.get("upload_date", ""),
        }
        self.last_metadata = metadata
        self.update_metadata_text(metadata)
        self.status_label.setText("Full video information loaded.")

    def on_playlist_item_double_clicked(self, item):
        """When a playlist video is double-clicked, fetch its full metadata and update UI."""
        video_url = item.data(Qt.UserRole)
        self.current_playlist_index = self.playlist_list.currentRow()
        # Preview only: do not overwrite the memo, which holds the download list.
        self.load_video_info(video_url)

    def info_error(self, error_msg):
        error_lower = error_msg.lower()
        if (
            "unavailable" in error_lower
            or "authentication" in error_lower
            or "not available" in error_lower
        ):
            cookie_path = get_cookie_file_path()
            full_msg = f"Error fetching information: {error_msg}\n\n"
            full_msg += "This error may be caused by:\n"
            full_msg += "- Video is private, deleted, or geo-restricted\n"
            full_msg += "- Cookies are expired or invalid\n\n"
            full_msg += f"Try updating your cookies at:\n{cookie_path}\n\n"
            full_msg += "Use a browser extension to export fresh YouTube cookies."
            QMessageBox.critical(self, "Error", full_msg)
        else:
            QMessageBox.critical(
                self, "Error", f"Error fetching information: {error_msg}"
            )
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
        if os.name == "nt" and self.last_downloaded_file:
            try:
                subprocess.Popen(["explorer", "/select,", self.last_downloaded_file])
                return
            except Exception as e:
                pass  # Fallback if error occurs
        if sys.platform.startswith("darwin"):
            subprocess.Popen(["open", self.output_folder])
        elif os.name == "nt":
            os.startfile(self.output_folder)
        elif os.name == "posix":
            subprocess.Popen(["xdg-open", self.output_folder])
        else:
            QMessageBox.warning(
                self, "Error", "Platform not supported for opening folder."
            )

    def start_download(self):
        # Build the download queue from the memo: one URL per line, downloaded in order.
        # A playlist URL is handled by yt-dlp itself (it downloads all of its items).
        urls = self.get_urls()
        if not urls:
            QMessageBox.warning(self, "Error", "Enter a valid URL.")
            return

        # Check if cookies file exists
        if not check_cookies_exist():
            cookie_path = get_cookie_file_path()
            reply = QMessageBox.question(
                self,
                "Cookies Not Found",
                f"The cookies file was not found at:\n{cookie_path}\n\n"
                "Without cookies, the download may fail with a 403 error.\n\n"
                "Do you want to continue anyway?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply == QMessageBox.No:
                return

        if not self.output_folder:
            QMessageBox.warning(self, "Error", "Select an output folder.")
            return

        if not self.quality_combo.currentData():
            QMessageBox.warning(self, "Error", "Select a download quality.")
            return

        self.download_queue = urls
        self.queue_index = 0
        self.toggle_buttons(False)
        self._download_next_in_queue()

    def _download_next_in_queue(self):
        """Starts the download of the current queue item."""
        url = self.download_queue[self.queue_index]
        quality_format = self.quality_combo.currentData()
        self.progress_bar.setValue(0)
        self.status_label.setText(
            f"Downloading {self.queue_index + 1} of {len(self.download_queue)}..."
        )

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
        if data.get("status") == "downloading":
            total_bytes = data.get("total_bytes") or data.get("total_bytes_estimate")
            downloaded = data.get("downloaded_bytes", 0)
            speed = data.get("speed", 0)  # bytes per second
            eta = data.get("eta", 0)  # seconds
            if total_bytes:
                progress = int(downloaded * 100 / total_bytes)
                self.progress_bar.setValue(progress)
                # Convert speed to MB/s if available
                speed_mb = speed / (1024 * 1024) if speed else 0
                eta_formatted = self.format_eta(eta)
                self.status_label.setText(
                    f"Downloading: {progress}% "
                    f"({downloaded / 1024 / 1024:.2f} MB of {total_bytes / 1024 / 1024:.2f} MB) | "
                    f"Speed: {speed_mb:.2f} MB/s | ETA: {eta_formatted}"
                )
        elif data.get("status") == "finished":
            self.progress_bar.setValue(100)
            self.status_label.setText("Download finished.")
            if data.get("filename"):
                self.last_downloaded_file = data.get("filename")

    def download_finished(self):
        self.download_in_progress = False
        # If there are more URLs queued, automatically download the next one.
        if self.queue_index < len(self.download_queue) - 1:
            self.queue_index += 1
            self._download_next_in_queue()
            return
        QMessageBox.information(
            self, "Download complete", "The video(s) were downloaded successfully."
        )
        self.toggle_buttons(True)
        self.progress_bar.setValue(0)
        self.save_config()

    def download_error(self, error_msg):
        self.download_in_progress = False  # Reset flag on download error
        error_lower = error_msg.lower()
        if (
            "403" in error_lower
            or "forbidden" in error_lower
            or "authentication" in error_lower
        ):
            cookie_path = get_cookie_file_path()
            full_msg = f"An error occurred during download:\n{error_msg}\n\n"
            full_msg += "This error is likely caused by:\n"
            full_msg += "- Cookies are expired or invalid\n"
            full_msg += "- Video requires authentication\n\n"
            full_msg += f"Update your cookies at:\n{cookie_path}\n\n"
            full_msg += "Use a browser extension to export fresh YouTube cookies."
            QMessageBox.critical(self, "Download error", full_msg)
        else:
            QMessageBox.critical(
                self,
                "Download error",
                f"An error occurred during download:\n{error_msg}",
            )
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
            msg_box.setText(
                "A video is currently downloading.\nAre you sure you want to exit?"
            )
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


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.resize(600, 600)
    window.show()
    sys.exit(app.exec_())
