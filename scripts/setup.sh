#!/bin/bash
# Setup script — install dependencies + create directories
set -e

echo "🇻🇳 VN Breakout Scanner — Setup"
echo "=============================="

# Check Python version
python_version=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
required="3.10"
if [ "$(printf '%s\n' "$required" "$python_version" | sort -V | head -n1)" != "$required" ]; then
    echo "❌ Python >= 3.10 required (found $python_version)"
    exit 1
fi
echo "✓ Python $python_version"

# Create venv if not exists
if [ ! -d "venv" ]; then
    echo "→ Creating virtual environment..."
    python3 -m venv venv
fi

# shellcheck source=/dev/null
source venv/bin/activate
echo "✓ Virtual environment activated"

# Install
echo "→ Installing dependencies..."
pip install --upgrade pip --quiet
pip install -r backend/requirements.txt --quiet
echo "✓ Dependencies installed"

# Create runtime directories
mkdir -p backend/data/cache backend/data/results web/data
echo "✓ Directories ready"

# Test import
python -c "from scanner import BreakoutScanner; print('✓ Scanner import works')" \
    --eval-when=loaded 2>/dev/null || \
    (cd backend && python -c "from scanner import BreakoutScanner; print('✓ Scanner import works')")

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Activate venv:    source venv/bin/activate"
echo "  2. Run daily scan:   python backend/run_daily.py"
echo "  3. Start API:        uvicorn backend.api:app --reload"
echo "  4. Open dashboard:   open web/index.html"
