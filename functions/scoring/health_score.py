"""
Health Score Calculator - Core scoring algorithm.

Uses continuous functions (log-scale, exponential decay, sigmoid)
to calculate health scores based on multiple signals.

Components:
- Maintainer Health: 30%
- User-Centric: 30% (most predictive per research)
- Evolution: 25%
- Community: 15%
"""

import math
from datetime import datetime, timezone
from typing import Optional


def calculate_health_score(data: dict) -> dict:
    """
    Calculate overall health score (0-100).

    Args:
        data: Package data dictionary with all collected signals

    Returns:
        Dictionary with health score, risk level, components, and confidence
    """
    # Calculate component scores
    maintainer = _maintainer_health(data)
    user_centric = _user_centric_health(data)
    evolution = _evolution_health(data)
    community = _community_health(data)

    # Weighted combination
    raw_score = (
        maintainer * 0.30 + user_centric * 0.30 + evolution * 0.25 + community * 0.15
    )

    health_score = round(raw_score * 100, 1)
    confidence = _calculate_confidence(data)

    return {
        "health_score": health_score,
        "risk_level": _get_risk_level(health_score),
        "components": {
            "maintainer_health": round(maintainer * 100, 1),
            "user_centric": round(user_centric * 100, 1),
            "evolution_health": round(evolution * 100, 1),
            "community_health": round(community * 100, 1),
        },
        "confidence": confidence,
    }


def _maintainer_health(data: dict) -> float:
    """
    Maintainer activity signals.

    Uses smooth exponential decay for recency and sigmoid for bus factor.
    """
    # Recency score: exponential decay with 90-day half-life
    # Half-life means score = 0.5 after 90 days of inactivity
    days = data.get("days_since_last_commit", 365)
    if days is None:
        days = 365
    recency = math.exp(-0.693 * days / 90)  # 0.693 = ln(2)

    # Bus factor score: sigmoid centered at 2 contributors
    # 1 contributor ~= 0.27, 2 ~= 0.5, 3+ ~= 0.73+
    contributors = data.get("active_contributors_90d", 1)
    if contributors is None:
        contributors = 1
    bus_factor = 1 / (1 + math.exp(-(contributors - 2)))

    return recency * 0.6 + bus_factor * 0.4


def _user_centric_health(data: dict) -> float:
    """
    User adoption signals - MOST PREDICTIVE per research.

    Uses continuous log-scale functions instead of step functions.
    """
    # Download score: log-scaled continuous function
    # log10(1M) = 6, log10(10M) = 7, normalize so 10M+ = 1.0
    downloads = data.get("weekly_downloads", 0) or 0
    download_score = min(math.log10(downloads + 1) / 7, 1.0)

    # Dependents: log-scaled (ecosystem position)
    # log10(10K) = 4, normalize so 10K+ = 1.0
    dependents = data.get("dependents_count", 0) or 0
    dependent_score = min(math.log10(dependents + 1) / 4, 1.0)

    # Stars: log-scaled community interest proxy
    # log10(100K) = 5, normalize so 100K+ = 1.0
    stars = data.get("stars", 0) or 0
    star_score = min(math.log10(stars + 1) / 5, 1.0)

    return download_score * 0.5 + dependent_score * 0.3 + star_score * 0.2


def _evolution_health(data: dict) -> float:
    """
    Project evolution signals.

    Uses continuous exponential decay for release recency
    and log-scale for commit activity.
    """
    # Release recency: exponential decay with 180-day half-life
    last_published = data.get("last_published")
    release_score = 0.5  # Default neutral

    if last_published:
        try:
            if isinstance(last_published, str):
                published_date = datetime.fromisoformat(
                    last_published.replace("Z", "+00:00")
                )
            else:
                published_date = last_published

            now = datetime.now(timezone.utc)
            if published_date.tzinfo is None:
                published_date = published_date.replace(tzinfo=timezone.utc)

            days_since_release = (now - published_date).days
            release_score = math.exp(-0.693 * days_since_release / 180)
        except (ValueError, TypeError):
            pass

    # Commit activity: log-scaled continuous function
    # log10(50) ~= 1.7, normalize so 50+ commits/90d = ~1.0
    commits_90d = data.get("commits_90d", 0) or 0
    activity_score = min(math.log10(commits_90d + 1) / 1.7, 1.0)

    return release_score * 0.5 + activity_score * 0.5


def _community_health(data: dict) -> float:
    """
    Community engagement signals.

    Includes OpenSSF score, contributor diversity, and security posture.
    """
    # OpenSSF Scorecard (if available) - already 0-10 scale
    openssf = data.get("openssf_score")
    if openssf is not None:
        openssf_score = openssf / 10.0
    else:
        openssf_score = 0.5  # Neutral if not available

    # Contributors: log-scaled continuous
    # log10(50) ~= 1.7, normalize so 50+ contributors = ~1.0
    contributors = data.get("total_contributors", 1) or 1
    contributor_score = min(math.log10(contributors + 1) / 1.7, 1.0)

    # Security: sigmoid decay based on advisory count and severity
    advisories = data.get("advisories", []) or []
    critical = sum(1 for a in advisories if a.get("severity") == "CRITICAL")
    high = sum(1 for a in advisories if a.get("severity") == "HIGH")
    medium = sum(1 for a in advisories if a.get("severity") == "MEDIUM")

    # Weighted vulnerability score (higher = worse)
    vuln_score = critical * 3 + high * 2 + medium * 1

    # Sigmoid decay: 0 vulns = 1.0, 5+ weighted vulns = ~0.2
    security_score = 1 / (1 + math.exp((vuln_score - 2) / 1.5))

    return openssf_score * 0.4 + contributor_score * 0.3 + security_score * 0.3


def _calculate_confidence(data: dict) -> dict:
    """
    Calculate confidence in the score.

    Returns INSUFFICIENT_DATA for packages < 90 days old.
    """
    # Data completeness check
    required_fields = [
        "days_since_last_commit",
        "weekly_downloads",
        "active_contributors_90d",
        "last_published",
    ]
    present = sum(
        1
        for f in required_fields
        if data.get(f) is not None and data.get(f) != 0
    )
    completeness = present / len(required_fields)

    # Package age (cold start penalty)
    created = data.get("created_at")
    age_score = 0.5

    if created:
        try:
            if isinstance(created, str):
                created_date = datetime.fromisoformat(created.replace("Z", "+00:00"))
            else:
                created_date = created

            now = datetime.now(timezone.utc)
            if created_date.tzinfo is None:
                created_date = created_date.replace(tzinfo=timezone.utc)

            age_days = (now - created_date).days

            if age_days < 90:
                # Package too new - insufficient data
                return {
                    "score": 20.0,
                    "level": "INSUFFICIENT_DATA",
                    "reason": f"Package is only {age_days} days old. Scores may be unreliable.",
                }
            elif age_days < 180:
                age_score = 0.5
            elif age_days < 365:
                age_score = 0.7
            else:
                age_score = 1.0

        except (ValueError, TypeError):
            pass

    # Data freshness penalty
    last_updated = data.get("last_updated")
    freshness_score = 1.0

    if last_updated:
        try:
            if isinstance(last_updated, str):
                updated_date = datetime.fromisoformat(
                    last_updated.replace("Z", "+00:00")
                )
            else:
                updated_date = last_updated

            now = datetime.now(timezone.utc)
            if updated_date.tzinfo is None:
                updated_date = updated_date.replace(tzinfo=timezone.utc)

            hours_since_update = (now - updated_date).total_seconds() / 3600

            if hours_since_update > 168:  # > 1 week old
                freshness_score = 0.7
            elif hours_since_update > 48:
                freshness_score = 0.9
        except (ValueError, TypeError):
            pass

    # Calculate overall confidence
    confidence_score = completeness * 0.5 + age_score * 0.3 + freshness_score * 0.2

    if confidence_score >= 0.8:
        level = "HIGH"
    elif confidence_score >= 0.5:
        level = "MEDIUM"
    else:
        level = "LOW"

    return {
        "score": round(confidence_score * 100, 1),
        "level": level,
    }


def _get_risk_level(score: float) -> str:
    """Map health score to risk level."""
    if score >= 80:
        return "LOW"
    elif score >= 60:
        return "MEDIUM"
    elif score >= 40:
        return "HIGH"
    else:
        return "CRITICAL"
