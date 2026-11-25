#!/usr/bin/env bash
set -euo pipefail
case "${SSH_ORIGINAL_COMMAND:-}" in
    "") exit 0 ;;
    rollback) exec sudo -n /opt/auctions-lr6/staging.sh rollback ;;
esac
pattern='^deploy ([0-9a-f]{40})( (sha256:[0-9a-f]{64}))?$'
if [[ "$SSH_ORIGINAL_COMMAND" =~ $pattern ]]; then
    args=(deploy "${BASH_REMATCH[1]}")
    if [[ -n "${BASH_REMATCH[3]}" ]]; then args+=("${BASH_REMATCH[3]}"); fi
    exec sudo -n /opt/auctions-lr6/staging.sh "${args[@]}"
fi
exit 2
