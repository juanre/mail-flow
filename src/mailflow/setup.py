"""Interactive setup utility for mailflow.

This wizard helps you create/update ~/.config/mailflow/config.json and optionally
install runtime dependencies (Playwright browsers, Gmail API libs, llmemory).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import click

from mailflow.config import Config


def _run_cmd(cmd: list[str]) -> tuple[int, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        out = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode, out.strip()
    except Exception as e:  # pragma: no cover - environment dependent
        return 1, str(e)


def _check_import(module: str) -> bool:
    try:
        __import__(module)
        return True
    except Exception:
        return False


def ensure_playwright_browsers():
    click.echo("\nPlaywright (for PDF conversion)")
    has_playwright = _check_import("playwright.sync_api")
    if not has_playwright:
        click.echo("- Python package 'playwright' is not installed. It is already a dependency here.")
    if click.confirm("Install/refresh Playwright Chromium browser now?", default=True):
        rc, out = _run_cmd(["playwright", "install", "chromium"])  # assumes on PATH via uv
        if rc != 0:
            click.echo(out)
            click.echo("If this fails, try: uv run playwright install chromium", err=True)
        else:
            click.echo("✓ Playwright Chromium installed")


def configure_gmail(config: Config):
    click.echo("\nGmail API (optional)")
    enable = click.confirm("Enable Gmail API integration?", default=False)
    if not enable:
        return

    # Dependencies
    deps_ok = _check_import("googleapiclient.discovery") and _check_import("google_auth_oauthlib.flow")
    if not deps_ok and click.confirm(
        "Install Gmail API dependencies (uv add google-api-python-client google-auth google-auth-oauthlib)?",
        default=True,
    ):
        rc, out = _run_cmd(
            [
                "uv",
                "add",
                "google-api-python-client",
                "google-auth",
                "google-auth-oauthlib",
            ]
        )
        if rc != 0:
            click.echo(out)
            click.echo("Install failed; you can run the command manually later.", err=True)

    # Client secret guidance
    paths = {
        "client_secret": str(config.config_dir / "gmail_client_secret.json"),
        "token": str(config.config_dir / "gmail_token.json"),
    }
    click.echo(
        f"Place your Google OAuth Desktop client JSON at: {paths['client_secret']}\n"
        f"(It will create tokens at {paths['token']} after first auth.)"
    )


def configure_llmemory(config: Config):
    click.echo("\nllmemory semantic search (optional)")
    enable = click.confirm("Enable llmemory indexing and search?", default=False)
    if not enable:
        return

    # Dependency
    llm_ok = _check_import("llmemory")
    if not llm_ok and click.confirm("Install llmemory (uv add llmemory)?", default=True):
        rc, out = _run_cmd(["uv", "add", "llmemory"]) 
        if rc != 0:
            click.echo(out)
            click.echo("Install failed; you can run 'uv add llmemory' later.", err=True)

    # Config prompts
    cs = click.prompt(
        "PostgreSQL connection string (postgresql://user:pass@host:port/db)", default=""
    )
    owner = click.prompt("Owner ID (for multi-tenant isolation)", default="default-owner")
    provider = click.prompt("Embedding provider id (e.g., openai, local)", default="openai")
    api_key = None
    if provider == "openai":
        api_key = click.prompt("OpenAI API key (sk-...)", default="", hide_input=True)

    # Update config
    settings = config.settings
    settings.setdefault("llmemory", {})
    settings["llmemory"].update(
        {
            "enabled": True,
            "connection_string": cs,
            "owner_id": owner,
            "embedding_provider": provider,
            "openai_api_key": api_key or None,
        }
    )
    config.save_config()
    click.echo("✓ llmemory configuration saved")


def install_auth_from_repo():
    """Install auth materials from a local 'mailflow-auth' folder into XDG config.

    - Source: ./mailflow-auth (in current working directory)
    - Destination: ~/.config/mailflow/
    - Preserves directory structure (e.g., slack/<entity>/user_token)
    """
    src = Path.cwd() / "mailflow-auth"
    if not src.exists() or not src.is_dir():
        return

    xdg = Path(os.environ.get("XDG_CONFIG_HOME", "~/.config")).expanduser()
    dst = (xdg / "mailflow").resolve()

    click.echo(f"\nFound local auth directory: {src}")
    if not click.confirm(f"Copy auth files into {dst}?", default=True):
        return

    # Copy tree (merge), creating directories as needed
    for root, dirs, files in os.walk(src):
        rel = Path(root).relative_to(src)
        target_dir = dst / rel
        target_dir.mkdir(parents=True, exist_ok=True)

        for name in files:
            src_file = Path(root) / name
            dst_file = target_dir / name
            try:
                shutil.copy2(src_file, dst_file)
                # Tighten permissions for likely secret files
                if name.lower() in {"user_token", "token", "token.json"} or "secret" in name.lower():
                    try:
                        os.chmod(dst_file, 0o600)
                    except Exception:
                        pass
            except Exception as e:
                click.echo(f"  ✗ Failed to copy {src_file} → {dst_file}: {e}", err=True)
    # Ensure base dir permissions are reasonable
    try:
        os.chmod(dst, 0o700)
    except Exception:
        pass

    click.echo(f"✓ Auth files installed to {dst}")


@click.command()
def main():
    """mailflow setup wizard."""
    click.echo("mailflow setup\n==========")
    config = Config()

    # Ensure base config exists
    click.echo(f"Using config dir: {config.config_dir}")

    # Optionally install local auth files into XDG config
    install_auth_from_repo()

    # Core: Playwright (browsers)
    ensure_playwright_browsers()

    # Optional: Gmail
    configure_gmail(config)

    # Optional: llmemory
    configure_llmemory(config)

    click.echo(
        "\nAll done! You can now run:\n  mailflow init\n  uv run mailflow gmail --query 'label:INBOX'\n  uv run mailflow search 'invoice'\n"
    )


if __name__ == "__main__":  # pragma: no cover
    main()


