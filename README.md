# Scaleway provider for Pulser

Scaleway provider implementation to use neutral atoms based quantum computers.

**Pulser Scaleway** is a Python package to run quantum sequence on [Scaleway](https://www.scaleway.com/en/) infrastructure, providing access to [Pasqal](https://www.pasqal.com/) neutral atom quantum computers.

More info on the [Quantum service web page](https://www.scaleway.com/en/quantum-as-a-service/).

## Installation

We encourage installing Scaleway provider via the pip tool (a Python package manager):

```bash
pip install pulser-scaleway
```

## Getting started

To instantiate the `ScalewayProvider`, you need to have an access token and a project_id

```python
from pulser_scaleway import ScalewayProvider

qaas_connection = ScalewayProvider(
    project_id=os.environ["PULSER_SCALEWAY_PROJECT_ID"],
    secret_key=os.environ["PULSER_SCALEWAY_SECRET_KEY"],
)
```

Alternatively, the `ScalewayProvider` can discover your access token from environment variables:

```
export PULSER_SCALEWAY_PROJECT_ID="project_id"
export PULSER_SCALEWAY_SECRET_KEY="token"
```

Then you can instantiate the provider without any arguments:

```python
from pulser_scaleway import ScalewayProvider

qaas_connection = ScalewayProvider()
```

Now you have access to the supported backends and can design your pulse sequence. [See the technical documentation](https://docs.pasqal.com/cloud/first-job/) on how to write a sequence.


```python
# Retrieve all QPU devices (emulated or real)
devices = qaas_connection.fetch_available_devices()
fresnel_device = devices["pasqal_fresnel"]

# Create a register of trapped atoms before performing operation on them
register = Register.square(5, 5).with_automatic_layout(fresnel_device)

# Declare the sequence of pulses to perform on the register
sequence = Sequence(register, fresnel_device)
sequence.declare_channel("rydberg_global", "rydberg_global")
t = sequence.declare_variable("t", dtype=int)

amp_wf = BlackmanWaveform(t, np.pi)
det_wf = RampWaveform(t, -5, 5)
sequence.add(Pulse(amp_wf, det_wf, 0), "rydberg_global")

# Declare a backend based on the sequence and remote connection
backend = QPUBackend(sequence=sequence, connection=qaas_connection)

# Run jobs with different arguments over the same sequence and register
results = backend.run(
    job_params=[
        {"runs": 100, "variables": {"t": 1000}},
        {"runs": 20, "variables": {"t": 2000}},
    ],
    wait=True,
)

```

## Development
This repository is at its early stage and is still in active development. If you are looking for a way to contribute please read [CONTRIBUTING.md](CONTRIBUTING.md).

## Reach us
We love feedback. Feel free to reach us on [Scaleway Slack community](https://slack.scaleway.com/), we are waiting for you on [#opensource](https://scaleway-community.slack.com/app_redirect?channel=opensource).

## License
[License Apache 2.0](LICENSE)
