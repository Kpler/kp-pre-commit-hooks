#!/usr/bin/env bash

# Safety measures
set -o errexit  # Leave immediately if a command returns an error
set -o nounset  # Leave immediately if an unitialized value is used
set -o pipefail # Leave immediately if a command fails in a pipe

[[ "${BASH_VERSION}" =~ ^(5|4\.[0-9]).* ]] && shopt -s inherit_errexit

#####################################################################
# Helper functions
#####################################################################

function error() {
    local msg="$1" exit_code="${2:-}"
    echo "ERROR: ${msg}">&2
    exit "${exit_code}"
}

function check_binary_exists() {
    local binary="$1"
  command -v "${binary}" &>/dev/null || error "${binary} is required but it's not installed"
}

#####################################################################
# Main code
#####################################################################

check_binary_exists "sbt"

sbt "runMain tools.generateSchemaFile schemas/schema.json"
