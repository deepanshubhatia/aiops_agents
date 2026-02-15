"""
Multi-Agent System for Project Aether
Implements hierarchical agent architecture with Ollama
"""
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
import json
import asyncio
from abc import ABC, abstractmethod

# AI SDK imports
import ollama

from config.settings import settings


class AgentState(Enum):
    """Agent execution states"""
    IDLE = "idle"
    THINKING = "thinking"
    EXECUTING = "executing"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class AgentContext:
    """Context passed between agents"""
    incident_id: str
    service_name: str
    namespace: str
    symptoms: List[str] = field(default_factory=list)
    findings: List[Dict] = field(default_factory=list)
    actions_taken: List[Dict] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    """Result from agent execution"""
    success: bool
    message: str
    data: Dict[str, Any] = field(default_factory=dict)
    next_agent: Optional[str] = None
    terminate: bool = False


class Tool:
    """Represents a tool that an agent can use"""
    
    def __init__(self, name: str, description: str, 
                 parameters: Dict[str, Any],
                 function: Callable):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.function = function
    
    def to_ollama_schema(self) -> Dict:
        """Convert to Ollama function schema"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
            }
        }
    
    async def execute(self, **kwargs) -> Any:
        """Execute the tool function"""
        if asyncio.iscoroutinefunction(self.function):
            return await self.function(**kwargs)
        return self.function(**kwargs)


class BaseAgent(ABC):
    """Base class for all agents"""
    
    def __init__(self, name: str, description: str, tools: List[Tool] = None):
        self.name = name
        self.description = description
        self.tools = tools or []
        self.state = AgentState.IDLE
        self.context: Optional[AgentContext] = None
    
    @abstractmethod
    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute the agent's logic"""
        pass
    
    def add_tool(self, tool: Tool):
        """Add a tool to the agent"""
        self.tools.append(tool)
    
    def get_tools_schema(self) -> List[Dict]:
        """Get tools schema for LLM provider"""
        return [tool.to_ollama_schema() for tool in self.tools]


class OllamaAgent(BaseAgent):
    """Agent powered by Ollama with glm-4.6:cloud model"""
    
    def __init__(self, name: str, description: str, 
                 model: str = None, tools: List[Tool] = None):
        super().__init__(name, description, tools)
        self.model = model or settings.ollama_model
        self.host = settings.ollama_host
        
        # Initialize Ollama client
        self.client = ollama.Client(host=self.host)
    
    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute using Ollama API"""
        self.state = AgentState.THINKING
        self.context = context
        
        try:
            # Build system prompt
            system_prompt = self._build_system_prompt()
            
            # Build user prompt from context
            user_prompt = self._build_user_prompt(context)
            
            # Call Ollama
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            # Generate response
            response = self.client.chat(
                model=self.model,
                messages=messages,
                tools=self.get_tools_schema() if self.tools else None,
                options={
                    "temperature": 0.2  # Low temperature for deterministic responses
                }
            )
            
            message = response.message
            
            # Handle tool calls
            if hasattr(message, 'tool_calls') and message.tool_calls:
                self.state = AgentState.EXECUTING
                tool_results = await self._execute_tool_calls(message.tool_calls)
                
                # Follow-up with tool results
                messages.append({
                    "role": "assistant",
                    "content": message.content if message.content else "",
                })
                
                for tool_name, result in tool_results.items():
                    messages.append({
                        "role": "tool",
                        "content": json.dumps({"tool": tool_name, "result": result})
                    })
                
                # Get final response
                final_response = self.client.chat(
                    model=self.model,
                    messages=messages,
                    options={"temperature": 0.2}
                )
                
                message = final_response.message
            
            self.state = AgentState.COMPLETED
            
            return AgentResult(
                success=True,
                message=message.content if message.content else "Task completed",
                data=self._parse_response(message.content if message.content else "")
            )
            
        except Exception as e:
            self.state = AgentState.ERROR
            return AgentResult(
                success=False,
                message=f"Error executing {self.name}: {str(e)}",
                data={}
            )
    
    def _build_system_prompt(self) -> str:
        """Build system prompt for the agent"""
        tools_desc = "\n".join([
            f"- {tool.name}: {tool.description}"
            for tool in self.tools
        ])
        
        return f"""You are {self.name}, an AI operations agent.
{self.description}

Available tools:
{tools_desc}

Always provide structured, actionable responses. If you need to use tools, do so systematically.
Respond with clear analysis and specific recommendations."""
    
    def _build_user_prompt(self, context: AgentContext) -> str:
        """Build user prompt from context"""
        return f"""Incident ID: {context.incident_id}
Service: {context.service_name} (namespace: {context.namespace})
Symptoms: {', '.join(context.symptoms)}
Findings so far: {json.dumps(context.findings, indent=2)}
Actions taken: {json.dumps(context.actions_taken, indent=2)}

What should be done next? Analyze the situation and provide specific recommendations."""
    
    async def _execute_tool_calls(self, tool_calls) -> Dict[str, Any]:
        """Execute tool calls from LLM"""
        results = {}
        
        for tool_call in tool_calls:
            tool_name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments)
            
            # Find and execute tool
            tool = next((t for t in self.tools if t.name == tool_name), None)
            if tool:
                result = await tool.execute(**arguments)
                results[tool_name] = result
            else:
                results[tool_name] = {"error": f"Tool {tool_name} not found"}
        
        return results
    
    def _parse_response(self, content: str) -> Dict[str, Any]:
        """Parse LLM response into structured data"""
        # Try to extract JSON if present
        try:
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0]
                return json.loads(json_str)
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0]
                return json.loads(json_str)
            else:
                # Try to parse the entire content
                return json.loads(content)
        except (json.JSONDecodeError, IndexError):
            # Return as text if not valid JSON
            return {"response": content}


class AgentOrchestrator:
    """Orchestrates multiple agents with hierarchical state management"""
    
    def __init__(self):
        self.agents: Dict[str, BaseAgent] = {}
        self.execution_history: List[Dict] = []
        self.context: Optional[AgentContext] = None
    
    def register_agent(self, agent: BaseAgent):
        """Register an agent with the orchestrator"""
        self.agents[agent.name] = agent
        print(f"Registered agent: {agent.name}")
    
    def create_flow(self, flow: List[str]):
        """Define agent execution flow"""
        self.flow = flow
    
    async def execute_incident_workflow(self, 
                                        incident_id: str,
                                        service_name: str,
                                        namespace: str,
                                        symptoms: List[str],
                                        flow: List[str] = None) -> Dict:
        """Execute complete incident response workflow"""
        
        # Initialize context
        self.context = AgentContext(
            incident_id=incident_id,
            service_name=service_name,
            namespace=namespace,
            symptoms=symptoms
        )
        
        execution_plan = flow or self.flow
        results = []
        
        for agent_name in execution_plan:
            if agent_name not in self.agents:
                results.append({
                    "agent": agent_name,
                    "error": "Agent not found"
                })
                continue
            
            agent = self.agents[agent_name]
            print(f"\n>>> Executing {agent_name}...")
            
            # Execute agent
            result = await agent.execute(self.context)
            
            # Update context with findings
            if result.success:
                self.context.findings.append({
                    "agent": agent_name,
                    "message": result.message,
                    "data": result.data
                })
                
                # Record actions if present
                if "actions" in result.data:
                    self.context.actions_taken.extend(result.data["actions"])
            
            results.append({
                "agent": agent_name,
                "success": result.success,
                "message": result.message,
                "data": result.data
            })
            
            self.execution_history.append({
                "timestamp": asyncio.get_event_loop().time(),
                "agent": agent_name,
                "result": result
            })
            
            # Check for early termination
            if result.terminate:
                print(f"\nWorkflow terminated by {agent_name}")
                break
        
        return {
            "incident_id": incident_id,
            "service": service_name,
            "status": "completed",
            "results": results,
            "context": {
                "findings": self.context.findings,
                "actions_taken": self.context.actions_taken
            }
        }
    
    def get_execution_history(self) -> List[Dict]:
        """Get execution history"""
        return self.execution_history
    
    def get_agent_status(self) -> Dict[str, str]:
        """Get current status of all agents"""
        return {
            name: agent.state.value 
            for name, agent in self.agents.items()
        }


# Factory function for creating agents
def create_agent(name: str, 
                description: str,
                model: str = None,
                tools: List[Tool] = None) -> BaseAgent:
    """Factory function to create Ollama agent"""
    return OllamaAgent(name, description, model, tools)
