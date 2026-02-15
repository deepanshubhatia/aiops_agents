"""
Specialized Agents for Project Aether
"""
from agents.orchestrator.core import BaseAgent, AgentContext, AgentResult, Tool
from agents.orchestrator.core import AgentState
from typing import List, Dict, Any
from knowledge_graph.graph import KnowledgeGraph
import asyncio


class TriageAgent(BaseAgent):
    """Initial triage agent that categorizes incidents"""
    
    def __init__(self, model: str = None):
        super().__init__(
            name="triage",
            description="Classifies incidents and determines severity",
            tools=[]
        )
    
    async def execute(self, context: AgentContext) -> AgentResult:
        """Classify the incident based on symptoms"""
        self.state = AgentState.THINKING
        
        # Analyze symptoms
        severity = "unknown"
        category = "unknown"
        
        # Simple rule-based classification
        symptoms_lower = [s.lower() for s in context.symptoms]
        
        if any(s in symptoms_lower for s in ["crash", "error", "failure", "down"]):
            severity = "critical"
            category = "availability"
        elif any(s in symptoms_lower for s in ["slow", "latency", "timeout", "performance"]):
            severity = "high"
            category = "performance"
        elif any(s in symptoms_lower for s in ["memory", "cpu", "disk", "resource"]):
            severity = "medium"
            category = "resource"
        elif any(s in symptoms_lower for s in ["warning", "degraded"]):
            severity = "low"
            category = "degradation"
        
        self.state = AgentState.COMPLETED
        
        return AgentResult(
            success=True,
            message=f"Incident classified as {severity} severity, {category} category",
            data={
                "severity": severity,
                "category": category,
                "next_agents": ["root_cause_analyzer"]
            },
            next_agent="root_cause_analyzer"
        )


class RootCauseAnalyzer(BaseAgent):
    """Agent for multi-hop root cause analysis"""
    
    def __init__(self, knowledge_graph: KnowledgeGraph = None, 
                 model: str = None):
        # Import here to avoid circular dependency
        from tools.k8s_tools import get_service_status, get_pod_logs
        from tools.metrics_tools import query_metrics
        
        tools = [
            Tool(
                name="get_service_status",
                description="Get the status of a Kubernetes service",
                parameters={
                    "type": "object",
                    "properties": {
                        "service_name": {"type": "string"},
                        "namespace": {"type": "string"}
                    },
                    "required": ["service_name", "namespace"]
                },
                function=get_service_status
            ),
            Tool(
                name="query_metrics",
                description="Query Prometheus metrics for a service",
                parameters={
                    "type": "object",
                    "properties": {
                        "service_name": {"type": "string"},
                        "metric_name": {"type": "string"},
                        "duration": {"type": "string", "default": "1h"}
                    },
                    "required": ["service_name", "metric_name"]
                },
                function=query_metrics
            ),
            Tool(
                name="get_pod_logs",
                description="Get logs from service pods",
                parameters={
                    "type": "object",
                    "properties": {
                        "service_name": {"type": "string"},
                        "namespace": {"type": "string"},
                        "tail_lines": {"type": "integer", "default": 100}
                    },
                    "required": ["service_name", "namespace"]
                },
                function=get_pod_logs
            )
        ]
        
        super().__init__(
            name="root_cause_analyzer",
            description="Performs multi-hop root cause analysis using knowledge graph",
            tools=tools
        )
        
        self.kg = knowledge_graph
    
    async def execute(self, context: AgentContext) -> AgentResult:
        """Perform root cause analysis"""
        self.state = AgentState.THINKING
        
        findings = []
        root_causes = []
        
        # 1. Query knowledge graph for dependencies
        if self.kg and self.kg.driver:
            try:
                dependencies = self.kg.get_dependencies(context.service_name, direction="upstream")
                findings.append({
                    "type": "dependency_analysis",
                    "dependencies": dependencies,
                    "description": f"Found {len(dependencies)} upstream dependencies"
                })
                
                # Multi-hop analysis
                multi_hop_results = self.kg.multi_hop_analysis(
                    context.service_name,
                    max_hops=3,
                    min_impact_score=0.5
                )
                
                for result in multi_hop_results:
                    root_causes.append({
                        "service": result["service"],
                        "hops": result["hops"],
                        "impact_score": result["impact_score"],
                        "path": result["path_services"]
                    })
                
                findings.append({
                    "type": "multi_hop_analysis",
                    "root_causes": root_causes
                })
                
            except Exception as e:
                findings.append({
                    "type": "error",
                    "message": f"Knowledge graph query failed: {str(e)}"
                })
        
        # 2. Check current service status
        if "get_service_status" in [t.name for t in self.tools]:
            tool = next(t for t in self.tools if t.name == "get_service_status")
            try:
                status = await tool.execute(
                    service_name=context.service_name,
                    namespace=context.namespace
                )
                findings.append({
                    "type": "service_status",
                    "data": status
                })
            except Exception as e:
                findings.append({
                    "type": "error",
                    "message": f"Status check failed: {str(e)}"
                })
        
        self.state = AgentState.COMPLETED
        
        return AgentResult(
            success=True,
            message=f"Root cause analysis complete. Found {len(root_causes)} potential root causes.",
            data={
                "findings": findings,
                "root_causes": root_causes,
                "next_agents": ["remediation_advisor"]
            },
            next_agent="remediation_advisor"
        )


class RemediationAdvisor(BaseAgent):
    """Agent that suggests remediation actions"""
    
    def __init__(self, model: str = None):
        from tools.k8s_tools import generate_yaml_patch
        
        tools = [
            Tool(
                name="generate_yaml_patch",
                description="Generate Kubernetes YAML patches for remediation",
                parameters={
                    "type": "object",
                    "properties": {
                        "resource_type": {"type": "string", "enum": ["deployment", "service", "configmap"]},
                        "resource_name": {"type": "string"},
                        "namespace": {"type": "string"},
                        "patches": {"type": "object"}
                    },
                    "required": ["resource_type", "resource_name", "namespace", "patches"]
                },
                function=generate_yaml_patch
            )
        ]
        
        super().__init__(
            name="remediation_advisor",
            description="Suggests and generates remediation actions",
            tools=tools
        )
    
    async def execute(self, context: AgentContext) -> AgentResult:
        """Generate remediation recommendations"""
        self.state = AgentState.THINKING
        
        recommendations = []
        remediation_actions = []
        
        # Analyze findings from previous agents
        for finding in context.findings:
            if finding.get("type") == "service_status":
                data = finding.get("data", {})
                
                # Check for specific issues and recommend actions
                if data.get("restarts", 0) > 5:
                    recommendations.append({
                        "issue": "High pod restart count",
                        "severity": "high",
                        "suggestion": "Check resource limits and application logs"
                    })
                    remediation_actions.append({
                        "type": "scale",
                        "action": "increase_replicas",
                        "resource": context.service_name,
                        "namespace": context.namespace
                    })
                
                if data.get("cpu_usage", 0) > 80:
                    recommendations.append({
                        "issue": "High CPU usage",
                        "severity": "medium",
                        "suggestion": "Consider horizontal pod autoscaling or resource optimization"
                    })
                    remediation_actions.append({
                        "type": "resource",
                        "action": "increase_cpu_limit",
                        "resource": context.service_name,
                        "namespace": context.namespace
                    })
        
        # Check root causes
        for finding in context.findings:
            if finding.get("type") == "multi_hop_analysis":
                root_causes = finding.get("root_causes", [])
                for cause in root_causes[:3]:  # Top 3 root causes
                    recommendations.append({
                        "issue": f"Dependency issue with {cause['service']}",
                        "severity": "high" if cause["impact_score"] > 0.8 else "medium",
                        "suggestion": f"Investigate {cause['service']} (impact score: {cause['impact_score']:.2f})"
                    })
        
        self.state = AgentState.COMPLETED
        
        return AgentResult(
            success=True,
            message=f"Generated {len(recommendations)} recommendations and {len(remediation_actions)} actions",
            data={
                "recommendations": recommendations,
                "actions": remediation_actions,
                "next_agents": ["action_executor"]
            },
            next_agent="action_executor"
        )


class ActionExecutor(BaseAgent):
    """Agent that executes remediation actions"""
    
    def __init__(self, auto_execute: bool = False, 
                 model: str = None):
        from tools.k8s_tools import apply_yaml_patch, restart_deployment
        
        tools = [
            Tool(
                name="apply_yaml_patch",
                description="Apply Kubernetes YAML patch",
                parameters={
                    "type": "object",
                    "properties": {
                        "yaml_content": {"type": "string"},
                        "namespace": {"type": "string"}
                    },
                    "required": ["yaml_content", "namespace"]
                },
                function=apply_yaml_patch
            ),
            Tool(
                name="restart_deployment",
                description="Restart a Kubernetes deployment",
                parameters={
                    "type": "object",
                    "properties": {
                        "deployment_name": {"type": "string"},
                        "namespace": {"type": "string"}
                    },
                    "required": ["deployment_name", "namespace"]
                },
                function=restart_deployment
            )
        ]
        
        super().__init__(
            name="action_executor",
            description="Executes approved remediation actions",
            tools=tools
        )
        
        self.auto_execute = auto_execute
    
    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute remediation actions"""
        self.state = AgentState.THINKING
        
        executed_actions = []
        
        # Get remediation actions from previous findings
        for finding in context.findings:
            if finding.get("agent") == "remediation_advisor":
                data = finding.get("data", {})
                actions = data.get("actions", [])
                
                for action in actions:
                    if self.auto_execute or action.get("severity") == "critical":
                        try:
                            # Execute the action
                            if action["type"] == "scale":
                                result = await self._scale_service(
                                    action["resource"],
                                    action["namespace"]
                                )
                                executed_actions.append({
                                    "action": action,
                                    "result": result,
                                    "status": "executed"
                                })
                            
                            elif action["type"] == "resource":
                                result = await self._update_resources(
                                    action["resource"],
                                    action["namespace"]
                                )
                                executed_actions.append({
                                    "action": action,
                                    "result": result,
                                    "status": "executed"
                                })
                            
                        except Exception as e:
                            executed_actions.append({
                                "action": action,
                                "error": str(e),
                                "status": "failed"
                            })
                    else:
                        executed_actions.append({
                            "action": action,
                            "status": "pending_approval"
                        })
        
        self.state = AgentState.COMPLETED
        
        return AgentResult(
            success=True,
            message=f"Executed {len([a for a in executed_actions if a['status'] == 'executed'])} actions, {len([a for a in executed_actions if a['status'] == 'pending_approval'])} pending approval",
            data={
                "executed_actions": executed_actions,
                "terminate": True
            },
            terminate=True
        )
    
    async def _scale_service(self, service_name: str, namespace: str) -> Dict:
        """Scale a service by increasing replicas"""
        tool = next(t for t in self.tools if t.name == "apply_yaml_patch")
        
        yaml_patch = f"""
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {service_name}
  namespace: {namespace}
spec:
  replicas: 5
"""
        
        return await tool.execute(yaml_content=yaml_patch, namespace=namespace)
    
    async def _update_resources(self, service_name: str, namespace: str) -> Dict:
        """Update resource limits for a service"""
        tool = next(t for t in self.tools if t.name == "apply_yaml_patch")
        
        yaml_patch = f"""
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {service_name}
  namespace: {namespace}
spec:
  template:
    spec:
      containers:
      - name: app
        resources:
          limits:
            cpu: "1000m"
            memory: "1Gi"
"""
        
        return await tool.execute(yaml_content=yaml_patch, namespace=namespace)
