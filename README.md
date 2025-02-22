# 🎬 Youtube Downloader

A cross-platform graphical user interface (GUI) built with PyQt5 and `yt-dlp` for downloading YouTube videos efficiently. The application allows users to fetch metadata, choose video formats, and set custom output directories. It also supports cookies authentication to resolve 403 errors and authentication issuess and uses multithreading to ensure smooth performance.

## 🔥 Why Use This Tool?

✅ Works with [YouTube Cookies Exporter](https://github.com/reiarseni/youtube-cookies-exporter) to extract cookies from Chrome  
✅ Supports cookies authentication (Fixes authentication issues)  
✅ Resolves 403 Forbidden errors that prevent video downloads  
✅ Supports high-quality downloads by ensuring proper audio-video merging with `ffmpeg`  
✅ Cross-platform – Works on Windows, macOS, and Linux  
✅ User-friendly GUI built with PyQt5 for ease of use  
✅ Multi-threaded for smooth UI interaction  
✅ Saves user preferences in `config.json`  
✅ Fetch video metadata and available formats  
✅ Download videos in different resolutions and formats  
✅ Set custom output directories for downloaded files  

---

## 🛠 Installation

### 1️⃣ Install Dependencies

Make sure you have Python 3.8+ installed.

```sh
pip install yt-dlp PyQt5
```

You also need `ffmpeg` for proper video merging. Install it as follows:

- **Windows:** Download from [FFmpeg official site](https://ffmpeg.org/download.html) and add it to the system path.
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
git clone https://github.com/yourusername/yt-dlp-gui-downloader.git
cd yt-dlp-gui-downloader
```

### 3️⃣ Run the Application

```sh
python main.py
```

---

## 📌 How to Use

1️⃣ Install the [YouTube Cookies Exporter](https://github.com/reiarseni/youtube-cookies-exporter) Chrome extension.  
2️⃣ Export your YouTube cookies and save them as `cookies.txt`.  
3️⃣ Open **Youtube Downloader** and load your `cookies.txt`.  
4️⃣ Enter the video URL and start downloading without authentication errors!  

---

## ⚠️ Troubleshooting

- **403 Forbidden Error?** Make sure your cookies are up to date. refresh youtubepage and export again your YouTube cookies.  
- **Download Fails?** Ensure `ffmpeg` is correctly installed and added to the system path.  
- **Login Issues?** Re-export your cookies and restart the application.  

---

## 📝 License

This project is open-source under the MIT License.  

---

🚀 **Enjoy seamless YouTube downloads without restrictions!**
