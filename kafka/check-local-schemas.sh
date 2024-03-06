#!/usr/bin/env bash

# Safety measures
set -o errexit  # Leave immediately if a command returns an error
set -o nounset  # Leave immediately if an unitialized value is used
set -o pipefail # Leave immediately if a command fails in a pipe

shopt -s nullglob

[[ "${BASH_VERSION}" =~ ^(5|4\.[0-9]).* ]] && shopt -s inherit_errexit


#####################################################################
# Helper functions
#####################################################################

fatal() {
  local msg="$1" exit_code="${2:-1}"
  echo "FATAL: ${msg}">&2
  exit "${exit_code}"
}

error() {
  local msg="$1"
  echo "ERROR: ${msg}">&2
}

check_binary_exists() {
  local binary="$1"
  command -v "${binary}" &>/dev/null || error "${binary} is required but it's not installed"
}

clean_temporary_folder() {
  [[ -z "${generator_source_folder:-}" ]] || rm -rf "${generator_source_folder}"
}

is_git_tracked() {
    git ls-files --error-unmatch "$1" &> /dev/null || return 1
}

get_repository_url() {
  git remote get-url origin
}

md5sum_files() {
  [[ -z "$*" ]] || md5sum "$@"
}


get_md5sum() {
  local file="$1" checksums="$2"
  awk -v file="${file}" '$2 == file { print $1 }' <<< "${checksums}"
}

detect_current_project_language() {
  if [[ -n "${PROJECT_LANGUAGE:-}" ]]; then
    echo "${PROJECT_LANGUAGE}"
  elif [[ -f "build.sbt" ]]; then
    echo "scala"
  else
    echo "unknown"
  fi
}

fix_end_of_file() {
  local file="$1"
  [[ $(tail -c1 "${file}") == "" ]] || echo >> "${file}"
}

fix_kafka_schemas_end_of_file() {
  for schema_file in $(find_schema_files); do
    fix_end_of_file "${schema_file}"
  done
}

find_schema_files() {
  find schemas -type f -name '*.avsc' | sort
}

find_obsolete_schema_files() {
  local date="$1"
  find schemas -type f -name '*.avsc' -not -newermt "${date}"
}

generate_kafka_schemas_for_scala() {
    if ! sbt "tasks -V" | grep -qE "^ *generateKafkaSchemas "; then
      error "The project does not have a sbt generateKafkaSchemas task"
    fi
    sbt -batch -error  "set fork := false; generateKafkaSchemas"
}

run_schema_generation_task() {
  local language="$1"
  case "${language}" in
    scala)
      check_binary_exists "sbt"
      generate_kafka_schemas_for_scala
      fix_kafka_schemas_end_of_file
      ;;
    *)
      error "Unsupported language: ${language}"
      ;;
  esac
}

#####################################################################
# Main code
#####################################################################

trap clean_temporary_folder EXIT

language="$(detect_current_project_language)"

before_schema_generation="$(date --date='-1 second' +'%Y-%m-%d %H:%M:%S')"

# shellcheck disable=SC2046
schema_md5sum_before="$(md5sum_files $(find_schema_files))"

run_schema_generation_task "${language}"

schema_files_generated=$(find_schema_files)
[[ -n "${schema_files_generated}" ]] || fatal "No schema files found were generated"

# shellcheck disable=SC2086
schema_md5sum_after="$(md5sum_files ${schema_files_generated})"

error_found="false"

for schema_file in ${schema_files_generated}; do
  if ! is_git_tracked "${schema_file}"; then
    error "Schema file \"${schema_file}\" is not tracked by git. Please commit it."
    error_found="true"
  fi

  checksum_after="$(get_md5sum "${schema_file}" "${schema_md5sum_after}")"
  checksum_before="$(get_md5sum "${schema_file}" "${schema_md5sum_before}")"
  if [[ "${checksum_after}" != "${checksum_before}" ]]; then
    error "Schema file \"${schema_file}\" is not consistent with code. Please commit the updated version."
    error_found="true"
  fi
done

obsolete_schemas_files=$(find_obsolete_schema_files "${before_schema_generation}")
if [[ -n "${obsolete_schemas_files}" ]]; then
  error "The following schema files seem obsolete: ${obsolete_schemas_files}. Please delete them."
  error_found="true"
fi

[[ "${error_found}" == "false" ]] || exit 1

