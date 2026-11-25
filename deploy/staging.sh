#!/usr/bin/env bash
set -euo pipefail
umask 077
cd /opt/auctions-lr6
registry_config=/opt/auctions-lr6/registry-auth
unset APP_IMAGE COMPOSE_FILE COMPOSE_PROJECT_NAME DOCKER_HOST DOCKER_CONTEXT
repository=127.0.0.1:15001/auctions
phase=arguments
trap 'echo "Staging command failed at: $phase" >&2' ERR
mode="${1:-}"
[[ "$mode" == deploy && ( $# == 2 || $# == 3 ) || "$mode" == rollback && $# == 1 ]]

phase=lock
exec 9>release.lock
flock -n 9
current= previous=
if [[ -f accepted ]]; then
    read -r current < accepted
    previous="$(sed -n '2p' accepted)"
fi

phase=select
if [[ "$mode" == deploy ]]; then
    revision="$2"
    digest="${3:-}"
else
    target="$previous"
    if [[ -f attempted ]]; then target="$current"; fi
    [[ -n "$target" ]]
    read -r revision digest <<< "$target"
fi
[[ "$revision" =~ ^[0-9a-f]{40}$ ]]
[[ -z "$digest" || "$digest" =~ ^sha256:[0-9a-f]{64}$ ]]

compose=(docker compose --project-name auctions-lr6 --env-file staging.env -f compose.yml)
phase=configuration
export APP_IMAGE="$repository:$revision"
"${compose[@]}" config --quiet
[[ -r smoke.json ]]

phase=pull
if [[ -z "$digest" ]]; then
    docker --config "$registry_config" pull "$APP_IMAGE"
    references="$(docker image inspect "$APP_IMAGE" --format '{{range .RepoDigests}}{{println .}}{{end}}')"
    digest="$(awk -v prefix="$repository@" 'index($0, prefix)==1 {print substr($0,length(prefix)+1); exit}' <<< "$references")"
fi
[[ "$digest" =~ ^sha256:[0-9a-f]{64}$ ]]
export APP_IMAGE="$repository@$digest"
docker --config "$registry_config" pull "$APP_IMAGE"
[[ "$(docker image inspect "$APP_IMAGE" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')" == "$revision" ]]

candidate="$revision $digest"
phase=apply
printf '%s\n' "$candidate" > attempted.tmp
mv -f attempted.tmp attempted
"${compose[@]}" up -d --no-build --wait --wait-timeout 120

phase=containers
for service in db app; do
    id="$("${compose[@]}" ps -q "$service")"
    [[ "$(docker inspect --format '{{.State.Health.Status}}' "$id")" == healthy ]]
done
id="$("${compose[@]}" ps -a -q migrate)"
[[ "$(docker inspect --format '{{.State.Status}}:{{.State.ExitCode}}' "$id")" == exited:0 ]]

phase=http
python3 smoke.py "$revision" smoke.json

phase=accept
if [[ "$candidate" != "$current" ]]; then
    printf '%s\n%s\n' "$candidate" "$current" > accepted.tmp
    mv -f accepted.tmp accepted
fi
rm -f attempted
printf 'Accepted %s\n' "$candidate"
