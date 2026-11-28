from google.genai.errors import ServerError

from agent.errors import format_gemini_error


def test_quota_error_is_formatted_for_users_with_retry_delay():
    error = ServerError(
        429,
        {
            "error": {
                "status": "RESOURCE_EXHAUSTED",
                "message": "Quota exceeded",
                "details": [
                    {
                        "@type": "type.googleapis.com/google.rpc.RetryInfo",
                        "retryDelay": "49834s",
                    }
                ],
            }
        },
    )

    message = format_gemini_error(error)

    assert "Gemini agotó la cuota disponible (HTTP 429)" in message
    assert "13 h 50 min 34 s" in message
    assert "RESOURCE_EXHAUSTED" not in message
    assert "retryDelay" not in message


def test_service_unavailable_error_has_short_actionable_message():
    error = ServerError(503, {"error": {"status": "UNAVAILABLE"}})

    assert format_gemini_error(error) == (
        "Gemini no está disponible temporalmente (HTTP 503). Inténtalo de nuevo más tarde."
    )
