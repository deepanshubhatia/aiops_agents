"""
Kind Cluster Management for Project Aether
Manages local Kubernetes clusters for development and testing
"""
import subprocess
import yaml
import json
from pathlib import Path
from typing import Optional, List, Dict
from rich.console import Console

console = Console()


class KindClusterManager:
    """Manages Kind (Kubernetes in Docker) clusters"""
    
    def __init__(self, cluster_name: str = "aether-cluster"):
        self.cluster_name = cluster_name
        self.config_dir = Path("infrastructure/kind")
        self.config_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_config(self, 
                       control_plane_nodes: int = 1,
                       worker_nodes: int = 2,
                       enable_ingress: bool = True) -> Dict:
        """Generate Kind cluster configuration"""
        
        config = {
            "kind": "Cluster",
            "apiVersion": "kind.x-k8s.io/v1alpha4",
            "name": self.cluster_name,
            "nodes": []
        }
        
        # Control plane nodes
        for i in range(control_plane_nodes):
            node = {
                "role": "control-plane",
                "kubeadmConfigPatches": [
                    "kind: InitConfiguration\n" +
                    "nodeRegistration:\n" +
                    "  kubeletExtraArgs:\n" +
                    "    node-labels: \"ingress-ready=true\"\n"
                ]
            }
            if enable_ingress and i == 0:
                node["extraPortMappings"] = [
                    {
                        "containerPort": 80,
                        "hostPort": 8080,
                        "protocol": "TCP"
                    },
                    {
                        "containerPort": 443,
                        "hostPort": 8443,
                        "protocol": "TCP"
                    }
                ]
            config["nodes"].append(node)
        
        # Worker nodes
        for i in range(worker_nodes):
            config["nodes"].append({
                "role": "worker",
                "labels": {
                    "node-type": "worker",
                    "zone": f"zone-{i % 3}"
                }
            })
        
        return config
    
    def create_cluster(self, 
                      control_plane_nodes: int = 1,
                      worker_nodes: int = 2,
                      enable_ingress: bool = True) -> bool:
        """Create a Kind cluster"""
        
        console.print(f"[bold blue]Creating Kind cluster: {self.cluster_name}[/bold blue]")
        
        # Generate and save config
        config = self.generate_config(control_plane_nodes, worker_nodes, enable_ingress)
        config_path = self.config_dir / f"{self.cluster_name}-config.yaml"
        
        with open(config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
        
        console.print(f"[green]Generated config: {config_path}[/green]")
        
        # Create cluster
        try:
            result = subprocess.run(
                ["kind", "create", "cluster", 
                 "--name", self.cluster_name,
                 "--config", str(config_path),
                 "--wait", "300s"],
                capture_output=True,
                text=True,
                check=True
            )
            console.print(f"[green]Cluster created successfully![/green]")
            return True
        except subprocess.CalledProcessError as e:
            console.print(f"[red]Failed to create cluster: {e.stderr}[/red]")
            return False
    
    def delete_cluster(self) -> bool:
        """Delete the Kind cluster"""
        
        console.print(f"[bold yellow]Deleting Kind cluster: {self.cluster_name}[/bold yellow]")
        
        try:
            result = subprocess.run(
                ["kind", "delete", "cluster", "--name", self.cluster_name],
                capture_output=True,
                text=True,
                check=True
            )
            console.print(f"[green]Cluster deleted successfully![/green]")
            return True
        except subprocess.CalledProcessError as e:
            console.print(f"[red]Failed to delete cluster: {e.stderr}[/red]")
            return False
    
    def get_cluster_info(self) -> Optional[Dict]:
        """Get cluster information"""
        
        try:
            # Get nodes
            nodes_result = subprocess.run(
                ["kubectl", "get", "nodes", "-o", "json"],
                capture_output=True,
                text=True,
                check=True
            )
            nodes = json.loads(nodes_result.stdout)
            
            # Get contexts
            context_result = subprocess.run(
                ["kubectl", "config", "current-context"],
                capture_output=True,
                text=True,
                check=True
            )
            
            return {
                "name": self.cluster_name,
                "current_context": context_result.stdout.strip(),
                "nodes": len(nodes.get("items", [])),
                "status": "running"
            }
        except subprocess.CalledProcessError:
            return None
    
    def list_clusters(self) -> List[str]:
        """List all Kind clusters"""
        
        try:
            result = subprocess.run(
                ["kind", "get", "clusters"],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip().split('\n') if result.stdout.strip() else []
        except subprocess.CalledProcessError:
            return []
    
    def export_kubeconfig(self) -> bool:
        """Export kubeconfig for the cluster"""
        
        try:
            subprocess.run(
                ["kind", "export", "kubeconfig", "--name", self.cluster_name],
                capture_output=True,
                text=True,
                check=True
            )
            console.print(f"[green]Kubeconfig exported for {self.cluster_name}[/green]")
            return True
        except subprocess.CalledProcessError as e:
            console.print(f"[red]Failed to export kubeconfig: {e.stderr}[/red]")
            return False


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Kind Cluster Manager for Project Aether")
    parser.add_argument("action", choices=["create", "delete", "info", "list"],
                       help="Action to perform")
    parser.add_argument("--name", default="aether-cluster", help="Cluster name")
    parser.add_argument("--workers", type=int, default=2, help="Number of worker nodes")
    parser.add_argument("--control-planes", type=int, default=1, help="Number of control plane nodes")
    
    args = parser.parse_args()
    
    manager = KindClusterManager(args.name)
    
    if args.action == "create":
        manager.create_cluster(args.control_planes, args.workers)
    elif args.action == "delete":
        manager.delete_cluster()
    elif args.action == "info":
        info = manager.get_cluster_info()
        if info:
            console.print(json.dumps(info, indent=2))
        else:
            console.print("[red]Cluster not found or not running[/red]")
    elif args.action == "list":
        clusters = manager.list_clusters()
        console.print("[bold]Available clusters:[/bold]")
        for cluster in clusters:
            console.print(f"  - {cluster}")
