#!/bin/zsh
set -euo pipefail
DEMO_ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
exec "$DEMO_ROOT/.venv/bin/python" "$(dirname "$0")/code/presentation_steps.py" --workspace "$DEMO_ROOT" "${1:-data}"
