"""
Kubernetes Tools for Project Aether
Provides kubectl and Kubernetes API operations for agents
"""
import subprocess
import json
from typing import Dict, List, Optional, Any
from kubernetes import client, config
from kubernetes.client import V1Pod, V1Deployment, V1Service
import yaml


def load_kubeconfig(kubeconfig_path: str = None):
    """Load Kubernetes configuration"""
    try:
        if kubeconfig_path:
            config.load_kube_config(config_file=kubeconfig_path)
        else:
            config.load_kube_config()
        return True
    except Exception as e:
        print(f"Failed to load kubeconfig: {e}")
        return False


async def get_service_status(service_name: str, namespace: str = "default") -> Dict:
    """Get comprehensive status of a Kubernetes service"""
    
    load_kubeconfig()
    
    v1 = client.CoreV1Api()
    apps_v1 = client.AppsV1Api()
    
    status = {
        "service_name": service_name,
        "namespace": namespace,
        "exists": False,
        "pods": [],
        "deployments": [],
        "restarts": 0,
        "cpu_usage": 0,
        "memory_usage": 0,
        "errors": []
    }
    
    try:
        # Get service
        service = v1.read_namespaced_service(name=service_name, namespace=namespace)
        status["exists"] = True
        status["service_type"] = service.spec.type
        status["cluster_ip"] = service.spec.cluster_ip
        status["ports"] = [
            {"port": p.port, "target_port": p.target_port, "protocol": p.protocol}
            for p in service.spec.ports
        ] if service.spec.ports else []
        
        # Get selector to find related pods
        selector = service.spec.selector
        if selector:
            label_selector = ",".join([f"{k}={v}" for k, v in selector.items()])
            pods = v1.list_namespaced_pod(
                namespace=namespace,
                label_selector=label_selector
            )
            
            total_restarts = 0
            for pod in pods.items:
                pod_info = {
                    "name": pod.metadata.name,
                    "status": pod.status.phase,
                    "ready": all(cs.ready for cs in pod.status.container_statuses) if pod.status.container_statuses else False,
                    "restarts": sum(cs.restart_count for cs in pod.status.container_statuses) if pod.status.container_statuses else 0,
                    "pod_ip": pod.status.pod_ip,
                    "node": pod.spec.node_name
                }
                
                # Calculate restarts
                total_restarts += pod_info["restarts"]
                status["pods"].append(pod_info)
            
            status["restarts"] = total_restarts
            status["ready_pods"] = sum(1 for p in status["pods"] if p["ready"])
            status["total_pods"] = len(status["pods"])
        
        # Get deployments matching the service
        deployments = apps_v1.list_namespaced_deployment(
            namespace=namespace,
            label_selector=label_selector if selector else None
        )
        
        for deployment in deployments.items:
            dep_info = {
                "name": deployment.metadata.name,
                "replicas": deployment.spec.replicas,
                "available_replicas": deployment.status.available_replicas or 0,
                "ready_replicas": deployment.status.ready_replicas or 0,
                "strategy": deployment.spec.strategy.type if deployment.spec.strategy else "Unknown"
            }
            status["deployments"].append(dep_info)
        
    except client.exceptions.ApiException as e:
        status["errors"].append(f"API error: {e.reason}")
    except Exception as e:
        status["errors"].append(f"Error: {str(e)}")
    
    return status


async def get_pod_logs(service_name: str, 
                       namespace: str = "default",
                       tail_lines: int = 100,
                       container: str = None) -> List[Dict]:
    """Get logs from pods of a service"""
    
    load_kubeconfig()
    v1 = client.CoreV1Api()
    
    logs = []
    
    try:
        # Get service to find selector
        service = v1.read_namespaced_service(name=service_name, namespace=namespace)
        selector = service.spec.selector
        
        if selector:
            label_selector = ",".join([f"{k}={v}" for k, v in selector.items()])
            pods = v1.list_namespaced_pod(
                namespace=namespace,
                label_selector=label_selector
            )
            
            for pod in pods.items:
                try:
                    # Get logs for this pod
                    pod_logs = v1.read_namespaced_pod_log(
                        name=pod.metadata.name,
                        namespace=namespace,
                        tail_lines=tail_lines,
                        container=container or pod.spec.containers[0].name
                    )
                    
                    logs.append({
                        "pod_name": pod.metadata.name,
                        "container": container or pod.spec.containers[0].name,
                        "logs": pod_logs.split('\n') if pod_logs else [],
                        "timestamp": pod.metadata.creation_timestamp.isoformat() if pod.metadata.creation_timestamp else None
                    })
                    
                except Exception as e:
                    logs.append({
                        "pod_name": pod.metadata.name,
                        "error": str(e)
                    })
    
    except Exception as e:
        logs.append({
            "error": f"Failed to get logs: {str(e)}"
        })
    
    return logs


async def get_pod_events(service_name: str, 
                         namespace: str = "default",
                         since_seconds: int = 3600) -> List[Dict]:
    """Get Kubernetes events related to a service"""
    
    load_kubeconfig()
    v1 = client.CoreV1Api()
    
    events = []
    
    try:
        # Get events for the namespace
        event_list = v1.list_namespaced_event(
            namespace=namespace,
            field_selector=f"involvedObject.name={service_name}"
        )
        
        for event in event_list.items:
            events.append({
                "type": event.type,
                "reason": event.reason,
                "message": event.message,
                "count": event.count,
                "first_timestamp": event.first_timestamp.isoformat() if event.first_timestamp else None,
                "last_timestamp": event.last_timestamp.isoformat() if event.last_timestamp else None,
                "involved_object": {
                    "kind": event.involved_object.kind,
                    "name": event.involved_object.name
                }
            })
    
    except Exception as e:
        events.append({
            "error": f"Failed to get events: {str(e)}"
        })
    
    return events


async def generate_yaml_patch(resource_type: str,
                              resource_name: str,
                              namespace: str,
                              patches: Dict[str, Any]) -> Dict:
    """Generate Kubernetes YAML patch for resource modification"""
    
    patch = {
        "apiVersion": "",
        "kind": resource_type.capitalize(),
        "metadata": {
            "name": resource_name,
            "namespace": namespace
        },
        "spec": {}
    }
    
    if resource_type == "deployment":
        patch["apiVersion"] = "apps/v1"
        patch["spec"].update(patches)
    elif resource_type == "service":
        patch["apiVersion"] = "v1"
        patch["spec"].update(patches)
    elif resource_type == "configmap":
        patch["apiVersion"] = "v1"
        patch["kind"] = "ConfigMap"
        patch["data"] = patches
        del patch["spec"]
    
    return {
        "yaml": yaml.dump(patch, default_flow_style=False),
        "resource_type": resource_type,
        "resource_name": resource_name,
        "namespace": namespace
    }


async def apply_yaml_patch(yaml_content: str, namespace: str) -> Dict:
    """Apply a YAML patch to Kubernetes using kubectl"""
    
    try:
        # Write YAML to temporary file
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            temp_file = f.name
        
        # Apply using kubectl
        result = subprocess.run(
            ["kubectl", "apply", "-f", temp_file, "-n", namespace],
            capture_output=True,
            text=True,
            check=True
        )
        
        # Clean up temp file
        os.unlink(temp_file)
        
        return {
            "success": True,
            "output": result.stdout,
            "resource_applied": True
        }
        
    except subprocess.CalledProcessError as e:
        return {
            "success": False,
            "error": e.stderr,
            "output": e.stdout
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


async def restart_deployment(deployment_name: str, namespace: str) -> Dict:
    """Restart a Kubernetes deployment by updating rollout"""
    
    try:
        result = subprocess.run(
            ["kubectl", "rollout", "restart", "deployment", deployment_name, "-n", namespace],
            capture_output=True,
            text=True,
            check=True
        )
        
        return {
            "success": True,
            "message": f"Deployment {deployment_name} restarted successfully",
            "output": result.stdout
        }
        
    except subprocess.CalledProcessError as e:
        return {
            "success": False,
            "error": e.stderr
        }


async def get_service_topology() -> Dict:
    """Get complete service topology from Kubernetes"""
    
    load_kubeconfig()
    v1 = client.CoreV1Api()
    
    services = []
    dependencies = []
    
    try:
        # Get all services across all namespaces
        all_services = v1.list_service_for_all_namespaces()
        
        for svc in all_services.items:
            service_info = {
                "name": svc.metadata.name,
                "namespace": svc.metadata.namespace,
                "type": "service",
                "labels": dict(svc.metadata.labels) if svc.metadata.labels else {},
                "status": "active",
                "dependencies": []
            }
            
            # Try to infer dependencies from endpoints or configuration
            # This is a simplified version - in production you'd analyze
            # network policies, service mesh data, etc.
            
            services.append(service_info)
    
    except Exception as e:
        return {
            "error": str(e),
            "services": [],
            "dependencies": []
        }
    
    return {
        "services": services,
        "dependencies": dependencies
    }


async def exec_command_in_pod(pod_name: str,
                               namespace: str,
                               command: List[str],
                               container: str = None) -> Dict:
    """Execute a command inside a Kubernetes pod"""
    
    load_kubeconfig()
    
    try:
        # Build kubectl exec command
        exec_cmd = ["kubectl", "exec", pod_name, "-n", namespace]
        
        if container:
            exec_cmd.extend(["-c", container])
        
        exec_cmd.extend(["--"])
        exec_cmd.extend(command)
        
        result = subprocess.run(
            exec_cmd,
            capture_output=True,
            text=True,
            check=True
        )
        
        return {
            "success": True,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": 0
        }
        
    except subprocess.CalledProcessError as e:
        return {
            "success": False,
            "stdout": e.stdout,
            "stderr": e.stderr,
            "exit_code": e.returncode
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
