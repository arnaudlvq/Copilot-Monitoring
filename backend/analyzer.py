import json
import os
import pathlib
from collections import Counter
from datetime import datetime

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.syntax import Syntax
    from rich.table import Table
except ImportError:
    print("Error: The 'rich' library is required. Please run 'pip install rich'.")
    exit(1)

# --- Configuration ---
# This should match the BASE_DIR in your copilot_logger.py
BASE_DIR = pathlib.Path(os.path.expanduser("~/.mitmproxy/intercepter_vscode/copilot_mitm"))
EVENTS_PATH = BASE_DIR / "events.jsonl"

console = Console()


def load_events():
    """Loads all events from the events.jsonl file."""
    if not EVENTS_PATH.exists():
        console.print(f"[bold red]Error:[/bold red] Events file not found at {EVENTS_PATH}")
        return []
    with open(EVENTS_PATH, "r", encoding="utf-8") as f:
        events = [json.loads(line) for line in f]
    # Sort by timestamp descending (most recent first)
    return sorted(events, key=lambda x: x.get("ts_end", 0), reverse=True)


def read_body_content(path_str: str | None) -> str:
    """Reads the content of a request/response body file."""
    if not path_str:
        return "[No body file path recorded]"
    path = pathlib.Path(path_str)
    if not path.exists():
        return f"[File not found: {path.name}]"
    return path.read_text(encoding="utf-8")


def display_summary(events):
    """Calculates and displays a summary of all requests."""
    if not events:
        console.print("[yellow]No events to summarize.[/yellow]")
        return

    total_reqs = len(events)
    hosts = Counter(e["host"] for e in events)
    statuses = Counter(e["status"] for e in events)
    methods = Counter(e["method"] for e in events)
    latencies = [e["latency_total_s"] for e in events if e.get("latency_total_s") is not None]

    table = Table(title="[bold cyan]Traffic Summary[/bold cyan]")
    table.add_column("Metric", style="magenta")
    table.add_column("Value", style="green")

    table.add_row("Total Requests", str(total_reqs))
    table.add_row("Hosts", "\n".join([f"{h}: {c}" for h, c in hosts.items()]))
    table.add_row("Status Codes", "\n".join([f"{s}: {c}" for s, c in statuses.items()]))
    table.add_row("HTTP Methods", "\n".join([f"{m}: {c}" for m, c in methods.items()]))
    if latencies:
        table.add_row("Avg. Latency", f"{sum(latencies) / len(latencies):.2f}s")
        table.add_row("Max Latency", f"{max(latencies):.2f}s")

    console.print(table)


def list_requests(events):
    """Displays a list of all captured requests."""
    table = Table(title="[bold cyan]Captured Requests[/bold cyan]", show_lines=True)
    table.add_column("#", style="dim", justify="right")
    table.add_column("Time", style="magenta")
    table.add_column("Method", style="bold yellow")
    table.add_column("Host & Path", style="green")
    table.add_column("Status", style="blue")
    table.add_column("Latency", style="cyan")

    for i, event in enumerate(events):
        status_color = "green" if 200 <= event["status"] < 300 else "red"
        dt = datetime.fromtimestamp(event["ts_end"]).strftime("%H:%M:%S")
        table.add_row(
            str(i),
            dt,
            event["method"],
            f"{event['host']}{event['path']}",
            f"[{status_color}]{event['status']}[/{status_color}]",
            f"{event['latency_total_s']:.3f}s" if event.get("latency_total_s") else "N/A",
        )
    console.print(table)


def view_request_details(events):
    """Prompts the user to select a request and shows its details."""
    if not events:
        console.print("[yellow]No requests to view.[/yellow]")
        return

    try:
        idx_str = console.input("[bold]Enter request # to view details: [/bold]")
        idx = int(idx_str)
        if not 0 <= idx < len(events):
            raise ValueError
    except (ValueError, IndexError):
        console.print("[bold red]Invalid selection.[/bold red]")
        return

    event = events[idx]

    # Display general info
    info_table = Table(title=f"[bold cyan]Details for Request #{idx}[/bold cyan]")
    info_table.add_column("Field", style="magenta")
    info_table.add_column("Value")
    for key, value in event.items():
        if key not in ["req_json", "resp_json", "req_path", "resp_path"]:
            info_table.add_row(str(key), str(value))
    console.print(info_table)

    # Display request body
    req_body = read_body_content(event.get("req_path"))
    req_syntax = Syntax(req_body, "json", theme="monokai", line_numbers=True)
    console.print(Panel(req_syntax, title="[bold green]Request Body[/bold green]", border_style="green"))

    # Display response body
    resp_body = read_body_content(event.get("resp_path"))
    lexer = "json" if "json" in event.get("resp_ct", "") else "text"
    resp_syntax = Syntax(resp_body, lexer, theme="monokai", line_numbers=True)
    console.print(Panel(resp_syntax, title="[bold blue]Response Body[/bold blue]", border_style="blue"))


def main():
    """Main interactive loop."""
    while True:
        events = load_events()
        console.print("\n[bold]GitHub Copilot Log Analyzer[/bold]")
        console.print("─" * 30)
        console.print("[1] Show Summary")
        console.print("[2] List All Requests")
        console.print("[3] View Request Details")
        console.print("[q] Quit")
        choice = console.input("[bold]Choose an option: [/bold]")

        if choice == "1":
            display_summary(events)
        elif choice == "2":
            list_requests(events)
        elif choice == "3":
            list_requests(events)
            if events:
                view_request_details(events)
        elif choice.lower() == "q":
            break
        else:
            console.print("[bold red]Invalid option, please try again.[/bold red]")


if __name__ == "__main__":
    main()