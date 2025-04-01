from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from fastapi import FastAPI
from fastapi import Request, Response
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from kuhl_haus.metrics.data.metrics import Metrics
from kuhl_haus.metrics.middleware.request_logging import request_metrics
from kuhl_haus.metrics.recorders.graphite_logger import GraphiteLogger


@pytest.fixture
def valid_test_server_name():
    return "test.server"


@pytest.fixture
def valid_url_path():
    return "/test"


@pytest.fixture
def null_url_path():
    return "/null"


@pytest.fixture
def mock_request(valid_url_path, valid_test_server_name):
    """Fixture providing a mock Request object."""
    request = MagicMock(spec=Request)
    request.url.path = f"{valid_url_path}/users"
    request.headers = {"host": valid_test_server_name}
    return request


@pytest.fixture
def mock_response():
    """Fixture providing a mock Response object."""
    response = MagicMock(spec=Response)
    response.headers = {}
    return response


@pytest.fixture
def mock_call_next(mock_response):
    """Fixture providing a mock for call_next that returns the mock response."""
    mock = MagicMock()
    mock.return_value = mock_response
    return mock


@pytest.fixture
def mock_recorder():
    """Fixture providing a mock GraphiteLogger."""

    recorder = MagicMock(spec=GraphiteLogger)
    recorder.log_metrics = MagicMock()
    recorder.logger = MagicMock()
    mock_metrics = MagicMock(spec=Metrics)
    mock_metrics.attributes = {}
    recorder.get_metrics.return_value = mock_metrics
    return recorder


@pytest.fixture
def mock_success_message():
    return {"message": "success"}


# Create a test app with the middleware
@pytest.fixture
def app(mock_recorder, mock_success_message, valid_url_path, null_url_path):
    app = FastAPI()

    # Create middleware class using your function
    class MetricsMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            return await request_metrics(request, call_next, mock_recorder)

    app.add_middleware(MetricsMiddleware)

    # @app.get("/test")
    # async def test_endpoint():
    #     return mock_success_message

    @app.get(valid_url_path)
    async def valid_endpoint():
        return mock_success_message

    @app.get("/")
    async def default_endpoint():
        return mock_success_message

    @app.get(null_url_path)
    async def null_endpoint():
        return

    return app


# Create a test client
@pytest.fixture
def client(app):
    return TestClient(app)


def test_request_metrics_successful_request(client, mock_recorder, valid_url_path, valid_test_server_name):
    # Make a request to trigger the middleware
    response = client.get("/test", headers={"host": valid_test_server_name})

    # Assert response is correct
    assert response.status_code == 200
    assert "X-Request-Time" in response.headers
    assert "X-Request-Time-MS" in response.headers
    assert "X-Metrics-Time" in response.headers
    assert "X-Metrics-Time-MS" in response.headers

    # Assert metrics were recorded correctly
    mock_recorder.get_metrics.assert_called_once()
    metrics = mock_recorder.get_metrics.return_value
    metrics.set_counter.assert_called_with('responses', 1)
    mock_recorder.log_metrics.assert_called_with(metrics)

    # Check that metrics attributes were set
    assert 'request_time' in metrics.attributes
    assert 'request_time_ms' in metrics.attributes
    assert 'response_length' in metrics.attributes
    assert int(metrics.attributes['response_length']) > 0


def test_request_metrics_with_content_length(
        mock_request,
        client,
        mock_recorder,
        mock_success_message,
        valid_url_path,
        valid_test_server_name
):
    """Test request metrics middleware when response has Content-Length header."""
    # Arrange

    # Act
    response = client.get(valid_url_path, headers={"host": valid_test_server_name})

    # Assert
    metrics = mock_recorder.get_metrics.return_value
    assert 'response_length' in metrics.attributes
    print(metrics.attributes['response_length'])
    assert int(metrics.attributes['response_length']) > 0
    assert int(metrics.attributes['response_length']) == 21
    mock_recorder.log_metrics.assert_called_once_with(metrics)
    assert "Content-Length" in response.headers


def test_request_metrics_with_null_content_length_header(
        mock_request,
        client,
        mock_recorder,
        mock_success_message,
        null_url_path,
        valid_test_server_name
):
    """Test request metrics middleware when response does not have a Content-Length header."""
    # Arrange
    mock_response = AsyncMock(spec=Response)
    mock_response.headers = {}
    mock_call_next = AsyncMock()
    mock_call_next.return_value = mock_response

    sut = request_metrics

    # Act
    _ = sut(mock_request, mock_call_next, mock_recorder)

    # Assert
    metrics = mock_recorder.get_metrics.return_value
    assert 'response_length' not in metrics.attributes


@patch('kuhl_haus.metrics.middleware.request_logging.time.perf_counter_ns')
def test_request_metrics_exception_handling(
        mock_perf_counter,
        mock_request,
        mock_call_next,
        mock_recorder,
        client,
        valid_url_path,
        valid_test_server_name
):
    """Test request metrics middleware when an exception occurs."""
    # Arrange
    test_exception = ValueError("Test error")
    mock_perf_counter.side_effect = test_exception

    # Act & Assert
    with pytest.raises(ValueError, match="Test error"):
        _ = client.get(valid_url_path, headers={"host": valid_test_server_name})

    metrics = mock_recorder.get_metrics.return_value
    assert metrics.attributes['exception'] == repr(test_exception)
    metrics.set_counter.assert_called_once_with('exceptions', 1)
    mock_recorder.log_metrics.assert_called_once_with(metrics)
    mock_recorder.logger.error.assert_called_once()
    assert "Unhandled exception raised" in mock_recorder.logger.error.call_args[0][0]
    assert repr(test_exception) in mock_recorder.logger.error.call_args[0][0]


def test_request_metrics_path_normalization(
        mock_request,
        mock_call_next,
        mock_recorder,
        client,
        valid_test_server_name
):
    """Test the normalization of URL paths into mnemonics."""
    # Arrange
    test_cases = [
        ("/test/users", "test_users"),
        ("/", ""),
        ("", ""),
        ("/test/users/123", "test_users_123"),
    ]

    for path, expected_mnemonic in test_cases:
        mock_request.url.path = path

        # Act
        _ = client.get(path, headers={"host": mock_request.headers['host']})

        # Assert
        mock_recorder.get_metrics.assert_called_with(
            mnemonic=expected_mnemonic,
            hostname=mock_request.headers['host']
        )
        mock_recorder.get_metrics.reset_mock()


@patch('kuhl_haus.metrics.middleware.request_logging.time.perf_counter_ns')
def test_request_metrics_millisecond_conversion(
        mock_perf_counter,
        mock_request,
        mock_call_next,
        mock_recorder,
        client,
        valid_url_path,
        valid_test_server_name
):
    """Test correct conversion of nanoseconds to milliseconds."""
    # Arrange
    # Test different values to ensure proper conversion
    test_cases = [
        (1_000_000, 1),  # 1ms
        (1_500_000, 1),  # 1.5ms should be truncated to 1ms
        (10_000_000, 10),  # 10ms
        (1_000_000_000, 1000),  # 1 second = 1000ms
        (0, 0),  # Zero case
    ]

    for ns_value, expected_ms in test_cases:
        mock_perf_counter.side_effect = [1000, 1000 + ns_value, 3000, 3000]

        # Act
        response = client.get(valid_url_path, headers={"host": valid_test_server_name})

        # Assert
        assert response.headers["X-Request-Time"] == str(ns_value)
        assert response.headers["X-Request-Time-MS"] == str(expected_ms)
        assert mock_recorder.get_metrics.return_value.attributes['request_time'] == ns_value
        assert mock_recorder.get_metrics.return_value.attributes['request_time_ms'] == expected_ms

