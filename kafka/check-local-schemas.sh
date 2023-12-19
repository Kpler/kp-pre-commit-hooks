#!/usr/bin/env bash

# Safety measures
set -o errexit  # Leave immediately if a command returns an error
set -o nounset  # Leave immediately if an unitialized value is used
set -o pipefail # Leave immediately if a command fails in a pipe

[[ "${BASH_VERSION}" =~ ^(5|4\.[0-9]).* ]] && shopt -s inherit_errexit

SCRIPT_DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

#####################################################################
# Helper functions
#####################################################################

error() {
  local msg="$1" exit_code="${2:-1}"
  echo "ERROR: ${msg}">&2
  exit "${exit_code}"
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

get_md5sum() {
  local file="$1"
  md5sum "${file}" | awk '{ print $1}'
}


find_schema_class() {
  # The schema class heuristic is a bit hacky for now, we just expect
  # the filename containing the schema code to end with Schema or is named InputModel
  # We might want to improve this in the future
  schema_class_file="$(find src -name "*Schema.scala" -o -name "InputModel.scala" | head -n 1)"
  schema_class_name="$(basename "${schema_class_file}" .scala)"
  schema_package="$(awk ' $1 == "package" { print $2 }' "${schema_class_file}")"

  echo "${schema_package}.${schema_class_name}"
}

generate_schema_generator_code() {
  local schema_class="$1"

  schema_class_name="${schema_class##*.}"
  schema_package="${schema_class%.*}"

  # only schema class using vulcan are supported for now
  # but we might add support for avro4s in the future
  sed \
    -e "s/__SCHEMA_CLASS_NAME__/${schema_class_name}/g" \
    -e "s/__SCHEMA_PACKAGE__/${schema_package}/g" \
    "${SCRIPT_DIR}/generators/VulcanSchemaGenerator.tmpl.scala"
}

run_schema_generator_code() {
  local generator_code_file="$1" target_schema_file="$2"

  generator_source_folder="$(dirname "${generator_code_file}")"

  sbt_command=""
  # When fork is enabled, it seems we can't avoid all sbt logs to be printed
  # so we just disable it
  sbt_command+="set fork := false;"
  # We tell sbt to look for our generator code in the temporary folder in addition
  # to the existing source code, so we can run our generator code alongside the existing code
  # We need that as the generator code import the schema class
  sbt_command+="set Compile / unmanagedSourceDirectories += file(\"${generator_source_folder}\");"
  sbt_command+="runMain kp_pre_commit_hooks.generateSchemaFile ${target_schema_file}"

  sbt -batch -error "${sbt_command}"
}

#####################################################################
# Main code
#####################################################################

trap clean_temporary_folder EXIT

check_binary_exists "sbt"

target_schema_file="schemas/schema.avsc"

generator_source_folder="$(mktemp -d)"
generator_code_file="${generator_source_folder}/SchemaGenerator.scala"

[[ ! -f "${target_schema_file}" ]] || checksum_before="$(get_md5sum "${target_schema_file}")"

generate_schema_generator_code "$(find_schema_class)" > "${generator_code_file}"
run_schema_generator_code "${generator_code_file}" "${target_schema_file}"

if ! is_git_tracked "${target_schema_file}"; then
  error "Schema file \"${target_schema_file}\" is not tracked by git. Please commit it."
fi

checksum_after="$(get_md5sum "${target_schema_file}")"
if [[ "${checksum_after}" != "${checksum_before:-}" ]]; then
  error "Schema file \"${target_schema_file}\" was not consistent with code. Please commit the updated version."
fi
