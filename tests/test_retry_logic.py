"""
Unit tests for retry logic with exponential backoff.
"""

import pytest
import time
from unittest.mock import Mock, MagicMock
import requests
from shared.retry_utils import retry_with_backoff, RetryConfig, calculate_backoff, is_retryable_http_error


class TestRetryLogic:
    """Test suite for retry decorator and utility functions"""

    def test_successful_first_attempt(self):
        """Should not retry if first attempt succeeds"""
        mock_func = Mock(return_value="success")
        decorated = retry_with_backoff()(mock_func)

        result = decorated()

        assert result == "success"
        assert mock_func.call_count == 1

    def test_retry_on_timeout(self):
        """Should retry on network timeout"""
        mock_func = Mock(side_effect=[
            requests.exceptions.Timeout("Connection timeout"),
            "success"
        ])
        decorated = retry_with_backoff(RetryConfig(max_attempts=3))(mock_func)

        result = decorated()

        assert result == "success"
        assert mock_func.call_count == 2

    def test_retry_on_connection_error(self):
        """Should retry on connection error"""
        mock_func = Mock(side_effect=[
            requests.exceptions.ConnectionError("Connection refused"),
            "success"
        ])
        decorated = retry_with_backoff(RetryConfig(max_attempts=3))(mock_func)

        result = decorated()

        assert result == "success"
        assert mock_func.call_count == 2

    def test_retry_on_500_error(self):
        """Should retry on 500 server error"""
        response = Mock()
        response.status_code = 500

        http_error = requests.exceptions.HTTPError()
        http_error.response = response

        mock_func = Mock(side_effect=[
            http_error,
            "success"
        ])
        decorated = retry_with_backoff(RetryConfig(max_attempts=3))(mock_func)

        result = decorated()

        assert result == "success"
        assert mock_func.call_count == 2

    def test_retry_on_429_rate_limit(self):
        """Should retry on 429 rate limit error"""
        response = Mock()
        response.status_code = 429

        http_error = requests.exceptions.HTTPError()
        http_error.response = response

        mock_func = Mock(side_effect=[
            http_error,
            "success"
        ])
        decorated = retry_with_backoff(RetryConfig(max_attempts=3))(mock_func)

        result = decorated()

        assert result == "success"
        assert mock_func.call_count == 2

    def test_no_retry_on_404_error(self):
        """Should NOT retry on 404 client error"""
        response = Mock()
        response.status_code = 404

        http_error = requests.exceptions.HTTPError()
        http_error.response = response

        mock_func = Mock(side_effect=http_error)
        decorated = retry_with_backoff(RetryConfig(max_attempts=3))(mock_func)

        with pytest.raises(requests.exceptions.HTTPError):
            decorated()

        assert mock_func.call_count == 1  # No retry

    def test_no_retry_on_400_error(self):
        """Should NOT retry on 400 bad request"""
        response = Mock()
        response.status_code = 400

        http_error = requests.exceptions.HTTPError()
        http_error.response = response

        mock_func = Mock(side_effect=http_error)
        decorated = retry_with_backoff(RetryConfig(max_attempts=3))(mock_func)

        with pytest.raises(requests.exceptions.HTTPError):
            decorated()

        assert mock_func.call_count == 1  # No retry

    def test_no_retry_on_401_error(self):
        """Should NOT retry on 401 unauthorized"""
        response = Mock()
        response.status_code = 401

        http_error = requests.exceptions.HTTPError()
        http_error.response = response

        mock_func = Mock(side_effect=http_error)
        decorated = retry_with_backoff(RetryConfig(max_attempts=3))(mock_func)

        with pytest.raises(requests.exceptions.HTTPError):
            decorated()

        assert mock_func.call_count == 1  # No retry

    def test_exponential_backoff_calculation(self):
        """Should calculate exponential backoff correctly"""
        config = RetryConfig(
            max_attempts=3,
            base_delay=1.0,
            exponential_base=2.0,
            jitter=False  # Disable jitter for predictable testing
        )

        delay_0 = calculate_backoff(0, config)
        delay_1 = calculate_backoff(1, config)
        delay_2 = calculate_backoff(2, config)

        assert delay_0 == 1.0  # 1.0 * 2^0
        assert delay_1 == 2.0  # 1.0 * 2^1
        assert delay_2 == 4.0  # 1.0 * 2^2

    def test_max_delay_cap(self):
        """Should cap delay at max_delay"""
        config = RetryConfig(
            base_delay=1.0,
            max_delay=5.0,
            exponential_base=2.0,
            jitter=False
        )

        # 1.0 * 2^10 = 1024, but should be capped at 5.0
        delay = calculate_backoff(10, config)
        assert delay == 5.0

    def test_max_attempts_exhausted(self):
        """Should raise after max attempts"""
        mock_func = Mock(side_effect=requests.exceptions.Timeout("Always fails"))
        decorated = retry_with_backoff(RetryConfig(max_attempts=2, base_delay=0.01))(mock_func)

        with pytest.raises(requests.exceptions.Timeout):
            decorated()

        assert mock_func.call_count == 2

    def test_jitter_adds_randomness(self):
        """Jitter should vary wait times"""
        config = RetryConfig(base_delay=1.0, jitter=True)

        delays = [calculate_backoff(0, config) for _ in range(10)]

        # Should have variation due to jitter
        assert len(set(delays)) > 1
        # All delays should be close to 1.0 (±25%)
        assert all(0.75 <= d <= 1.25 for d in delays)

    def test_no_jitter_gives_consistent_delays(self):
        """Without jitter, delays should be consistent"""
        config = RetryConfig(base_delay=1.0, jitter=False)

        delays = [calculate_backoff(0, config) for _ in range(10)]

        # All delays should be identical
        assert len(set(delays)) == 1
        assert delays[0] == 1.0

    def test_is_retryable_http_error_function(self):
        """Test is_retryable_http_error function"""
        # Test retryable status codes
        for status_code in [429, 500, 502, 503, 504]:
            response = Mock()
            response.status_code = status_code
            http_error = requests.exceptions.HTTPError()
            http_error.response = response
            assert is_retryable_http_error(http_error) is True

        # Test non-retryable status codes
        for status_code in [400, 401, 403, 404]:
            response = Mock()
            response.status_code = status_code
            http_error = requests.exceptions.HTTPError()
            http_error.response = response
            assert is_retryable_http_error(http_error) is False

        # Test non-HTTP exception (should be retryable)
        assert is_retryable_http_error(Exception("Generic error")) is True

    def test_multiple_failures_then_success(self):
        """Should keep retrying until success"""
        mock_func = Mock(side_effect=[
            requests.exceptions.Timeout("Timeout 1"),
            requests.exceptions.Timeout("Timeout 2"),
            "success"
        ])
        decorated = retry_with_backoff(RetryConfig(max_attempts=4, base_delay=0.01))(mock_func)

        result = decorated()

        assert result == "success"
        assert mock_func.call_count == 3

    def test_preserves_function_name(self):
        """Decorator should preserve original function name"""
        @retry_with_backoff()
        def my_function():
            return "test"

        assert my_function.__name__ == "my_function"

    def test_passes_arguments_correctly(self):
        """Should pass arguments and kwargs to decorated function"""
        mock_func = Mock(return_value="success")
        decorated = retry_with_backoff()(mock_func)

        result = decorated("arg1", "arg2", kwarg1="value1")

        assert result == "success"
        mock_func.assert_called_once_with("arg1", "arg2", kwarg1="value1")

    def test_custom_config_parameters(self):
        """Should respect custom configuration parameters"""
        config = RetryConfig(
            max_attempts=5,
            base_delay=0.5,
            max_delay=10.0,
            exponential_base=3.0,
            jitter=False
        )

        delay_0 = calculate_backoff(0, config)
        delay_1 = calculate_backoff(1, config)
        delay_2 = calculate_backoff(2, config)

        assert delay_0 == 0.5  # 0.5 * 3^0
        assert delay_1 == 1.5  # 0.5 * 3^1
        assert delay_2 == 4.5  # 0.5 * 3^2

    def test_non_negative_delay(self):
        """Delay should never be negative"""
        config = RetryConfig(base_delay=0.1, jitter=True)

        # Generate many delays to ensure none are negative
        delays = [calculate_backoff(0, config) for _ in range(100)]
        assert all(d >= 0 for d in delays)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
