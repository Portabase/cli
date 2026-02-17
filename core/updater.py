import requests
import subprocess
import time
import json
import os
import platform
import sys
import shutil
import typer
from pathlib import Path
from core.utils import current_version, console
from core.config import get_config_value

GITHUB_REPO = "Portabase/cli"
GITHUB_API_BASE_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases"
CACHE_FILE = Path.home() / ".portabase" / "update_cache.json"

def is_prerelease(version: str) -> bool:
    v = version.lower()
    return any(x in v for x in ['a', 'b', 'rc', 'alpha', 'beta'])

def get_platform_info():
    system = platform.system().lower()
    if system == "darwin":
        system = "macos"
    machine = platform.machine().lower()
    
    arch = "amd64"
    if machine in ["arm64", "aarch64"]:
        arch = "arm64"
    elif machine in ["x86_64", "amd64"]:
        arch = "amd64"
    
    return system, arch

def get_latest_release_data(pre=False):
    try:
        if not pre:
            response = requests.get(f"{GITHUB_API_BASE_URL}/latest", timeout=5)
            response.raise_for_status()
            return response.json()
        else:
            response = requests.get(GITHUB_API_BASE_URL, timeout=5)
            response.raise_for_status()
            releases = response.json()
            return releases[0] if releases else None
    except Exception:
        return None

def check_for_updates(force=False):
    if not force and not getattr(sys, 'frozen', False) and platform.system().lower() != "windows":
        return None

    current = current_version()
    if current == "unknown":
        return None
    
    channel = get_config_value("update_channel")
    if channel:
        include_pre = (channel == "beta")
    else:
        include_pre = is_prerelease(current)
    
    latest_tag = None

    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        if not force and CACHE_FILE.exists():
            with open(CACHE_FILE, "r") as f:
                cache = json.load(f)
                if time.time() - cache.get("last_check", 0) < 86400:
                    latest_tag = cache.get("latest_version")
    except Exception:
        pass

    if latest_tag is None:
        data = get_latest_release_data(pre=include_pre)
        if data:
            latest_tag = data.get("tag_name", "").lstrip('v')
            try:
                with open(CACHE_FILE, "w") as f:
                    json.dump({"last_check": time.time(), "latest_version": latest_tag}, f)
            except Exception:
                pass

    if not latest_tag:
        return None

    if latest_tag != current:
        console.print(f"\n[warning]⚠ A new version of Portabase CLI is available: [bold]{latest_tag}[/bold] (current: {current})[/warning]")
        console.print("[info]Run [bold]portabase update[/bold] to update.[/info]\n")
        return latest_tag
    return None

def update_cli():
    if not getattr(sys, 'frozen', False) and platform.system().lower() != "windows":
        console.print("[warning]⚠ The update command is only available for the binary version of Portabase CLI.[/warning]")
        console.print("[info]If you installed via source, please use [bold]git pull[/bold] to update.[/info]")
        return

    current = current_version()
    
    channel = get_config_value("update_channel")
    if channel:
        pre = (channel == "beta")
    else:
        pre = is_prerelease(current) if current != "unknown" else False

    data = get_latest_release_data(pre=pre)
    if not data:
        console.print("[danger]✖ Could not fetch latest release data from GitHub.[/danger]")
        return

    latest_tag = data.get("tag_name", "").lstrip('v')
    
    if latest_tag == current:
        console.print(f"[success]✔ Portabase CLI is already up to date ({current}).[/success]")
        return

    try:
        if latest_tag < current and not (is_prerelease(current) and not is_prerelease(latest_tag)):
             console.print(f"[warning]⚠ Current version ({current}) appears to be older than the latest remote version ({latest_tag}).[/warning]")
             if not typer.confirm("Do you want to continue with the update ?"):
                 return
    except Exception:
        pass

    system, arch = get_platform_info()
    asset_name = f"portabase_{system}_{arch}"
    if system == "windows":
        asset_name += ".exe"
    
    asset = next((a for a in data.get("assets", []) if a["name"] == asset_name), None)
    
    if not asset:
        console.print(f"[danger]✖ Could not find binary for your platform ({system}/{arch}) in the latest release.[/danger]")
        available_assets = [a["name"] for a in data.get("assets", [])]
        console.print(f"[info]Target asset name: {asset_name}[/info]")
        console.print(f"[info]Available assets: {', '.join(available_assets)}[/info]")
        return

    console.print(f"[info]Updating Portabase CLI from {current} to {latest_tag}...[/info]")
    
    try:
        if system == "windows":
            default_bin_path = Path(os.environ.get("APPDATA", "")) / "Portabase" / "portabase.exe"
        else:
            default_bin_path = Path("/usr/local/bin/portabase")

        if getattr(sys, 'frozen', False):
            current_exe = Path(sys.executable)
        else:
            if default_bin_path.exists():
                current_exe = default_bin_path
            else:
                current_exe = Path.home() / ".local" / "bin" / ("portabase" if system != "windows" else "portabase.exe")
        
        console.print(f"[info]Target installation path: {current_exe}[/info]")

        download_url = asset["browser_download_url"]
        import tempfile
        # Create a temporary file that won't have permission issues or conflicts
        fd, temp_path = tempfile.mkstemp(prefix="portabase_update_")
        temp_file = Path(temp_path)
        os.close(fd)
        
        try:
            response = requests.get(download_url, stream=True, timeout=15)
            response.raise_for_status()
            total_size = int(response.headers.get('content-length', 0))
            
            from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, DownloadColumn, TransferSpeedColumn
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                DownloadColumn(),
                TransferSpeedColumn(),
                console=console
            ) as progress:
                task = progress.add_task(f"Downloading {asset_name}...", total=total_size)
                with open(temp_file, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            progress.update(task, advance=len(chunk))
        except Exception as e:
            if temp_file.exists(): temp_file.unlink()
            raise e
        
        if system != "windows":
            temp_file.chmod(0o755)

        if system == "windows":
            if current_exe.exists():
                old_exe = Path(f"{current_exe}.old")
                if old_exe.exists(): old_exe.unlink()
                current_exe.rename(old_exe)
            temp_file.rename(current_exe)
        else:
            need_sudo = not os.access(current_exe.parent, os.W_OK) or (current_exe.exists() and not os.access(current_exe, os.W_OK))
            
            if need_sudo:
                console.print("[info]Permissions required to install to /usr/local/bin. Using sudo...[/info]")
                if current_exe.exists():
                    subprocess.run(["sudo", "mv", str(current_exe), f"{current_exe}.old"], check=False)
                subprocess.run(["sudo", "mv", str(temp_file), str(current_exe)], check=True)
                subprocess.run(["sudo", "chmod", "+x", str(current_exe)], check=True)
            else:
                if current_exe.exists():
                    old_exe = Path(f"{current_exe}.old")
                    if old_exe.exists(): old_exe.unlink()
                    current_exe.rename(old_exe)
                current_exe.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(temp_file), str(current_exe))
            
        try:
            console.print(f"[success]✔ Successfully updated to {latest_tag}![/success]")
        except Exception:
            # Fallback to plain print if rich/PyInstaller fails to load modules after update
            print(f"Successfully updated to {latest_tag}!")
            
    except Exception as e:
        try:
            console.print(f"[danger]✖ An error occurred during update: {e}[/danger]")
        except Exception:
            print(f"An error occurred during update: {e}")
        if 'temp_file' in locals() and temp_file.exists():
            temp_file.unlink()