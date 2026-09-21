#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${ENV_FILE:-${PROJECT_DIR}/.env}"
PYTHON_BIN="${PROJECT_DIR}/.venv/bin/python"
PID_FILE="${PROJECT_DIR}/.demo.pid"
DEFAULT_HOST="${APP_HOST:-127.0.0.1}"
DEFAULT_PORT="${APP_PORT:-2001}"
CHECK_ONLY=false
UVICORN_ARGS=()

usage() {
  printf '%s\n' \
    'Usage: ./start.sh [--check] [uvicorn options]' \
    '' \
    'Validates the demo environment before starting Uvicorn.' \
    'Before launch, all previous instances of this demo are stopped.' \
    '' \
    'Options:' \
    '  --check       Validate configuration without starting the server' \
    '  -h, --help    Show this help' \
    '' \
    'Examples:' \
    '  ./start.sh --check' \
    '  ./start.sh --reload' \
    '  ./start.sh --host 0.0.0.0 --port 2002' \
    '  ENV_FILE=/secure/demo.env ./start.sh'
}

for argument in "$@"; do
  case "$argument" in
    --check) CHECK_ONLY=true ;;
    -h|--help) usage; exit 0 ;;
    *) UVICORN_ARGS+=("$argument") ;;
  esac
done

is_demo_process() {
  local process_id="$1"
  local process_command process_cwd
  [[ "$process_id" =~ ^[0-9]+$ ]] || return 1
  kill -0 "$process_id" 2>/dev/null || return 1
  process_command="$(ps -p "$process_id" -o args= 2>/dev/null || true)"
  [[ "$process_command" == *"uvicorn app.main:app"* ]] || return 1

  # On Linux, also require the process to belong to this project. The PID file
  # remains the portable fallback for platforms without /proc.
  if [[ -e "/proc/${process_id}/cwd" ]]; then
    process_cwd="$(readlink "/proc/${process_id}/cwd" 2>/dev/null || true)"
    [[ "$process_cwd" == "$PROJECT_DIR" ]] || return 1
  fi
  return 0
}

stop_existing_demo_processes() {
  local process_id deadline still_running
  local -a candidates=()

  if [[ -f "$PID_FILE" ]]; then
    read -r process_id < "$PID_FILE" || true
    if is_demo_process "${process_id:-}"; then
      candidates+=("$process_id")
    fi
  fi

  if command -v pgrep >/dev/null 2>&1; then
    while read -r process_id; do
      if is_demo_process "$process_id"; then
        candidates+=("$process_id")
      fi
    done < <(pgrep -f "uvicorn app[.]main:app" 2>/dev/null || true)
  fi

  if (( ${#candidates[@]} == 0 )); then
    rm -f "$PID_FILE"
    return
  fi

  # Sort/unique prevents duplicate signals when the PID file and process scan
  # identify the same server.
  mapfile -t candidates < <(printf '%s\n' "${candidates[@]}" | sort -un)
  printf 'Stopping %s previous demo process(es): %s\n' "${#candidates[@]}" "${candidates[*]}"
  kill -TERM "${candidates[@]}" 2>/dev/null || true

  deadline=$((SECONDS + 5))
  while (( SECONDS < deadline )); do
    still_running=false
    for process_id in "${candidates[@]}"; do
      if kill -0 "$process_id" 2>/dev/null; then
        still_running=true
        break
      fi
    done
    [[ "$still_running" == false ]] && break
    sleep 0.1
  done

  for process_id in "${candidates[@]}"; do
    if kill -0 "$process_id" 2>/dev/null; then
      printf 'Process %s did not stop gracefully; force-stopping it.\n' "$process_id"
      kill -KILL "$process_id" 2>/dev/null || true
    fi
  done
  rm -f "$PID_FILE"
}

if [[ ! -x "$PYTHON_BIN" ]]; then
  printf 'ERROR: Python virtual environment not found at %s\n' "$PYTHON_BIN" >&2
  printf 'Create it with: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt\n' >&2
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  printf 'ERROR: Environment file not found at %s\n' "$ENV_FILE" >&2
  printf 'Create it with: cp .env.example .env\n' >&2
  exit 1
fi

cd "$PROJECT_DIR"

"$PYTHON_BIN" - "$ENV_FILE" <<'PY'
from __future__ import annotations

import importlib.metadata
import os
from pathlib import Path
import sys
from urllib.parse import urlparse

from dotenv import dotenv_values


project_dir = Path.cwd()
env_path = Path(sys.argv[1]).resolve()
file_values = {key: value for key, value in dotenv_values(env_path).items() if value is not None}
configuration = {**file_values, **os.environ}
errors: list[str] = []
warnings: list[str] = []


def value(name: str, default: str = "") -> str:
    return configuration.get(name, default).strip()


def allowed(name: str, default: str, choices: set[str]) -> str:
    configured = value(name, default).lower()
    if configured not in choices:
        errors.append(f"{name} must be one of: {', '.join(sorted(choices))} (got {configured!r})")
    return configured


if sys.version_info < (3, 12):
    errors.append(f"Python 3.12+ is required; found {sys.version.split()[0]}")

required_packages = {
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "jinja2": "jinja2",
    "pydantic": "pydantic",
    "openai": "openai",
    "python-dotenv": "python-dotenv",
    "python-multipart": "python-multipart",
}
missing_packages = []
for display_name, distribution_name in required_packages.items():
    try:
        importlib.metadata.version(distribution_name)
    except importlib.metadata.PackageNotFoundError:
        missing_packages.append(display_name)
if missing_packages:
    errors.append("Missing packages: " + ", ".join(missing_packages) + ". Run: .venv/bin/pip install -r requirements.txt")

api_key = value("OPENAI_API_KEY")
if not api_key:
    errors.append("OPENAI_API_KEY is empty; a key is required to run the agent demonstration")
elif api_key.lower() in {"<key>", "your-key-here", "changeme"}:
    errors.append("OPENAI_API_KEY still contains a placeholder value")

model = value("OPENAI_MODEL", "gpt-5.6-sol")
if not model:
    errors.append("OPENAI_MODEL cannot be empty")

reasoning = allowed("OPENAI_REASONING_EFFORT", "medium", {"none", "minimal", "low", "medium", "high", "xhigh"})
security_mode = allowed("AGENT_SECURITY_MODE", "vulnerable", {"vulnerable", "protected"})
storage_mode = allowed("DEMO_STORAGE_MODE", "local", {"local", "azure"})

database_value = value("DATABASE_PATH", "demo.db")
database_path = Path(database_value)
if not database_path.is_absolute():
    database_path = project_dir / database_path
existing_parent = database_path.parent
while not existing_parent.exists() and existing_parent != existing_parent.parent:
    existing_parent = existing_parent.parent
if not existing_parent.is_dir() or not os.access(existing_parent, os.W_OK):
    errors.append(f"Database location is not writable: {database_path.parent}")

if storage_mode == "local":
    products_dir = project_dir / "demo_blob" / "products"
    shell_script = project_dir / "demo_blob" / "scripts" / "validation-check.sh"
    if not products_dir.is_dir():
        errors.append(f"Local product feed is missing: {products_dir}")
    else:
        required_products = {
            "product-001.txt",
            "product-002.md",
            "product-003.json",
            "product-016-poisoned.md",
        }
        missing_products = sorted(name for name in required_products if not (products_dir / name).is_file())
        if missing_products:
            errors.append("Local product feed is missing required files: " + ", ".join(missing_products))
    if not shell_script.is_file():
        errors.append(f"Approved shell script is missing: {shell_script}")
else:
    try:
        importlib.metadata.version("azure-storage-blob")
    except importlib.metadata.PackageNotFoundError:
        errors.append("Azure mode requires azure-storage-blob; install requirements.txt")
    azure_values = {
        "AZURE_STORAGE_ACCOUNT_URL": value("AZURE_STORAGE_ACCOUNT_URL"),
        "AZURE_STORAGE_CONTAINER": value("AZURE_STORAGE_CONTAINER"),
        "AZURE_STORAGE_SAS_TOKEN": value("AZURE_STORAGE_SAS_TOKEN"),
    }
    for name, configured in azure_values.items():
        if not configured:
            errors.append(f"{name} is required when DEMO_STORAGE_MODE=azure")
    account_url = azure_values["AZURE_STORAGE_ACCOUNT_URL"]
    if account_url:
        parsed = urlparse(account_url)
        if parsed.scheme != "https" or not parsed.netloc:
            errors.append("AZURE_STORAGE_ACCOUNT_URL must be a valid HTTPS account URL")
    if azure_values["AZURE_STORAGE_SAS_TOKEN"].lower() in {"<scoped-read-token>", "changeme"}:
        errors.append("AZURE_STORAGE_SAS_TOKEN still contains a placeholder value")
    warnings.append("Azure credentials are present but connectivity and SAS permissions are not tested during startup")

print("Poisoned at the Source — configuration check")
print(f"  Environment:      {env_path}")
print(f"  Python:           {sys.version.split()[0]}")
print(f"  OpenAI key:       {'configured' if api_key else 'missing'}")
print(f"  Model:            {model or 'missing'}")
print(f"  Reasoning effort: {reasoning}")
print(f"  Storage:          {storage_mode}")
print(f"  Security mode:    {security_mode}")
print(f"  Database:         {database_path}")

for warning in warnings:
    print(f"WARNING: {warning}")
if errors:
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    raise SystemExit(1)
print("Configuration valid.")
PY

if [[ "$CHECK_ONLY" == true ]]; then
  exit 0
fi

stop_existing_demo_processes
printf '%s\n' "$$" > "$PID_FILE"
printf 'Starting Uvicorn (default endpoint http://%s:%s; command-line options may override it)\n' "$DEFAULT_HOST" "$DEFAULT_PORT"
exec "$PYTHON_BIN" -m uvicorn app.main:app --env-file "$ENV_FILE" --host "$DEFAULT_HOST" --port "$DEFAULT_PORT" "${UVICORN_ARGS[@]}"
