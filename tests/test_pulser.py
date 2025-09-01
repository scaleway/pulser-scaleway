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

from pulser import Pulse, Register, Sequence, BlackmanWaveform, RampWaveform
from pulser.backends import QPUBackend
from pulser.devices import DigitalAnalogDevice, AnalogDevice

from pulser_scaleway import ScalewayQuantumService


def test_simple():
    qaas_connection = ScalewayQuantumService(
        project_id=os.environ["PULSER_SCALEWAY_PROJECT_ID"],
        secret_key=os.environ["PULSER_SCALEWAY_SECRET_KEY"],
        url=os.getenv("PULSER_SCALEWAY_API_URL"),
    )

    reg = Register({"q0": (-5, 0), "q1": (5, 0)})

    seq = Sequence(reg, AnalogDevice)
    seq.declare_channel("rydberg_global", "rydberg_global")
    t = seq.declare_variable("t", dtype=int)

    amp_wf = BlackmanWaveform(t, np.pi)
    det_wf = RampWaveform(t, -5, 5)
    seq.add(Pulse(amp_wf, det_wf, 0), "rydberg_global")

    backend = QPUBackend(sequence=seq.build(t=2000), connection=qaas_connection)

    results = backend.run(
        job_params=[
            {"runs": 100, "variables": {"t": 1000}},
            {"runs": 50, "variables": {"t": 2000}},
        ]
    )

    print(results)
