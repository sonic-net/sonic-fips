"""Keep prepared FIPS changelogs aligned with the existing Make recipe."""

def fips_changelog(ctx):
    """Apply Makefile's +fips policy to the selected Debian source version."""
    text = ctx.read("debian/changelog")
    header = text.split("\n", 1)[0]
    if "(" not in header or ")" not in header:
        fail("Invalid Debian changelog header")
    version = header.split("(", 1)[1].split(")", 1)[0]
    if not version.endswith("+fips"):
        ctx.file("debian/changelog", text.replace("(" + version + ")", "(" + version + "+fips)", 1))
