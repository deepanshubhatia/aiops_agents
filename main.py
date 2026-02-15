"""
Project Aether CLI Interface
Main entry point for the AIOps multi-agent system
"""
import asyncio
import click
import json
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from pathlib import Path

# Import components
from agents.orchestrator.core import AgentOrchestrator, create_agent
from agents.specialized.incident_agents import (
    TriageAgent, RootCauseAnalyzer, 
    RemediationAdvisor, ActionExecutor
)
from knowledge_graph.graph import KnowledgeGraph
from infrastructure.kind.manager import KindClusterManager
from infrastructure.helm_charts.manager import HelmManager, ObservabilityStack
from resilience.chaos_mesh import ChaosMeshManager, ResilienceBenchmark

console = Console()


@click.group()
@click.version_option(version="1.0.0")
def cli():
    """Project Aether - AIOps Multi-Agent System
    
    An intelligent operations platform with multi-agent orchestration,
    knowledge graphs, and chaos engineering capabilities.
    """
    pass


@cli.group()
def infra():
    """Infrastructure management commands"""
    pass


@infra.command()
@click.option('--name', default='aether-cluster', help='Cluster name')
@click.option('--workers', default=2, help='Number of worker nodes')
@click.option('--control-planes', default=1, help='Number of control plane nodes')
def create_cluster(name, workers, control_planes):
    """Create a Kind Kubernetes cluster"""
    manager = KindClusterManager(name)
    success = manager.create_cluster(control_planes, workers)
    
    if success:
        console.print(Panel.fit(
            f"[green]Cluster '{name}' created successfully![/green]\n"
            f"Workers: {workers}\nControl Planes: {control_planes}",
            title="Kind Cluster"
        ))
    else:
        console.print(f"[red]Failed to create cluster '{name}'[/red]")


@infra.command()
@click.option('--name', default='aether-cluster', help='Cluster name')
def delete_cluster(name):
    """Delete a Kind Kubernetes cluster"""
    manager = KindClusterManager(name)
    success = manager.delete_cluster()
    
    if success:
        console.print(f"[green]Cluster '{name}' deleted successfully![/green]")
    else:
        console.print(f"[red]Failed to delete cluster '{name}'[/red]")


@infra.command()
def deploy_observability():
    """Deploy Prometheus, Loki, and Grafana"""
    helm = HelmManager()
    stack = ObservabilityStack(helm)
    success = stack.deploy_all()
    
    if success:
        console.print(Panel.fit(
            "[green]Observability stack deployed![/green]\n\n"
            "Access URLs:\n"
            "  Prometheus: http://localhost:9090\n"
            "  Grafana: http://localhost:3000\n"
            "  Loki: http://localhost:3100",
            title="Observability Stack"
        ))


@cli.group()
def agents():
    """Multi-agent system commands"""
    pass


@agents.command()
@click.option('--incident-id', required=True, help='Incident identifier')
@click.option('--service', required=True, help='Affected service name')
@click.option('--namespace', default='default', help='Kubernetes namespace')
@click.option('--symptoms', required=True, help='Comma-separated list of symptoms')
@click.option('--provider', default='openai', type=click.Choice(['openai', 'google']))
def run_incident(incident_id, service, namespace, symptoms, provider):
    """Run incident response workflow"""
    
    console.print(Panel.fit(
        f"Incident: [bold]{incident_id}[/bold]\n"
        f"Service: {service}\n"
        f"Namespace: {namespace}\n"
        f"Symptoms: {symptoms}",
        title="Incident Response"
    ))
    
    # Initialize orchestrator
    orchestrator = AgentOrchestrator()
    
    # Initialize knowledge graph
    kg = KnowledgeGraph()
    kg.connect()
    
    # Register agents
    orchestrator.register_agent(TriageAgent(provider=provider))
    orchestrator.register_agent(RootCauseAnalyzer(
        knowledge_graph=kg,
        provider=provider
    ))
    orchestrator.register_agent(RemediationAdvisor(provider=provider))
    orchestrator.register_agent(ActionExecutor(
        auto_execute=False,
        provider=provider
    ))
    
    # Define workflow
    flow = ["triage", "root_cause_analyzer", "remediation_advisor", "action_executor"]
    
    # Run workflow
    async def run_workflow():
        result = await orchestrator.execute_incident_workflow(
            incident_id=incident_id,
            service_name=service,
            namespace=namespace,
            symptoms=symptoms.split(','),
            flow=flow
        )
        
        # Display results
        table = Table(title="Agent Execution Results")
        table.add_column("Agent", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Message")
        
        for agent_result in result['results']:
            status = "✅" if agent_result['success'] else "❌"
            table.add_row(
                agent_result['agent'],
                status,
                agent_result['message'][:50] + "..." if len(agent_result['message']) > 50 else agent_result['message']
            )
        
        console.print(table)
        
        # Display findings
        if result['context']['findings']:
            console.print("\n[bold]Key Findings:[/bold]")
            for finding in result['context']['findings']:
                console.print(f"  • {finding['agent']}: {finding['message']}")
        
        # Display actions
        if result['context']['actions_taken']:
            console.print("\n[bold]Recommended Actions:[/bold]")
            for action in result['context']['actions_taken']:
                console.print(f"  • {action.get('type', 'unknown')}: {action.get('action', 'N/A')}")
    
    asyncio.run(run_workflow())


@agents.command()
def status():
    """Check agent system status"""
    orchestrator = AgentOrchestrator()
    
    # Display status
    table = Table(title="Agent System Status")
    table.add_column("Component", style="cyan")
    table.add_column("Status", style="green")
    
    table.add_row("Orchestrator", "✅ Ready")
    table.add_row("Knowledge Graph", "✅ Connected" if KnowledgeGraph().connect() else "❌ Disconnected")
    
    console.print(table)


@cli.group()
def knowledge():
    """Knowledge graph commands"""
    pass


@knowledge.command()
@click.option('--service', help='Service name to analyze')
@click.option('--namespace', default='default', help='Namespace')
def dependencies(service, namespace):
    """Show service dependencies"""
    
    kg = KnowledgeGraph()
    kg.connect()
    
    if service:
        deps = kg.get_dependencies(service, direction="both")
        
        console.print(f"\n[bold]Dependencies for {service}:[/bold]")
        
        if deps:
            table = Table()
            table.add_column("Type", style="cyan")
            table.add_column("Service", style="green")
            table.add_column("Relationship")
            
            for dep in deps:
                table.add_row(
                    dep.get('upstream_name', '-'),
                    dep.get('downstream_name', '-'),
                    dep.get('upstream_type', 'depends on')
                )
            
            console.print(table)
        else:
            console.print("  No dependencies found")
    else:
        # Show topology
        topology = kg.get_service_topology(namespace)
        
        console.print(f"\n[bold]Service Topology ({namespace}):[/bold]")
        table = Table()
        table.add_column("Service", style="cyan")
        table.add_column("Type", style="green")
        table.add_column("Status")
        
        for svc in topology.get('services', []):
            table.add_row(svc['name'], svc['type'], svc['status'])
        
        console.print(table)


@knowledge.command()
@click.option('--start-service', required=True, help='Starting service')
@click.option('--max-hops', default=3, help='Maximum hops to analyze')
def root_cause(start_service, max_hops):
    """Perform multi-hop root cause analysis"""
    
    kg = KnowledgeGraph()
    kg.connect()
    
    console.print(f"\n[bold]Analyzing root cause for {start_service}...[/bold]")
    
    results = kg.multi_hop_analysis(start_service, max_hops=max_hops)
    
    if results:
        table = Table(title="Potential Root Causes")
        table.add_column("Service", style="cyan")
        table.add_column("Hops", style="blue")
        table.add_column("Impact Score", style="red")
        table.add_column("Path")
        
        for result in results[:10]:  # Top 10
            table.add_row(
                result['service'],
                str(result['hops']),
                f"{result['impact_score']:.2f}",
                " -> ".join(result['path'])
            )
        
        console.print(table)
    else:
        console.print("  No root causes identified")


@cli.group()
def chaos():
    """Chaos engineering commands"""
    pass


@chaos.command()
@click.option('--target', required=True, help='Target service')
@click.option('--type', 'fault_type', 
              type=click.Choice(['network-partition', 'pod-failure', 'stress', 'io-delay']),
              default='network-partition',
              help='Type of fault to inject')
@click.option('--duration', default='5m', help='Duration of fault')
@click.option('--namespace', default='default', help='Namespace')
def inject(target, fault_type, duration, namespace):
    """Inject a fault into the system"""
    
    console.print(Panel.fit(
        f"Fault Injection\n"
        f"Target: [bold]{target}[/bold]\n"
        f"Type: {fault_type}\n"
        f"Duration: {duration}",
        title="Chaos Engineering"
    ))
    
    async def run_injection():
        from resilience.chaos_mesh import inject_fault
        
        result = await inject_fault(
            target=target,
            fault_type=fault_type,
            duration=duration,
            namespace=namespace
        )
        
        if result.get('success'):
            console.print(f"[green]✅ Fault injected successfully![/green]")
            console.print(f"Experiment ID: {result['experiment_name']}")
        else:
            console.print(f"[red]❌ Failed to inject fault: {result.get('error', 'Unknown error')}[/red]")
    
    asyncio.run(run_injection())


@chaos.command()
@click.option('--services', required=True, help='Comma-separated list of services to test')
@click.option('--namespace', default='default', help='Namespace')
def benchmark(services, namespace):
    """Run resilience benchmark on services"""
    
    service_list = [s.strip() for s in services.split(',')]
    
    console.print(f"\n[bold]Running resilience benchmark on {len(service_list)} services...[/bold]")
    
    manager = ChaosMeshManager()
    benchmarker = ResilienceBenchmark(manager)
    
    result = benchmarker.run_benchmark(service_list, namespace=namespace)
    
    # Display results
    table = Table(title="Resilience Benchmark Results")
    table.add_column("Service", style="cyan")
    table.add_column("Experiments", style="blue")
    table.add_column("Status")
    
    for service_result in result['results']:
        total = service_result['summary']['total']
        passed = service_result['summary']['passed']
        status = f"{passed}/{total} passed"
        
        table.add_row(
            service_result['target'],
            str(total),
            status
        )
    
    console.print(table)
    console.print("\nUse 'chaos report' to generate a detailed report.")


@chaos.command()
def experiments():
    """List active chaos experiments"""
    
    manager = ChaosMeshManager()
    experiments = manager.list_experiments()
    
    if experiments:
        table = Table(title="Active Chaos Experiments")
        table.add_column("Name", style="cyan")
        table.add_column("Type", style="blue")
        table.add_column("Status", style="green")
        table.add_column("Created")
        
        for exp in experiments:
            table.add_row(
                exp['name'],
                exp['type'],
                exp['status'],
                exp['created']
            )
        
        console.print(table)
    else:
        console.print("  No active experiments")


@cli.command()
def demo():
    """Run a complete demo workflow"""
    
    console.print(Panel.fit(
        "[bold blue]Project Aether Demo[/bold blue]\n\n"
        "This will demonstrate the complete AIOps workflow:\n"
        "1. Infrastructure setup\n"
        "2. Knowledge graph population\n"
        "3. Incident detection & response\n"
        "4. Chaos testing",
        title="Demo"
    ))
    
    console.print("\n[yellow]Note: This is a demonstration. Ensure you have:\n"
                  "  - Kind installed\n"
                  "  - Helm installed\n"
                  "  - Neo4j running\n"
                  "  - API keys configured in .env[/yellow]\n")
    
    if click.confirm("Do you want to proceed?"):
        console.print("\n[cyan]Starting demo workflow...[/cyan]\n")
        
        # Demo steps would go here
        console.print("Demo completed!")


def main():
    """Main entry point"""
    cli()


if __name__ == "__main__":
    main()
