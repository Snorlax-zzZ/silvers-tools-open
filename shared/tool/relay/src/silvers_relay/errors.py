from __future__ import annotations

from typing import Any


class RelayError(Exception):
    """A user-actionable Relay protocol error."""

    code = "relay_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


class SchemaUnsupported(RelayError):
    code = "schema_unsupported"

    def __init__(
        self,
        *,
        component: str,
        cli_version: str,
        supported_schema: int,
        encountered_schema: int,
    ) -> None:
        super().__init__(
            (
                f"当前 Relay {cli_version} 不支持 {component} schema "
                f"{encountered_schema}；本机支持 {supported_schema}"
            ),
            details={
                "component": component,
                "cli_version": cli_version,
                "supported_schema": supported_schema,
                "encountered_schema": encountered_schema,
                "suggested_action": (
                    "更新本机 Relay 后重试；不要手工降级或改写数据"
                ),
            },
        )


class ProjectError(RelayError):
    code = "store_error"


class NotGitProject(ProjectError):
    code = "not_git_project"


class StoreError(RelayError):
    code = "store_error"


class MigrationFailed(RelayError):
    code = "migration_failed"


class InstallationError(RelayError):
    code = "installation_error"


class InvalidRequest(RelayError):
    code = "invalid_request"


class PhaseAuthorizationRequired(RelayError):
    code = "phase_authorization_required"


class RequestTooLarge(RelayError):
    code = "request_too_large"


class InternalError(RelayError):
    code = "internal_error"


class NotConfigured(RelayError):
    code = "not_configured"


class InvalidRelayId(InvalidRequest):
    pass


class SecretDetected(RelayError):
    code = "secret_detected"


class StaleRevision(RelayError):
    code = "stale_revision"


class RelayNotFound(RelayError):
    code = "relay_not_found"


class SelectionRequired(RelayError):
    code = "selection_required"


class UnresolvedP0(RelayError):
    code = "unresolved_p0"


class UnapprovedDeviation(RelayError):
    code = "unapproved_deviation"


class IncompleteRelay(RelayError):
    code = "incomplete_relay"


class CriteriaTransitionRequired(RelayError):
    code = "criteria_transition_required"


class LoadTooLarge(RelayError):
    code = "load_too_large"


class StoreDirty(RelayError):
    code = "store_dirty"


class StoreBusy(RelayError):
    code = "store_busy"


class SyncError(RelayError):
    code = "sync_error"
