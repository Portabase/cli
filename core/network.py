import requests
import typer
from rich.console import Console
from core.config import TEMPLATE_BASE_URL
from core.utils import current_version

console = Console()

def fetch_template(filename: str) -> str:
    version = current_version()
    url = f"{TEMPLATE_BASE_URL}/{version if version != 'unknown' else 'latest'}/{filename}"
    
    try:
        with console.status(f"[dim]Fetching template from {url}...[/dim]"):
            response = requests.get(url, timeout=10)
            if response.status_code == 404 and version != "unknown":
                url = f"{TEMPLATE_BASE_URL}/latest/{filename}"
                response = requests.get(url, timeout=10)
                
            response.raise_for_status()
            return response.text
    except requests.RequestException as e:
        console.print(f"[bold red] Error fetching template:[/bold red] {e}")
        console.print("[dim]Check your internet connection or the template URL.[/dim]")
        raise typer.Exit(1)