"""`python -m factory.film <command>`: the film recorder's entry. Parses nothing itself; the CLI
module does, and the composition root builds the services."""

import sys

from factory.composition import build_film
from factory.film.cli import main

if __name__ == "__main__":
    sys.exit(main(app_factory=build_film))
