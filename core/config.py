import json
import os
import uuid
from pathlib import Path

TEMPLATE_BASE_URL = "https://portabase-cli.s3.fr-par.scw.cloud/templates/v1"

def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write(content)

def write_env_file(work_dir: Path, env_vars: dict):
    existing = {}
    env_path = work_dir / ".env"
    if env_path.exists():
        with open(env_path, "r") as f:
            for line in f:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    existing[k] = v.strip('"')
    
    existing.update(env_vars)
    content = ""
    for k, v in existing.items():
        content += f'{k}="{v}"\n'
    write_file(env_path, content)

def load_db_config(path: Path) -> dict:
    json_path = path / "databases.json"
    if not json_path.exists():
        return {"databases": []}
    try:
        with open(json_path, "r") as f:
            return json.load(f)
    except:
        return {"databases": []}

def save_db_config(path: Path, config: dict):
    json_path = path / "databases.json"
    with open(json_path, "w") as f:
        json.dump(config, f, indent=2)
    try:
        os.chmod(json_path, 0o666)
    except:
        pass

def add_db_to_json(path: Path, db_entry: dict):
    config = load_db_config(path)
    if "databases" not in config:
        config["databases"] = []
    
    if "generatedId" not in db_entry:
        db_entry["generatedId"] = str(uuid.uuid4())
        
    config["databases"].append(db_entry)
    save_db_config(path, config)