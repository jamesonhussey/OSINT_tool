import asyncio
import re
from osint_tool.core.models import SearchResult
from osint_tool.modules.username_enum import enumerate_username
from osint_tool.modules.gravatar import lookup_gravatar
from osint_tool.modules.email_utils import generate_username_variations


def is_email(query: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", query))


async def search_email(email: str) -> SearchResult:
    """Run all lookups starting from an email address."""
    result = SearchResult(query=email, query_type="email")

    # Generate username variations from the email
    variations = generate_username_variations(email)
    result.derived_usernames = variations

    # Run gravatar lookup and username enumeration in parallel
    gravatar_task = lookup_gravatar(email)
    enum_tasks = [enumerate_username(username) for username in variations]

    all_tasks = await asyncio.gather(gravatar_task, *enum_tasks)

    result.gravatar = all_tasks[0]
    for account_list in all_tasks[1:]:
        result.accounts.extend(account_list)

    return result


async def search_username(username: str) -> SearchResult:
    """Run all lookups starting from a username."""
    result = SearchResult(query=username, query_type="username")
    result.derived_usernames = [username]

    accounts = await enumerate_username(username)
    result.accounts = accounts

    return result


async def search(query: str) -> SearchResult:
    """Auto-detect query type and run appropriate search."""
    if is_email(query):
        return await search_email(query)
    else:
        return await search_username(query)
