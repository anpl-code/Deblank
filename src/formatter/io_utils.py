import os
import tempfile

TEMP_DIR='./temp'
TEMP_DIR_EXISTED = os.path.exists(TEMP_DIR)

def create_temp_input_file(content: str, suffix: str = "") -> str:
    global TEMP_DIR_EXISTED
    if not TEMP_DIR_EXISTED:
        os.makedirs(TEMP_DIR, exist_ok=True)
        TEMP_DIR_EXISTED = True

    with tempfile.NamedTemporaryFile(mode="w+", suffix=suffix, delete=False, dir=TEMP_DIR) as temp_in:
        temp_in.write(content)
        return temp_in.name

def read_text_file(file_path: str) -> str:
    with open(file_path, "r") as f:
        return f.read()

def normalize_stderr(stderr: str):
    if stderr and stderr.strip():
        return stderr
    return None

def safe_unlink(file_path):
    if file_path and os.path.exists(file_path):
        os.unlink(file_path)

def safe_cleanup(*file_paths):
    for file_path in file_paths:
        safe_unlink(file_path)
