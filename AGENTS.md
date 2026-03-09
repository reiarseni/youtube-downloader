# YouTube Downloader - Agent Guidelines

## Build & Run Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
python main.py

# Activate virtual environment (if using .venv)
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows
```

## Testing & Code Quality

This project currently has **no formal test suite** or linting configuration. When adding tests or linting, use:
- **Testing**: `pytest` (recommended for Python)
- **Linting**: `ruff` or `flake8` (PEP 8 compliance)
- **Type Checking**: `mypy` (if adding type hints)

To run a single test with pytest:
```bash
pytest tests/test_feature.py::test_specific_function -v
```

## Code Style Guidelines

### Imports
- Order: standard library → third-party → local imports
- Group imports with blank lines between groups
- Prefer explicit imports over `from module import *`
- PyQt5 imports: group widgets together, keep core separate
- Example:
  ```python
  import sys
  import os
  
  from PyQt5.QtWidgets import QWidget, QVBoxLayout, QPushButton
  from PyQt5.QtCore import QThread, pyqtSignal
  import yt_dlp
  ```

### Naming Conventions
- **Classes**: PascalCase (e.g., `DownloadThread`, `MainWindow`)
- **Functions/Methods**: snake_case (e.g., `fetch_info`, `update_progress`)
- **Variables**: snake_case (e.g., `url_input`, `download_thread`)
- **Constants**: UPPER_SNAKE_CASE (e.g., if adding, use `MAX_RETRIES`)
- **Private members**: prefix with underscore (e.g., `_internal_method`)

### Formatting
- **Indentation**: 4 spaces (no tabs)
- **Line length**: Aim for ≤ 100 characters
- **Blank lines**: 2 blank lines before class definitions, 1 before methods
- **Spaces**: Use spaces around operators and after commas
- Follow PEP 8 style guide

### Type Hints
- **Current state**: No type hints used in main.py
- **Future additions**: Use Python type hints for better IDE support
  ```python
  def format_eta(self, seconds: float) -> str:
      """Formats ETA in user-friendly format."""
  ```

### Error Handling
- Use try-except blocks with specific exceptions when possible
- Prefer `Exception as e` over bare `except:`
- Log errors with `logging.exception()` for stack traces
- Show user-friendly errors via `QMessageBox.critical()` or `.warning()`
- Example pattern:
  ```python
  try:
      with yt_dlp.YoutubeDL(ydl_opts) as ydl:
          ydl.download([self.url])
  except Exception as e:
      logging.exception("Error during download:")
      self.error_signal.emit(str(e))
  ```

### Logging
- Use Python's logging module (configured at DEBUG level)
- `logging.debug()` for detailed debugging info
- `logging.info()` for informational messages
- `logging.error()` for error conditions
- `logging.exception()` for errors with stack traces
- Do not use `print()` for logging

### Documentation
- **Docstrings**: Use triple-quoted strings for class/method descriptions
- **Comments**: Use `#` for inline comments explaining complex logic
- Keep comments concise and relevant
- Example:
  ```python
  def cancel(self):
      """Set the cancellation flag to True to cooperatively stop the download."""
      self.cancelled = True
  ```

### Threading Pattern (PyQt5)
- All long-running operations MUST use `QThread`
- Define signals using `pyqtSignal` decorator pattern
- Use signal-slot pattern for thread communication
- **Cooperative cancellation**: Set a `cancelled` flag, check periodically in hooks
- Store thread references as instance variables to prevent premature cleanup
- Example pattern:
  ```python
  class DownloadThread(QThread):
      progress_signal = pyqtSignal(dict)
      finished_signal = pyqtSignal()
      error_signal = pyqtSignal(str)
      
      def __init__(self, url, quality_format, output_path):
          super().__init__()
          self.cancelled = False
      
      def cancel(self):
          self.cancelled = True
      
      def run(self):
          # Check self.cancelled periodically
          if self.cancelled:
              return
  ```

### UI/UX Patterns
- Use `QVBoxLayout` for main layout, `QHBoxLayout` for button groups
- Store UI widgets as instance variables (e.g., `self.url_input`)
- Connect signals to slots in `setup_ui()` method
- Use `QMessageBox` for user notifications (info/warning/critical)
- Disable buttons during long operations (see `toggle_buttons()`)
- Implement `closeEvent()` to handle cleanup and confirmations

### State Management
- Persist configuration in `config.json`
- Save user preferences (last URL, output folder, quality, playlist state)
- Load config in `__init__`, save on changes
- Store last state in instance variables (e.g., `last_formats`, `last_metadata`)

### Cross-Platform Compatibility
- Handle Windows (`os.name == 'nt'`)
- Handle macOS (`sys.platform.startswith('darwin')`)
- Handle Linux (`os.name == 'posix'`)
- Use `subprocess.Popen()` for external commands
- Test on multiple platforms when adding OS-specific code

### Project Structure
- Single-file architecture (main.py)
- All classes in one file (DownloadThread, InfoFetchThread, MainWindow)
- Configuration: `config.json`
- Dependencies: `requirements.txt`
- Cookies: `~/Downloads/cookies.txt` (see `get_cookie_file_path()`)

### Best Practices
- **Never block the UI**: Always use threads for I/O operations
- **Clean up resources**: Use context managers (`with yt_dlp.YoutubeDL()`)
- **Validate inputs**: Check URLs, file paths, user selections before processing
- **Provide feedback**: Update status labels, progress bars during operations
- **Graceful shutdown**: Handle window close event, cancel running operations

### Git Configuration
- `.gitignore` excludes: `__pycache__/`, `*.pyc`, `.venv/`, `config.json`, `*.egg-info/`
- Do not commit: virtual environments, user config, IDE files (.idea/)
- Commit: Python source, requirements, documentation
