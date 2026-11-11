FROM postgres:14-bookworm@sha256:a389ed49344afc8f4444efd4eb512965df07aaa6ed84b239b54a23246e9fe347 AS pgclient
FROM docker:27.5.1-cli@sha256:851f91d241214e7c6db86513b270d58776379aacc5eb9c4a87e5b47115e3065c AS dockercli
FROM jenkins/inbound-agent:latest-jdk21@sha256:0c5908a376ff73381f3617c8277b77559a9c8916fe0c22efd9b9e9ef326aeb27
USER root
RUN apt-get update && apt-get install -y --no-install-recommends make python3 postgresql-client git curl ca-certificates && rm -rf /var/lib/apt/lists/*
COPY --from=pgclient /usr/lib/postgresql/14/bin/pg_dump /usr/local/bin/pg_dump
COPY --from=pgclient /usr/lib/postgresql/14/bin/pg_restore /usr/local/bin/pg_restore
COPY --from=dockercli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=dockercli /usr/local/libexec/docker/cli-plugins/ /usr/local/libexec/docker/cli-plugins/
COPY --from=ghcr.io/astral-sh/uv:0.10.7@sha256:edd1fd89f3e5b005814cc8f777610445d7b7e3ed05361f9ddfae67bebfe8456a /uv /uvx /usr/local/bin/
USER jenkins
RUN uv python install 3.12.5
