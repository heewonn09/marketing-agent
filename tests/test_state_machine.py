"""FSM 상태 전이 단위 테스트."""
import pytest
from utils.state_machine import validate_transition, InvalidTransitionError, is_terminal


class TestValidTransitions:
    def test_none_to_running(self):
        validate_transition(None, "running")

    def test_running_to_pending_approval(self):
        validate_transition("running", "pending_approval")

    def test_pending_approval_to_posting(self):
        validate_transition("pending_approval", "posting")

    def test_posting_to_done(self):
        validate_transition("posting", "done")

    def test_running_to_error(self):
        validate_transition("running", "error")

    def test_running_to_interrupted(self):
        validate_transition("running", "interrupted")

    def test_interrupted_to_running(self):
        validate_transition("interrupted", "running")

    def test_error_to_running_rerun(self):
        validate_transition("error", "running")

    def test_idempotent_done(self):
        validate_transition("done", "done")

    def test_idempotent_error(self):
        validate_transition("error", "error")

    def test_always_allowed_error(self):
        validate_transition("done", "error")

    def test_always_allowed_interrupted(self):
        validate_transition("done", "interrupted")


class TestInvalidTransitions:
    def test_done_to_running_invalid(self):
        with pytest.raises(InvalidTransitionError):
            validate_transition("done", "running")

    def test_done_to_pending(self):
        with pytest.raises(InvalidTransitionError):
            validate_transition("done", "pending_approval")

    def test_posting_to_running(self):
        with pytest.raises(InvalidTransitionError):
            validate_transition("posting", "running")

    def test_none_to_done(self):
        with pytest.raises(InvalidTransitionError):
            validate_transition(None, "done")


class TestIsTerminal:
    def test_done_is_terminal(self):
        assert is_terminal("done")

    def test_rejected_is_terminal(self):
        assert is_terminal("rejected")

    def test_error_not_terminal(self):
        assert not is_terminal("error")

    def test_running_not_terminal(self):
        assert not is_terminal("running")
