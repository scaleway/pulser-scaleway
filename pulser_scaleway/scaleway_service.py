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
import httpx
import json
import time

from functools import lru_cache
from typing import Optional, Mapping, List, Dict, Tuple
from datetime import datetime

from pulser import Sequence
from pulser.backend.remote import (
    BatchStatus,
    JobParams,
    JobStatus,
    RemoteConnection,
    RemoteResults,
)

from pulser.backend.config import EmulationConfig
from pulser.result import Result, SampledResult
from pulser.devices import Device
from pulser.json.utils import make_json_compatible
from pulser.json.abstract_repr.deserializer import deserialize_device

from scaleway_qaas_client.v1alpha1 import QaaSClient, QaaSPlatform, QaaSJobResult

_DEFAULT_PLATFORM_PROVIDER = "pasqal"
_DEFAULT_URL = "https://api.scaleway.com"
_DEFAULT_FETCH_INTERVAL = 2  # in second


class ScalewayProvider(RemoteConnection):
    """Sacleway Quantum as a Service connection bridge.

    :param project_id: optional UUID of the Scaleway Project, if the provided ``project_id`` is None, the value is loaded from the PULSER_SCALEWAY_PROJECT_ID environment variables

    :param secret_key: optional authentication token required to access the Scaleway API, if the provided ``secret_key`` is None, the value is loaded from the PULSER_SCALEWAY_SECRET_KEY environment variables

    :param url: optional value, endpoint URL of the API, if the provided ``url`` is None, the value is loaded from the PULSER_SCALEWAY_API_URL environment variables

    :param deduplication_id: optional value, if you created your QPU session from the Scaleway's console, console.scaleway.com/qaas, you can retrieve your session by providing the same deduplication_id
    """

    def __init__(
        self,
        project_id: Optional[str] = None,
        secret_key: Optional[str] = None,
        url: Optional[str] = None,
        deduplication_id: Optional[str] = None,
    ):
        secret_key = secret_key or os.getenv("PULSER_SCALEWAY_SECRET_KEY")
        project_id = project_id or os.getenv("PULSER_SCALEWAY_PROJECT_ID")
        url = url or os.getenv("PULSER_SCALEWAY_API_URL") or _DEFAULT_URL

        self._client = QaaSClient(project_id=project_id, secret_key=secret_key, url=url)
        self._session_deduplication_id = deduplication_id

    def submit(
        self,
        sequence: Sequence,
        wait: bool = False,
        open: bool = False,
        batch_id: Optional[str] = None,
        backend_configuration: Optional[EmulationConfig] = None,
        **kwargs,
    ) -> RemoteResults:
        job_params = kwargs.get("job_params", [])

        if batch_id:
            job_ids = self._create_jobs(
                session_id=batch_id,
                job_params=job_params,
            )
        else:
            device_name = sequence.device.name
            platforms = self._client.list_platforms(name=device_name)

            if len(platforms) == 0:
                raise Exception(f"no platform available with name {device_name}")

            sequence = self._add_measurement_to_sequence(sequence)

            if sequence.is_parametrized() or sequence.is_register_mappable():
                for params in job_params:
                    vars = params.get("variables", {})
                    sequence.build(**vars)

            backend_configuration_str = (
                backend_configuration.to_abstract_repr()
                if backend_configuration
                else None
            )

            model = self._client.create_model(
                payload={
                    "sequence": sequence.to_abstract_repr(),
                }
            )

            session = self._client.create_session(
                platform_id=platforms[0].id,
                name=f"qs-pulser-{datetime.now():%Y-%m-%d-%H-%M-%S}",
                model_id=model.id,
                max_duration="12h",
                max_idle_duration="10m",
                deduplication_id=self._session_deduplication_id,
                parameters={
                    "backend_configuration": backend_configuration_str,
                },
            )

            batch_id = session.id

            job_ids = self._create_jobs(
                session_id=batch_id,
                job_params=job_params,
            )

            if wait:
                while any(
                    job.status in ["waiting", "running"]
                    for job in self._client.list_jobs(session_id=batch_id)
                ) and self._client.get_session(session_id=batch_id).status in [
                    "starting",
                    "running",
                ]:
                    time.sleep(_DEFAULT_FETCH_INTERVAL)

                if not open:
                    self._close_batch(batch_id)

        return RemoteResults(batch_id=batch_id, connection=self, job_ids=job_ids)

    def _create_jobs(self, session_id: str, job_params: List[JobParams]) -> List[str]:
        job_params = make_json_compatible(job_params)
        job_ids = []

        for params in job_params:
            job = self._client.create_job(
                session_id=session_id, parameters=params, payload=None
            )
            job_ids.append(job.id)

        return job_ids

    def _get_job_result_data(self, job_result: QaaSJobResult) -> str:
        result = job_result.result

        if result is None or result == "":
            url = job_result.url

            if url is not None:
                return self._get_data(url)
            else:
                raise RuntimeError("Got result with empty data and url fields")
        else:
            return result

    @lru_cache
    def _get_batch_sequence(self, session_id: str) -> Sequence:
        session = self._client.get_session(session_id)
        model = self._client.get_model(session.model_id)

        model_data = self._get_data(model.url)
        sequence_str = json.loads(model_data).get("sequence")

        sequence = Sequence.from_abstract_repr(sequence_str)

        return sequence

    @lru_cache
    def _get_job_params(self, job_id: str) -> Dict:
        job = self._client.get_job(job_id)

        return json.loads(job.parameters) if job.parameters else {}

    def _get_data(self, url: str) -> str:
        resp = httpx.get(url=url)
        resp.raise_for_status()

        return resp.text

    def _get_result(self, job_id: str, session_id: str) -> SampledResult:
        job_results = self._client.list_job_results(job_id=job_id)

        if job_results is None or len(job_results) == 0:
            return None

        job_params = self._get_job_params(job_id)
        sequence = self._get_batch_sequence(session_id)
        job_result = self._get_job_result_data(job_results[0])

        reg = sequence.get_register(include_mappable=True)
        meas_basis = sequence.get_measurement_basis()
        all_qubit_ids = reg.qubit_ids

        size = None
        vars = job_params.get("variables")

        if vars and "qubits" in vars:
            size = len(vars["qubits"])

        return SampledResult(
            atom_order=all_qubit_ids[slice(size)],
            meas_basis=meas_basis,
            bitstring_counts=json.loads(job_result)["counter"],
        )

    def _fetch_result(self, batch_id: str, job_ids: List[str] | None) -> List[Result]:
        """Fetches the results of a completed batch."""
        jobs = self._client.list_jobs(session_id=batch_id)

        jobs_results = [self._get_result(job.id, batch_id) for job in jobs]

        return jobs_results

    def _query_job_progress(
        self, batch_id: str
    ) -> Mapping[str, Tuple[JobStatus, Result | None]]:
        """Fetches the status and results of all the jobs in a batch.

        Unlike `_fetch_result`, this method does not raise an error if some
        jobs in the batch do not have results.

        It returns a dictionary mapping the job ID to its status and results.
        """
        jobs = self._client.list_jobs(session_id=batch_id)

        status_mapping = {
            "waiting": JobStatus.PENDING,
            "running": JobStatus.RUNNING,
            "completed": JobStatus.DONE,
            "cancelled": JobStatus.CANCELED,
            "cancelling": JobStatus.CANCELED,
        }

        job_progress = {
            job.id: (
                status_mapping.get(job.status, JobStatus.ERROR),
                (
                    self._get_result(job.id, batch_id)
                    if status_mapping.get(job.status, JobStatus.ERROR) == JobStatus.DONE
                    else None
                ),
            )
            for job in jobs
        }

        return job_progress

    def _get_batch_status(self, batch_id: str) -> BatchStatus:
        """Gets the status of a batch from its ID."""
        jobs = self._client.list_jobs(session_id=batch_id)

        error_in_jobs = any(
            job.status in ["cancelled", "cancelling", "error"] for job in jobs
        )

        if error_in_jobs:
            return BatchStatus.ERROR

        session = self._client.get_session(session_id=batch_id)

        session_status_mapping = {
            "starting": BatchStatus.PENDING,
            "running": BatchStatus.RUNNING,
            "stopping": BatchStatus.DONE,
            "stopped": BatchStatus.DONE,
        }

        return session_status_mapping.get(session.status, BatchStatus.ERROR)

    def _get_job_ids(self, batch_id: str) -> List[str]:
        """Gets all the job IDs within a batch."""
        jobs = self._client.list_jobs(session_id=batch_id)
        job_ids = [job.id for job in jobs]

        return job_ids

    def fetch_available_devices(self) -> Dict[str, Device]:
        """Fetches the devices available through this connection."""
        platforms = self._client.list_platforms(
            provider_name=_DEFAULT_PLATFORM_PROVIDER
        )

        def _plt_to_device(plt: QaaSPlatform) -> Device:
            metadata = plt.metadata or "{}"

            if isinstance(metadata, str):
                metadata = json.loads(metadata) or {}

            specs = metadata.get("specs") or "{}"

            if isinstance(specs, str):
                specs = json.loads(specs) or {}

            if isinstance(specs, str):
                specs = json.loads(specs)
                specs["name"] = plt.name
                specs = json.dumps(specs)

            return deserialize_device(specs)

        devices = {plt.name: _plt_to_device(plt) for plt in platforms}

        return devices

    def _close_batch(self, batch_id: str) -> None:
        """Closes a batch using its ID."""
        self._client.terminate_session(session_id=batch_id)

    def supports_open_batch(self) -> bool:
        """Flag to confirm this class can support creating an open batch."""
        return True
