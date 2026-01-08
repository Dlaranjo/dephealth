"""
Tests for the health check endpoint.
"""

import json


class TestHealthEndpoint:
    """Tests for GET /health endpoint."""

    def test_returns_200(self):
        """Health endpoint should return 200."""
        from api.health import handler

        result = handler({}, {})

        assert result["statusCode"] == 200

    def test_returns_healthy_status(self):
        """Health endpoint should return healthy status."""
        from api.health import handler

        result = handler({}, {})
        body = json.loads(result["body"])

        assert body["status"] == "healthy"

    def test_returns_version(self):
        """Health endpoint should return version."""
        from api.health import handler

        result = handler({}, {})
        body = json.loads(result["body"])

        assert "version" in body
        assert body["version"] == "1.0.0"

    def test_returns_timestamp(self):
        """Health endpoint should return timestamp."""
        from api.health import handler

        result = handler({}, {})
        body = json.loads(result["body"])

        assert "timestamp" in body

    def test_returns_json_content_type(self):
        """Health endpoint should return JSON content type."""
        from api.health import handler

        result = handler({}, {})

        assert result["headers"]["Content-Type"] == "application/json"

    def test_returns_no_cache_header(self):
        """Health endpoint should not be cached."""
        from api.health import handler

        result = handler({}, {})

        assert result["headers"]["Cache-Control"] == "no-cache"
