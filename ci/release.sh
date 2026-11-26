#!/usr/bin/env bash
# Запускать только из доверенной конфигурации публикации, недоступной PR.
set -euo pipefail
root="${AUCTIONS_CI_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
password="$root/ci/.secrets/registry-password"
[ -f "$password" ] || { echo "Registry credentials missing" >&2; exit 1; }
docker_host="$(docker context inspect --format '{{.Endpoints.docker.Host}}')"
case "$docker_host" in unix://*) ;; *) echo "A local Docker socket is required" >&2; exit 1;; esac
export DOCKER_HOST="$docker_host"
unset DOCKER_CONTEXT
tmp="$(mktemp -d -t auctions-release.XXXXXXXX)"
db="auctions-release-$(python3 -c 'import uuid; print(uuid.uuid4().hex)')"
sha=""
cleanup() {
    docker rm -f "$db" >/dev/null 2>&1 || true
    if [ -n "$sha" ] && [ -d "$tmp/source/reports" ]; then
        mkdir -p "$root/reports/releases/$sha"
        cp -R "$tmp/source/reports/." "$root/reports/releases/$sha/" || true
    fi
    rm -rf "$tmp"
}
trap cleanup EXIT
git clone --quiet --depth=1 --single-branch --branch main https://github.com/myffyy/auctions.git "$tmp/source"
cd "$tmp/source"
sha="$(git rev-parse HEAD)"
case "$sha" in (*[!0-9a-f]*|'') exit 1;; esac
[ "${#sha}" -eq 40 ] || exit 1
image="localhost:5001/auctions:$sha"
mkdir -p reports
docker run -d --name "$db" -p 127.0.0.1::5432 -e POSTGRES_PASSWORD=ci-test-only postgres:14-alpine >/dev/null
for n in $(seq 1 60); do
    if docker exec "$db" pg_isready -U postgres >/dev/null 2>&1; then break; fi
    [ "$n" -lt 60 ] || exit 1
    sleep 1
done
port="$(docker port "$db" 5432 | head -n 1 | cut -d: -f2)"
export TEST_DATABASE_URL="postgresql+psycopg://postgres:ci-test-only@127.0.0.1:$port/auctions_test"
export SETUP_DATABASE_URL="postgresql+psycopg://postgres:ci-test-only@127.0.0.1:$port/postgres"
export DATABASE_URL="postgresql+psycopg://postgres:ci-test-only@127.0.0.1:$port/auctions"
export POSTGRES_PASSWORD=ci-container-only SESSION_SECRET=ci-container-session-only ADMIN_PASSWORD=ci-container-admin-only
make verify docker-lint-check secrets-check dependencies-check container-check
docker build --build-arg "RELEASE_REVISION=$sha" -t "$image" .
make image-check IMAGE="$image"
remote_sha="$(git ls-remote --exit-code origin refs/heads/main | cut -f1)"
[ "$remote_sha" = "$sha" ] || { echo "main changed while checks were running; refusing to publish" >&2; exit 1; }
export DOCKER_CONFIG="$tmp/docker-config"
mkdir -p "$DOCKER_CONFIG"
cat "$password" | docker login localhost:5001 --username ci --password-stdin >/dev/null
docker push "$image" | tee reports/publish.log
docker image inspect "$image" --format '{{index .RepoDigests 0}}' > reports/published-digest.txt
mkdir -p "$root/reports/releases/$sha"
cp -R reports/. "$root/reports/releases/$sha/"
printf 'Published commit %s\n' "$sha"
