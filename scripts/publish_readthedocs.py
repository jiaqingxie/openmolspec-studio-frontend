"""Create/configure OpenMolSpec on RTD and trigger a build (standard library only).

Default: print the plan, without network or credentials. Use --apply to publish.
READTHEDOCS_TOKEN or an interactive hidden prompt supplies credentials; credentials
are never written to disk. Use --direct to bypass environment HTTP proxies.
API contract: https://docs.readthedocs.com/platform/stable/api/v3.html
"""
import argparse
import getpass
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "https://app.readthedocs.org"
REPOSITORY = "https://github.com/jiaqingxie/openmolspec-studio-frontend.git"
BRANCH = "release/openmolspec-v1"


class PublicationError(RuntimeError):
    pass


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise PublicationError("Unexpected API redirect; credentials were not forwarded.")


class Client:
    def __init__(self, token, direct=False):
        if not token or any(c.isspace() for c in token):
            raise PublicationError("RTD token is missing or contains whitespace.")
        self.token = token
        self.opener = build_opener(ProxyHandler({}) if direct else ProxyHandler(), NoRedirects())

    def request(self, method, path, data=None):
        url = urljoin(ORIGIN, path)
        parts = urlsplit(url)
        if (parts.scheme != "https" or parts.netloc != "app.readthedocs.org"
                or not parts.path.startswith("/api/v3/")):
            raise PublicationError("Refusing to send RTD credentials outside its API.")
        req = Request(url, method=method,
                      data=None if data is None else json.dumps(data).encode(),
                      headers={"Authorization": "Token " + self.token,
                               "Content-Type": "application/json",
                               "Accept": "application/json"})
        try:
            with self.opener.open(req, timeout=25) as response:
                body = response.read()
                return json.loads(body) if body else None
        except HTTPError as exc:
            detail = exc.read(2000).decode("utf-8", "replace").replace(self.token, "[redacted]")
            raise PublicationError(f"RTD HTTP {exc.code}: {detail}") from None
        except (URLError, OSError) as exc:
            raise PublicationError(f"RTD connection failed: {str(exc).replace(self.token, '[redacted]')}") from None

    def projects(self):
        path = "/api/v3/projects/?limit=100"
        seen = set()
        while path:
            if path in seen:
                raise PublicationError("RTD repeated a pagination link.")
            seen.add(path)
            page = self.request("GET", path)
            yield from page["results"]
            path = page.get("next")


def check_network():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM):
            pass
    except OSError as exc:
        raise PublicationError(f"This execution environment cannot create network sockets: {exc}") from None


def git_env(direct=False):
    env = os.environ.copy()
    for key in list(env):
        if direct and key.lower() in ("http_proxy", "https_proxy", "all_proxy"):
            env.pop(key)
    # The RTD credential has no purpose in Git or any Git credential helper.
    env.pop("READTHEDOCS_TOKEN", None)
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def verify_remote(expected, direct=False):
    if expected is None:
        expected = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, env=git_env(direct), text=True).strip()
    if not re.fullmatch(r"[0-9a-f]{40}", expected):
        raise PublicationError("Expected commit must be the full Git SHA.")
    result = subprocess.run(
        ["git"] + (["-c", "http.proxy=", "-c", "https.proxy="] if direct else [])
        + ["ls-remote", "--heads", REPOSITORY, "refs/heads/" + BRANCH],
        env=git_env(direct), capture_output=True,
        text=True, timeout=40, check=True)
    remote = result.stdout.split()
    if not remote or remote[0] != expected:
        raise PublicationError(
            "The remote release branch does not match the expected commit. "
            "Push the release branch first; no RTD changes were made.")
    return expected


def same_repository(url):
    return url.rstrip("/").removesuffix(".git").lower() == REPOSITORY.removesuffix(".git").lower()


def configure(client, name, project_slug=None):
    projects = list(client.projects())
    if project_slug:
        candidates = [p for p in projects if p["slug"] == project_slug]
        if not candidates:
            raise PublicationError("Requested existing project is not in this RTD account.")
    else:
        candidates = [p for p in projects if p["name"].lower() == name.lower()]
        if not candidates:
            candidates = [p for p in projects if same_repository(p["repository"]["url"])]
    if len(candidates) > 1:
        raise PublicationError("Multiple matching projects exist; select one with --project.")
    if candidates:
        project = candidates[0]
        if not same_repository(project["repository"]["url"]):
            raise PublicationError("Project name belongs to another repository; choose --name.")
    else:
        project = client.request("POST", "/api/v3/projects/", {
            "name": name, "repository": {"url": REPOSITORY, "type": "git"},
            "language": "en", "programming_language": "py",
            "readthedocs_yaml_path": ".readthedocs.yaml"})
    slug = project["slug"]
    endpoint = "/api/v3/projects/" + quote(slug, safe="") + "/"
    print(json.dumps({"project": slug, "project_url": ORIGIN + "/projects/" + quote(slug, safe="") + "/"}), flush=True)
    desired = {"default_branch": BRANCH, "default_version": "latest",
               "readthedocs_yaml_path": ".readthedocs.yaml"}
    if any(project.get(k) != v for k, v in desired.items()):
        client.request("PATCH", endpoint, desired)
    project = client.request("GET", endpoint)
    if any(project.get(k) != v for k, v in desired.items()):
        raise PublicationError("RTD did not retain the requested release branch/configuration.")
    return endpoint, project


def build_result(build, expected):
    state = build.get("state")
    if isinstance(state, dict):
        state = state.get("code")
    success = state == "finished" and build.get("success") is True
    return {"build_id": build.get("id"), "state": state,
            "success": build.get("success"), "commit": build.get("commit"),
            "expected_commit": expected,
            "hosted_build_verified": success and build.get("commit") == expected}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Create/configure the project and trigger a build")
    parser.add_argument("--direct", action="store_true", help="Bypass environment HTTP proxies")
    parser.add_argument("--name", default="OpenMolSpec")
    parser.add_argument("--project", help="Reuse this existing account project slug")
    parser.add_argument("--expected-commit", help="Defaults to this checkout's HEAD")
    parser.add_argument("--wait", type=int, default=0, help="Seconds to watch the triggered build")
    args = parser.parse_args(argv)
    if args.wait < 0:
        parser.error("--wait cannot be negative")
    if not args.apply:
        print(json.dumps({"name": args.name, "repository": REPOSITORY, "branch": BRANCH,
                          "configuration": ".readthedocs.yaml", "version": "latest",
                          "apply": False, "remote_publication_verified": False}, indent=2))
        return 0
    check_network()
    expected = verify_remote(args.expected_commit, args.direct)
    token = os.environ.get("READTHEDOCS_TOKEN", "").strip()
    if not token:
        if not sys.stdin.isatty():
            raise PublicationError("Set READTHEDOCS_TOKEN or run in an interactive terminal.")
        token = getpass.getpass("RTD API token (hidden): ").strip()
    client = Client(token, direct=args.direct)
    endpoint, project = configure(client, args.name, args.project)
    response = client.request("POST", endpoint + "versions/latest/builds/")
    build = response["build"]
    build_id = build["id"]
    if not isinstance(build_id, int):
        raise PublicationError("RTD returned no numeric build ID; inspect the project before retrying.")
    deadline = time.monotonic() + args.wait
    while True:
        build = client.request("GET", endpoint + f"builds/{build_id}/")
        result = build_result(build, expected)
        result["documentation_url"] = (project.get("urls") or {}).get("documentation")
        print(json.dumps(result), flush=True)
        if result["state"] in ("finished", "cancelled"):
            return 0 if result["hosted_build_verified"] else 1
        if time.monotonic() >= deadline:
            return 0
        time.sleep(min(10, max(0, deadline - time.monotonic())))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (PublicationError, subprocess.SubprocessError, OSError, ValueError, KeyError) as exc:
        # A response body must not be allowed to echo credentials to the terminal.
        message = str(exc)
        secret = os.environ.get("READTHEDOCS_TOKEN")
        if secret:
            message = message.replace(secret, "[redacted]")
        print("Publication stopped: " + message, file=sys.stderr)
        sys.exit(1)
