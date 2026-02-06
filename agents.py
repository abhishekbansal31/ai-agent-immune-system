"""
Agent Runtime - Core agent implementation with state and execution logic
"""
import asyncio
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List
import time


class AgentStatus(Enum):
    HEALTHY = "healthy"
    INFECTED = "infected"
    QUARANTINED = "quarantined"


@dataclass
class AgentState:
    """Agent's internal state"""
    memory: Dict = field(default_factory=dict)
    prompt_version: int = 1
    temperature: float = 0.7
    max_tools: int = 5
    
    def reset_memory(self):
        """Clear agent's memory"""
        self.memory.clear()
    
    def rollback_prompt(self):
        """Rollback to previous prompt version"""
        if self.prompt_version > 1:
            self.prompt_version -= 1
    
    def reduce_autonomy(self):
        """Reduce agent's autonomy"""
        self.temperature = max(0.1, self.temperature * 0.5)
        self.max_tools = max(1, self.max_tools - 2)


class BaseAgent:
    """Base agent class with telemetry emission"""
    
    def __init__(self, agent_id: str, agent_type: str, model_name: str = "GPT-4", mcp_servers: List[str] = None):
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.model_name = model_name
        self.mcp_servers = mcp_servers or []
        self.state = AgentState()
        self.status = AgentStatus.HEALTHY
        self.execution_count = 0
        
        # Baseline behavioral characteristics (varies by agent type)
        self.base_latency_ms = random.randint(200, 400)
        self.base_tokens = random.randint(1000, 1500)
        self.base_tool_calls = random.randint(2, 4)
        
        # Infection state
        self.infected = False
        self.infection_type = None
    
    async def execute(self) -> Dict:
        """Execute agent task and return telemetry"""
        start_time = time.time()
        
        # Simulate work
        await asyncio.sleep(random.uniform(0.1, 0.3))
        
        # Calculate metrics with some natural variance
        variance = random.uniform(0.8, 1.2)
        
        if self.infected:
            # Apply infection effects
            latency_ms = self._infected_latency()
            token_count = self._infected_tokens()
            tool_calls = self._infected_tool_calls()
            retries = self._infected_retries()
        else:
            latency_ms = int(self.base_latency_ms * variance)
            token_count = int(self.base_tokens * variance)
            tool_calls = max(1, int(self.base_tool_calls * variance))
            retries = 1 if random.random() > 0.9 else 0
        success = random.random() > 0.05  # 95% success rate normally
        
        self.execution_count += 1
        
        elapsed_ms = int((time.time() - start_time) * 1000)
        
        return {
            'agent_id': self.agent_id,
            'agent_type': self.agent_type,
            'latency_ms': max(elapsed_ms, latency_ms),
            'token_count': token_count,
            'tool_calls': tool_calls,
            'retries': retries,
            'success': success,
            'timestamp': time.time()
        }
    
    def _infected_latency(self) -> int:
        """Modified latency when infected (varied so severity spreads 5-10)"""
        if self.infection_type == "latency_spike":
            return self.base_latency_ms * random.randint(3, 7)
        if self.infection_type in ("prompt_drift", "memory_corruption", "full_meltdown"):
            return self.base_latency_ms * random.randint(3, 6)
        return self.base_latency_ms
    
    def _infected_tokens(self) -> int:
        """Modified token usage when infected (varied so severity spreads 5-10)"""
        if self.infection_type == "token_explosion":
            return self.base_tokens * random.randint(4, 9)
        if self.infection_type in ("prompt_drift", "full_meltdown"):
            return self.base_tokens * random.randint(4, 8)
        return self.base_tokens
    
    def _infected_tool_calls(self) -> int:
        """Modified tool calls when infected (varied so severity spreads 5-10)"""
        if self.infection_type == "tool_loop":
            return self.base_tool_calls * random.randint(5, 11)
        if self.infection_type == "full_meltdown":
            return self.base_tool_calls * random.randint(5, 10)
        return self.base_tool_calls
    
    def _infected_retries(self) -> int:
        """Modified retry behavior when infected (for high_retry_rate / memory_corruption)"""
        if self.infection_type == "high_retry_rate":
            return 1 if random.random() > 0.25 else 0  # ~75% retries
        if self.infection_type == "memory_corruption":
            return 1 if random.random() > 0.3 else 0   # ~70% retries
        return 1 if random.random() > 0.9 else 0
    
    def infect(self, infection_type: str):
        """Infect the agent with specific problem"""
        self.infected = True
        self.infection_type = infection_type
        self.status = AgentStatus.INFECTED
    
    def cure(self):
        """Cure the agent"""
        self.infected = False
        self.infection_type = None
        self.status = AgentStatus.HEALTHY
    
    def quarantine(self):
        """Quarantine the agent"""
        self.status = AgentStatus.QUARANTINED
    
    def release(self):
        """Release from quarantine"""
        self.status = AgentStatus.HEALTHY if not self.infected else AgentStatus.INFECTED


class ResearchAgent(BaseAgent):
    """Agent that does research tasks"""
    def __init__(self, agent_id: str):
        super().__init__(agent_id, "Research")
        self.base_tokens = random.randint(1200, 1600)
        self.base_tool_calls = random.randint(3, 5)


class DataAgent(BaseAgent):
    """Agent that processes data"""
    def __init__(self, agent_id: str):
        super().__init__(agent_id, "Data")
        self.base_latency_ms = random.randint(150, 300)
        self.base_tokens = random.randint(800, 1200)


class AnalyticsAgent(BaseAgent):
    """Agent that performs analytics"""
    def __init__(self, agent_id: str):
        super().__init__(agent_id, "Analytics")
        self.base_latency_ms = random.randint(300, 500)
        self.base_tool_calls = random.randint(4, 6)


class CoordinatorAgent(BaseAgent):
    """Agent that coordinates other agents"""
    def __init__(self, agent_id: str):
        super().__init__(agent_id, "Coordinator")
        self.base_tokens = random.randint(1000, 1400)
        self.base_tool_calls = random.randint(5, 8)


# Real-world AI agent names (VPN, Docker, Slack, DB, network, etc.)
AGENT_NAMES = [
    "VPN",
    "Docker",
    "Slack",
    "Postgres",
    "Network",
    "GitHub",
    "Kubernetes",
    "Nginx",
    "Redis",
    "Elasticsearch",
    "Notion",
    "Figma",
    "Linear",
    "SendGrid",
    "Brave Search",
]

# Example models and MCP servers for dashboard display (hackathon realism)
MODELS = ["GPT-5", "Claude Sonnet 4", "Claude Opus 4", "Gemini 2.0", "GPT-4o", "Claude Sonnet 3.5"]
MCP_SERVER_PRESETS = [
    ["filesystem", "github", "slack"],
    ["postgres", "web-fetch", "notion"],
    ["google-drive", "figma", "linear"],
    ["brave-search", "fetch", "memory"],
    ["filesystem", "postgres", "sendgrid"],
    ["github", "slack", "notion"],
]


def create_agent_pool(count: int) -> List[BaseAgent]:
    """Create a pool of diverse agents with real-world names and model/MCP labels"""
    agents = []
    agent_classes = [ResearchAgent, DataAgent, AnalyticsAgent, CoordinatorAgent]
    names = (AGENT_NAMES * ((count // len(AGENT_NAMES)) + 1))[:count]
    
    for i in range(count):
        agent_cls = agent_classes[i % len(agent_classes)]
        agent = agent_cls(names[i])
        agent.model_name = MODELS[i % len(MODELS)]
        agent.mcp_servers = MCP_SERVER_PRESETS[i % len(MCP_SERVER_PRESETS)]
        agents.append(agent)
    
    return agents
