#!/usr/bin/env bash
# Запускается вне Jenkins-агента; скрипт публикации хранится в защищённом локальном каталоге.
set -u
root="${AUCTIONS_CI_ROOT:?set AUCTIONS_CI_ROOT}"
state="$root/ci/.secrets/release-last-attempt"
runner="$root/ci/.secrets/trusted-release.sh"
export GIT_TERMINAL_PROMPT=0
while :; do
    sha="$(git ls-remote https://github.com/myffyy/auctions.git refs/heads/main 2>/dev/null | cut -f1)"
    if [ "${#sha}" -eq 40 ]; then
        if [ ! -f "$state" ]; then
            printf '%s\n' "$sha" > "$state"
            echo "Release monitor started at $sha"
        elif [ "$(cat "$state")" != "$sha" ]; then
            echo "Checking main commit $sha"
            if "$runner"; then echo "Release passed for $sha"; else echo "Release blocked for $sha"; fi
            printf '%s\n' "$sha" > "$state"
        fi
    fi
    sleep 300
done
