# AI Agent Immune System

The AI Agent Immune System is a control plane for autonomous AI agents that continuously monitors their behavior, detects anomalies, quarantines unhealthy agents, and heals them using policy-driven actions with optional human-in-the-loop approval for high-severity cases.

The system learns per-agent baselines, correlates anomalies into diagnoses, and maintains an immune memory so that failed healing actions are not repeated—improving stability and reducing operator load as the number of agents scales.

---

## Product Overview

### Problem

Autonomous AI agents (e.g. those backed by models like GPT-5 or Claude and tools exposed via MCP) can exhibit unhealthy behavior: prompt drift, token explosions, tool-call loops, latency spikes, or high retry rates. Without a structured response, such behavior can cascade, and manual intervention does not scale.

### Approach

The system treats agents as managed entities with an *immune system*:

- **Baseline learning:** Each agent’s normal behavior (tokens, latency, tool calls, retries) is learned from vitals (OTEL) so that anomalies are judged relative to that agent, not a single global threshold.
- **Anomaly detection:** A sentinel compares recent vitals to the baseline and flags infections with a severity score (0–10). Multiple anomaly types are supported (token spike, latency spike, tool explosion, high retry rate).
- **Containment:** Infected agents are quarantined immediately so they no longer affect the rest of the system.
- **Human-in-the-loop for severe cases:** Infections above a configurable severity threshold require explicit Approve or Reject in the web dashboard before healing runs. Rejected agents remain quarantined until an operator chooses “Heal now” (per agent or “Heal all”).
- **Policy-driven healing:** For each diagnosis type (e.g. prompt drift, infinite loop, tool instability), a fixed *healing policy* defines an ordered list of actions (e.g. reset memory, rollback prompt, reduce autonomy, clone agent). The healer tries actions in order; immune memory records successes and failures and skips actions that have already failed for that agent and diagnosis.
- **Adaptive learning:** Immune memory is used across the fleet so the system converges toward actions that work and avoids repeating known failures.

The web dashboard provides a single pane of glass: agent status (with model and MCP labels), pending and rejected approvals, bulk actions (Approve all, Reject all, Heal all), recent healing actions, and learned patterns.

---

## Use Cases in Real Environments

The AI Agent Immune System is designed for environments where many autonomous or agentic AI workloads run on shared infrastructure. Operators need to detect misbehavior early, contain impact, and restore agents without scaling manual intervention linearly with fleet size.

### Example: Cisco AI PODs and agentic AI

**Cisco AI PODs** are pre-validated, modular AI infrastructure (Cisco UCS compute, Nexus networking, NVIDIA AI Enterprise, Red Hat OpenShift, Intersight, and partners) used for the full AI lifecycle: training, fine-tuning, RAG pipelines, and **inference at scale**. Cisco’s Secure AI Factory and related solutions explicitly target **agentic AI**—intelligent agents that automate tasks and interact autonomously with tools and data.

In such a setting, customers may run:

- **Inference agents** serving different models or use cases (e.g. support, analytics, code, networking).
- **Agentic workflows** that call tools (APIs, MCP servers, databases) and can drift, loop, or spike in tokens/latency.
- **RAG and retrieval agents** with distinct baselines for token and tool usage.

**How the immune system helps customers on Cisco AI PODs (and similar platforms):**

| Customer need | How the immune system addresses it |
|---------------|-------------------------------------|
| **Stability at scale** | Per-agent baselines and anomaly detection catch misbehavior (prompt drift, tool loops, latency spikes) before it affects more users or downstream systems. Quarantine limits blast radius. |
| **Controlled remediation** | Severe anomalies require approval before healing, so operators can review diagnosis and decide when to auto-heal vs. investigate or reject. Rejected agents stay quarantined until an explicit “Heal now,” avoiding unwanted automatic actions. |
| **Reduced toil** | Immune memory learns which actions work for which diagnosis types and avoids repeating failed cures. As the fleet grows, healing success rate improves and repeat manual fixes decrease. |
| **Single pane of glass** | The dashboard shows all agents (with model/MCP context), pending and rejected approvals, and healing history. Approve all / Reject all / Heal all support bulk operations during incidents. |
| **Safe rollout of agentic AI** | New agent types or MCP integrations can be monitored with learned baselines; human-in-the-loop for high severity keeps critical decisions under operator control while mild cases are healed automatically. |

This pattern applies beyond Cisco AI PODs: any deployment (on-prem, hybrid, or cloud) that runs multiple autonomous AI agents—whether on Kubernetes, OpenShift, or dedicated inference stacks—can use the immune system as an operational control plane for detection, containment, approval, and healing.

---

## High-Level Architecture

### System overview

High-level view: agents emit telemetry into the immune system, which detects, diagnoses, contains, and recovers, with learning over time.

```
┌─────────────────────────────────────────────────────────────┐
│                      AGENT RUNTIME                           │
│  15+ AI Agents executing tasks, emitting telemetry           │
└─────────────────────────────────────────────────────────────┘
                            ↓ vitals (OTEL)
┌─────────────────────────────────────────────────────────────┐
│                    IMMUNE SYSTEM                             │
│                                                              │
│  ┌─────────────┐   ┌──────────────┐   ┌────────────────┐   │
│  │  Sentinel   │   │ Diagnostician│   │    Healer      │   │
│  │  (Detect)   │ → │  (Diagnose)  │ → │   (Recover)    │   │
│  └─────────────┘   └──────────────┘   └────────────────┘   │
│         ↓                                      ↓             │
│  ┌─────────────────┐              ┌──────────────────────┐ │
│  │   Quarantine    │              │   Immune Memory       │ │
│  │   (Contain)     │              │   (Learn)              │ │
│  └─────────────────┘              └──────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Component architecture

This view shows the main components and how they connect (logical architecture).

```
Agent runtime (telemetry) ── vitals (OTEL) ──► Sentinel (detect) ──► Diagnostician (diagnose)
                                                │
                                                ▼
                                    Quarantine ◄── Severity check
                                                │
                                                ▼
                                    Pending approval (severe)  or  auto-heal (mild)
                                                │
                                                ▼
                                    Healer (policy ladder) + Immune memory (learning)
```

### Data flow

This view shows how data and control flow through the system (data flow diagram).

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           AI AGENT IMMUNE SYSTEM                                  │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │ AGENT RUNTIME                                                             │   │
│  │ • N agents (e.g. VPN, Docker, Slack, Postgres, Network, …)                │   │
│  │ • Each runs on a 1s tick; executes, emits vitals (OTEL): latency, tokens, │   │
│  │   tool_calls, retries                                                     │   │
│  │ • Quarantined agents skip execution until released                        │   │
│  └──────────────────────────────────────────────────────────────────────────┘   │
│                                        │                                         │
│                                        ▼ vitals (OTEL)                            │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │ TELEMETRY + BASELINE                                                       │   │
│  │ • TelemetryCollector: stores recent vitals (OTEL) per agent               │   │
│  │ • BaselineLearner: after enough samples, computes mean/std per metric     │   │
│  │   per agent (no baseline → no infection detection for that agent)         │   │
│  └──────────────────────────────────────────────────────────────────────────┘   │
│                                        │                                         │
│                                        ▼                                         │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │ SENTINEL (detection loop, 1s)                                             │   │
│  │ • For each non-quarantined agent with a baseline:                         │   │
│  │   - Fetch recent vitals (OTEL) (e.g. last 10s window)                      │   │
│  │   - Compare to baseline (deviation in std-devs) → anomalies + severity    │   │
│  │ • If infection: quarantine agent, then branch by severity                  │   │
│  └──────────────────────────────────────────────────────────────────────────┘   │
│                                        │                                         │
│                    ┌───────────────────┴───────────────────┐                     │
│                    ▼                                       ▼                     │
│  ┌─────────────────────────────┐         ┌─────────────────────────────────┐   │
│  │ SEVERE (≥ threshold)        │         │ MILD (< threshold)                 │   │
│  │ • Diagnostician: diagnosis   │         │ • Diagnostician: diagnosis        │   │
│  │ • Add to PENDING_APPROVALS   │         │ • Healer: auto-heal (policy +     │   │
│  │ • Wait for user Approve/     │         │   immune memory), then release   │   │
│  │   Reject in dashboard        │         │   or escalate                    │   │
│  │ • If Reject → REJECTED_      │         │                                  │   │
│  │   APPROVALS (until Heal now) │         │                                  │   │
│  └─────────────────────────────┘         └─────────────────────────────────┘   │
│                    │                                       │                     │
│                    │ (on Approve / Heal now)               │                     │
│                    └───────────────────┬───────────────────┘                     │
│                                        ▼                                         │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │ HEALER + IMMUNE MEMORY                                                    │   │
│  │ • Diagnose → policy ladder for that diagnosis type                       │   │
│  │ • Immune memory: exclude actions that failed before for this agent+       │   │
│  │   diagnosis                                                               │   │
│  │ • Apply next allowed action; if success → release; if fail → escalate   │   │
│  │ • Record outcome in immune memory                                         │   │
│  └──────────────────────────────────────────────────────────────────────────┘   │
│                                        │                                         │
│  ┌─────────────────────────────────────┴─────────────────────────────────────┐   │
│  │ WEB DASHBOARD (Flask, port 8090)                                           │   │
│  │ • Reads: agents, pending/rejected lists, healing log, stats, patterns      │   │
│  │ • Writes: Approve/Reject (single or all), Heal now (single or all)         │   │
│  │ • Approve/Heal now → schedule heal_agent on orchestrator’s event loop     │   │
│  └──────────────────────────────────────────────────────────────────────────┘   │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Coordination Between Components

### Concurrency model

- **Orchestrator** runs one asyncio event loop. It starts three concurrent logical flows:
  1. **Agent loops:** One async task per agent (`run_agent_loop(agent)`). Each task runs on a 1s tick: if the agent is not quarantined, it calls `agent.execute()`, records vitals (OTEL) with `TelemetryCollector`, and optionally triggers baseline learning when enough samples exist. If quarantined, the task sleeps for the tick interval and skips execution.
  2. **Sentinel loop:** One async task that, after an initial delay (to allow baselines to be learned), runs every 1s. It iterates over all agents, skips quarantined and no-baseline agents, and for the rest gets recent telemetry and runs `Sentinel.detect_infection(recent, baseline)`. If an infection is found, it quarantines the agent and either adds it to pending approvals (severe) or spawns a healing task (mild).
  3. **Chaos schedule (optional):** Injects failures into agents at fixed times for demos.

- **Web dashboard** runs in a separate thread (Flask). It holds a reference to the orchestrator’s event loop. When the user Approves or chooses Heal now, the dashboard calls orchestrator methods (e.g. `approve_healing`, `start_healing_explicitly`) and, when healing must run, schedules `heal_agent(...)` on the main loop via `asyncio.run_coroutine_threadsafe(...)` so that healing runs in the same process as the agent and sentinel tasks, without blocking the HTTP server.

### Data flow

- **Telemetry:** Agent loops push vitals (OTEL) into `TelemetryCollector` (per-agent time-series). Baseline learner consumes these to compute mean/std per metric per agent. Sentinel and healer read from telemetry and baseline for detection and diagnosis.
- **Quarantine:** `QuarantineController` holds the set of quarantined agent IDs. Agent loops check it to skip execution; sentinel skips quarantined agents for re-detection; healing releases from quarantine on success.
- **Pending / rejected state:** Severe infections are stored in `_pending_approvals` (agent_id → infection, diagnosis). Dashboard reads this for the “Pending approvals” list. On Approve, the entry is removed and `heal_agent` is scheduled. On Reject, the entry is moved to `_rejected_approvals` and the agent stays quarantined. “Heal now” (single or all) removes from `_rejected_approvals` and schedules `heal_agent` for each. Sentinel does not re-add an agent to pending if it is already in `_rejected_approvals`.
- **Healing:** `heal_agent(agent_id, infection, trigger)` is async: it diagnoses, loads the policy for that diagnosis type, filters by immune memory (skip previously failed actions for this agent+diagnosis), applies the next action, records the result in immune memory, and either releases the agent (success) or escalates to the next action (failure). All of this runs on the main asyncio loop; the dashboard only triggers it.

### Timing and alignment

- Agent tick and sentinel tick are both 1s (`TICK_INTERVAL_SECONDS`). The dashboard polls the backend every 1s. This keeps UI state aligned with backend state (e.g. “healing in progress” and runtime stats).
- Healing steps use a short delay (`HEALING_STEP_DELAY_SECONDS`) so that “healing in progress” is visible in the UI before the next action.

### Thread safety

- `_pending_approvals`, `_rejected_approvals`, and the healing action log are accessed from both the asyncio thread and the Flask thread. Access is protected by a shared lock so that dashboard actions (approve, reject, heal now) and sentinel updates (adding to pending) do not race.

---

## Components (Reference)

| Component        | File              | Responsibility |
|-----------------|-------------------|----------------|
| Agent runtime   | `agents.py`       | Multiple agent types (Research, Data, Analytics, Coordinator); each executes on a tick and returns vitals (OTEL); supports infection simulation and model/MCP-style labels for the UI. |
| Telemetry       | `telemetry.py`    | Stores vitals (OTEL) per agent; provides recent window and counts for baseline and sentinel. |
| Baseline        | `baseline.py`     | Learns mean and standard deviation per metric per agent after a minimum sample count. |
| Sentinel        | `detection.py`    | Compares recent vitals (OTEL) to baseline; emits infection report with anomaly types and severity (0–10). |
| Diagnostician   | `diagnosis.py`    | Maps anomaly patterns to diagnosis types (e.g. prompt drift, infinite loop, tool instability). |
| Healer          | `healing.py`      | Holds healing policies (diagnosis → ordered actions); applies actions; consults immune memory to skip failed actions. |
| Immune memory   | `memory.py`       | Records per-agent, per-diagnosis healing outcomes; exposes failed actions and success-rate summaries. |
| Quarantine      | `quarantine.py`   | Tracks quarantined agent IDs; quarantine/release used by orchestrator and agent loop. |
| Chaos           | `chaos.py`        | Injects token/tool/latency/retry-style failures for demos. |
| Orchestrator    | `orchestrator.py` | Holds all of the above; runs agent loops, sentinel loop, and chaos schedule; implements approve/reject/heal-now and approve-all/reject-all/heal-all; exposes state and actions for the dashboard. |
| Web dashboard   | `web_dashboard.py`| Flask app; serves UI and REST endpoints for status, agents, pending/rejected, healing log, stats; triggers healing on the orchestrator’s event loop. |
| Entry point     | `main.py`         | Creates agent pool and orchestrator; starts dashboard with loop reference; runs orchestrator for a configurable duration. |

---

## Setup and Run

```bash
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Then open **http://localhost:8090** in a browser. The dashboard refreshes every second.

---

## Dashboard

- **Stats:** Total AI agents, executions, infections detected, healed count, success rate, runtime (wall-clock).
- **Pending approvals:** Severe infections awaiting a decision. Per-item Approve/Reject (✓/✗ with tooltips) or **Approve all** / **Reject all**.
- **Rejected healings:** Agents that were rejected; **Heal now** per item or **Heal all**.
- **AI Agent Status Grid:** One card per agent (name, model, MCP servers, status). For pending agents: Approve/Reject on the card. For rejected: Heal now on the card.
- **Recent Healing Actions:** Timeline of approval requests, user approvals/rejections, Heal now, and healing attempts (with trigger: auto-healed, after approval, or Heal now).
- **Learned Healing Patterns:** Which diagnosis types responded best to which actions.

Sections are collapsible. All data is read from the orchestrator and refreshed every 1s.

---

## Behavior Summary

- **Severity:** Derived from deviation of recent vitals from baseline (compressed into 0–10). Higher severity means a larger anomaly.
- **Severe infections:** When severity is at or above a configurable threshold, the agent is quarantined and added to **pending approvals**. Healing does not start until a user Approves (or Approve all) in the dashboard.
- **Rejected:** If the user Rejects, the agent remains quarantined and is listed under **Rejected healings**. Healing can be started later via **Heal now** (single or Heal all).
- **Auto-heal:** When severity is below the threshold, the orchestrator starts healing immediately using the diagnosis, policy ladder, and immune memory.
- **Healing policy:** Each diagnosis type has an ordered list of actions (e.g. reset memory, rollback prompt, reduce autonomy, clone agent). Immune memory skips actions that have already failed for that agent and diagnosis; the healer escalates to the next until success or exhaustion.

---

## Requirements

- Python 3.8+
- Dependencies: `flask`, `flask-cors` (see `requirements.txt`)

---

## License

See `LICENSE` in the repository.
