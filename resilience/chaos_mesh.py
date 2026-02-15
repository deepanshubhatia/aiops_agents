"""
Chaos Engineering Module for Project Aether
Integrates with Chaos Mesh for automated fault injection and resilience testing
"""
import yaml
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime
import subprocess
from kubernetes import client, config


@dataclass
class ChaosExperiment:
    """Represents a chaos experiment configuration"""
    name: str
    experiment_type: str  # network, pod, stress, io, etc.
    target: str  # Service or deployment name
    namespace: str
    duration: str  # e.g., "5m", "30s"
    parameters: Dict[str, Any]
    expected_behavior: str
    created_at: Optional[datetime] = None


class ChaosMeshManager:
    """Manages Chaos Mesh experiments and fault injection"""
    
    def __init__(self, namespace: str = "chaos-testing"):
        self.namespace = namespace
        self.experiments: List[ChaosExperiment] = []
        
        # Try to load kubernetes config
        try:
            config.load_kube_config()
            self.k8s_client = client.CustomObjectsApi()
            self.available = True
        except Exception as e:
            print(f"Warning: Could not load Kubernetes config: {e}")
            self.k8s_client = None
            self.available = False
    
    def install_chaos_mesh(self) -> bool:
        """Install Chaos Mesh using Helm"""
        
        try:
            # Add Chaos Mesh repo
            subprocess.run(
                ["helm", "repo", "add", "chaos-mesh", "https://charts.chaos-mesh.org"],
                capture_output=True,
                text=True,
                check=True
            )
            
            # Update repos
            subprocess.run(
                ["helm", "repo", "update"],
                capture_output=True,
                text=True,
                check=True
            )
            
            # Install Chaos Mesh
            subprocess.run([
                "helm", "install", "chaos-mesh", "chaos-mesh/chaos-mesh",
                "-n", self.namespace,
                "--create-namespace",
                "--set", "dashboard.create=true"
            ], capture_output=True, text=True, check=True)
            
            print(f"Chaos Mesh installed in namespace: {self.namespace}")
            return True
            
        except subprocess.CalledProcessError as e:
            print(f"Failed to install Chaos Mesh: {e.stderr}")
            return False
    
    def create_network_partition(self, 
                                 target: str,
                                 duration: str = "5m",
                                 direction: str = "both",
                                 namespace: str = "default") -> ChaosExperiment:
        """Create a network partition chaos experiment"""
        
        experiment = ChaosExperiment(
            name=f"network-partition-{target}-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            experiment_type="network-partition",
            target=target,
            namespace=namespace,
            duration=duration,
            parameters={
                "direction": direction,
                "action": "partition"
            },
            expected_behavior="Service should handle network isolation gracefully"
        )
        
        # Generate Chaos Mesh NetworkChaos YAML
        chaos_yaml = f"""
apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: {experiment.name}
  namespace: {self.namespace}
spec:
  action: partition
  mode: all
  selector:
    namespaces:
      - {namespace}
    labelSelectors:
      app: {target}
  direction: {direction}
  duration: {duration}
"""
        
        experiment.chaos_yaml = chaos_yaml
        self.experiments.append(experiment)
        
        return experiment
    
    def create_pod_failure(self,
                         target: str,
                         duration: str = "5m",
                         namespace: str = "default") -> ChaosExperiment:
        """Create a pod failure chaos experiment"""
        
        experiment = ChaosExperiment(
            name=f"pod-failure-{target}-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            experiment_type="pod-failure",
            target=target,
            namespace=namespace,
            duration=duration,
            parameters={
                "action": "pod-failure"
            },
            expected_behavior="System should recover and maintain availability"
        )
        
        chaos_yaml = f"""
apiVersion: chaos-mesh.org/v1alpha1
kind: PodChaos
metadata:
  name: {experiment.name}
  namespace: {self.namespace}
spec:
  action: pod-failure
  mode: all
  selector:
    namespaces:
      - {namespace}
    labelSelectors:
      app: {target}
  duration: {duration}
"""
        
        experiment.chaos_yaml = chaos_yaml
        self.experiments.append(experiment)
        
        return experiment
    
    def create_stress_test(self,
                          target: str,
                          duration: str = "5m",
                          cpu_stress: int = 80,
                          memory_stress: int = 50,
                          namespace: str = "default") -> ChaosExperiment:
        """Create a resource stress chaos experiment"""
        
        experiment = ChaosExperiment(
            name=f"stress-{target}-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            experiment_type="stress",
            target=target,
            namespace=namespace,
            duration=duration,
            parameters={
                "cpu": cpu_stress,
                "memory": memory_stress
            },
            expected_behavior="Service should throttle or scale appropriately"
        )
        
        chaos_yaml = f"""
apiVersion: chaos-mesh.org/v1alpha1
kind: StressChaos
metadata:
  name: {experiment.name}
  namespace: {self.namespace}
spec:
  mode: all
  selector:
    namespaces:
      - {namespace}
    labelSelectors:
      app: {target}
  stressors:
    cpu:
      workers: 1
      load: {cpu_stress}
    memory:
      workers: 1
      size: "{memory_stress}%"
  duration: {duration}
"""
        
        experiment.chaos_yaml = chaos_yaml
        self.experiments.append(experiment)
        
        return experiment
    
    def create_io_delay(self,
                       target: str,
                       duration: str = "5m",
                       delay: str = "100ms",
                       namespace: str = "default") -> ChaosExperiment:
        """Create an I/O delay chaos experiment"""
        
        experiment = ChaosExperiment(
            name=f"io-delay-{target}-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            experiment_type="io-delay",
            target=target,
            namespace=namespace,
            duration=duration,
            parameters={
                "delay": delay,
                "path": "/var/lib/data"
            },
            expected_behavior="Service should handle I/O latency gracefully"
        )
        
        chaos_yaml = f"""
apiVersion: chaos-mesh.org/v1alpha1
kind: IOChaos
metadata:
  name: {experiment.name}
  namespace: {self.namespace}
spec:
  action: latency
  mode: all
  selector:
    namespaces:
      - {namespace}
    labelSelectors:
      app: {target}
  delay: {delay}
  path: /var/lib/data
  duration: {duration}
"""
        
        experiment.chaos_yaml = chaos_yaml
        self.experiments.append(experiment)
        
        return experiment
    
    def apply_experiment(self, experiment: ChaosExperiment) -> bool:
        """Apply a chaos experiment to the cluster"""
        
        if not self.k8s_client:
            print("Kubernetes client not available")
            return False
        
        try:
            # Parse YAML and apply
            yaml_content = yaml.safe_load(experiment.chaos_yaml)
            
            group = yaml_content["apiVersion"].split("/")[0]
            version = yaml_content["apiVersion"].split("/")[1]
            plural = yaml_content["kind"].lower() + "es"  # Basic pluralization
            
            # Create the experiment
            self.k8s_client.create_namespaced_custom_object(
                group=group,
                version=version,
                namespace=self.namespace,
                plural=plural,
                body=yaml_content
            )
            
            print(f"Applied chaos experiment: {experiment.name}")
            experiment.created_at = datetime.now()
            return True
            
        except Exception as e:
            print(f"Failed to apply experiment: {e}")
            return False
    
    def delete_experiment(self, experiment_name: str, experiment_type: str) -> bool:
        """Delete a chaos experiment"""
        
        if not self.k8s_client:
            return False
        
        try:
            plural = experiment_type.lower() + "es"
            group = "chaos-mesh.org"
            version = "v1alpha1"
            
            self.k8s_client.delete_namespaced_custom_object(
                group=group,
                version=version,
                namespace=self.namespace,
                plural=plural,
                name=experiment_name
            )
            
            print(f"Deleted chaos experiment: {experiment_name}")
            return True
            
        except Exception as e:
            print(f"Failed to delete experiment: {e}")
            return False
    
    def list_experiments(self) -> List[Dict]:
        """List all active chaos experiments"""
        
        if not self.k8s_client:
            return []
        
        all_experiments = []
        experiment_types = ["networkchaos", "podchaos", "stresschaos", "iochaos"]
        
        for exp_type in experiment_types:
            try:
                result = self.k8s_client.list_namespaced_custom_object(
                    group="chaos-mesh.org",
                    version="v1alpha1",
                    namespace=self.namespace,
                    plural=exp_type
                )
                
                for item in result.get("items", []):
                    all_experiments.append({
                        "name": item["metadata"]["name"],
                        "type": exp_type,
                        "status": item.get("status", {}).get("phase", "unknown"),
                        "created": item["metadata"]["creationTimestamp"]
                    })
                    
            except Exception as e:
                pass  # Type might not exist
        
        return all_experiments
    
    def run_resilience_test_suite(self,
                                   target: str,
                                   namespace: str = "default") -> Dict:
        """Run a comprehensive resilience test suite"""
        
        results = {
            "target": target,
            "namespace": namespace,
            "start_time": datetime.now().isoformat(),
            "experiments": [],
            "summary": {
                "total": 0,
                "passed": 0,
                "failed": 0
            }
        }
        
        # Create test suite
        experiments_to_run = [
            self.create_network_partition(target, duration="2m", namespace=namespace),
            self.create_pod_failure(target, duration="2m", namespace=namespace),
            self.create_stress_test(target, duration="2m", namespace=namespace),
            self.create_io_delay(target, duration="2m", namespace=namespace)
        ]
        
        for experiment in experiments_to_run:
            result = {
                "name": experiment.name,
                "type": experiment.experiment_type,
                "applied": False,
                "expected": experiment.expected_behavior
            }
            
            if self.apply_experiment(experiment):
                result["applied"] = True
                result["status"] = "running"
                results["summary"]["total"] += 1
            else:
                result["status"] = "failed"
                results["summary"]["failed"] += 1
            
            results["experiments"].append(result)
        
        results["end_time"] = datetime.now().isoformat()
        
        return results
    
    def get_experiment_status(self, experiment_name: str, experiment_type: str) -> Dict:
        """Get status of a specific experiment"""
        
        if not self.k8s_client:
            return {"error": "Kubernetes client not available"}
        
        try:
            plural = experiment_type.lower() + "es"
            
            result = self.k8s_client.get_namespaced_custom_object(
                group="chaos-mesh.org",
                version="v1alpha1",
                namespace=self.namespace,
                plural=plural,
                name=experiment_name
            )
            
            return {
                "name": result["metadata"]["name"],
                "type": experiment_type,
                "phase": result.get("status", {}).get("phase", "unknown"),
                "start_time": result.get("status", {}).get("experimentStartTime"),
                "end_time": result.get("status", {}).get("experimentEndTime")
            }
            
        except Exception as e:
            return {"error": str(e)}


class ResilienceBenchmark:
    """Benchmarks system resilience against various failure scenarios"""
    
    def __init__(self, chaos_manager: ChaosMeshManager):
        self.chaos_manager = chaos_manager
        self.benchmarks = []
    
    def run_benchmark(self,
                     services: List[str],
                     namespace: str = "default",
                     duration_per_test: str = "5m") -> Dict:
        """Run resilience benchmark across multiple services"""
        
        benchmark_result = {
            "timestamp": datetime.now().isoformat(),
            "namespace": namespace,
            "services_tested": [],
            "results": []
        }
        
        for service in services:
            print(f"Running resilience tests for {service}...")
            
            result = self.chaos_manager.run_resilience_test_suite(
                target=service,
                namespace=namespace
            )
            
            benchmark_result["services_tested"].append(service)
            benchmark_result["results"].append(result)
        
        self.benchmarks.append(benchmark_result)
        
        return benchmark_result
    
    def generate_report(self, benchmark_id: int = -1) -> str:
        """Generate a human-readable resilience report"""
        
        if not self.benchmarks:
            return "No benchmarks available"
        
        benchmark = self.benchmarks[benchmark_id]
        
        report = f"""
# Resilience Benchmark Report
Generated: {benchmark['timestamp']}
Namespace: {benchmark['namespace']}

## Services Tested
{', '.join(benchmark['services_tested'])}

## Test Results

"""
        
        for result in benchmark['results']:
            report += f"""### {result['target']}
- Total experiments: {result['summary']['total']}
- Passed: {result['summary']['passed']}
- Failed: {result['summary']['failed']}

**Experiments:**
"""
            for exp in result['experiments']:
                status_icon = "✅" if exp['status'] == 'running' else "❌"
                report += f"- {status_icon} {exp['name']} ({exp['type']}) - {exp['status']}\n"
            
            report += "\n"
        
        return report


# Helper function for quick chaos testing
async def inject_fault(target: str,
                      fault_type: str = "network-partition",
                      duration: str = "5m",
                      namespace: str = "default") -> Dict:
    """Quick function to inject a fault for testing"""
    
    manager = ChaosMeshManager()
    
    experiment_creators = {
        "network-partition": manager.create_network_partition,
        "pod-failure": manager.create_pod_failure,
        "stress": manager.create_stress_test,
        "io-delay": manager.create_io_delay
    }
    
    creator = experiment_creators.get(fault_type)
    if not creator:
        return {"error": f"Unknown fault type: {fault_type}"}
    
    experiment = creator(target, duration=duration, namespace=namespace)
    
    if manager.apply_experiment(experiment):
        return {
            "success": True,
            "experiment_name": experiment.name,
            "type": fault_type,
            "target": target,
            "duration": duration,
            "status": "applied"
        }
    else:
        return {
            "success": False,
            "error": "Failed to apply experiment"
        }
