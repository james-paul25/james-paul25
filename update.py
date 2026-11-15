import logging
import os
import pathlib
import re
from typing import Dict, List

import requests

USERNAME = "james-paul25"
DEFAULT_N = 5

root = pathlib.Path(__file__).parent.resolve()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

PUBLIC_TOKEN = os.environ.get("GITHUB_TOKEN")      # default Actions token: public data only
PRIVATE_TOKEN = os.environ.get("PROFILE_TOKEN")    # your PAT: needed to see private activity


def headers(token: str | None) -> dict:
    h = {"Accept": "application/vnd.github+json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def get(url: str, token: str | None = None, **params) -> dict | list:
    try:
        r = requests.get(url, headers=headers(token), params=params, timeout=20)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"Request failed for {url}: {e}")
        return {}


def fetch_prs() -> List[str]:
    """Latest pull requests you opened, on any repo."""
    data = get(
        "https://api.github.com/search/issues",
        PUBLIC_TOKEN,
        q=f"author:{USERNAME} type:pr",
        sort="created",
        order="desc",
        per_page=DEFAULT_N,
    )
    lines = []
    for pr in data.get("items", []) if isinstance(data, dict) else []:
        repo = pr["repository_url"].split("repos/")[-1]
        state = "merged" if pr.get("pull_request", {}).get("merged_at") else pr["state"]
        lines.append(f"- [{pr['title']}]({pr['html_url']}) in `{repo}` ({state})")
    return lines


def fetch_commits() -> List[str]:
    """Latest pushes. Private repos are shown as a generic line, with no repo or message."""
    token = PRIVATE_TOKEN or PUBLIC_TOKEN
    events = get(f"https://api.github.com/users/{USERNAME}/events", token, per_page=100)
    lines = []
    for ev in events if isinstance(events, list) else []:
        if ev["type"] != "PushEvent":
            continue
        date = ev["created_at"][:10]
        if not ev.get("public", True):
            lines.append(f"- Commit in a private repository - {date}")
        else:
            repo = ev["repo"]["name"]
            payload = ev["payload"]
            commits = payload.get("commits")
            if commits:
                items = [(c["sha"], c["message"].splitlines()[0]) for c in reversed(commits)]
            else:  # newer API payloads only carry the head sha
                head = payload.get("head")
                info = get(f"https://api.github.com/repos/{repo}/commits/{head}", PUBLIC_TOKEN) if head else {}
                msg = info.get("commit", {}).get("message", "").splitlines()[0] if info else ""
                items = [(head, msg or "Push")] if head else []
            for sha, msg in items:
                url = f"https://github.com/{repo}/commit/{sha}"
                lines.append(f"- [{msg}]({url}) in `{repo}` · {date}")
        if len(lines) >= DEFAULT_N:
            break
    return lines[:DEFAULT_N]


def replace_chunk(content: str, marker: str, chunk: str) -> str:
    """Replaces the text between <!-- marker start --> and <!-- marker end -->."""
    pattern = re.compile(f"<!-- {marker} start -->.*<!-- {marker} end -->", re.DOTALL)
    if not pattern.search(content):
        logging.error(f"Marker '{marker}' not found.")
        return content
    return pattern.sub(f"<!-- {marker} start -->\n{chunk}\n<!-- {marker} end -->", content)


def main() -> None:
    readme = root / "README.md"
    content = readme.read_text(encoding="utf-8")

    prs = fetch_prs() or ["_No pull requests yet._"]
    commits = fetch_commits() or ["_No recent commits._"]

    content = replace_chunk(content, "prs", "\n".join(prs))
    content = replace_chunk(content, "commits", "\n".join(commits))
    readme.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    main()