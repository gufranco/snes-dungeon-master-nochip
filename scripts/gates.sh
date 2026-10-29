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

step "coverage"
coverage report
