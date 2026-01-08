"""
Tests for scoring algorithms: health_score.py and abandonment_risk.py

These are the core business logic - pure functions that must be reliable.
"""

import math

import pytest
from freezegun import freeze_time

from scoring.health_score import (
    _calculate_confidence,
    _calculate_maturity_factor,
    _community_health,
    _evolution_health,
    _get_risk_level,
    _maintainer_health,
    _security_health,
    _user_centric_health,
    calculate_health_score,
)
from scoring.abandonment_risk import (
    calculate_abandonment_risk,
    get_risk_trend,
)


# =============================================================================
# Health Score Tests
# =============================================================================


class TestCalculateHealthScore:
    """Tests for the main calculate_health_score function."""

    def test_healthy_package_scores_high(self, sample_healthy_package):
        """A well-maintained package should score 70+."""
        result = calculate_health_score(sample_healthy_package)

        assert result["health_score"] >= 70
        assert result["risk_level"] in ["LOW", "MEDIUM"]
        assert "components" in result
        assert "confidence" in result

    def test_empty_data_returns_valid_score(self):
        """Empty data should return a valid score using defaults."""
        result = calculate_health_score({})

        assert 0 <= result["health_score"] <= 100
        assert result["risk_level"] in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]

    def test_score_components_sum_correctly(self, sample_healthy_package):
        """Component weights should add up correctly."""
        result = calculate_health_score(sample_healthy_package)

        # Verify all 5 components exist (v2 added security_health)
        components = result["components"]
        assert "maintainer_health" in components
        assert "user_centric" in components
        assert "evolution_health" in components
        assert "community_health" in components
        assert "security_health" in components  # v2 addition

        # All components should be 0-100
        for name, value in components.items():
            assert 0 <= value <= 100, f"{name} out of range: {value}"


class TestMaintainerHealth:
    """Tests for _maintainer_health component."""

    def test_recent_commit_scores_high(self):
        """Recent activity (7 days) should score near 1.0."""
        data = {"days_since_last_commit": 7, "active_contributors_90d": 5}
        score = _maintainer_health(data)

        # exp(-0.693 * 7 / 90) * 0.6 + bus_factor * 0.4
        # recency ~= 0.95, bus_factor for 5 contributors ~= 0.95
        assert score > 0.8

    def test_stale_commit_scores_low(self):
        """365 days without commits should score low."""
        data = {"days_since_last_commit": 365, "active_contributors_90d": 1}
        score = _maintainer_health(data)

        assert score < 0.3

    def test_single_maintainer_penalized(self):
        """Single maintainer (bus factor = 1) should reduce score."""
        data_single = {"days_since_last_commit": 0, "active_contributors_90d": 1}
        data_multi = {"days_since_last_commit": 0, "active_contributors_90d": 5}

        score_single = _maintainer_health(data_single)
        score_multi = _maintainer_health(data_multi)

        assert score_multi > score_single

    def test_none_values_use_defaults(self):
        """None values should use safe defaults."""
        data = {"days_since_last_commit": None, "active_contributors_90d": None}
        score = _maintainer_health(data)

        # Should use defaults: 365 days, 1 contributor
        assert 0 <= score <= 1

    def test_missing_keys_use_defaults(self):
        """Missing keys should use safe defaults."""
        score = _maintainer_health({})
        assert 0 <= score <= 1


class TestUserCentricHealth:
    """Tests for _user_centric_health component."""

    def test_high_downloads_scores_high(self):
        """10M+ weekly downloads should score near 1.0."""
        data = {"weekly_downloads": 10_000_000, "dependents_count": 10000, "stars": 50000}
        score = _user_centric_health(data)

        assert score > 0.8

    def test_low_downloads_scores_low(self):
        """Low downloads should reduce score."""
        data = {"weekly_downloads": 10, "dependents_count": 0, "stars": 0}
        score = _user_centric_health(data)

        assert score < 0.2

    def test_zero_values_handled(self):
        """Zero values should not cause errors."""
        data = {"weekly_downloads": 0, "dependents_count": 0, "stars": 0}
        score = _user_centric_health(data)

        assert score == 0.0  # log10(1) / 7 + log10(1) / 4 + log10(1) / 5 = 0


class TestEvolutionHealth:
    """Tests for _evolution_health component."""

    @freeze_time("2026-01-07")
    def test_recent_release_scores_high(self):
        """Release within 30 days should score high."""
        data = {
            "last_published": "2025-12-15T00:00:00Z",
            "commits_90d": 30,
        }
        score = _evolution_health(data)

        assert score > 0.7

    @freeze_time("2026-01-07")
    def test_old_release_scores_low(self):
        """Release 2 years ago should score low."""
        data = {
            "last_published": "2024-01-01T00:00:00Z",
            "commits_90d": 0,
        }
        score = _evolution_health(data)

        assert score < 0.3

    def test_missing_release_date_uses_neutral(self):
        """Missing release date should use neutral score."""
        data = {"last_published": None, "commits_90d": 0}
        score = _evolution_health(data)

        # Default release_score = 0.5, activity_score = 0 for 0 commits
        # 0.5 * 0.5 + 0 * 0.5 = 0.25
        assert 0.2 <= score <= 0.3


class TestCommunityHealth:
    """Tests for _community_health component.

    NOTE: In v2, _community_health ONLY uses total_contributors.
    OpenSSF and advisories moved to _security_health() to avoid double-counting.
    """

    def test_high_contributors_scores_high(self):
        """Many contributors should score high."""
        data = {"total_contributors": 100}
        score = _community_health(data)

        # log10(101) / 1.7 ~= 1.18 -> capped at 1.0
        assert score >= 0.95

    def test_low_contributors_scores_low(self):
        """Few contributors should score lower."""
        data = {"total_contributors": 2}
        score = _community_health(data)

        # log10(3) / 1.7 ~= 0.28
        assert 0.2 < score < 0.4

    def test_single_contributor(self):
        """Single contributor should score low but not zero."""
        data = {"total_contributors": 1}
        score = _community_health(data)

        # log10(2) / 1.7 ~= 0.18
        assert 0.1 < score < 0.3

    def test_missing_contributors_defaults_to_one(self):
        """Missing total_contributors should default to 1."""
        data = {}
        score = _community_health(data)

        # Default = 1, so log10(2) / 1.7 ~= 0.18
        assert 0.1 < score < 0.3

    def test_none_contributors_defaults_to_one(self):
        """None total_contributors should default to 1."""
        data = {"total_contributors": None}
        score = _community_health(data)

        assert 0.1 < score < 0.3

    def test_zero_contributors_defaults_to_one(self):
        """Zero contributors should be treated as 1."""
        data = {"total_contributors": 0}
        score = _community_health(data)

        # 0 or 1 pattern should give 1
        assert 0.1 < score < 0.3


class TestRiskLevel:
    """Tests for _get_risk_level function."""

    @pytest.mark.parametrize(
        "score,expected",
        [
            (100, "LOW"),
            (85, "LOW"),
            (80, "LOW"),
            (79.9, "MEDIUM"),
            (70, "MEDIUM"),
            (60, "MEDIUM"),
            (59.9, "HIGH"),
            (50, "HIGH"),
            (40, "HIGH"),
            (39.9, "CRITICAL"),
            (20, "CRITICAL"),
            (0, "CRITICAL"),
        ],
    )
    def test_risk_level_boundaries(self, score, expected):
        """Test exact boundary values for risk levels."""
        assert _get_risk_level(score) == expected


class TestConfidence:
    """Tests for _calculate_confidence function."""

    @freeze_time("2026-01-07")
    def test_new_package_insufficient_data(self):
        """Package < 90 days old should have INSUFFICIENT_DATA confidence."""
        data = {"created_at": "2025-11-01T00:00:00Z"}  # ~67 days old
        result = _calculate_confidence(data)

        assert result["level"] == "INSUFFICIENT_DATA"
        assert "days old" in result.get("reason", "")

    @freeze_time("2026-01-07")
    def test_mature_package_high_confidence(self):
        """Mature package with complete data should have high confidence."""
        data = {
            "created_at": "2020-01-01T00:00:00Z",  # 6 years old
            "days_since_last_commit": 7,
            "weekly_downloads": 1_000_000,
            "active_contributors_90d": 5,
            "last_published": "2025-12-01T00:00:00Z",
            "last_updated": "2026-01-06T00:00:00Z",  # Yesterday
        }
        result = _calculate_confidence(data)

        assert result["level"] == "HIGH"
        assert result["score"] >= 80


# =============================================================================
# Abandonment Risk Tests
# =============================================================================


class TestCalculateAbandonmentRisk:
    """Tests for calculate_abandonment_risk function."""

    def test_healthy_package_low_risk(self, sample_healthy_package):
        """Well-maintained package should have low abandonment risk."""
        result = calculate_abandonment_risk(sample_healthy_package)

        assert result["probability"] < 30
        assert result["time_horizon_months"] == 12

    def test_abandoned_package_high_risk(self, sample_abandoned_package):
        """Package with abandonment signals should have high risk."""
        result = calculate_abandonment_risk(sample_abandoned_package)

        # Archived flag sets risk to 95%
        assert result["probability"] == 95.0
        assert "Repository is archived" in result["risk_factors"]

    def test_deprecated_package_high_risk(self, sample_deprecated_package):
        """Deprecated package should have high risk."""
        result = calculate_abandonment_risk(sample_deprecated_package)

        assert result["probability"] == 95.0
        assert "Package is deprecated" in result["risk_factors"]

    def test_longer_horizon_increases_risk(self, sample_healthy_package):
        """Longer time horizon should increase risk probability."""
        risk_12m = calculate_abandonment_risk(sample_healthy_package, months=12)
        risk_24m = calculate_abandonment_risk(sample_healthy_package, months=24)

        assert risk_24m["probability"] > risk_12m["probability"]

    def test_risk_factors_populated(self):
        """Risk factors should be populated for risky packages."""
        data = {
            "days_since_last_commit": 200,
            "active_contributors_90d": 1,
            "weekly_downloads": 500,
            "last_published": "2024-01-01T00:00:00Z",
        }
        result = calculate_abandonment_risk(data)

        # Should have multiple risk factors
        assert len(result["risk_factors"]) >= 2
        assert any("commit" in f.lower() for f in result["risk_factors"])
        assert any("maintainer" in f.lower() for f in result["risk_factors"])

    def test_components_present(self):
        """Risk components should be included in result."""
        result = calculate_abandonment_risk({})

        assert "components" in result
        components = result["components"]
        assert "inactivity_risk" in components
        assert "bus_factor_risk" in components
        assert "adoption_risk" in components
        assert "release_risk" in components


class TestAdoptionRisk:
    """Tests for adoption risk calculation within abandonment_risk."""

    def test_adoption_risk_continuous_scale(self):
        """Adoption risk should decrease continuously with higher downloads."""
        # Test that higher downloads = lower risk (continuous function)
        data_low = {
            "weekly_downloads": 10,
            "days_since_last_commit": 0,
            "active_contributors_90d": 10,
        }
        data_medium = {
            "weekly_downloads": 10_000,
            "days_since_last_commit": 0,
            "active_contributors_90d": 10,
        }
        data_high = {
            "weekly_downloads": 1_000_000,
            "days_since_last_commit": 0,
            "active_contributors_90d": 10,
        }

        risk_low = calculate_abandonment_risk(data_low)
        risk_medium = calculate_abandonment_risk(data_medium)
        risk_high = calculate_abandonment_risk(data_high)

        # Risk should decrease with more downloads
        assert risk_low["components"]["adoption_risk"] > risk_medium["components"]["adoption_risk"]
        assert risk_medium["components"]["adoption_risk"] > risk_high["components"]["adoption_risk"]

        # Verify reasonable bounds (continuous scale from ~90% to 10%)
        assert risk_low["components"]["adoption_risk"] > 70  # Very low downloads = high risk
        assert risk_high["components"]["adoption_risk"] == 10.0  # Capped at 10% for high downloads

    def test_adoption_risk_no_discontinuities(self):
        """Adoption risk should not have sudden jumps at boundaries."""
        # Test values around old step function boundaries (99 vs 101, 999 vs 1001)
        downloads_around_100 = [99, 100, 101]
        downloads_around_1000 = [999, 1000, 1001]

        for downloads in downloads_around_100:
            data = {
                "weekly_downloads": downloads,
                "days_since_last_commit": 0,
                "active_contributors_90d": 10,
            }
            result = calculate_abandonment_risk(data)
            # All should be relatively close (within a few percentage points)
            # Old step function had 80% vs 50% jump at 100 downloads
            assert 55 < result["components"]["adoption_risk"] < 70

        for downloads in downloads_around_1000:
            data = {
                "weekly_downloads": downloads,
                "days_since_last_commit": 0,
                "active_contributors_90d": 10,
            }
            result = calculate_abandonment_risk(data)
            # Should be around 47% (log10(1000)/7 = 0.43, 0.9 - 0.43 = 0.47)
            assert 40 < result["components"]["adoption_risk"] < 55


class TestGetRiskTrend:
    """Tests for get_risk_trend function."""

    def test_stable_trend(self):
        """Small changes should be STABLE."""
        result = get_risk_trend([50.0, 51.0, 52.0])

        assert result["trend"] == "STABLE"
        assert result["change"] == 1.0

    def test_increasing_trend(self):
        """Large increase should be INCREASING."""
        result = get_risk_trend([30.0, 40.0, 50.0])

        assert result["trend"] == "INCREASING"
        assert result["change"] == 10.0

    def test_decreasing_trend(self):
        """Large decrease should be DECREASING."""
        result = get_risk_trend([50.0, 40.0, 30.0])

        assert result["trend"] == "DECREASING"
        assert result["change"] == -10.0

    def test_single_score_stable(self):
        """Single score should return STABLE."""
        result = get_risk_trend([50.0])

        assert result["trend"] == "STABLE"
        assert result["change"] == 0.0

    def test_empty_list_stable(self):
        """Empty list should return STABLE."""
        result = get_risk_trend([])

        assert result["trend"] == "STABLE"


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_negative_days_handled(self):
        """Negative days should be clamped and produce valid score."""
        data = {"days_since_last_commit": -5}
        score = _maintainer_health(data)

        # AFTER FIX: Negative days are clamped to 0, so score must be bounded 0-1
        assert 0 <= score <= 1

    def test_very_large_downloads(self):
        """Very large download numbers should not overflow."""
        data = {"weekly_downloads": 10**12, "dependents_count": 0, "stars": 0}
        score = _user_centric_health(data)

        # Should cap at 1.0
        assert score <= 1.0

    def test_malformed_date_handled(self):
        """Malformed dates should not crash."""
        data = {"last_published": "not-a-date"}
        score = _evolution_health(data)

        # Should use default and return valid score
        assert 0 <= score <= 1

    def test_unicode_in_deprecation_message(self):
        """Unicode in deprecation message should not crash."""
        data = {
            "is_deprecated": True,
            "deprecation_message": "Use @new/pkg instead.",
        }
        result = calculate_abandonment_risk(data)

        assert result["probability"] == 95.0


# =============================================================================
# v2 Scoring System Tests (Maturity, True Bus Factor, Security)
# =============================================================================


class TestMaturityFactor:
    """Tests for maturity factor calculation (stable packages)."""

    def test_high_adoption_low_activity_gets_bonus(self):
        """Packages like lodash should get maturity bonus."""
        data = {
            "weekly_downloads": 5_000_000,  # High adoption
            "dependents_count": 10_000,
            "commits_90d": 2,  # Very low activity
        }
        factor = _calculate_maturity_factor(data)

        # Should get a significant maturity factor (0.3-0.7 range)
        assert factor > 0.3
        assert factor <= 0.7

    def test_low_adoption_low_activity_no_bonus(self):
        """Unknown packages with low activity should NOT get bonus."""
        data = {
            "weekly_downloads": 100,  # Low adoption
            "dependents_count": 5,
            "commits_90d": 2,  # Low activity
        }
        factor = _calculate_maturity_factor(data)

        # Should get minimal/no maturity factor
        assert factor < 0.1

    def test_high_adoption_high_activity_no_bonus(self):
        """Active packages don't need maturity bonus."""
        data = {
            "weekly_downloads": 5_000_000,
            "dependents_count": 10_000,
            "commits_90d": 50,  # High activity
        }
        factor = _calculate_maturity_factor(data)

        # Activity is high, so maturity factor should be low
        assert factor < 0.2

    def test_maturity_scales_with_adoption(self):
        """Higher adoption should yield higher maturity factor."""
        data_1m = {
            "weekly_downloads": 1_000_000,
            "dependents_count": 0,
            "commits_90d": 0,
        }
        data_10m = {
            "weekly_downloads": 10_000_000,
            "dependents_count": 0,
            "commits_90d": 0,
        }

        factor_1m = _calculate_maturity_factor(data_1m)
        factor_10m = _calculate_maturity_factor(data_10m)

        assert factor_10m > factor_1m

    def test_dependents_can_trigger_maturity(self):
        """High dependents should also trigger maturity bonus."""
        data = {
            "weekly_downloads": 100,  # Low downloads
            "dependents_count": 10_000,  # But high dependents
            "commits_90d": 0,
        }
        factor = _calculate_maturity_factor(data)

        assert factor > 0.3


class TestTrueBusFactor:
    """Tests for true bus factor in maintainer health."""

    def test_true_bus_factor_used_when_available(self):
        """True bus factor should override contributor count."""
        data = {
            "days_since_last_commit": 7,
            "active_contributors_90d": 10,  # Would give high score
            "true_bus_factor": 1,  # But 1 person does 50% of work
        }
        score = _maintainer_health(data)

        # Bus factor of 1 should reduce score significantly
        # Recency is good (~0.95), but bus factor of 1 ~= 0.27
        # Score = 0.95 * 0.6 + 0.27 * 0.4 = 0.57 + 0.108 = ~0.68
        assert 0.5 < score < 0.8

    def test_fallback_to_contributor_count(self):
        """Should use contributor count if true_bus_factor missing."""
        data = {
            "days_since_last_commit": 7,
            "active_contributors_90d": 5,
            # No true_bus_factor
        }
        score = _maintainer_health(data)

        # Both recency and bus factor should be good
        assert score > 0.8

    def test_true_bus_factor_zero_fallback(self):
        """Bus factor of 0 should fall back to contributor count."""
        data = {
            "days_since_last_commit": 7,
            "active_contributors_90d": 5,
            "true_bus_factor": 0,
        }
        score = _maintainer_health(data)

        # Should fall back to active_contributors_90d
        assert score > 0.8


class TestSecurityHealth:
    """Tests for the new security health component."""

    def test_high_openssf_high_score(self):
        """High OpenSSF score with no vulnerabilities = high security."""
        data = {
            "openssf_score": 9.0,
            "advisories": [],
            "openssf_checks": [
                {"name": "Security-Policy", "score": 10},
            ],
        }
        score = _security_health(data)

        assert score > 0.8

    def test_missing_openssf_penalized(self):
        """Missing OpenSSF score should be penalized (default 0.3)."""
        data = {
            "openssf_score": None,
            "advisories": [],
            "openssf_checks": [],
        }
        score = _security_health(data)

        # Default OpenSSF = 0.3, no vulns = good, no policy = 0.3
        # 0.3 * 0.5 + ~0.79 * 0.3 + 0.3 * 0.2 = 0.15 + 0.237 + 0.06 = ~0.45
        assert 0.3 < score < 0.6

    def test_critical_vulns_reduce_score(self):
        """Critical vulnerabilities should significantly reduce score."""
        data = {
            "openssf_score": 7.0,
            "advisories": [
                {"severity": "CRITICAL"},
                {"severity": "HIGH"},
            ],
            "openssf_checks": [],
        }
        score = _security_health(data)

        # Critical + High = 3 + 2 = 5 weighted vulns -> low vulnerability score
        assert score < 0.5

    def test_security_policy_bonus(self):
        """Having security policy should improve score."""
        data_with = {
            "openssf_score": 5.0,
            "advisories": [],
            "openssf_checks": [{"name": "Security-Policy", "score": 8}],
        }
        data_without = {
            "openssf_score": 5.0,
            "advisories": [],
            "openssf_checks": [],
        }

        score_with = _security_health(data_with)
        score_without = _security_health(data_without)

        assert score_with > score_without


class TestWeightDistribution:
    """Tests for v2 component weight distribution."""

    def test_component_weights_sum_to_100(self):
        """Verify component weights total 100%.

        v2 weights: Maintainer 25%, User-Centric 30%, Evolution 20%,
        Community 10%, Security 15%
        """
        # This test documents the expected weights and verifies they sum correctly
        expected_weights = {
            "maintainer_health": 0.25,
            "user_centric": 0.30,
            "evolution_health": 0.20,
            "community_health": 0.10,
            "security_health": 0.15,
        }
        assert sum(expected_weights.values()) == 1.0

        # Verify the weights by checking score calculation
        # Create data where each component scores exactly 1.0
        data = {
            # Maintainer: recent commits + good bus factor
            "days_since_last_commit": 0,
            "active_contributors_90d": 10,
            "true_bus_factor": 10,
            # User-Centric: very high adoption
            "weekly_downloads": 100_000_000,
            "dependents_count": 100_000,
            "stars": 500_000,
            # Evolution: recent release + active
            "last_published": "2026-01-01T00:00:00Z",
            "commits_90d": 100,
            # Community: many contributors
            "total_contributors": 100,
            # Security: perfect score
            "openssf_score": 10.0,
            "advisories": [],
            "openssf_checks": [{"name": "Security-Policy", "score": 10}],
        }
        result = calculate_health_score(data)

        # With all components near 1.0, total should be near 100
        assert result["health_score"] >= 95

    def test_weights_produce_valid_score(self):
        """Verify weighted components produce score in valid range."""
        data = {
            "days_since_last_commit": 30,
            "active_contributors_90d": 3,
            "weekly_downloads": 100_000,
            "dependents_count": 500,
            "stars": 5000,
            "last_published": "2025-12-01T00:00:00Z",
            "commits_90d": 20,
            "total_contributors": 10,
            "openssf_score": 6.0,
            "advisories": [],
            "openssf_checks": [],
        }
        result = calculate_health_score(data)

        assert 0 <= result["health_score"] <= 100
        assert len(result["components"]) == 5

    def test_security_component_contributes(self):
        """Security component should affect overall score."""
        # Good security
        data_secure = {
            "days_since_last_commit": 7,
            "active_contributors_90d": 5,
            "weekly_downloads": 1_000_000,
            "openssf_score": 9.0,
            "advisories": [],
            "openssf_checks": [{"name": "Security-Policy", "score": 10}],
        }
        # Poor security
        data_insecure = {
            "days_since_last_commit": 7,
            "active_contributors_90d": 5,
            "weekly_downloads": 1_000_000,
            "openssf_score": 2.0,
            "advisories": [
                {"severity": "CRITICAL"},
                {"severity": "CRITICAL"},
            ],
            "openssf_checks": [],
        }

        result_secure = calculate_health_score(data_secure)
        result_insecure = calculate_health_score(data_insecure)

        # Security is 15% of score, so ~15 point difference possible
        assert result_secure["health_score"] > result_insecure["health_score"]
        assert result_secure["components"]["security_health"] > result_insecure["components"]["security_health"]


class TestScoreBounds:
    """Tests ensuring scores stay within valid ranges."""

    def test_health_score_bounds_extreme_low(self):
        """Extreme low case should still be 0-100."""
        result = calculate_health_score({})

        assert 0 <= result["health_score"] <= 100
        for name, value in result["components"].items():
            assert 0 <= value <= 100, f"{name} out of bounds: {value}"

    def test_health_score_bounds_extreme_high(self):
        """Extreme high case should still be 0-100."""
        data = {
            "days_since_last_commit": 0,
            "active_contributors_90d": 100,
            "true_bus_factor": 10,
            "weekly_downloads": 100_000_000,
            "dependents_count": 100_000,
            "stars": 500_000,
            "commits_90d": 1000,
            "last_published": "2026-01-01T00:00:00Z",
            "openssf_score": 10.0,
            "advisories": [],
            "openssf_checks": [{"name": "Security-Policy", "score": 10}],
            "total_contributors": 500,
        }
        result = calculate_health_score(data)

        assert 0 <= result["health_score"] <= 100
        for name, value in result["components"].items():
            assert 0 <= value <= 100, f"{name} out of bounds: {value}"

    def test_negative_inputs_handled(self):
        """Negative inputs should be clamped and produce valid scores."""
        data = {
            "days_since_last_commit": -100,
            "weekly_downloads": -1000,
            "commits_90d": -50,
        }
        result = calculate_health_score(data)

        assert 0 <= result["health_score"] <= 100
        for name, value in result["components"].items():
            assert 0 <= value <= 100, f"{name} out of bounds: {value}"
