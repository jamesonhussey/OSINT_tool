import asyncio
import click
from osint_tool.core.engine import search
from osint_tool.output.formatter import print_results


@click.group()
def main():
    """OSINT Tool - Consolidate a target's online presence."""


@main.command()
@click.argument("query")
def search_cmd(query: str):
    """Search by email address or username.

    QUERY can be an email address or a username. The tool auto-detects which
    type it is and runs the appropriate lookups.

    \b
    Examples:
        python -m osint_tool search john.doe@example.com
        python -m osint_tool search johndoe
    """
    result = asyncio.run(search(query))
    print_results(result)


@main.command()
@click.option("--host", default="127.0.0.1", show_default=True, help="Bind host.")
@click.option("--port", default=8000, show_default=True, help="Bind port.")
@click.option("--reload", is_flag=True, default=False, help="Enable auto-reload (dev mode).")
def web(host: str, port: int, reload: bool):
    """Start the web UI server."""
    try:
        import uvicorn
    except ImportError:
        raise click.ClickException(
            "uvicorn is not installed. Run: pip install uvicorn"
        )
    click.echo(f"Starting web UI at http://{host}:{port}")
    uvicorn.run(
        "osint_tool.web.app:app",
        host=host,
        port=port,
        reload=reload,
    )


if __name__ == "__main__":
    main()
