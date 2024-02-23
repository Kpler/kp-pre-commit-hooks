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

get_repository_url() {
  git remote get-url origin
}

get_md5sum() {
  local file="$1"
  md5sum "${file}" | awk '{ print $1}'
}

find_schema_class_file() {
  # The schema class heuristic is a bit hacky for now, we try to find a file
  # where a class has been annotated with the schema annotation
  # Otherwise we fallback on finding the filename containing the schema code
  # to end with Schema or is named InputModel
  # We might want to improve this in the future
  schema_class_file="$(grep -lr "^@schema" src | head -n 1 || return 0)"

  if [[ -z "${schema_class_file}" ]]; then
    schema_class_file="$(find src -name "*Schema.scala" -o -name "InputModel.scala" | head -n 1 || return 0)"
  fi

  echo "${schema_class_file}"

}

find_schema_class() {
  local schema_class_file="$1"
  schema_class_name="$(basename "${schema_class_file}" .scala)"
  schema_package="$(awk ' $1 == "package" { print $2 }' "${schema_class_file}")"

  echo "${schema_package}.${schema_class_name}"
}

is_library_used() {
  local library="$1" candidate_class_file="$2"

  # if the library is not directly found in the candidate class file
  # we fallback on checking the build.sbt file itself
  # This doesn't fully protect against from indirect library loading
  # but it's a good enough heuristic for now
  for candidate in "${candidate_class_file}" build.sbt; do
    if grep -q -E "[^#]*${library}" "${candidate}"; then
      return 0
    fi
  done
  return 1
}

find_avro_library() {
  local schema_class_file="$1"

  if is_library_used "com.sksamuel.avro4s" "${schema_class_file}"; then
    echo "avro4s"
  elif is_library_used "vulcan" "${schema_class_file}"; then
    echo "vulcan"
  else
    error "Could not find any avro library import in ${schema_class_file}"
  fi

}

generate_schema_generator_code() {
  local schema_class="$1" schema_library="$2"

  schema_class_name="${schema_class##*.}"
  schema_package="${schema_class%.*}"

  # only schema class using vulcan are supported for now
  # but we might add support for avro4s in the future
  sed \
    -e "s/__SCHEMA_CLASS_NAME__/${schema_class_name}/g" \
    -e "s/__SCHEMA_PACKAGE__/${schema_package}/g" \
    "${SCRIPT_DIR}/generators/${schema_library^}SchemaGenerator.tmpl.scala"
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
  # Dynamically add the required dependencies to the build.sbt file
  sbt_command+="set libraryDependencies += \"com.lihaoyi\" %% \"upickle\" % \"3.1.3\";"
  sbt_command+="set libraryDependencies += \"com.lihaoyi\" %% \"os-lib\" % \"0.9.1\";"

  sbt_command+="runMain kp_pre_commit_hooks.generateSchemaFile ${target_schema_file}"

  sbt -batch -error "${sbt_command}"
  # Add a last linefeed to make pre-commit end-of-line fixer happy
  echo >> "${target_schema_file}"
}

#####################################################################
# Main code
#####################################################################

trap clean_temporary_folder EXIT

# We don't want to run on template repositories
[[ "$(get_repository_url)" != "git@github.com:Kpler/template-"* ]] || exit 0

check_binary_exists "sbt"

target_schema_file="schemas/schema.avsc"

generator_source_folder="$(mktemp -d)"
generator_code_file="${generator_source_folder}/SchemaGenerator.scala"

[[ ! -f "${target_schema_file}" ]] || checksum_before="$(get_md5sum "${target_schema_file}")"

schema_class_file="$(find_schema_class_file)"
[[ -n "${schema_class_file}" ]] || error "Could not find any schema class file"

schema_class="$(find_schema_class "${schema_class_file}")"
schema_library="$(find_avro_library "${schema_class_file}")"

generate_schema_generator_code "${schema_class}" "${schema_library}" > "${generator_code_file}"
run_schema_generator_code "${generator_code_file}" "${target_schema_file}"

if ! is_git_tracked "${target_schema_file}"; then
  error "Schema file \"${target_schema_file}\" is not tracked by git. Please commit it."
fi

checksum_after="$(get_md5sum "${target_schema_file}")"
if [[ "${checksum_after}" != "${checksum_before:-}" ]]; then
  error "Schema file \"${target_schema_file}\" was missing or not consistent with code. Please commit the updated version."
fi
