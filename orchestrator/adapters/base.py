"""
ORCHESTRATOR V3: Base Worker Adapter Interface
Standard-library only.
"""
from __future__ import annotations

import abc
import pathlib
from typing import Optional, Tuple

from orchestrator.contracts import WorkerRequest, WorkerResponse
from orchestrator.provider_manager import ProviderManager
from orchestrator.worker_registry import WorkerDefinition


class BaseWorkerAdapter(abc.ABC):
    def __init__(
        self,
        definition: WorkerDefinition,
        project_root: Optional[pathlib.Path] = None,
        provider_manager: Optional[ProviderManager] = None,
    ):
        self.definition = definition
        self.project_root = pathlib.Path(project_root or ".").resolve()
        self.provider_manager = provider_manager or ProviderManager()

    @abc.abstractmethod
    def is_available(self) -> Tuple[bool, str]:
        """Returns whether the worker is physically available to execute."""
        pass

    @abc.abstractmethod
    def invoke(self, request: WorkerRequest) -> WorkerResponse:
        """Executes the worker with the given request."""
        pass
