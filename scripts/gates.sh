#!/bin/sh
set -eu

cd "$(dirname -- "$0")/.."

step() {
  printf '\n== %s\n' "$1"
}

step "ruff check"
ruff check .

step "ruff format"
ruff format --check .

step "mypy"
mypy

step "prettier"
prettier --check "**/*.{json,yml,yaml}"

step "yamllint"
yamllint --strict .

step "shellcheck"
shellcheck --severity=style scripts/*.sh run.sh

step "actionlint"
actionlint

step "tests under coverage"
coverage erase
for module in *.test.py tools/*.test.py conformance/*.test.py; do
  if [ ! -e "${module}" ]; then
    continue
  fi
  printf '%s\n' "-- ${module}"
  coverage run -a "${module}"
done

if [ "${RETAIL_INPUTS:-present}" = "absent" ]; then
  step "coverage, without the *.retail.* files, because RETAIL_INPUTS=absent"
  coverage report --omit='*.retail.*'
else
  step "coverage, every file, the *.retail.* ones included"
  if ! coverage report; then
    printf '%s\n' "A file is under 100%. If this machine has no dumps, run with RETAIL_INPUTS=absent, as CI does." >&2
    exit 1
  fi
fi
