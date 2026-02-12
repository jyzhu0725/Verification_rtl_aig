#!/bin/bash
# Clean build script for Verification_rtl_aig
# This script removes all build artifacts to ensure clean compilation on any machine

echo "Cleaning build directories..."

# Clean mockturtle build
if [ -d "tools/mockturtle/build" ]; then
    echo "  Removing tools/mockturtle/build..."
    rm -rf tools/mockturtle/build
fi

# Clean kissat build
if [ -d "tools/kissat/build" ]; then
    echo "  Removing tools/kissat/build..."
    rm -rf tools/kissat/build
fi

# Clean ABC build artifacts (but keep source)
if [ -f "tools/abc/abc" ]; then
    echo "  Removing tools/abc/abc..."
    rm -f tools/abc/abc
fi

# Clean AIGER build artifacts
if [ -f "tools/aiger/aigtocnf" ]; then
    echo "  Removing tools/aiger/aigtocnf..."
    rm -f tools/aiger/aigtocnf
fi

# Clean CMake cache files
find . -name "CMakeCache.txt" -type f -delete 2>/dev/null
find . -name "CMakeFiles" -type d -exec rm -rf {} + 2>/dev/null
find . -name "cmake_install.cmake" -type f -delete 2>/dev/null
find . -name "Makefile" -path "*/build/*" -type f -delete 2>/dev/null

echo "Build directories cleaned successfully!"
echo "You can now rebuild the project from scratch."

