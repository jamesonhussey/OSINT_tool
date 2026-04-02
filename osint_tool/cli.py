import asyncio
import click
from osint_tool.core.engine import search
from osint_tool.output.formatter import print_results


@click.command()
@click.argument("query")
def main(query: str):
    """OSINT Tool - Consolidate a target's online presence.

    QUERY can be an email address or a username. The tool auto-detects which
    type it is and runs the appropriate lookups.

    Examples:

        python -m osint_tool john.doe@example.com

        python -m osint_tool johndoe
    """
    result = asyncio.run(search(query))
    print_results(result)


if __name__ == "__main__":
    main()
