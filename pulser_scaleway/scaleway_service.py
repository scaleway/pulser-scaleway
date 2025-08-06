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
import typing
import httpx
import json
import time

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

# from pulser.backend.qpu import QPUBackend
from pulser.backend.results import Results
from pulser.devices import Device
from pulser.json.utils import make_json_compatible

from scaleway_qaas_client.v1alpha1 import QaaSClient, QaaSPlatform, QaaSJobResult


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

        self._client = QaaSClient(project_id=project_id, secret_key=secret_key, url=url)

    def submit(
        self,
        sequence: Sequence,
        wait: bool = False,
        batch_id: Optional[str] = None,
        **kwargs,
    ) -> RemoteResults:
        job_params = kwargs.get("job_params", [])

        # sequence = self.update_sequence_device(sequence)
        # QPUBackend.validate_job_params(job_params, sequence.device.max_runs)

        if batch_id:
            job_ids = self._create_jobs(
                session_id=batch_id,
                sequence=sequence,
                job_params=job_params,
            )
        else:
            platforms = self._client.list_platforms(name=sequence.device.name)

            if len(platforms) == 0:
                raise Exception(
                    f"no platform available with name {sequence.device.name}"
                )

            session = self._client.create_session(
                platform_id=platforms[0].id,
                name=f"pulser-{datetime.now():%Y-%m-%d-%H-%M-%S}",
            )

            batch_id = session.id

            job_ids = self._create_jobs(
                session_id=batch_id,
                sequence=sequence,
                job_params=job_params,
            )

            if wait:
                while any(
                    job.status in ["waiting", "running"]
                    for job in self._client.list_jobs(session_id=batch_id)
                ):
                    time.sleep(3)

        return RemoteResults(batch_id=batch_id, connection=self, job_ids=job_ids)

    def _create_jobs(
        self, session_id: str, sequence: Sequence, job_params: List[JobParams]
    ) -> List[str]:
        sequence = self._add_measurement_to_sequence(sequence)
        job_params = make_json_compatible(job_params)

        job_ids = []

        for params in job_params:
            if sequence.is_parametrized() or sequence.is_register_mappable():
                vars = params.get("variables", {})
                sequence.build(**vars)

            payload = {
                "sequence": sequence.to_abstract_repr(),
                "params": params,
            }
            job = self._client.create_job(session_id=session_id, payload=payload)
            job_ids.append(job.id)

        return job_ids

    def _get_data_from_job_result(self, job_result: QaaSJobResult) -> str:
        result = job_result.result

        if result is None or result == "":
            url = job_result.url

            if url is not None:
                resp = httpx.get(url.replace("http://s3", "http://localhost"))
                resp.raise_for_status()

                return resp.text
            else:
                raise Exception("Got result with empty data and url fields")
        else:
            return result

    def _get_result(self, job_id: str) -> Results:
        job_results = self._client.list_job_results(job_id=job_id)

        if job_results is None or len(job_results) == 0:
            return None

        job_result = self._get_data_from_job_result(job_results[0])

        return Results.from_abstract_repr(json.loads(job_result))

    def _fetch_result(
        self, batch_id: str, job_ids: List[str] | None
    ) -> typing.Sequence[Results]:
        """Fetches the results of a completed batch."""
        jobs = self._client.list_jobs(session_id=batch_id)

        jobs_results = [self._get_result(job.id) for job in jobs]

        return jobs_results

    def _query_job_progress(
        self, batch_id: str
    ) -> Mapping[str, Tuple[JobStatus, Results | None]]:
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
                    self._get_result(job.id)
                    if status_mapping.get(job.status, JobStatus.ERROR) == JobStatus.DONE
                    else None
                ),
            )
            for job in jobs
        }

        return job_progress

    def _get_batch_status(self, batch_id: str) -> BatchStatus:
        """Gets the status of a batch from its ID."""
        session = self._client.get_session(session_id=batch_id)

        status_mapping = {
            "starting": BatchStatus.PENDING,
            "running": BatchStatus.RUNNING,
            "stopping": BatchStatus.CANCELED,
            "stopped": BatchStatus.DONE,
        }

        return status_mapping.get(session.status, BatchStatus.ERROR)

    def _get_job_ids(self, batch_id: str) -> List[str]:
        """Gets all the job IDs within a batch."""
        jobs = self._client.list_jobs(session_id=batch_id)
        job_ids = [job.id for job in jobs]

        return job_ids

    def fetch_available_devices(self) -> Dict[str, Device]:
        """Fetches the devices available through this connection."""
        platforms = self._client.list_platforms(provider_name="pasqal")

        def _plt_to_device(plt: QaaSPlatform) -> Device:
            metadata = plt.metadata

            return Device(
                name=plt.name,
                max_runs=plt.max_shot_count,
                max_atom_num=plt.max_qubit_count,
                **metadata,
            )

        devices = {plt.name: _plt_to_device(plt) for plt in platforms}

        return devices

    def _close_batch(self, batch_id: str) -> None:
        """Closes a batch using its ID."""
        self._client.terminate_session(session_id=batch_id)

    def supports_open_batch(self) -> bool:
        """Flag to confirm this class can support creating an open batch."""
        return True
