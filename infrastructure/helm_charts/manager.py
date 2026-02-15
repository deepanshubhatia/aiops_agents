"""
Helm Chart Manager for Project Aether
Manages deployment of observability and infrastructure components
"""
import subprocess
import yaml
from pathlib import Path
from typing import Optional, Dict, List
from dataclasses import dataclass
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()


@dataclass
class HelmRelease:
    """Represents a Helm release configuration"""
    name: str
    chart: str
    namespace: str
    version: Optional[str] = None
    values: Optional[Dict] = None
    repo: Optional[str] = None


class HelmManager:
    """Manages Helm deployments for Project Aether"""
    
    def __init__(self, kubeconfig: Optional[str] = None):
        self.kubeconfig = kubeconfig or "~/.kube/config"
        self.charts_dir = Path("infrastructure/helm-charts")
        self.charts_dir.mkdir(parents=True, exist_ok=True)
    
    def add_repo(self, name: str, url: str) -> bool:
        """Add a Helm repository"""
        
        console.print(f"[blue]Adding Helm repo: {name}[/blue]")
        
        try:
            subprocess.run(
                ["helm", "repo", "add", name, url],
                capture_output=True,
                text=True,
                check=True
            )
            subprocess.run(
                ["helm", "repo", "update"],
                capture_output=True,
                text=True,
                check=True
            )
            console.print(f"[green]Repository {name} added successfully[/green]")
            return True
        except subprocess.CalledProcessError as e:
            console.print(f"[red]Failed to add repository: {e.stderr}[/red]")
            return False
    
    def create_namespace(self, namespace: str) -> bool:
        """Create a Kubernetes namespace"""
        
        try:
            subprocess.run(
                ["kubectl", "create", "namespace", namespace, "--dry-run=client", "-o", "yaml"],
                capture_output=True,
                text=True,
                check=True
            )
            subprocess.run(
                ["kubectl", "apply", "-f", "-"],
                input=subprocess.run(
                    ["kubectl", "create", "namespace", namespace, "--dry-run=client", "-o", "yaml"],
                    capture_output=True,
                    text=True,
                    check=True
                ).stdout,
                capture_output=True,
                text=True,
                check=True
            )
            console.print(f"[green]Namespace {namespace} ready[/green]")
            return True
        except subprocess.CalledProcessError as e:
            console.print(f"[red]Failed to create namespace: {e.stderr}[/red]")
            return False
    
    def install_or_upgrade(self, release: HelmRelease) -> bool:
        """Install or upgrade a Helm release"""
        
        console.print(f"[bold blue]Deploying {release.name} to {release.namespace}...[/bold blue]")
        
        # Create namespace
        self.create_namespace(release.namespace)
        
        # Add repository if specified
        if release.repo:
            repo_name = release.chart.split('/')[0]
            if not self.add_repo(repo_name, release.repo):
                return False
        
        # Prepare values file if provided
        values_file = None
        if release.values:
            values_file = self.charts_dir / f"{release.name}-values.yaml"
            with open(values_file, 'w') as f:
                yaml.dump(release.values, f, default_flow_style=False)
        
        # Build helm command
        cmd = [
            "helm", "upgrade", "--install",
            release.name,
            release.chart,
            "--namespace", release.namespace,
            "--create-namespace"
        ]
        
        if release.version:
            cmd.extend(["--version", release.version])
        
        if values_file:
            cmd.extend(["--values", str(values_file)])
        
        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            console.print(f"[green]{release.name} deployed successfully![/green]")
            return True
        except subprocess.CalledProcessError as e:
            console.print(f"[red]Failed to deploy {release.name}: {e.stderr}[/red]")
            return False
    
    def uninstall(self, name: str, namespace: str) -> bool:
        """Uninstall a Helm release"""
        
        console.print(f"[yellow]Uninstalling {name} from {namespace}...[/yellow]")
        
        try:
            subprocess.run(
                ["helm", "uninstall", name, "--namespace", namespace],
                capture_output=True,
                text=True,
                check=True
            )
            console.print(f"[green]{name} uninstalled successfully[/green]")
            return True
        except subprocess.CalledProcessError as e:
            console.print(f"[red]Failed to uninstall {name}: {e.stderr}[/red]")
            return False
    
    def list_releases(self, namespace: Optional[str] = None) -> List[Dict]:
        """List Helm releases"""
        
        cmd = ["helm", "list", "-o", "json"]
        if namespace:
            cmd.extend(["--namespace", namespace])
        else:
            cmd.append("--all-namespaces")
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            import json
            return json.loads(result.stdout)
        except (subprocess.CalledProcessError, json.JSONDecodeError):
            return []
    
    def get_values(self, name: str, namespace: str) -> Optional[Dict]:
        """Get values for a Helm release"""
        
        try:
            result = subprocess.run(
                ["helm", "get", "values", name, "--namespace", namespace, "-o", "json"],
                capture_output=True,
                text=True,
                check=True
            )
            import json
            return json.loads(result.stdout)
        except (subprocess.CalledProcessError, json.JSONDecodeError):
            return None


class ObservabilityStack:
    """Deploys the observability stack (Prometheus + Loki + Grafana)"""
    
    def __init__(self, helm_manager: HelmManager):
        self.helm = helm_manager
    
    def deploy_prometheus(self) -> bool:
        """Deploy Prometheus with Grafana"""
        
        values = {
            "server": {
                "persistentVolume": {
                    "enabled": True,
                    "size": "10Gi"
                },
                "retention": "15d"
            },
            "alertmanager": {
                "enabled": True,
                "persistence": {
                    "enabled": True,
                    "size": "2Gi"
                }
            },
            "pushgateway": {
                "enabled": True
            },
            "nodeExporter": {
                "enabled": True
            },
            "service": {
                "type": "NodePort",
                "nodePort": 30090
            }
        }
        
        release = HelmRelease(
            name="prometheus",
            chart="prometheus-community/kube-prometheus-stack",
            namespace="monitoring",
            repo="https://prometheus-community.github.io/helm-charts",
            values=values
        )
        
        return self.helm.install_or_upgrade(release)
    
    def deploy_loki(self) -> bool:
        """Deploy Loki for log aggregation"""
        
        values = {
            "loki": {
                "enabled": True,
                "persistence": {
                    "enabled": True,
                    "size": "10Gi"
                }
            },
            "promtail": {
                "enabled": True,
                "config": {
                    "clients": [{
                        "url": "http://loki:3100/loki/api/v1/push"
                    }]
                }
            },
            "grafana": {
                "enabled": False  # Using Grafana from kube-prometheus-stack
            }
        }
        
        release = HelmRelease(
            name="loki",
            chart="grafana/loki-stack",
            namespace="monitoring",
            repo="https://grafana.github.io/helm-charts",
            values=values
        )
        
        return self.helm.install_or_upgrade(release)
    
    def deploy_all(self) -> bool:
        """Deploy complete observability stack"""
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            
            task = progress.add_task("Deploying observability stack...", total=2)
            
            if not self.deploy_prometheus():
                return False
            progress.update(task, advance=1)
            
            if not self.deploy_loki():
                return False
            progress.update(task, advance=1)
        
        console.print("[bold green]Observability stack deployed successfully![/bold green]")
        console.print("\n[bold]Access points:[/bold]")
        console.print("  Prometheus: http://localhost:9090")
        console.print("  Grafana: http://localhost:3000")
        console.print("  Loki: http://localhost:3100")
        
        return True


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Helm Manager for Project Aether")
    parser.add_argument("action", choices=["deploy-observability", "list", "uninstall"],
                       help="Action to perform")
    parser.add_argument("--kubeconfig", help="Path to kubeconfig")
    
    args = parser.parse_args()
    
    helm = HelmManager(args.kubeconfig)
    
    if args.action == "deploy-observability":
        stack = ObservabilityStack(helm)
        stack.deploy_all()
    elif args.action == "list":
        releases = helm.list_releases()
        for release in releases:
            console.print(f"  {release['name']} ({release['chart']}) in {release['namespace']}")
    elif args.action == "uninstall":
        name = input("Release name: ")
        namespace = input("Namespace: ")
        helm.uninstall(name, namespace)
