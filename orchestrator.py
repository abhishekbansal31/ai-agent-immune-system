"""
Orchestrator - Main control loop coordinating all components
"""
import asyncio
import threading
from typing import List, Dict, Any, Optional, Tuple
import time

from agents import BaseAgent
from detection import InfectionReport
from telemetry import TelemetryCollector
from baseline import BaselineLearner
from detection import Sentinel
from diagnosis import Diagnostician
from healing import Healer
from memory import ImmuneMemory
from quarantine import QuarantineController
from chaos import ChaosInjector
from logging_config import get_logger

logger = get_logger("orchestrator")


# Backend tick interval (seconds) - aligned with UI poll interval in web_dashboard.py
TICK_INTERVAL_SECONDS = 1.0

# Severe infections (severity >= this) require UI approval before healing
# Lower value = more infections show as severe in the UI (severity scale 0-10)
SEVERITY_REQUIRING_APPROVAL = 7.0

# Delay between healing steps so UI can show "healing in progress"
HEALING_STEP_DELAY_SECONDS = 1.5

# Max time to wait for all quarantined agents to be healed before shutdown
DRAIN_TIMEOUT_SECONDS = 120


class ImmuneSystemOrchestrator:
    """Coordinates all immune system components"""
    
    def __init__(self, agents: List[BaseAgent]):
        self.agents = {agent.agent_id: agent for agent in agents}
        
        # Initialize components
        self.telemetry = TelemetryCollector()
        self.baseline_learner = BaselineLearner(min_samples=15)
        self.sentinel = Sentinel(threshold_stddev=2.5)
        self.diagnostician = Diagnostician()
        self.quarantine = QuarantineController()
        self.immune_memory = ImmuneMemory()
        self.healer = Healer(self.telemetry, self.baseline_learner, self.sentinel)
        self.chaos = ChaosInjector()
        
        # Statistics
        self.total_infections = 0
        self.total_healed = 0
        self.total_failed_healings = 0
        self.start_time = time.time()
        
        # State
        self.running = True
        self.baselines_learned = False

        # Severe infections awaiting UI approval (agent_id -> {infection, diagnosis, requested_at})
        self._pending_approvals: Dict[str, Dict[str, Any]] = {}
        # Rejected approvals: agent stays quarantined until user clicks "Heal now"
        self._rejected_approvals: Dict[str, Dict[str, Any]] = {}
        self._pending_lock = threading.Lock()

        # Agents currently in heal_agent() for UI "healing in progress" display
        self.healing_in_progress: set = set()

        # Unified log of user/system healing actions for "Recent Healing Actions" UI
        self._healing_action_log: List[Dict[str, Any]] = []
        self._action_log_max = 80
        self._action_log_lock = threading.Lock()

    def _log_action(self, action_type: str, agent_id: str, **kwargs):
        """Append a healing action for the UI (thread-safe)."""
        entry = {'type': action_type, 'agent_id': agent_id, 'timestamp': time.time(), **kwargs}
        with self._action_log_lock:
            self._healing_action_log.append(entry)
            if len(self._healing_action_log) > self._action_log_max:
                self._healing_action_log = self._healing_action_log[-self._action_log_max:]

    def get_healing_actions(self) -> List[Dict[str, Any]]:
        """Return recent healing actions (user + system) for UI (thread-safe)."""
        with self._action_log_lock:
            return list(self._healing_action_log[-50:])
    
    async def run_agent_loop(self, agent: BaseAgent):
        """Continuously run an agent and emit telemetry on a 1s tick (synced with UI poll)."""
        while self.running:
            tick_start = time.time()
            # Skip if quarantined
            if self.quarantine.is_quarantined(agent.agent_id):
                await asyncio.sleep(TICK_INTERVAL_SECONDS)
                continue

            # Execute and record telemetry
            vitals = await agent.execute()
            self.telemetry.record(vitals)

            # Check if baseline ready to learn
            count = self.telemetry.get_count(agent.agent_id)
            if self.baseline_learner.is_baseline_ready(agent.agent_id, count):
                all_vitals = self.telemetry.get_all(agent.agent_id)
                baseline = self.baseline_learner.learn_baseline(agent.agent_id, all_vitals)
                if baseline:
                    logger.info("Baseline learned for %s: %s", agent.agent_id, baseline)

            # Align to 1s tick so UI (polling every 1s) sees consistent backend state
            elapsed = time.time() - tick_start
            await asyncio.sleep(max(0.0, TICK_INTERVAL_SECONDS - elapsed))
    
    async def sentinel_loop(self):
        """Continuously monitor for infections"""
        await asyncio.sleep(15)  # Wait for baselines to be learned
        
        logger.info("SENTINEL ACTIVE - Monitoring for infections")
        self.baselines_learned = True
        
        while self.running:
            # Check each agent
            for agent_id, agent in self.agents.items():
                # Skip if already quarantined
                if self.quarantine.is_quarantined(agent_id):
                    continue
                
                # Skip if no baseline yet
                if not self.baseline_learner.has_baseline(agent_id):
                    continue
                
                # Get recent telemetry
                recent = self.telemetry.get_recent(agent_id, window_seconds=10)
                if not recent:
                    continue
                
                # Check for infection
                baseline = self.baseline_learner.get_baseline(agent_id)
                infection = self.sentinel.detect_infection(recent, baseline)
                
                if infection:
                    # Skip if user previously rejected healing — wait for "Heal now"
                    with self._pending_lock:
                        if agent_id in self._rejected_approvals:
                            continue

                    self.total_infections += 1

                    anomaly_names = ", ".join(a.value for a in infection.anomalies)
                    logger.warning(
                        "INFECTION DETECTED: %s | severity=%.1f/10 | anomalies=[%s]",
                        agent_id, infection.severity, anomaly_names,
                    )

                    # Quarantine immediately
                    self.quarantine.quarantine(agent_id)
                    agent.quarantine()
                    logger.warning("Agent %s QUARANTINED", agent_id)

                    # Severe infections require UI approval before healing
                    if infection.severity >= SEVERITY_REQUIRING_APPROVAL:
                        diagnosis = self.diagnostician.diagnose(infection, baseline)
                        with self._pending_lock:
                            self._pending_approvals[agent_id] = {
                                'infection': infection,
                                'diagnosis': diagnosis,
                                'requested_at': time.time()
                            }
                        self._log_action("approval_requested", agent_id, severity=round(infection.severity, 1))
                        logger.info(
                            "Agent %s requires approval (severity %.1f) - use dashboard to Approve/Reject",
                            agent_id, infection.severity,
                        )
                    else:
                        # Auto-heal for non-severe
                        asyncio.create_task(self.heal_agent(agent_id, infection))

            # Run sentinel every 1s to stay in sync with UI poll interval
            await asyncio.sleep(TICK_INTERVAL_SECONDS)
    
    def get_pending_approvals(self) -> List[Dict[str, Any]]:
        """Return list of severe infections awaiting UI approval (thread-safe)."""
        with self._pending_lock:
            out = []
            for agent_id, data in self._pending_approvals.items():
                inf = data['infection']
                diag = data['diagnosis']
                out.append({
                    'agent_id': agent_id,
                    'severity': round(inf.severity, 1),
                    'anomalies': [a.value for a in inf.anomalies],
                    'diagnosis_type': diag.diagnosis_type.value,
                    'reasoning': diag.reasoning,
                    'requested_at': data['requested_at'],
                })
            return out

    def approve_healing(self, agent_id: str, approved: bool) -> Tuple[Optional[InfectionReport], bool]:
        """
        Approve or reject healing for a severe infection (thread-safe).
        Returns (infection, approved). If approved, caller should schedule heal_agent(agent_id, infection).
        If rejected, agent stays quarantined until user clicks "Heal now".
        """
        with self._pending_lock:
            entry = self._pending_approvals.pop(agent_id, None)
        if not entry:
            return None, False
        infection = entry['infection']
        diagnosis = entry['diagnosis']
        if approved:
            self._log_action("user_approved", agent_id)
            return infection, True
        # Reject: keep quarantined, store so we don't re-prompt until user clicks Retry healing
        self._log_action("user_rejected", agent_id)
        with self._pending_lock:
            self._rejected_approvals[agent_id] = {
                'infection': infection,
                'diagnosis': diagnosis,
                'rejected_at': time.time(),
            }
        logger.warning("Healing rejected for %s - quarantined until 'Heal now' in the dashboard", agent_id)
        return None, False

    def approve_all_pending(self, approved: bool) -> List[Tuple[str, InfectionReport]]:
        """
        Approve or reject all pending approvals (thread-safe).
        Returns list of (agent_id, infection) for approved ones so caller can schedule heal_agent for each.
        """
        with self._pending_lock:
            agent_ids = list(self._pending_approvals.keys())
        approved_list = []
        for agent_id in agent_ids:
            infection, did_approve = self.approve_healing(agent_id, approved)
            if did_approve and infection:
                approved_list.append((agent_id, infection))
        return approved_list

    def get_rejected_approvals(self) -> List[Dict[str, Any]]:
        """Return list of agents whose healing was rejected (thread-safe)."""
        with self._pending_lock:
            out = []
            for agent_id, data in self._rejected_approvals.items():
                inf = data['infection']
                diag = data['diagnosis']
                out.append({
                    'agent_id': agent_id,
                    'severity': round(inf.severity, 1),
                    'anomalies': [a.value for a in inf.anomalies],
                    'diagnosis_type': diag.diagnosis_type.value,
                    'reasoning': diag.reasoning,
                    'rejected_at': data['rejected_at'],
                })
            return out

    def start_healing_explicitly(self, agent_id: str) -> Optional[InfectionReport]:
        """
        Start healing directly for an agent that had healing rejected (thread-safe).
        Removes from rejected and returns the stored infection so caller can schedule heal_agent.
        Returns None if agent was not in rejected_approvals.
        """
        with self._pending_lock:
            entry = self._rejected_approvals.pop(agent_id, None)
        if not entry:
            return None
        infection = entry['infection']
        self._log_action("explicit_heal_requested", agent_id)
        logger.info("Agent %s - healing started (Heal now)", agent_id)
        return infection

    def start_healing_all_rejected(self) -> List[Tuple[str, InfectionReport]]:
        """
        Start healing for all rejected agents (thread-safe).
        Removes all from rejected and returns list of (agent_id, infection) so caller can schedule heal_agent for each.
        """
        with self._pending_lock:
            agent_ids = list(self._rejected_approvals.keys())
        result = []
        for agent_id in agent_ids:
            infection = self.start_healing_explicitly(agent_id)
            if infection:
                result.append((agent_id, infection))
        return result

    async def heal_agent(self, agent_id: str, infection: InfectionReport, trigger: str = "auto"):
        """Heal an infected agent (with visible delays so UI can show progress)."""
        self.healing_in_progress.add(agent_id)
        try:
            agent = self.agents[agent_id]

            # Diagnose
            baseline = self.baseline_learner.get_baseline(agent_id)
            diagnosis = self.diagnostician.diagnose(infection, baseline)

            logger.info(
                "Diagnosis for %s: %s (confidence: %.0f%%) - %s",
                agent_id, diagnosis.diagnosis_type.value, diagnosis.confidence * 100, diagnosis.reasoning,
            )

            await asyncio.sleep(HEALING_STEP_DELAY_SECONDS)  # So UI shows "healing in progress"

            # Get healing policy
            policy = self.healer.get_healing_policy(diagnosis.diagnosis_type)
            policy_str = " -> ".join(a.value for a in policy)
            logger.info("Healing policy for %s: [%s]", agent_id, policy_str)

            # Get failed actions from immune memory
            failed_actions = self.immune_memory.get_failed_actions(agent_id, diagnosis.diagnosis_type)

            if failed_actions:
                failed_str = ", ".join(a.value for a in failed_actions)
                logger.info("Immune memory for %s: skipping previously failed actions: %s", agent_id, failed_str)

            await asyncio.sleep(HEALING_STEP_DELAY_SECONDS)

            # Get next action to try
            next_action = self.healer.get_next_action(diagnosis.diagnosis_type, failed_actions)

            if not next_action:
                logger.error("All healing actions exhausted for %s", agent_id)
                self.quarantine.release(agent_id)
                agent.release()
                return

            logger.info("Attempting healing on %s: %s", agent_id, next_action.value)

            result = await self.healer.apply_healing(agent, next_action)

            # Record in immune memory
            self.immune_memory.record_healing(
                agent_id=agent_id,
                diagnosis_type=diagnosis.diagnosis_type,
                healing_action=next_action,
                success=result.validation_passed
            )
            self._log_action(
                "healing_attempt", agent_id,
                diagnosis_type=diagnosis.diagnosis_type.value,
                action=next_action.value,
                success=result.validation_passed,
                trigger=trigger
            )

            if result.validation_passed:
                logger.info("HEALING SUCCESS for %s: %s - released from quarantine", agent_id, result.message)
                self.quarantine.release(agent_id)
                agent.release()
                self.total_healed += 1
            else:
                logger.warning("HEALING FAILED for %s: %s", agent_id, result.message)
                self.total_failed_healings += 1

                logger.info("Escalating to next healing action for %s", agent_id)
                await asyncio.sleep(HEALING_STEP_DELAY_SECONDS)

                await self.heal_agent(agent_id, infection, trigger=trigger)
        finally:
            self.healing_in_progress.discard(agent_id)
    
    async def chaos_injection_schedule(self, duration_seconds: int = 120):
        """Schedule chaos injections for demo. No new infections in last 5 sec so drain can reach 100% success."""
        no_inject_after = self.start_time + max(0, duration_seconds - 5)
        agents_list = list(self.agents.values())
        
        # Wait for baselines to be learned
        await asyncio.sleep(20)
        if time.time() >= no_inject_after or not self.running:
            return
        logger.info("CHAOS INJECTION (wave 1) - Simulating failures")
        results = self.chaos.inject_random_failure(agents_list, count=5)
        for agent_id, infection_type in results:
            logger.info("Injected %s into %s", infection_type, agent_id)
        
        # Second wave
        await asyncio.sleep(25)
        if time.time() >= no_inject_after or not self.running:
            return
        available = [a for a in agents_list if not a.infected]
        if available:
            logger.info("CHAOS INJECTION (wave 2) - More failures")
            wave2 = self.chaos.inject_random_failure(available, count=min(4, len(available)))
            for agent_id, infection_type in wave2:
                logger.info("Injected %s into %s", infection_type, agent_id)
        
        # Third wave — more chances for pending approvals
        await asyncio.sleep(25)
        if time.time() >= no_inject_after or not self.running:
            return
        available = [a for a in agents_list if not a.infected]
        if available:
            logger.info("CHAOS INJECTION (wave 3) - More failures")
            wave3 = self.chaos.inject_random_failure(available, count=min(4, len(available)))
            for agent_id, infection_type in wave3:
                logger.info("Injected %s into %s", infection_type, agent_id)
    
    def print_summary(self):
        """Log final summary statistics"""
        runtime = time.time() - self.start_time
        resolution_rate = (self.total_healed / self.total_infections) if self.total_infections else 0.0

        summary_lines = [
            "",
            "=" * 70,
            "AI AGENT IMMUNE SYSTEM - FINAL SUMMARY",
            "=" * 70,
            f"  {'Runtime':<35} {runtime:.1f} seconds",
            f"  {'Total Agents':<35} {len(self.agents)}",
            f"  {'Total Executions':<35} {self.telemetry.total_executions}",
            f"  {'Baselines Learned':<35} {len(self.baseline_learner.baselines)}",
            f"  {'Total Infections Detected':<35} {self.total_infections}",
            f"  {'Successfully Healed':<35} {self.total_healed}",
            f"  {'Failed Healing Attempts':<35} {self.total_failed_healings}",
            f"  {'Total Quarantine Events':<35} {self.quarantine.total_quarantines}",
            f"  {'Currently in Quarantine':<35} {self.quarantine.get_quarantined_count()}",
            f"  {'Healing Success Rate':<35} {resolution_rate:.1%}",
            f"  {'Immune Memory Records':<35} {self.immune_memory.get_total_healings()}",
        ]

        patterns = self.immune_memory.get_pattern_summary()
        if patterns:
            summary_lines.append("")
            summary_lines.append("  Learned Healing Patterns:")
            for diagnosis, info in patterns.items():
                summary_lines.append(
                    f"    {diagnosis}: best_action={info['best_action']} ({info['success_count']} successes)"
                )

        summary_lines.append("=" * 70)
        logger.info("\n".join(summary_lines))
    
    async def run(self, duration_seconds: int = 120):
        """Run the immune system for specified duration"""
        logger.info("=" * 70)
        logger.info("AI AGENT IMMUNE SYSTEM - Running %d agents with autonomous healing", len(self.agents))
        logger.info("=" * 70)
        
        # Start all agent loops
        agent_tasks = [asyncio.create_task(self.run_agent_loop(agent)) 
                      for agent in self.agents.values()]
        
        # Start sentinel
        sentinel_task = asyncio.create_task(self.sentinel_loop())
        
        # Start chaos injection (no new infections in last 5 sec)
        chaos_task = asyncio.create_task(self.chaos_injection_schedule(duration_seconds))
        
        # Run for specified duration
        await asyncio.sleep(duration_seconds)
        
        # Drain: heal all quarantined so success rate can reach 100% before closing
        logger.info("Draining: healing all quarantined agents before shutdown")
        drain_tasks = []
        approved_list = self.approve_all_pending(True)
        for agent_id, infection in approved_list:
            drain_tasks.append(asyncio.create_task(self.heal_agent(agent_id, infection, "drain_approve")))
        rejected_list = self.start_healing_all_rejected()
        for agent_id, infection in rejected_list:
            drain_tasks.append(asyncio.create_task(self.heal_agent(agent_id, infection, "drain_heal_now")))
        if drain_tasks:
            await asyncio.gather(*drain_tasks)
        deadline = time.time() + DRAIN_TIMEOUT_SECONDS
        while self.healing_in_progress and time.time() < deadline:
            await asyncio.sleep(0.5)
        if self.healing_in_progress:
            logger.warning("Drain timeout: some healing still in progress")
        else:
            logger.info("All quarantined agents healed")
        
        # Shutdown
        self.running = False
        logger.info("Shutting down immune system")
        
        # Wait for tasks to complete
        for task in agent_tasks + [sentinel_task, chaos_task]:
            task.cancel()
        
        # Print summary
        self.print_summary()
