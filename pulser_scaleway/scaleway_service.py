# Copyright 2025 Scaleway
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.from typing import Optional, List, Dict
import os

from typing import Optional, Any, Mapping, Type, TypedDict

from pulser import Sequence
from pulser.backend.config import EmulatorConfig
from pulser.backend.qpu import QPUBackend
from pulser.backend.remote import (
    BatchStatus,
    JobParams,
    JobStatus,
    RemoteConnection,
    RemoteResults,
    RemoteResultsError,
)
from pulser.json.utils import make_json_compatible
from pulser.backend.abc import Backend
from pulser.backend.results import Results, ResultsSequence
from pulser.devices import Device

from scaleway_qaas_client.v1alpha1 import QaaSClient, QaaSPlatform


class ScalewayQuantumService(RemoteConnection):
    def __init__(
        self,
        project_id: Optional[str] = None,
        secret_key: Optional[str] = None,
        url: Optional[str] = None,
    ):
        secret_key = secret_key or os.getenv("PULSER_SCALEWAY_SECRET_KEY")
        project_id = project_id or os.getenv("PULSER_SCALEWAY_PROJECT_ID")
        url = url or os.getenv("PULSER_SCALEWAY_API_URL")

        pass

    def submit(
        self,
        sequence: Sequence,
        wait: bool = False,
        open: bool = False,
        batch_id: str | None = None,
        **kwargs: Any,
    ) -> RemoteResults:

        sequence = self._add_measurement_to_sequence(sequence)
        emulator = kwargs.get("emulator", None)
        job_params: list[JobParams] = make_json_compatible(kwargs.get("job_params", []))

        if sequence.is_parametrized() or sequence.is_register_mappable():
            for params in job_params:
                vars = params.get("variables", {})
                sequence.build(**vars)

        configuration = self._convert_configuration(
            config=kwargs.get("config", None),
            emulator=emulator,
            strict_validation=False,
        )

        payload = sequence.to_abstract_repr()

    def _fetch_result(
        self, batch_id: str, job_ids: list[str] | None
    ) -> Sequence[Results]:
        """Fetches the results of a completed batch."""
        pass

    def _query_job_progress(
        self, batch_id: str
    ) -> Mapping[str, tuple[JobStatus, Results | None]]:
        """Fetches the status and results of all the jobs in a batch.

        Unlike `_fetch_result`, this method does not raise an error if some
        jobs in the batch do not have results.

        It returns a dictionary mapping the job ID to its status and results.
        """
        pass

    def _get_batch_status(self, batch_id: str) -> BatchStatus:
        """Gets the status of a batch from its ID."""
        pass

    def _get_job_ids(self, batch_id: str) -> list[str]:
        """Gets all the job IDs within a batch."""
        return None

    def fetch_available_devices(self) -> dict[str, Device]:
        """Fetches the devices available through this connection."""
        devices = {}
        return devices

    def _close_batch(self, batch_id: str) -> None:
        """Closes a batch using its ID."""
        return None

    def supports_open_batch(self) -> bool:
        """Flag to confirm this class can support creating an open batch."""
        return True
