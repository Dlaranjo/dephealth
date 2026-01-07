"""
GitHub collector - Secondary data source for repository metrics.

Provides:
- Commit activity (90 days)
- Contributor count
- Stars and forks
- Repository status (archived, etc.)

Rate limit: 5,000 requests/hour with token (single account)
Budget: ~2,400 calls/day for tiered refresh strategy
"""

import asyncio
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

GITHUB_API = "https://api.github.com"
DEFAULT_TIMEOUT = 30.0


def parse_github_url(url: str) -> Optional[tuple[str, str]]:
    """
    Parse GitHub repository URL to extract owner and repo.

    Handles various URL formats:
    - https://github.com/owner/repo
    - git://github.com/owner/repo.git
    - git+https://github.com/owner/repo.git
    - github.com/owner/repo

    Returns:
        Tuple of (owner, repo) or None if not a valid GitHub URL
    """
    if not url:
        return None

    # Normalize URL
    url = url.strip()
    url = url.replace("git+", "").replace("git://", "https://")
    if url.endswith(".git"):
        url = url[:-4]

    # Match GitHub URL pattern
    patterns = [
        r"github\.com[/:]([^/]+)/([^/]+?)(?:\.git)?$",
        r"github\.com[/:]([^/]+)/([^/]+)$",
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1), match.group(2)

    return None


class GitHubCollector:
    """
    GitHub API collector with rate limit awareness and retry logic.
    """

    def __init__(self, token: Optional[str] = None):
        """
        Initialize collector with optional token.

        Args:
            token: GitHub Personal Access Token (5K requests/hour)
        """
        self.token = token or os.environ.get("GITHUB_TOKEN")
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            self.headers["Authorization"] = f"Bearer {self.token}"

        self._rate_limit_remaining = 5000
        self._rate_limit_reset: Optional[int] = None

    async def _request_with_retry(
        self,
        client: httpx.AsyncClient,
        url: str,
        params: Optional[dict] = None,
        max_retries: int = 3,
    ) -> Optional[dict]:
        """
        Make request with exponential backoff retry.

        Handles:
        - Rate limiting (403 with X-RateLimit-Remaining: 0)
        - Server errors (5xx)
        - Network errors

        Returns:
            Response JSON or None if not found
        """
        for attempt in range(max_retries):
            try:
                resp = await client.get(url, params=params, headers=self.headers)

                # Track rate limits from response headers
                if "X-RateLimit-Remaining" in resp.headers:
                    self._rate_limit_remaining = int(
                        resp.headers.get("X-RateLimit-Remaining", 5000)
                    )
                if "X-RateLimit-Reset" in resp.headers:
                    self._rate_limit_reset = int(resp.headers.get("X-RateLimit-Reset", 0))

                if resp.status_code == 200:
                    return resp.json()

                elif resp.status_code == 404:
                    logger.debug(f"Resource not found: {url}")
                    return None

                elif resp.status_code == 403:
                    if self._rate_limit_remaining == 0:
                        # Rate limited - calculate wait time
                        now = int(datetime.now(timezone.utc).timestamp())
                        wait_time = max(0, (self._rate_limit_reset or now) - now)
                        wait_time = min(wait_time, 60)  # Cap at 60 seconds
                        logger.warning(f"Rate limited. Waiting {wait_time}s")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        # Other 403 (e.g., blocked repo)
                        logger.warning(f"Access forbidden: {url}")
                        return None

                elif resp.status_code == 409:
                    # Empty repository (no commits)
                    return []

                elif resp.status_code >= 500:
                    # Server error - retry
                    logger.warning(f"Server error {resp.status_code}, retrying...")

                else:
                    resp.raise_for_status()

            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                if attempt == max_retries - 1:
                    logger.error(f"Failed after {max_retries} retries: {url} - {e}")
                    raise

            # Exponential backoff
            delay = 2**attempt
            await asyncio.sleep(delay)

        return None

    async def get_repo_metrics(self, owner: str, repo: str) -> dict:
        """
        Fetch essential GitHub metrics for a repository.

        Optimized to use minimal API calls (~3-4 per repo):
        1. Repository metadata (stars, forks, issues, updated_at)
        2. Recent commits (last 90 days)
        3. Contributors

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            Dictionary with repository metrics
        """
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            # 1. Repository metadata (1 call)
            repo_url = f"{GITHUB_API}/repos/{owner}/{repo}"
            repo_data = await self._request_with_retry(client, repo_url)

            if repo_data is None:
                return {
                    "error": "repository_not_found",
                    "owner": owner,
                    "repo": repo,
                }

            # 2. Recent commits (1 call - last 90 days)
            since = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
            commits_url = f"{GITHUB_API}/repos/{owner}/{repo}/commits"
            commits = await self._request_with_retry(
                client,
                commits_url,
                params={"since": since, "per_page": 100},
            )
            commits = commits or []

            # 3. Contributors (1 call)
            contributors_url = f"{GITHUB_API}/repos/{owner}/{repo}/contributors"
            contributors = await self._request_with_retry(
                client,
                contributors_url,
                params={"per_page": 100},
            )
            contributors = contributors or []

            # Calculate derived metrics
            unique_committers_90d = 0
            if isinstance(commits, list):
                committers = set()
                for c in commits:
                    if isinstance(c, dict):
                        author = c.get("author")
                        if author and isinstance(author, dict):
                            login = author.get("login")
                            if login:
                                committers.add(login)
                unique_committers_90d = len(committers)

            # Days since last commit
            days_since_commit = 999
            if commits and isinstance(commits, list) and len(commits) > 0:
                first_commit = commits[0]
                if isinstance(first_commit, dict):
                    commit_info = first_commit.get("commit", {})
                    author_info = commit_info.get("author", {})
                    last_commit_date = author_info.get("date")

                    if last_commit_date:
                        try:
                            last_commit = datetime.fromisoformat(
                                last_commit_date.replace("Z", "+00:00")
                            )
                            days_since_commit = (
                                datetime.now(timezone.utc) - last_commit
                            ).days
                        except ValueError as e:
                            logger.warning(f"Could not parse commit date: {e}")

            return {
                "owner": owner,
                "repo": repo,
                "stars": repo_data.get("stargazers_count", 0),
                "forks": repo_data.get("forks_count", 0),
                "open_issues": repo_data.get("open_issues_count", 0),
                "watchers": repo_data.get("watchers_count", 0),
                "updated_at": repo_data.get("updated_at"),
                "pushed_at": repo_data.get("pushed_at"),
                "created_at": repo_data.get("created_at"),
                "days_since_last_commit": days_since_commit,
                "commits_90d": len(commits) if isinstance(commits, list) else 0,
                "active_contributors_90d": unique_committers_90d,
                "total_contributors": len(contributors) if isinstance(contributors, list) else 0,
                "archived": repo_data.get("archived", False),
                "disabled": repo_data.get("disabled", False),
                "default_branch": repo_data.get("default_branch", "main"),
                "language": repo_data.get("language"),
                "topics": repo_data.get("topics", []),
                "source": "github",
            }

    async def get_repo_metrics_from_url(self, url: str) -> dict:
        """
        Fetch metrics given a repository URL.

        Args:
            url: GitHub repository URL in any format

        Returns:
            Dictionary with repository metrics or error
        """
        parsed = parse_github_url(url)
        if not parsed:
            return {"error": "invalid_github_url", "url": url}

        owner, repo = parsed
        return await self.get_repo_metrics(owner, repo)

    @property
    def rate_limit_remaining(self) -> int:
        """Get remaining rate limit."""
        return self._rate_limit_remaining

    @property
    def rate_limit_reset_at(self) -> Optional[datetime]:
        """Get rate limit reset time."""
        if self._rate_limit_reset:
            return datetime.fromtimestamp(self._rate_limit_reset, tz=timezone.utc)
        return None
