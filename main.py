import sys
import os
import json
import logging
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QLineEdit, QPushButton, QListWidget, QListWidgetItem, QLabel, QFileDialog,
                             QProgressBar, QMessageBox, QTextEdit)
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtGui import QIcon
import yt_dlp

logging.basicConfig(level=logging.DEBUG)

def get_cookie_file_path():
    """Devuelve la ruta absoluta del archivo cookies.txt ubicado en la carpeta Downloads."""
    return os.path.join(os.path.expanduser("~"), "Downloads", "cookies.txt")

class DownloadThread(QThread):
    progress_signal = pyqtSignal(dict)
    finished_signal = pyqtSignal()
    error_signal = pyqtSignal(str)

    def __init__(self, url, format_id, output_path):
        super().__init__()
        self.url = url
        self.format_id = format_id
        self.output_path = output_path

    def run(self):
        ydl_opts = {
            'format': "bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]", #self.format_id, #
            'merge_output_format': True,
            'outtmpl': f'{self.output_path}/%(title)s_%(height)sp.%(ext)s',
            'progress_hooks': [self.my_hook],
            #'noplaylist': True,
            'cookiefile': get_cookie_file_path(),
            #'http_headers': {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'},
            #'fragment_retries': 'infinite',
            #'retries': 3,
            'verbose': True,
            'extractor_args': "youtube:player_client=android" #ios / tv  / web_safari  / web / android / tv_embedded
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([self.url])
            self.finished_signal.emit()
        except Exception as e:
            logging.exception("Error en la descarga:")
            self.error_signal.emit(str(e))

    def my_hook(self, d):
        if d.get('status') == 'downloading':
            self.progress_signal.emit(d)
        elif d.get('status') == 'finished':
            self.progress_signal.emit(d)

class InfoFetchThread(QThread):
    """
    Hilo que realiza una única petición para obtener toda la información del video:
    formatos, descripción y otros metadatos.
    """
    info_signal = pyqtSignal(dict)
    error_signal = pyqtSignal(str)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        ydl_opts = {
            'skip_download': True,
            'quiet': True,
            'cookiefile': get_cookie_file_path(),
            'http_headers': {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'},
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
            self.info_signal.emit(info)
        except Exception as e:
            logging.exception("Error al obtener la información:")
            self.error_signal.emit(str(e))

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Descargador de YouTube con yt-dlp")
        self.setWindowIcon(QIcon("icon.png"))
        self.last_formats = None      # Almacenará el array de formatos obtenido
        self.last_metadata = {}       # Almacenará metadatos (título, descripción, uploader, etc.)
        self.output_folder = None
        self.download_thread = None
        self.info_thread = None       # Hilo para obtener la info completa en una única petición
        self.setup_ui()
        self.load_config()

    def setup_ui(self):
        layout = QVBoxLayout()

        # Campo para ingresar la URL
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Introduce la URL del video de YouTube")
        layout.addWidget(self.url_input)

        # Botón para obtener la información completa (formatos y metadatos)
        self.fetch_button = QPushButton("Obtener información")
        self.fetch_button.clicked.connect(self.fetch_info)
        layout.addWidget(self.fetch_button)

        # Control tipo textarea para mostrar descripción y metadatos
        self.metadata_label = QLabel("Metadatos y descripción:")
        layout.addWidget(self.metadata_label)
        self.metadata_text = QTextEdit()
        self.metadata_text.setReadOnly(True)
        self.metadata_text.setPlaceholderText("La descripción y metadatos del video aparecerán aquí...")
        layout.addWidget(self.metadata_text)

        # Lista para mostrar los formatos (igual que antes)
        self.format_list = QListWidget()
        layout.addWidget(self.format_list)

        # Selección de carpeta de salida
        folder_layout = QHBoxLayout()
        self.folder_label = QLabel("Carpeta de salida: (No seleccionada)")
        self.folder_button = QPushButton("Seleccionar carpeta")
        self.folder_button.clicked.connect(self.select_folder)
        folder_layout.addWidget(self.folder_label)
        folder_layout.addWidget(self.folder_button)
        layout.addLayout(folder_layout)

        # Botones de descarga y stop
        buttons_layout = QHBoxLayout()
        self.download_button = QPushButton("Descargar")
        self.download_button.clicked.connect(self.start_download)
        buttons_layout.addWidget(self.download_button)
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop_operation)
        buttons_layout.addWidget(self.stop_button)
        layout.addLayout(buttons_layout)

        # Barra de progreso y etiqueta de estado
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        self.setLayout(layout)

    def load_config(self):
        """Carga la configuración desde config.json, si existe."""
        try:
            with open("config.json", "r") as f:
                config = json.load(f)
            self.url_input.setText(config.get("last_video", ""))
            self.output_folder = config.get("last_output_folder", None)
            if self.output_folder:
                self.folder_label.setText(f"Carpeta de salida: {self.output_folder}")
            formats = config.get("formats", [])
            if formats:
                self.populate_formats_from_config(formats)
                self.last_formats = formats
            metadata = config.get("metadata", {})
            if metadata:
                self.last_metadata = metadata
                self.update_metadata_text(metadata)
        except Exception as e:
            logging.info("No se pudo cargar config.json, se usará la configuración por defecto.")

    def save_config(self):
        """Guarda la configuración actual en config.json, incluyendo metadatos."""
        config = {
            "last_video": self.url_input.text().strip(),
            "last_output_folder": self.output_folder,
            "formats": self.last_formats if self.last_formats else [],
            "metadata": self.last_metadata if self.last_metadata else {}
        }
        try:
            with open("config.json", "w") as f:
                json.dump(config, f, indent=4)
        except Exception as e:
            logging.error("Error al guardar la configuración: %s", e)

    def populate_formats(self, formats):
        """Rellena la lista de formatos en el QListWidget."""
        self.format_list.clear()
        self.last_formats = formats
        for f in formats:
            format_id = f.get('format_id')
            ext = f.get('ext')
            resolution = f.get('resolution') or (str(f.get('height')) if f.get('height') else 'N/A')
            filesize = f.get('filesize') or 0
            filesize_str = f"{filesize/1024/1024:.2f} MB" if filesize else "Desconocido"
            item_text = f"Ext: {ext} | Resolución: {resolution} | Tamaño: {filesize_str}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, format_id)
            self.format_list.addItem(item)
        self.status_label.setText("Formatos cargados. Selecciona uno y presiona 'Descargar'.")

    def populate_formats_from_config(self, formats):
        """Rellena el QListWidget con los formatos guardados en config."""
        self.format_list.clear()
        for f in formats:
            format_id = f.get('format_id')
            ext = f.get('ext')
            resolution = f.get('resolution') or (str(f.get('height')) if f.get('height') else 'N/A')
            filesize = f.get('filesize') or 0
            filesize_str = f"{filesize/1024/1024:.2f} MB" if filesize else "Desconocido"
            item_text = f"Ext: {ext} | Resolución: {resolution} | Tamaño: {filesize_str}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, format_id)
            self.format_list.addItem(item)
        self.status_label.setText("Formatos cargados (desde config).")

    def update_metadata_text(self, metadata):
        """Actualiza el QTextEdit con los metadatos y descripción formateados."""
        text = (
            f"Título: {metadata.get('title', '')}\n"
            f"Uploader: {metadata.get('uploader', '')}\n"
            f"Fecha de subida: {metadata.get('upload_date', '')}\n\n"
            f"Descripción:\n{metadata.get('description', '')}"
        )
        self.metadata_text.setPlainText(text)

    def fetch_info(self):
        """Obtiene en una única petición los formatos y metadatos del video."""
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Error", "Por favor, ingresa una URL válida.")
            return

        # Limpiamos la lista de formatos y el área de metadatos
        self.format_list.clear()
        self.metadata_text.clear()
        self.status_label.setText("Obteniendo información del video...")
        self.toggle_buttons(False)

        self.info_thread = InfoFetchThread(url)
        self.info_thread.info_signal.connect(self.process_info)
        self.info_thread.error_signal.connect(self.info_error)
        self.info_thread.finished.connect(lambda: self.toggle_buttons(True))
        self.info_thread.start()

    def process_info(self, info):
        # Extraer formatos
        formats = info.get('formats', [])
        if not formats:
            QMessageBox.critical(self, "Error", "No se encontraron formatos disponibles.")
            self.status_label.setText("Error en la obtención de información.")
            self.toggle_buttons(True)
            return

        self.populate_formats(formats)

        # Extraer metadatos relevantes y actualizar el área de texto
        metadata = {
            "title": info.get("title", ""),
            "description": info.get("description", ""),
            "uploader": info.get("uploader", ""),
            "upload_date": info.get("upload_date", "")
        }
        self.last_metadata = metadata
        self.update_metadata_text(metadata)
        self.status_label.setText("Información cargada. Selecciona un formato y presiona 'Descargar'.")
        self.save_config()

    def info_error(self, error_msg):
        QMessageBox.critical(self, "Error", f"Error al obtener información: {error_msg}")
        self.status_label.setText("Error en la obtención de información.")
        self.toggle_buttons(True)

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta de salida")
        if folder:
            self.folder_label.setText(f"Carpeta de salida: {folder}")
            self.output_folder = folder
            self.save_config()
        else:
            self.output_folder = None

    def start_download(self):
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Error", "Ingresa una URL válida.")
            return

        if not self.output_folder:
            QMessageBox.warning(self, "Error", "Selecciona una carpeta de salida.")
            return

        selected_items = self.format_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Error", "Selecciona un formato de descarga.")
            return

        format_id = selected_items[0].data(Qt.UserRole)
        if not format_id:
            QMessageBox.warning(self, "Error", "No se pudo determinar el format_id del elemento seleccionado.")
            return

        self.toggle_buttons(False)
        self.status_label.setText("Descargando...")

        self.download_thread = DownloadThread(url, format_id, self.output_folder)
        self.download_thread.progress_signal.connect(self.update_progress)
        self.download_thread.finished_signal.connect(self.download_finished)
        self.download_thread.error_signal.connect(self.download_error)
        self.download_thread.start()

    def update_progress(self, data):
        if data.get('status') == 'downloading':
            total_bytes = data.get('total_bytes') or data.get('total_bytes_estimate')
            downloaded = data.get('downloaded_bytes', 0)
            if total_bytes:
                progress = int(downloaded * 100 / total_bytes)
                self.progress_bar.setValue(progress)
                self.status_label.setText(
                    f"Descargando: {progress}% ({downloaded/1024/1024:.2f} MB de {total_bytes/1024/1024:.2f} MB)"
                )
        elif data.get('status') == 'finished':
            self.progress_bar.setValue(100)
            self.status_label.setText("Descarga finalizada.")

    def download_finished(self):
        QMessageBox.information(self, "Descarga completa", "El video se descargó correctamente.")
        self.toggle_buttons(True)
        self.progress_bar.setValue(0)
        self.save_config()

    def download_error(self, error_msg):
        QMessageBox.critical(self, "Error en descarga", f"Ocurrió un error durante la descarga:\n{error_msg}")
        self.toggle_buttons(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("Error en descarga.")

    def stop_operation(self):
        """Detiene cualquier operación en curso (descarga o consulta de información)."""
        threads_stopped = False
        if self.download_thread is not None and self.download_thread.isRunning():
            self.download_thread.terminate()  # Nota: terminate() no es lo ideal en producción
            self.download_thread.wait()
            self.download_thread = None
            threads_stopped = True
        if self.info_thread is not None and self.info_thread.isRunning():
            self.info_thread.terminate()
            self.info_thread.wait()
            self.info_thread = None
            threads_stopped = True
        if threads_stopped:
            self.status_label.setText("Operación detenida.")
            self.progress_bar.setValue(0)
            self.toggle_buttons(True)

    def toggle_buttons(self, enable):
        """Habilita o deshabilita los botones principales de la interfaz."""
        self.download_button.setEnabled(enable)
        self.fetch_button.setEnabled(enable)
        self.folder_button.setEnabled(enable)
        self.stop_button.setEnabled(not enable)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.resize(800, 600)
    window.show()
    sys.exit(app.exec_())
