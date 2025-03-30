import pytest
from unittest.mock import Mock, patch, call, create_autospec, MagicMock
import time
from logging import Logger
from threading import BoundedSemaphore, RLock, Thread

from kuhl_haus.metrics.tasks.thread_pool import ThreadPool


@pytest.fixture
def mock_logger():
    mock = MagicMock(spec=Logger)
    return mock


@pytest.fixture
def thread_pool_size():
    return 2


@pytest.fixture
def mock_thread_pool(mock_logger, thread_pool_size):
    mock = ThreadPool(mock_logger, thread_pool_size)
    return mock


@pytest.fixture
def test_func():
    mock = MagicMock()
    return mock


@pytest.fixture
def long_running_func():
    return lambda: time.sleep(1.0)


@pytest.fixture
def error_func():
    return lambda: 1 / 0


@pytest.fixture
def task_func():
    return lambda: time.sleep(0.001)


class TestException(Exception):
    pass


def test_init(mock_logger, thread_pool_size):
    """Test initialization of the ThreadPool."""
    # Arrange & Act
    idle_time_out = 5
    clean_up_sleep = 15.5
    thread_pool = ThreadPool(
        logger=mock_logger,
        size=thread_pool_size,
        idle_time_out=idle_time_out,
        clean_up_sleep=clean_up_sleep,
    )

    # Assert
    assert thread_pool.size == thread_pool_size
    assert thread_pool.thread_count == 0
    assert thread_pool.idle_time_out == idle_time_out
    assert thread_pool.clean_up_sleep == clean_up_sleep
    assert thread_pool.clean_up_thread_is_alive is True


def test_thread_count_property(mock_thread_pool, task_func):
    """Test the thread_count property correctly reports active threads."""
    # Arrange

    # Act
    mock_thread_pool.start_task("task1", task_func, {})
    thread_count_after_one = mock_thread_pool.thread_count

    mock_thread_pool.start_task("task2", task_func, {})
    thread_count_after_two = mock_thread_pool.thread_count

    # Wait for tasks to complete
    time.sleep(0.3)
    thread_count_after_completion = mock_thread_pool.thread_count

    # Assert
    assert thread_count_after_one == 1
    assert thread_count_after_two == 2
    assert thread_count_after_completion == 0


def test_start_task_basic(mock_thread_pool, test_func):
    """Test starting a basic task."""
    # Arrange
    kwargs = {"value": 42}

    # Act
    mock_thread_pool.start_task("test_task", test_func, kwargs)

    # Wait for task to execute
    time.sleep(0.1)

    # Assert
    test_func.assert_called_once_with(value=42)


def test_start_task_same_name_alive(mock_thread_pool, task_func):
    """Test starting a task with the same name while previous is still alive."""
    # Arrange
    second_func = MagicMock()

    # Act
    mock_thread_pool.start_task("same_name", task_func, {})

    # Try to start another task with the same name before first completes
    mock_thread_pool.start_task("same_name", second_func, {})

    # Wait and verify
    time.sleep(0.3)

    # Assert
    second_func.assert_not_called()  # Second task should not be executed


def test_start_task_same_name_completed(mock_thread_pool, test_func):
    """Test starting a task with the same name after previous has completed."""
    # Arrange
    second_func = MagicMock()

    # Act
    mock_thread_pool.start_task("same_name", test_func, {})
    time.sleep(0.1)  # Let the first task complete

    mock_thread_pool.start_task("same_name", second_func, {})
    time.sleep(0.1)  # Let the second task complete

    # Assert
    test_func.assert_called_once()
    second_func.assert_called_once()


def test_pool_size_limit_non_blocking(mock_thread_pool, thread_pool_size, test_func, task_func):
    """Test pool size limits with non-blocking calls."""
    # Arrange
    blocking = False

    # Act - Fill the pool
    for i in range(thread_pool_size):
        mock_thread_pool.start_task(f"task{i}", task_func, {})

    # Try to add one more task (non-blocking)
    mock_thread_pool.start_task("extra_task", test_func, {}, blocking)

    # Assert
    assert mock_thread_pool.thread_count == thread_pool_size
    test_func.assert_not_called()  # Extra task should not run


def test_pool_size_limit_blocking(mock_thread_pool, thread_pool_size, test_func, task_func):
    """Test pool size limits with blocking calls."""
    # Arrange
    blocking = True

    # Act - Fill the pool
    for i in range(thread_pool_size):
        mock_thread_pool.start_task(f"task{i}", task_func, {})

    # Start a thread to add one more task (blocking)
    def add_blocking_task():
        mock_thread_pool.start_task("blocking_task", test_func, {}, blocking)

    blocking_thread = Thread(target=add_blocking_task)
    blocking_thread.start()

    # Wait a bit - the blocking task shouldn't run yet
    time.sleep(0.05)
    was_called_before = test_func.called

    # Wait for original tasks to complete
    time.sleep(0.2)
    blocking_thread.join(0.2)  # Wait for blocking thread to complete

    # Assert
    assert not was_called_before  # Should not be called before pool has space
    test_func.assert_called_once()  # Should run once pool has space


def test_cleanup_threads(mock_thread_pool, thread_pool_size, test_func, task_func):
    """Test that threads are cleaned up after completion."""
    # Arrange

    # Act
    for i in range(thread_pool_size):
        mock_thread_pool.start_task(f"cleanup_task{i}", task_func, {})

    count_during = mock_thread_pool.thread_count
    time.sleep(0.3)  # Wait for tasks to complete and cleanup to run
    count_after = mock_thread_pool.thread_count

    # Assert
    assert count_during == thread_pool_size
    assert count_after == 0


@patch('kuhl_haus.metrics.tasks.thread_pool.Thread')
def test_error_handling(patched_thread, mock_thread_pool, error_func, mock_logger):
    """Test error handling in tasks."""
    # Arrange
    # Act
    mock_thread = create_autospec(Thread)
    mock_thread.start = MagicMock()
    mock_thread.start.side_effect = TestException
    patched_thread.return_value = mock_thread

    mock_thread_pool.start_task("error_task", error_func, {})
    time.sleep(0.1)  # Give error time to be caught

    # Assert
    mock_thread.start.assert_called()
    mock_logger.error.assert_called()
    assert "Unhandled exception raised" in str(mock_logger.error.call_args)


@patch('kuhl_haus.metrics.tasks.thread_pool.Thread')
def test_cleanup_thread_restart(patched_thread, mock_logger, test_func):
    """Test that the cleanup thread is restarted if needed."""
    # Arrange
    mock_thread = create_autospec(Thread)
    mock_thread.is_alive = MagicMock()
    mock_thread.is_alive.side_effect = [False, True, True, False, False, False, False, False, False]
    patched_thread.return_value = mock_thread
    sut = ThreadPool(logger=mock_logger, size=3, idle_time_out=0, clean_up_sleep=0.01)

    # Wait for cleanup thread to exit
    time.sleep(0.1)
    before_start_task_result = sut.clean_up_thread_is_alive
    # Start a task to trigger a new cleanup thread
    sut.start_task("new_task", test_func, {})
    after_start_task_result = sut.clean_up_thread_is_alive
    time.sleep(0.1)

    # Assert
    assert before_start_task_result is False
    assert after_start_task_result is True
    assert before_start_task_result != after_start_task_result
