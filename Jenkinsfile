pipeline {
    agent { label 'auctions-ci' }
    options { skipDefaultCheckout(); timestamps(); timeout(time: 90, unit: 'MINUTES'); disableConcurrentBuilds(); buildDiscarder(logRotator(daysToKeepStr: '14')) }
    environment {
        POSTGRES_PASSWORD = 'ci-container-only'
        SESSION_SECRET = 'ci-container-session-only'
        ADMIN_PASSWORD = 'ci-container-admin-only'
    }
    stages {
        stage('Подготовка') {
            steps {
                deleteDir()
                checkout scm
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
        stage('Контейнер') { steps { sh 'make container-check' } }
        stage('Сборка и анализ') {
            steps { sh '''
                set -eu
                SHA=$(git rev-parse HEAD)
                docker build -t "auctions-ci:$SHA" .
                make image-check IMAGE="auctions-ci:$SHA"
            ''' }
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
