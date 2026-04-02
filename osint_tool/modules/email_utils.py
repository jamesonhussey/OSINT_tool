import re


def extract_username_from_email(email: str) -> str:
    """Extract the local part (before @) from an email address."""
    return email.split("@")[0]


def generate_username_variations(email: str) -> list[str]:
    """Generate likely username variations from an email address.

    Given "john.doe@gmail.com", produces variations like:
    john.doe, johndoe, john_doe, john-doe, jdoe, johnd
    """
    local = extract_username_from_email(email)
    variations = set()

    # Original local part
    variations.add(local)

    # Remove dots, hyphens, underscores
    stripped = re.sub(r"[.\-_]", "", local)
    variations.add(stripped)

    # Replace separators with each other
    for sep in [".", "-", "_"]:
        replaced = re.sub(r"[.\-_]", sep, local)
        variations.add(replaced)

    # Split on separators and create abbreviated forms
    parts = re.split(r"[.\-_]", local)
    if len(parts) >= 2:
        # First initial + last part: jdoe
        variations.add(parts[0][0] + parts[-1])
        # First part + last initial: johnd
        variations.add(parts[0] + parts[-1][0])
        # Just first part: john
        variations.add(parts[0])
        # Just last part: doe
        variations.add(parts[-1])

    # Remove any empty strings or single-char results (too generic)
    variations = {v for v in variations if len(v) > 1}

    return sorted(variations)
