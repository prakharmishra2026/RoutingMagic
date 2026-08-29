#!/bin/bash
# RoutingMagic Desk - One-command installer
# Installs the unified AI usage dashboard with all dependencies

set -e

echo "🔮 RoutingMagic Desk - Installer"
echo "================================="

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
echo "Python: $PYTHON_VERSION"

# Create directories
echo "📁 Creating directories..."
mkdir -p ~/.routingmagic/{metrics,registry,quality,learning}
mkdir -p ~/.local/bin

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip3 install --break-system-packages -q openai pyyaml requests 2>/dev/null || pip3 install --user -q openai pyyaml requests

# Copy dashboard_server.py to ~/.local/bin if not there
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ ! -f ~/.local/bin/rm-desk ]; then
    ln -sf "$SCRIPT_DIR/dashboard_server.py" ~/.local/bin/rm-desk
    chmod +x ~/.local/bin/rm-desk
    echo "✅ Linked rm-desk to ~/.local/bin"
fi

# Setup .env if not exists
if [ ! -f ~/.routingmagic/.env ]; then
    cp "$SCRIPT_DIR/.env.example" ~/.routingmagic/.env 2>/dev/null || cat > ~/.routingmagic/.env << 'ENVEOF'
# RoutingMagic API Keys
# Get NVAPI_KEY from https://build.nvidia.com/nim/dashboard
# Get OPENROUTER_API_KEY from https://openrouter.ai/keys
NVAPI_KEY=
OPENROUTER_API_KEY=
GEMINI_API_KEY=
ENVEOF
    chmod 600 ~/.routingmagic/.env
    echo "📝 Created ~/.routingmagic/.env - add your API keys"
fi

# Setup quotas.yaml if not exists
if [ ! -f ~/.routingmagic/quotas.yaml ]; then
    cat > ~/.routingmagic/quotas.yaml << 'YAMLEOF'
budgets:
  monthly_usd: 50.00
  daily_tokens: 2000000
  providers:
    anthropic:
      type: subscription
      plan: max
      periodic_tokens: 1000000
      refresh_hours: 5
    openrouter:
      type: credits
      balance_usd: 10.00
    nvidia_nim:
      type: rate_limit
      rpm: 40
      tpm: 200000
    openai:
      type: credits
      balance_usd: 5.00
    ollama:
      type: custom_cap
      daily_tokens: 1000000
      weekly_tokens: 5000000
    antigravity:
      type: subscription
      plan: ultra
      periodic_tokens: 5000000
      refresh_hours: 5
    chatgpt:
      type: credits
      balance_usd: 20.00
    gemini:
      type: credits
      balance_usd: 10.00
alerts:
  warning_pct: 80
  critical_pct: 90
  exhausted_pct: 100
  notify_desktop: true
YAMLEOF
    echo "📝 Created ~/.routingmagic/quotas.yaml"
fi

# Run initial scan
echo "🔍 Running initial scan..."
cd "$SCRIPT_DIR"
python3 unified_scanner.py 2>/dev/null || true

# Download Chart.js if not present
if [ ! -f "$SCRIPT_DIR/assets/chart.umd.min.js" ]; then
    echo "📥 Downloading Chart.js..."
    mkdir -p "$SCRIPT_DIR/assets"
    curl -sL "https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js" -o "$SCRIPT_DIR/assets/chart.umd.min.js"
fi

echo ""
echo "✅ RoutingMagic Desk installed!"
echo ""
echo "📋 Next steps:"
echo "  1. Add API keys to ~/.routingmagic/.env"
echo "  2. Run: rm-desk (or python3 dashboard_server.py)"
echo "  3. Open http://localhost:9898"
echo ""
echo "🔗 Useful commands:"
echo "  rm-desk              # Start dashboard"
echo "  rm-desk scan         # Scan all sources"
echo "  rm-desk --port 8080  # Custom port"
echo ""
