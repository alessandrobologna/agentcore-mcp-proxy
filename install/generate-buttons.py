#!/usr/bin/env python3
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "click",
#     "pyperclip",
# ]
# ///
"""
Generate markdown link snippets for VS Code MCP installation.

This script reads an MCP configuration JSON file and creates a markdown link
that can be used to install the MCP server directly in VS Code Insiders.
"""

import json
import urllib.parse
from pathlib import Path

import click
import pyperclip


@click.command()
@click.option(
    "--name",
    required=True,
    help="Display name for the MCP server (will be URL-encoded)",
)
@click.option(
    "--config",
    "config_path",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to the mcp.json configuration file",
)
@click.option(
    "--badge/--no-badge",
    default=False,
    help="Generate a shields.io badge instead of a plain text link",
)
@click.option(
    "--badge-label",
    default="MCP",
    help="Label text for the shields.io badge (default: 'MCP')",
)
@click.option(
    "--badge-color",
    default="blue",
    help="Color for the shields.io badge (default: 'blue')",
)
@click.option(
    "--logo",
    help="Logo name for the shields.io badge (e.g., 'visualstudiocode')",
)
@click.option(
    "--logo-color",
    default="white",
    help="Logo color for the shields.io badge (default: 'white')",
)
@click.option(
    "--style",
    default="flat-square",
    type=click.Choice(
        ["flat", "flat-square", "plastic", "for-the-badge", "social"],
        case_sensitive=False,
    ),
    help="Style for the shields.io badge (default: 'flat-square')",
)
@click.option(
    "--clipboard",
    is_flag=True,
    help="Copy the generated markdown to clipboard",
)
@click.option(
    "--insiders",
    is_flag=True,
    help="Target VS Code Insiders (default: stable)",
)
def generate_button(
    name: str,
    config_path: Path,
    badge: bool,
    badge_label: str,
    badge_color: str,
    logo: str | None,
    logo_color: str,
    style: str,
    clipboard: bool,
    insiders: bool,
) -> None:
    """
    Generate a markdown link snippet for VS Code MCP installation.

    The generated link allows users to install the MCP server configuration
    directly into VS Code Insiders with a single click.
    """
    # Read the configuration file
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config_data = json.load(f)
    except json.JSONDecodeError as e:
        click.echo(f"Error: Invalid JSON in {config_path}: {e}", err=True)
        raise click.Abort()
    except Exception as e:
        click.echo(f"Error reading {config_path}: {e}", err=True)
        raise click.Abort()

    # Extract the config name (this is what VS Code will use as the server identifier)
    config_name = config_data.get("name", "mcp-server")
    encoded_config_name = urllib.parse.quote(config_name)

    # Extract inputs if present and remove from config
    inputs = config_data.pop("inputs", None)

    # JSON-stringify and URL-encode the config
    config_json = json.dumps(config_data, separators=(",", ":"))
    encoded_config = urllib.parse.quote(config_json)

    # Construct the installation URL - use the config's name field, not the display name
    base_url = "https://insiders.vscode.dev/redirect/mcp/install"
    install_url = f"{base_url}?name={encoded_config_name}"

    # Add inputs as a separate parameter if present
    if inputs:
        inputs_json = json.dumps(inputs, separators=(",", ":"))
        encoded_inputs = urllib.parse.quote(inputs_json)
        install_url += f"&inputs={encoded_inputs}"

    # Add config
    install_url += f"&config={encoded_config}"

    if insiders:
        install_url += "&quality=insiders"

    # Generate markdown snippet
    if badge:
        # Generate shields.io badge
        badge_message = urllib.parse.quote(name)
        badge_url = f"https://img.shields.io/badge/{badge_label}-{badge_message}-{badge_color}?style={style}"
        if logo:
            badge_url += f"&logo={logo}&logoColor={logo_color}"
        markdown = f"[![{name}]({badge_url})]({install_url})"

        if not clipboard:
            click.echo("Generated Shields.io Badge:")
            click.echo()
            click.echo(markdown)
            click.echo()
            click.echo("Badge Image URL:")
            click.echo(badge_url)
    else:
        # Generate plain text link
        markdown = f"[Install {name} in VS Code]({install_url})"

        if not clipboard:
            click.echo("Generated Markdown Link:")
            click.echo()
            click.echo(markdown)

    if not clipboard:
        click.echo()
        click.echo("Installation URL:")
        click.echo(install_url)

    # Copy to clipboard if requested
    if clipboard:
        try:
            pyperclip.copy(markdown)
            click.echo("✓ Copied to clipboard!", err=False)
        except Exception as e:
            click.echo(f"✗ Failed to copy to clipboard: {e}", err=True)


if __name__ == "__main__":
    generate_button()
