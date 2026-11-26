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
                    sh '''#!/usr/bin/env bash
                        set -euo pipefail
                        mkdir -p reports
                        case "$RELEASE_ACTION" in
                            publish)
                                sha=$(git rev-parse HEAD)
                                digest=$(cut -d @ -f 2 reports/published-digest.txt)
                                [[ "$digest" =~ ^sha256:[a-f0-9]{64}$ ]]
                                command="deploy $sha $digest"
                                ;;
                            deploy)
                                [[ "$RELEASE_TAG" =~ ^[a-f0-9]{40}$ ]]
                                command="deploy $RELEASE_TAG"
                                ;;
                            rollback) command=rollback ;;
                            *) exit 2 ;;
                        esac
                        ssh -F /dev/null -i "$STAGING_KEY" -o IdentitiesOnly=yes -o UserKnownHostsFile="$STAGING_HOSTS" -o StrictHostKeyChecking=yes -o BatchMode=yes -o ExitOnForwardFailure=yes -o ConnectTimeout=10 -R 127.0.0.1:15001:127.0.0.1:5001 auctions-deploy@192.168.64.24 "$command" 2>&1 | tee reports/staging.log
                    '''
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
