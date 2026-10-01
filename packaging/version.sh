#!/bin/sh
# Print the version from the Python package.
sed -n 's/^__version__ = "\(.*\)"/\1/p' "$(dirname "$0")/../src/convertoor/__init__.py"
