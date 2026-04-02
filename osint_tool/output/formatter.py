from colorama import Fore, Style, init
from osint_tool.core.models import SearchResult, AccountStatus

init(autoreset=True)

BANNER = r"""
  ___  ____ ___ _   _ _____   _____ ___   ___  _
 / _ \/ ___|_ _| \ | |_   _| |_   _/ _ \ / _ \| |
| | | \___ \| ||  \| | | |     | || | | | | | | |
| |_| |___) | || |\  | | |     | || |_| | |_| | |___
 \___/|____/___|_| \_| |_|     |_| \___/ \___/|_____|
"""


def print_banner():
    print(f"{Fore.CYAN}{BANNER}{Style.RESET_ALL}")


def print_results(result: SearchResult):
    print_banner()
    print(f"{Fore.WHITE}Query: {Fore.YELLOW}{result.query}{Style.RESET_ALL}")
    print(f"{Fore.WHITE}Type:  {Fore.YELLOW}{result.query_type}{Style.RESET_ALL}")
    print()

    # Gravatar
    if result.gravatar:
        g = result.gravatar
        print(f"{Fore.CYAN}{'='*50}")
        print(f" Gravatar Profile")
        print(f"{'='*50}{Style.RESET_ALL}")
        if g.display_name:
            print(f"  Name:     {g.display_name}")
        if g.location:
            print(f"  Location: {g.location}")
        if g.about:
            print(f"  About:    {g.about}")
        if g.profile_url:
            print(f"  Profile:  {Fore.BLUE}{g.profile_url}{Style.RESET_ALL}")
        if g.avatar_url:
            print(f"  Avatar:   {Fore.BLUE}{g.avatar_url}{Style.RESET_ALL}")
        if g.urls:
            print(f"  Links:")
            for url in g.urls:
                print(f"    - {Fore.BLUE}{url}{Style.RESET_ALL}")
        print()

    # Derived usernames
    if result.derived_usernames and result.query_type == "email":
        print(f"{Fore.CYAN}{'='*50}")
        print(f" Username Variations Checked")
        print(f"{'='*50}{Style.RESET_ALL}")
        for u in result.derived_usernames:
            print(f"  - {u}")
        print()

    # Account results
    found = result.found_accounts
    all_accounts = result.accounts

    print(f"{Fore.CYAN}{'='*50}")
    print(f" Account Enumeration ({len(found)} found / {len(all_accounts)} checked)")
    print(f"{'='*50}{Style.RESET_ALL}")

    if not found:
        print(f"  {Fore.YELLOW}No accounts found.{Style.RESET_ALL}")
    else:
        for acc in found:
            print(
                f"  {Fore.GREEN}[+]{Style.RESET_ALL} "
                f"{acc.platform.value:15s} "
                f"{Fore.BLUE}{acc.url}{Style.RESET_ALL}"
            )

    # Show errors if any
    errors = [a for a in all_accounts if a.status == AccountStatus.ERROR]
    if errors:
        print()
        print(f"  {Fore.RED}Errors ({len(errors)}):{Style.RESET_ALL}")
        for acc in errors:
            print(
                f"  {Fore.RED}[!]{Style.RESET_ALL} "
                f"{acc.platform.value:15s} - request failed"
            )

    print()
