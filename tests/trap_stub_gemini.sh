#!/usr/bin/env bash
# Mock gemini CLI stub for hermetic E2E deploy testing.
# Intercepts "skills link" subcommands and exits 0.

has_skills=false
has_link=false

for arg in "$@"; do
  if [ "$arg" = "skills" ]; then
    has_skills=true
  elif [ "$arg" = "link" ]; then
    has_link=true
  fi
done

if [ "$has_skills" = true ] && [ "$has_link" = true ]; then
  # Intercepted "skills link"
  exit 0
fi

echo "gemini mock called with: $*"
exit 0
