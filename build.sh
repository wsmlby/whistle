#!/bin/bash
set -e

echo "Building whistle binary..."


# Clean up previous builds
rm -rf dist/ build/ whistle.spec

# Install dependencies from pyproject.toml
if [ -d "venv" ]; then
	source venv/bin/activate
fi
pip install --upgrade pip
pip install .[build]

apt list --installed |grep binutils || {
    echo "binutils is not installed. Installing..."
    apt update && apt install -y binutils
}

pyinstaller --onefile --name whistle whistle/__main__.py

echo "Build complete. The binary is in the dist/ directory."
