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
from __future__ import annotations

from typing import Any

from pulser import Sequence
from pulser.backend import Backend
from pulser.backend.remote import (
    JobParams,
    RemoteConnection,
    RemoteResults,
    _OpenBatchContextManager,
)


class RemoteBackend(Backend):
    """A backend for sequence execution through a remote connection.

    Args:
        sequence: A Sequence or a list of Sequences to execute on a
            backend accessible via a remote connection.
        connection: The remote connection through which the jobs
            are executed.
        mimic_qpu: Whether to mimic the validations necessary for
            execution on a QPU.
    """

    def __init__(
        self,
        name: str,
        sequence: Sequence,
        connection: RemoteConnection,
        mimic_qpu: bool = True,
    ) -> None:
        """Starts a new remote backend instance."""
        super().__init__(sequence, mimic_qpu=mimic_qpu)
        if not isinstance(connection, RemoteConnection):
            raise TypeError("'connection' must be a valid RemoteConnection instance.")
        self._connection = connection
        self._name = name
        self._batch_id: str | None = None

    def run(
        self, job_params: list[JobParams] | None = None, wait: bool = False
    ) -> RemoteResults:
        """Runs the sequence on the remote backend and returns the result.

        Args:
            job_params: A list of parameters for each job to execute. Each
                mapping must contain a defined 'runs' field specifying
                the number of times to run the same sequence. If the sequence
                is parametrized, the values for all the variables necessary
                to build the sequence must be given in it's own mapping, for
                each job, under the 'variables' field.
            wait: Whether to wait until the results of the jobs become
                available.  If set to False, the call is non-blocking and the
                obtained results' status can be checked using their `status`
                property.

        Returns:
            The results, which can be accessed once all sequences have been
            successfully executed.
        """
        return self._connection.submit(
            self._sequence,
            job_params=job_params,
            wait=wait,
            **self._submit_kwargs(),
        )

    def _submit_kwargs(self) -> dict[str, Any]:
        """Keyword arguments given to any call to RemoteConnection.submit()."""
        return dict(batch_id=self._batch_id, backend_name=self._name)

    @staticmethod
    def _type_check_job_params(job_params: list[JobParams] | None) -> None:
        if not isinstance(job_params, list):
            raise TypeError(
                f"'job_params' must be a list; got {type(job_params)} instead."
            )
        for d in job_params:
            if not isinstance(d, dict):
                raise TypeError(
                    "All elements of 'job_params' must be dictionaries; "
                    f"got {type(d)} instead."
                )

    def open_batch(self) -> _OpenBatchContextManager:
        """Creates an open batch within a context manager object."""
        if not self._connection.supports_open_batch():
            raise NotImplementedError(
                "Unable to execute open_batch using this remote connection"
            )
        return _OpenBatchContextManager(self)


class ScalewayBackend(RemoteBackend):
    """Backend for sequence execution on a QPU.

    Args:
        sequence: A Sequence or a list of Sequences to execute on a
            backend accessible via a remote connection.
        connection: The remote connection through which the jobs
            are executed.
    """

    def __init__(
        self, name: str, sequence: Sequence, connection: RemoteConnection
    ) -> None:
        """Starts a new QPU backend instance."""
        super().__init__(name, sequence, connection)

    def run(
        self, job_params: list[JobParams] | None = None, wait: bool = False
    ) -> RemoteResults:
        """Runs the sequence on the remote QPU and returns the result.

        Args:
            job_params: A list of parameters for each job to execute. Each
                mapping must contain a defined 'runs' field specifying
                the number of times to run the same sequence. If the sequence
                is parametrized, the values for all the variables necessary
                to build the sequence must be given in it's own mapping, for
                each job, under the 'variables' field.
            wait: Whether to wait until the results of the jobs become
                available.  If set to False, the call is non-blocking and the
                obtained results' status can be checked using their `status`
                property.

        Returns:
            The results, which can be accessed once all sequences have been
            successfully executed.
        """
        self.validate_job_params(job_params or [], self._sequence.device.max_runs)
        return super().run(job_params, wait)

    @staticmethod
    def validate_job_params(job_params: list[JobParams], max_runs: int | None) -> None:
        """Validates a list of job parameters prior to submission."""
        suffix = " when executing a sequence on a real QPU."
        if not job_params:
            raise ValueError("'job_params' must be specified" + suffix)
        RemoteBackend._type_check_job_params(job_params)
        for j in job_params:
            if "runs" not in j:
                raise ValueError(
                    "All elements of 'job_params' must specify 'runs'" + suffix
                )
            if max_runs is not None and j["runs"] > max_runs:
                raise ValueError(
                    "All 'runs' must be below the maximum allowed by the "
                    f"device ({max_runs})" + suffix
                )
