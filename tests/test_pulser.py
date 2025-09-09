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
import numpy as np

from pulser import Pulse, Sequence, BlackmanWaveform, RampWaveform
from pulser.backend.remote import BatchStatus
from pulser.register import Register
from pulser.devices import AnalogDevice

from pulser_scaleway import ScalewayQuantumService, ScalewayBackend


def test_simple():
    qaas_connection = ScalewayQuantumService(
        project_id=os.environ["PULSER_SCALEWAY_PROJECT_ID"],
        secret_key=os.environ["PULSER_SCALEWAY_SECRET_KEY"],
        url=os.getenv("PULSER_SCALEWAY_API_URL"),
    )

    real = False

    if real:
        # Real device
        devices = qaas_connection.fetch_available_devices()
        fresnel_device = devices["pasqal_fresnel"]
        register = Register.square(5, 5).with_automatic_layout(fresnel_device)
        seq = Sequence(register, fresnel_device)
    else:
        # Fake device
        register = AnalogDevice.pre_calibrated_layouts[0].hexagonal_register(12)
        seq = Sequence(register, AnalogDevice)

    seq.declare_channel("rydberg", "rydberg_global")
    t = seq.declare_variable("t", dtype=int)

    amp_wf = BlackmanWaveform(t, np.pi)
    det_wf = RampWaveform(t, -5, 5)
    seq.add(Pulse(amp_wf, det_wf, 0), "rydberg")

    backend = ScalewayBackend(
        name="pasqal_fresnel", sequence=seq, connection=qaas_connection
    )

    results = backend.run(
        job_params=[
            {"runs": 100, "variables": {"t": 1000}},
            {"runs": 20, "variables": {"t": 2000}},
        ],
        wait=True,
    )

    assert len(results.results) == 2
    assert results.get_batch_status() == BatchStatus.DONE
