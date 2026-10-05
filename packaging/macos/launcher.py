"""Entry point for the macOS app bundle."""
import sys

# Finder used to pass a process serial number argument; drop it if present.
sys.argv = [a for a in sys.argv if not a.startswith("-psn_")]

from convertoor.cli import main  # noqa: E402

sys.exit(main())
