#!/bin/sh
# The OspreyFlow bootstrap for macOS and Linux (06_DECISIONS.md ADR-114 decision 2; Amendment 3
# decision 3). It brings `uv`, gets the checkout, installs the `ospreyflow` command as a uv tool and
# records where the checkout is. It installs nothing else and starts nothing: the next two commands
# it prints do that.
#
#   sh install.sh                         # from inside a checkout
#   OSPREYFLOW_REPO=<address> sh install.sh   # clone the repository into ~/ospreyflow first
set -eu

say() { printf '%s\n' "$*"; }
stop() { printf 'install.sh: %s\n' "$*" >&2; exit 1; }

is_product() { [ -f "$1/harness/__init__.py" ] && [ -f "$1/osprey.yaml" ]; }

# 1. uv.
if ! command -v uv >/dev/null 2>&1; then
    say "uv is not installed; installing it with the official installer (https://astral.sh/uv)."
    command -v curl >/dev/null 2>&1 || stop "curl is needed to install uv. Install curl, or install uv yourself, then run this again."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    export PATH
    command -v uv >/dev/null 2>&1 || stop "uv was installed but is not on the PATH. Open a new terminal and run this again."
fi

# 2. The checkout: the one this script sits in, the one it is run from, or a fresh clone.
here=$(cd "$(dirname "$0")" 2>/dev/null && pwd || pwd)
product=""
for candidate in "$here" "$here/OspreyFlow_Core" "$PWD" "$PWD/OspreyFlow_Core"; do
    if is_product "$candidate"; then product=$candidate; break; fi
done
if [ -z "$product" ]; then
    [ -n "${OSPREYFLOW_REPO:-}" ] || stop "This is not run from inside an OspreyFlow checkout. Set OSPREYFLOW_REPO to the address of the OspreyFlow repository and run this again; it will be cloned into \$HOME/ospreyflow."
    command -v git >/dev/null 2>&1 || stop "Git is needed to get the checkout. Install Git (https://git-scm.com/downloads), then run this again."
    if is_product "$HOME/ospreyflow"; then
        say "Using the checkout already in $HOME/ospreyflow."
    else
        git clone "$OSPREYFLOW_REPO" "$HOME/ospreyflow"
    fi
    product="$HOME/ospreyflow"
    is_product "$product" || stop "$product is not an OspreyFlow checkout (it has no harness/ and osprey.yaml)."
fi

# 3. The checkout's own environment, then the command.
uv sync --inexact --project "$product"   # --inexact: never remove what the checkout already has
uv tool install --editable "$product/cli"

# 4. Remember where the checkout is, so the command finds it from any folder.
home_file="${XDG_CONFIG_HOME:-$HOME/.config}/ospreyflow/home"
mkdir -p "$(dirname "$home_file")"
printf '%s\n' "$product" > "$home_file"

say ""
say "OspreyFlow's command is installed. The checkout is $product."
say "Next:"
say "  ospreyflow doctor"
say "  ospreyflow install --mode lite"
say "(If the command is not found, open a new terminal, or run: uv tool update-shell)"
