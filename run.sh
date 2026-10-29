#!/bin/sh
set -eu

project=snes-dungeon-master-nochip
origin="https://github.com/gufranco/${project}.git"
root=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)

fail() {
  printf '%s\n' "$@" >&2
  exit 1
}

if [ ! -e "${root}/.git" ]; then
  fail "This folder has no git metadata, so it came from a downloaded archive." \
    "A downloaded ZIP never carries the submodules and nothing can add them afterwards." \
    "Delete this folder and clone instead:" \
    "  git clone --recurse-submodules ${origin}"
fi

if ! command -v docker >/dev/null 2>&1; then
  fail "Docker is not installed, and every command here runs in its container." \
    "Install Docker Desktop on Windows or macOS, or Docker Engine on Linux, then open a new terminal."
fi

if ! docker info >/dev/null 2>&1; then
  fail "Docker is installed but its engine is not answering." \
    "Start Docker Desktop and wait until it says the engine is running, or on Linux run: sudo systemctl start docker"
fi

target=runtime
case "${1:-}" in
--gates)
  target=gates
  shift
  if [ "$#" -eq 0 ]; then
    set -- sh scripts/gates.sh
  else
    set -- python3 "$@"
  fi
  ;;
--exec)
  shift
  ;;
*)
  set -- python3 "$@"
  ;;
esac

image="${project}:${target}"
docker build --quiet --target "${target}" --tag "${image}" "${root}" >/dev/null

terminal=""
if [ -t 0 ] && [ -t 1 ]; then
  terminal="--tty"
fi

exec docker run --rm --interactive ${terminal} \
  --network none \
  --user "$(id -u):$(id -g)" \
  --volume "${root}:/work" \
  --workdir /work \
  --env RETAIL_INPUTS \
  "${image}" "$@"
