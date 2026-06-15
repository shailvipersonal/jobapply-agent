"""Command-line interface for the job application agent.

Examples:
    python -m jobagent init
    python -m jobagent login https://boards.greenhouse.io/acme/jobs/123
    python -m jobagent apply https://boards.greenhouse.io/acme/jobs/123
    python -m jobagent apply https://... --auto
    python -m jobagent batch jobs.txt
    python -m jobagent list
    python -m jobagent export applications.csv
"""

from __future__ import annotations

import shutil
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import records
from .apply import apply_to_job
from .browser import browser_session, open_page
from .config import (
    CONFIG_DIR,
    CREDENTIALS_PATH,
    PROFILE_PATH,
    ConfigError,
    ensure_dirs,
    load_credentials,
    load_profile,
    load_settings,
)

app = typer.Typer(add_completion=False, help="Automated job application agent.")
console = Console()


def _load_all():
    try:
        return load_settings(), load_profile(), load_credentials()
    except ConfigError as exc:
        console.print(Panel(str(exc), title="Configuration error", style="red"))
        raise typer.Exit(code=1)


@app.command()
def init() -> None:
    """Create profile.yaml and credentials.yaml from the example templates."""
    ensure_dirs()
    pairs = [
        (CONFIG_DIR / "profile.example.yaml", PROFILE_PATH),
        (CONFIG_DIR / "credentials.example.yaml", CREDENTIALS_PATH),
    ]
    for src, dst in pairs:
        if dst.exists():
            console.print(f"[yellow]exists[/]  {dst}")
        elif src.exists():
            shutil.copy(src, dst)
            console.print(f"[green]created[/] {dst}")
        else:
            console.print(f"[red]missing template[/] {src}")
    env_example = CONFIG_DIR.parent / ".env.example"
    env = CONFIG_DIR.parent / ".env"
    if env_example.exists() and not env.exists():
        shutil.copy(env_example, env)
        console.print(f"[green]created[/] {env}")
    records.init_db()
    console.print(
        Panel(
            "Next steps:\n"
            "  1. Edit config/profile.yaml with your details.\n"
            "  2. Edit config/credentials.yaml with your login email/password.\n"
            "  3. (Optional) Put your OpenAI key in .env for smarter filling.\n"
            "  4. Run: playwright install chromium\n"
            "  5. Apply: python -m jobagent apply <job-url>",
            title="Setup complete",
            style="green",
        )
    )


@app.command()
def login(url: str) -> None:
    """Open a job site so you can create/confirm an account once.

    The session is saved to the persistent browser profile and reused later.
    """
    settings, _, creds = _load_all()
    email, password = creds.for_url(url)
    console.print(
        f"Opening [cyan]{url}[/]. Create or sign in to your account "
        f"(email: [bold]{email}[/]). The session will be remembered."
    )
    with browser_session(headless=False) as ctx:
        open_page(ctx, url)
        typer.prompt(
            "Press Enter here when you've finished logging in", default="", show_default=False
        )
    console.print("[green]Saved.[/] Future applies on this site will reuse the login.")


@app.command()
def apply(
    url: str,
    auto: bool = typer.Option(False, "--auto", help="Submit automatically without review."),
    review: bool = typer.Option(False, "--review", help="Fill, then ask before submitting."),
    headless: bool = typer.Option(False, "--headless", help="Run without a visible browser."),
    force: bool = typer.Option(False, "--force", help="Apply even if already recorded."),
) -> None:
    """Apply to a single job by URL."""
    settings, profile, creds = _load_all()
    mode = "auto" if auto else "review" if review else settings.submit_mode

    prior = records.already_applied(url)
    if prior and not force:
        console.print(
            f"[yellow]Already applied[/] on {prior.applied_at} "
            f"(status: {prior.status}). Use --force to apply again."
        )
        raise typer.Exit()

    use_headless = headless or settings.headless
    if mode == "review" and use_headless:
        console.print("[yellow]Review mode needs a visible browser; disabling headless.[/]")
        use_headless = False

    def _confirm(log: list[str]) -> bool:
        _print_log(log)
        return typer.confirm("Submit this application now?", default=False)

    with browser_session(headless=use_headless) as ctx:
        result = apply_to_job(ctx, url, settings, profile, creds, mode, _confirm)
        if mode == "auto":
            _print_log(result.log)
        color = {"submitted": "green", "filled_pending_review": "yellow"}.get(result.status, "red")
        console.print(
            Panel(
                f"{result.title or '(job)'}\n{result.url}\n\n"
                f"Status: [bold]{result.status}[/]\n{result.message}",
                title="Result",
                style=color,
            )
        )


@app.command()
def batch(
    file: Path = typer.Argument(..., help="Text file with one job URL per line."),
    auto: bool = typer.Option(False, "--auto", help="Submit automatically without review."),
    headless: bool = typer.Option(False, "--headless"),
) -> None:
    """Apply to many jobs listed in a file (one URL per line, # for comments)."""
    settings, profile, creds = _load_all()
    if not file.exists():
        console.print(f"[red]File not found:[/] {file}")
        raise typer.Exit(code=1)
    urls = [
        ln.strip()
        for ln in file.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    if not urls:
        console.print("[yellow]No URLs found in file.[/]")
        raise typer.Exit()

    mode = "auto" if auto else settings.submit_mode
    use_headless = headless or settings.headless
    if mode == "review" and use_headless:
        use_headless = False

    def _confirm(log: list[str]) -> bool:
        _print_log(log)
        return typer.confirm("Submit this application now?", default=False)

    console.print(f"Applying to [bold]{len(urls)}[/] jobs (mode: {mode}).")
    with browser_session(headless=use_headless) as ctx:
        for i, url in enumerate(urls, 1):
            console.rule(f"[{i}/{len(urls)}] {url}")
            if records.already_applied(url):
                console.print("[yellow]Skipped (already applied).[/]")
                continue
            try:
                result = apply_to_job(ctx, url, settings, profile, creds, mode, _confirm)
                console.print(f"-> [bold]{result.status}[/]: {result.message}")
            except Exception as exc:
                console.print(f"[red]Error:[/] {exc}")
                records.record(records.Application(url, "", "", "failed", str(exc)))


@app.command(name="list")
def list_apps(limit: int = typer.Option(50, help="Max rows to show.")) -> None:
    """Show your application history."""
    apps = records.list_all(limit=limit)
    if not apps:
        console.print("No applications recorded yet.")
        return
    table = Table(title="Application history")
    table.add_column("When", style="dim")
    table.add_column("Company")
    table.add_column("Title")
    table.add_column("Status")
    table.add_column("URL", overflow="fold")
    for a in apps:
        color = {"submitted": "green", "filled_pending_review": "yellow"}.get(a.status, "red")
        table.add_row(a.applied_at, a.company, a.title, f"[{color}]{a.status}[/]", a.url)
    console.print(table)


@app.command()
def export(path: Path = typer.Argument(Path("applications.csv"))) -> None:
    """Export your application history to a CSV file."""
    n = records.export_csv(path)
    console.print(f"[green]Exported[/] {n} applications to {path}")


def _print_log(log: list[str]) -> None:
    if not log:
        return
    console.print(Panel("\n".join(log), title="Fields filled", style="cyan"))


if __name__ == "__main__":
    app()
