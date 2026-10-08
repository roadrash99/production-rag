"""Fetch closed GitHub issue threads (issue + comments) and store raw JSON.

MVP version: search API for candidates, then one comments call per issue.
Output: data/raw/github/<owner>__<repo>/<number>.json
Resumable: issues already on disk are skipped.

Usage:
    python -m ingestion.adapters.github_issues --repo vllm-project/vllm --limit 200
"""

import argparse
import json
import os
import time
from datetime import date, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

API = "https://api.github.com"
RAW_DIR = Path("data/raw/github")


def make_session() -> requests.Session:
    load_dotenv()
    s = requests.Session()
    s.headers["Accept"] = "application/vnd.github+json"
    s.headers["X-GitHub-Api-Version"] = "2022-11-28"
    token = os.getenv("GITHUB_TOKEN")
    if token:
        s.headers["Authorization"] = f"Bearer {token}"
    else:
        print("warning: GITHUB_TOKEN not set, limited to 60 requests/hour")
    return s


def get(s: requests.Session, url: str, params: dict | None = None) -> requests.Response:
    """GET with primary and secondary rate-limit handling."""
    for attempt in range(5):
        r = s.get(url, params=params, timeout=30)
        if r.status_code in (403, 429):
            if "Retry-After" in r.headers:
                wait = int(r.headers["Retry-After"])
            elif r.headers.get("X-RateLimit-Remaining") == "0":
                wait = int(r.headers["X-RateLimit-Reset"]) - int(time.time()) + 1
            else:
                wait = 60 * (attempt + 1)
            print(f"rate limited, sleeping {wait}s")
            time.sleep(max(wait, 1))
            continue
        r.raise_for_status()
        return r
    raise RuntimeError(f"gave up on {url}")


def search_issues(s, repo, labels, since, min_comments, limit):
    """Yield issue search results, newest first. Search API caps at 1000 results."""
    q = (
        f"repo:{repo} is:issue is:closed comments:>={min_comments} "
        f"created:>={since} label:{','.join(labels)}"  # comma = OR
    )
    page, seen = 1, 0
    while seen < limit:
        r = get(s, f"{API}/search/issues",
                {"q": q, "sort": "created", "order": "desc", "per_page": 100, "page": page})
        items = r.json()["items"]
        if not items:
            return
        for item in items:
            yield item
            seen += 1
            if seen >= limit:
                return
        page += 1


def fetch_comments(s, comments_url):
    comments, url, params = [], comments_url, {"per_page": 100}
    while url:
        r = get(s, url, params)
        comments.extend(r.json())
        url, params = r.links.get("next", {}).get("url"), None
    return comments


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repo", default="vllm-project/vllm")
    p.add_argument("--limit", type=int, default=200)
    p.add_argument("--labels", default="bug,performance,usage")  # vLLM uses "usage" for questions
    p.add_argument("--min-comments", type=int, default=3)
    p.add_argument("--since", default=str(date.today() - timedelta(days=730)))
    args = p.parse_args()

    out_dir = RAW_DIR / args.repo.replace("/", "__")
    out_dir.mkdir(parents=True, exist_ok=True)
    s = make_session()

    fetched = skipped = 0
    for issue in search_issues(s, args.repo, args.labels.split(","), args.since,
                               args.min_comments, args.limit):
        path = out_dir / f"{issue['number']}.json"
        if path.exists():
            skipped += 1
            continue
        issue["comments_data"] = fetch_comments(s, issue["comments_url"])
        path.write_text(json.dumps(issue))
        fetched += 1
        print(f"#{issue['number']} ({len(issue['comments_data'])} comments) {issue['title'][:70]}")

    print(f"done: {fetched} fetched, {skipped} already on disk -> {out_dir}")


if __name__ == "__main__":
    main()
