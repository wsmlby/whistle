#!/bin/bash
set -e

echo "Building whistle binary..."

# Clean up previous builds
rm -rf dist/ build/ whistle.spec

pyinstaller --onefile --name whistle whistle/__main__.py

echo "Build complete. The binary is in the dist/ directory."
