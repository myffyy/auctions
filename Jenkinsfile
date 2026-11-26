pipeline {
    agent { label "${env.JOB_NAME == 'auctions-staging-release' ? 'auctions-release' : 'auctions-ci'}" }
    parameters {
        choice(name: 'RELEASE_ACTION', choices: ['publish', 'deploy', 'rollback'], description: 'Trusted release job only.')
        string(name: 'RELEASE_TAG', defaultValue: '', description: 'Full commit SHA for manual deployment.')
    }
    options { skipDefaultCheckout(); timestamps(); timeout(time: 90, unit: 'MINUTES'); disableConcurrentBuilds(); buildDiscarder(logRotator(daysToKeepStr: '14')) }
    stages {
        stage('Исходный код') {
            steps {
                deleteDir()
                checkout scm
            }
        }
        stage('Проверки и сборка') {
            when { expression { env.JOB_NAME != 'auctions-staging-release' || params.RELEASE_ACTION == 'publish' } }
            stages {
                stage('Подготовка') {
                    steps {
                        script { env.CI_DB = 'auctions-ci-' + java.util.UUID.randomUUID().toString() }
                        sh '''
                        set -eu
                        mkdir -p reports
                        docker run -d --name "$CI_DB" -p 127.0.0.1::5432 -e POSTGRES_PASSWORD=ci-test-only postgres:14-alpine
                        i=0
                        until docker exec "$CI_DB" pg_isready -U postgres; do
                            i=$((i+1)); [ "$i" -lt 60 ] || exit 1; sleep 1
                        done
                        uv sync --locked
                    '''
                        script {
                            def port = sh(script: 'docker port "$CI_DB" 5432 | head -n 1 | cut -d: -f2', returnStdout: true).trim()
                            env.TEST_DATABASE_URL = "postgresql+psycopg://postgres:ci-test-only@127.0.0.1:${port}/auctions_test"
                            env.SETUP_DATABASE_URL = "postgresql+psycopg://postgres:ci-test-only@127.0.0.1:${port}/postgres"
                            env.DATABASE_URL = "postgresql+psycopg://postgres:ci-test-only@127.0.0.1:${port}/auctions"
                        }
                    }
                }
                stage('Стиль') { steps { sh 'make quality docker-lint-check' } }
                stage('Тесты') { steps { sh 'make test test-mutations' } }
                stage('Миграции') { steps { sh 'make check-migrations' } }
                stage('Резервное копирование') { steps { sh 'make check-backup' } }
                stage('Безопасность') { steps { sh 'make sast secrets-check dependencies-check' } }
                stage('Контейнер') {
                    environment {
                        POSTGRES_PASSWORD = credentials('auctions-ci-postgres-password')
                        SESSION_SECRET = credentials('auctions-ci-session-secret')
                        ADMIN_PASSWORD = credentials('auctions-ci-admin-password')
                    }
                    steps { sh 'make container-check' }
                }
                stage('Сборка и анализ') {
                    steps { sh '''
                        set -eu
                        SHA=$(git rev-parse HEAD)
                        IMAGE="auctions-ci:$SHA"
                        if [ "$JOB_NAME" = auctions-staging-release ]; then
                            IMAGE="localhost:5001/auctions:$SHA"
                        fi
                        docker build --build-arg "RELEASE_REVISION=$SHA" -t "$IMAGE" .
                        make image-check IMAGE="$IMAGE"
                    ''' }
                }
            }
        }
        stage('CD · Публикация') {
            when { expression { env.JOB_NAME == 'auctions-staging-release' && params.RELEASE_ACTION == 'publish' } }
            steps {
                withCredentials([string(credentialsId: 'auctions-release-registry-password', variable: 'REGISTRY_PASSWORD')]) {
                    sh '''#!/usr/bin/env bash
                        set -euo pipefail
                        sha=$(git rev-parse HEAD)
                        remote=$(git ls-remote --exit-code origin refs/heads/main | cut -f1)
                        if [[ "$remote" != "$sha" ]]; then
                            echo 'main changed during the build' >&2
                            exit 1
                        fi
                        image="localhost:5001/auctions:$sha"
                        config=$(mktemp -d)
                        trap 'rm -rf "$config"' EXIT
                        printf '%s\\n' "$REGISTRY_PASSWORD" | docker --config "$config" login localhost:5001 --username ci --password-stdin
                        docker --config "$config" push "$image" | tee reports/publish.log
                        docker image inspect "$image" --format '{{range .RepoDigests}}{{println .}}{{end}}' | grep '^localhost:5001/auctions@sha256:' | sed -n '1p' > reports/published-digest.txt
                        grep -Eq '^localhost:5001/auctions@sha256:[a-f0-9]{64}$' reports/published-digest.txt
                    '''
                }
            }
        }
        stage('CD · Развёртывание и приёмка') {
            when { expression { env.JOB_NAME == 'auctions-staging-release' } }
            steps {
                withCredentials([
                    file(credentialsId: 'auctions-release-ssh-key', variable: 'STAGING_KEY'),
                    file(credentialsId: 'auctions-release-known-hosts', variable: 'STAGING_HOSTS')
                ]) {
                    sh '''\
                        |#!/usr/bin/env bash
                        |set -euo pipefail
                        |mkdir -p reports
                        |action="$RELEASE_ACTION"
                        |sha=
                        |digest=
                        |case "$action" in
                        |    publish)
                        |        action=deploy
                        |        sha=$(git rev-parse HEAD)
                        |        digest=$(cut -d @ -f 2 reports/published-digest.txt)
                        |        [[ "$digest" =~ ^sha256:[a-f0-9]{64}$ ]]
                        |        ;;
                        |    deploy) sha="$RELEASE_TAG" ;;
                        |    rollback) ;;
                        |    *) exit 2 ;;
                        |esac
                        |[[ "$action" == rollback || "$sha" =~ ^[a-f0-9]{40}$ ]]
                        |registry_socket="/home/auctions-deploy/staging/registry-$(openssl rand -hex 12).sock"
                        |ssh -T -F /dev/null -i "$STAGING_KEY" -o IdentitiesOnly=yes \\
                        |    -o UserKnownHostsFile="$STAGING_HOSTS" -o StrictHostKeyChecking=yes \\
                        |    -o BatchMode=yes -o ExitOnForwardFailure=yes -o ConnectTimeout=10 \\
                        |    -R "$registry_socket:127.0.0.1:5001" auctions-deploy@192.168.64.24 \\
                        |    "bash -s -- $registry_socket $action $sha $digest" 2>&1 <<'STAGING' | tee reports/staging.log
                        |set -Eeuo pipefail
                        |umask 077
                        |registry_socket="$1"
                        |shift
                        |[[ "$registry_socket" =~ ^/home/auctions-deploy/staging/registry-[a-f0-9]{24}[.]sock$ ]]
                        |registry_proxy=
                        |cleanup() {
                        |    if [[ -n "$registry_proxy" ]]; then kill "$registry_proxy" 2>/dev/null || true; fi
                        |    rm -f -- "$registry_socket"
                        |}
                        |trap cleanup EXIT
                        |phase=runtime
                        |trap 'echo "Staging command failed at: $phase" >&2' ERR
                        |cd "$HOME/staging"
                        |registry_config="$PWD/registry-auth"
                        |unset APP_IMAGE COMPOSE_FILE COMPOSE_PROJECT_NAME DOCKER_CONTEXT
                        |socket="/run/user/$(id -u)/docker.sock"
                        |[[ -S "$socket" ]]
                        |export DOCKER_HOST="unix://$socket"
                        |docker info --format '{{range .SecurityOptions}}{{println .}}{{end}}' | grep -Fx name=rootless >/dev/null
                        |repository=127.0.0.1:15001/auctions
                        |phase=arguments
                        |mode="${1:-}"
                        |[[ "$mode" == deploy && ( $# == 2 || $# == 3 ) || "$mode" == rollback && $# == 1 ]]
                        |
                        |phase=lock
                        |exec 9>release.lock
                        |flock -n 9
                        |current= previous=
                        |if [[ -f accepted ]]; then
                        |    read -r current < accepted
                        |    previous="$(sed -n '2p' accepted)"
                        |fi
                        |
                        |phase=select
                        |if [[ "$mode" == deploy ]]; then
                        |    revision="$2"
                        |    digest="${3:-}"
                        |else
                        |    target="$previous"
                        |    if [[ -f attempted ]]; then target="$current"; fi
                        |    [[ -n "$target" ]]
                        |    read -r revision digest <<< "$target"
                        |fi
                        |[[ "$revision" =~ ^[0-9a-f]{40}$ ]]
                        |[[ -z "$digest" || "$digest" =~ ^sha256:[0-9a-f]{64}$ ]]
                        |
                        |compose=(docker compose --project-name auctions-lr6 --env-file staging.env -f compose.yml)
                        |phase=configuration
                        |export APP_IMAGE="$repository:$revision"
                        |"${compose[@]}" config --quiet
                        |[[ -r smoke.json ]]
                        |
                        |phase=pull
                        |[[ -S "$registry_socket" ]]
                        |daemon_pid=$(cat "/run/user/$(id -u)/docker.pid")
                        |[[ "$daemon_pid" =~ ^[0-9]+$ ]]
                        |namespace=(nsenter -U --preserve-credentials -n -t "$daemon_pid" --)
                        |"${namespace[@]}" socat TCP4-LISTEN:15001,bind=127.0.0.1,reuseaddr,fork "UNIX-CONNECT:$registry_socket" </dev/null &
                        |registry_proxy=$!
                        |for attempt in {1..10}; do
                        |    if "${namespace[@]}" curl --silent --max-time 2 --output /dev/null http://127.0.0.1:15001/v2/; then
                        |        break
                        |    fi
                        |    kill -0 "$registry_proxy"
                        |    [[ "$attempt" -lt 10 ]]
                        |    sleep 1
                        |done
                        |if [[ -z "$digest" ]]; then
                        |    docker --config "$registry_config" pull "$APP_IMAGE"
                        |    references="$(docker image inspect "$APP_IMAGE" --format '{{range .RepoDigests}}{{println .}}{{end}}')"
                        |    digest="$(awk -v prefix="$repository@" 'index($0, prefix)==1 {print substr($0,length(prefix)+1); exit}' <<< "$references")"
                        |fi
                        |[[ "$digest" =~ ^sha256:[0-9a-f]{64}$ ]]
                        |export APP_IMAGE="$repository@$digest"
                        |docker --config "$registry_config" pull "$APP_IMAGE"
                        |[[ "$(docker image inspect "$APP_IMAGE" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')" == "$revision" ]]
                        |
                        |candidate="$revision $digest"
                        |phase=apply
                        |printf '%s\\n' "$candidate" > attempted.tmp
                        |mv -f attempted.tmp attempted
                        |"${compose[@]}" up -d --no-build --wait --wait-timeout 120
                        |
                        |phase=containers
                        |for service in db app; do
                        |    id="$("${compose[@]}" ps -q "$service")"
                        |    [[ "$(docker inspect --format '{{.State.Health.Status}}' "$id")" == healthy ]]
                        |done
                        |id="$("${compose[@]}" ps -a -q migrate)"
                        |[[ "$(docker inspect --format '{{.State.Status}}:{{.State.ExitCode}}' "$id")" == exited:0 ]]
                        |
                        |phase=http
                        |python3 - "$revision" smoke.json <<'PYTHON'
                        |"""Verify the staging release through its HTTP interface."""
                        |
                        |import json
                        |import sys
                        |from http.cookiejar import CookieJar
                        |from pathlib import Path
                        |from urllib.request import HTTPCookieProcessor, Request, build_opener
                        |
                        |
                        |def verify(revision: str, config_path: Path) -> None:
                        |    config = json.loads(config_path.read_text())
                        |    opener = build_opener(HTTPCookieProcessor(CookieJar()))
                        |    base = "http://127.0.0.1:18060"
                        |
                        |    def request(path: str, data: dict[str, str] | None = None) -> tuple[bytes, str]:
                        |        payload = json.dumps(data).encode() if data is not None else None
                        |        query = Request(base + path, data=payload, headers={"Content-Type": "application/json"})
                        |        with opener.open(query, timeout=5) as response:
                        |            if response.status != 200:
                        |                raise RuntimeError(f"{path}: HTTP {response.status}")
                        |            return response.read(), response.geturl()
                        |
                        |    if json.loads(request("/health")[0]) != {"status": "ok"}:
                        |        raise RuntimeError("Unexpected health response")
                        |    if json.loads(request("/version")[0]) != {"revision": revision}:
                        |        raise RuntimeError("The running revision does not match the candidate")
                        |
                        |    username = config["username"]
                        |    account = json.loads(
                        |        request("/auth/login", {"username": username, "password": config["password"]})[0]
                        |    )
                        |    if account["username"] != username or request("/app")[1] != base + "/app":
                        |        raise RuntimeError("Staging smoke account could not open the dashboard")
                        |    lots = json.loads(request("/web/lots")[0])
                        |    if not any(lot["id"] == config["lot_id"] for lot in lots):
                        |        raise RuntimeError("The control lot is missing from the staging catalog")
                        |
                        |
                        |if __name__ == "__main__":
                        |    try:
                        |        verify(sys.argv[1], Path(sys.argv[2]))
                        |    except Exception as error:
                        |        sys.exit(f"Staging HTTP verification failed: {type(error).__name__}: {error}")
                        |PYTHON
                        |
                        |phase=accept
                        |if [[ "$candidate" != "$current" ]]; then
                        |    printf '%s\\n%s\\n' "$candidate" "$current" > accepted.tmp
                        |    mv -f accepted.tmp accepted
                        |fi
                        |rm -f attempted
                        |printf 'Accepted %s\\n' "$candidate"
                        |STAGING
                    '''.stripMargin()
                }
            }
        }
    }
    post {
        always {
            archiveArtifacts artifacts: 'reports/**', allowEmptyArchive: true
            junit allowEmptyResults: true, testResults: 'reports/tests.xml'
            sh 'if [ -n "${CI_DB:-}" ]; then docker rm -f "$CI_DB" >/dev/null 2>&1 || true; fi'
        }
    }
}
