"""Legacy spider file.

The current Immobilienscout24 workflow in this repository no longer relies on Scrapy.
Use `python immo.py ...` with one or more saved-search URLs instead.
"""


def main() -> None:
    raise SystemExit(
        "This repository now uses Selenium saved-search monitoring. Run: python immo.py --help"
    )


if __name__ == "__main__":
    main()

