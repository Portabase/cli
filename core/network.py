import requests
import typer
from rich.console import Console
from core.config import TEMPLATE_BASE_URL
from core.utils import current_version, get_random_hint

console = Console()

def fetch_template(filename: str) -> str:
    version = current_version()
    url = f"{TEMPLATE_BASE_URL}/{version if version != 'unknown' else 'latest'}/{filename}"
    
    try:
        status_msg = f"[dim]Fetching template...[/dim]\n{get_random_hint()}"
        with console.status(status_msg):
            response = requests.get(url, timeout=10)
            if response.status_code in [403, 404] and version != "unknown":
                url = f"{TEMPLATE_BASE_URL}/latest/{filename}"
                response = requests.get(url, timeout=10)
                
            response.raise_for_status()
            return response.text
    except requests.RequestException as e:
        console.print(f"[bold red] Error fetching template:[/bold red] {e}")
        console.print("[dim]Check your internet connection or the template URL.[/dim]")
        raise typer.Exit(1)