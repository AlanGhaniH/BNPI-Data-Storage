import os
import time
from pathlib import Path
import json

UNALLOWED_EXTENSIONS = {"exe", "js", "bat", "sh", "php", "py", "pl", "cgi", "html"}

def is_unallowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in UNALLOWED_EXTENSIONS

def extract_meta(file_path):
    path = Path(file_path)
    stats = path.stat()
    return path.name,f"{path.suffix};{stats.st_size};{time.ctime(stats.st_ctime)};{time.ctime(stats.st_mtime)}"

def extract_file_size(file_path):
    path = Path(file_path)
    stats = path.stat()
    return stats.st_size

def parsed_meta(selected_meta : str):
    parsed = selected_meta.split(';')
    return parsed


def load_contract_info(file_loc : str):
    pwd = os.path.dirname(os.path.abspath(__file__))
    with open(file_loc, "r") as f:
        contract_info = json.load(f)
        return contract_info

if __name__ == "__main__":
    sample_path = "contracts\\contract.json"
    meta = extract_meta(sample_path)
    print(meta)