# 🎬 YouTube Downloader

A cross-platform graphical user interface (GUI) built with PyQt5 and [yt-dlp](https://github.com/yt-dlp/yt-dlp) for efficient YouTube video downloads. This application allows users to fetch metadata, choose video formats, and set custom output directories. It supports cookies authentication to resolve 403 errors and uses multithreading for smooth performance. **New:** It now supports downloading entire playlists sequentially, with full metadata for each video.

## 🔥 Why Use This Tool?

- **Cookies Authentication:** Works with [YouTube Cookies Exporter](https://github.com/reiarseni/youtube-cookies-exporter) to export Chrome cookies for seamless authentication.
- **Error Resolution:** Fixes 403 Forbidden errors and login issues.
- **High-Quality Downloads:** Ensures proper audio-video merging using `ffmpeg`.
- **Cross-Platform:** Runs on Windows, macOS, and Linux.
- **User-Friendly GUI:** Built with PyQt5 for ease of use.
- **Multithreading:** Maintains smooth UI interaction during downloads.
- **Persistent Configuration:** Saves user preferences in `config.json`.
- **Playlist Support:** Automatically loads playlists, displays video titles, and fetches full metadata and formats for each video. Double-click on a playlist item to view details.
- **Flexible Format Selection:** Choose from various resolutions and formats.
- **Custom Output Directory:** Set and open download folders with ease.

## 🛠 Installation

### 1️⃣ Prerequisites

Ensure you have Python 3.8+ installed.

Install dependencies with:

```sh
pip install yt-dlp PyQt5
```

You also need `ffmpeg` for video merging:

- **Windows:** Download from [FFmpeg official site](https://ffmpeg.org/download.html) and add it to your system PATH.
- **Linux (Debian/Ubuntu):**
  ```sh
  sudo apt update && sudo apt install ffmpeg
  ```
- **macOS:**
  ```sh
  brew install ffmpeg
  ```

### 2️⃣ Clone the Repository

```sh
git clone https://github.com/reiarseni/youtube-downloader.git
cd youtube-downloader
```

### 3️⃣ Run the Application

```sh
python main.py
```

## 📌 How to Use

1. **Cookies Setup:**  
   Install the [YouTube Cookies Exporter](https://github.com/reiarseni/youtube-cookies-exporter) Chrome extension, export your YouTube cookies, and save them as `cookies.txt`.

2. **Fetching Video Information:**  
   - Enter a video or playlist URL in the input field.
   - Click **Get Information** to load metadata and available formats.
   - If a playlist is detected, the application displays a list of videos. Full metadata for the first video is automatically loaded.
   - Double-click any video in the playlist to fetch and display its full metadata, description, and formats.

3. **Download Videos:**  
   - Select a download quality.
   - Choose an output folder (or open the folder directly with **Open Folder**).
   - Click **Download**. For playlists, the application will download videos sequentially until the last video is processed.

## ⚠️ Troubleshooting

- **403 Forbidden Error:**  
  Refresh your YouTube page, export your cookies again, and update the `cookies.txt`.

- **Download Issues:**  
  Verify that `ffmpeg` is correctly installed and in your system PATH.

- **Playlist Not Loading Properly:**  
  Ensure you use a valid playlist URL. Double-click a video in the playlist list to load its details.

## 📝 License

This project is open-source under the [MIT License](LICENSE).

---

🚀 **Enjoy seamless YouTube downloads and playlist management with ease!**
```