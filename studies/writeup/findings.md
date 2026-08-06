# Load Study Findings

> **Note:** Section stubs below are for the owner to complete after running the studies.
> Replace each stub with measured results and narrative analysis.

## Hardware & Setup

- GPUs: 2x 96 GB workstation GPU (96 GB GDDR7 each)
- Models: [BIG_MODEL] on GPU 1, [SMALL_MODEL] on GPU 0
- vLLM version: [VERSION]
- Stack: docker compose, gateway v0.1.0
- Clock lock: [CLOCK_FREQ] MHz on both GPUs

## Methodology

[Owner: describe warmup, repetitions, how GPU clocks were locked, open vs closed loop choice per study]

## Study 1: Saturation

[Owner: describe what happened as concurrency increased. Where did the system saturate — queue, compute, KV memory? Use vLLM metrics to explain.]

**Headline number:** p99 TTFT was Xms at Y concurrent sessions; system saturated at Z.

![saturation plot](saturation.png)

## Study 2: Session-Affinity

[Owner: compare multi-turn TTFT with affinity ON vs OFF. Explain the mechanism — prefix cache hit rate from vLLM /metrics.]

**Headline number:** affinity ON reduced median TTFT by X% on deep sessions (Y+ turns).

![affinity plot](affinity.png)

## Study 3: Routing Economics

[Owner: report % of requests routed to small tier, tokens saved, task pass-rate retained.]

**Headline number:** X% of requests served by the 7B model at Y% quality retention.

![routing economics plot](routing_economics.png)

## Study 4: Failure Drill

[Owner: describe what happened when you killed the big backend mid-run. Latency spike? Detection time? Recovery? Include dashboard screenshot.]

## Conclusions

[Owner: 3-5 bullet conclusions about the system behavior.]
