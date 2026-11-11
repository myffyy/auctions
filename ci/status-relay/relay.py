"""Publish Jenkins PR results without exposing GitHub credentials to build agents."""

import base64
import json
import os
import time
import urllib.error
import urllib.request

GITHUB = "https://api.github.com/repos/myffyy/auctions"
JENKINS = "http://jenkins:8080"
user = os.environ["JENKINS_STATUS_USER"]
jenkins_token = os.environ["JENKINS_STATUS_TOKEN"]
github_token = os.environ["GITHUB_STATUS_TOKEN"]
if not all((user, jenkins_token, github_token)):
    raise SystemExit("Status relay credentials are missing")
auth = base64.b64encode(f"{user}:{jenkins_token}".encode()).decode()
jenkins_headers = {"Authorization": f"Basic {auth}"}
github_headers = {
    "Authorization": f"Bearer {github_token}",
    "Accept": "application/vnd.github+json",
    "Content-Type": "application/json",
    "User-Agent": "auctions-lr5-status-relay",
}


def request(url, headers, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(url, headers=headers, data=data)
    with urllib.request.urlopen(req, timeout=20) as response:  # nosec B310
        return json.load(response)


def scan(cache):
    pulls = request(f"{GITHUB}/pulls?state=open&per_page=100", github_headers)
    for pr in pulls:
        number = pr["number"]
        sha = pr["head"]["sha"]
        state, description = "pending", "Waiting for Jenkins to check this commit"
        try:
            job = f"{JENKINS}/job/auctions/job/PR-{int(number)}/lastBuild/api/json"
            build = request(
                job + "?tree=number,building,result,actions[lastBuiltRevision[SHA1]]",
                jenkins_headers,
            )
            revisions = [a.get("lastBuiltRevision", {}).get("SHA1") for a in build["actions"]]
            if sha in revisions and not build["building"]:
                state = "success" if build["result"] == "SUCCESS" else "failure"
                description = (
                    "Jenkins checks passed" if state == "success" else "Jenkins checks failed"
                )
        except (urllib.error.URLError, KeyError, ValueError):
            pass
        marker = (sha, state, description)
        if cache.get(number) == marker:
            continue
        request(
            f"{GITHUB}/statuses/{sha}",
            github_headers,
            {
                "state": state,
                "context": "ci/jenkins-pr",
                "description": description,
                "target_url": f"http://localhost:8081/job/auctions/job/PR-{int(number)}/",
            },
        )
        cache[number] = marker
        print(f"PR #{number}: {state}", flush=True)


def main():
    cache = {}
    while True:
        try:
            scan(cache)
        except (OSError, ValueError, KeyError) as exc:
            print(f"Status refresh failed: {type(exc).__name__}", flush=True)
        time.sleep(60)


if __name__ == "__main__":
    main()
