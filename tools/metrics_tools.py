"""
Metrics and Logging Tools for Project Aether
Integrates with Prometheus and Loki
"""
import requests
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import json
from config.settings import settings


class PrometheusClient:
    """Client for querying Prometheus metrics"""
    
    def __init__(self, base_url: str = None):
        self.base_url = base_url or settings.prometheus_url
        self.api_url = f"{self.base_url}/api/v1"
    
    def query(self, query_string: str, time: datetime = None) -> Dict:
        """Execute an instant query"""
        
        params = {"query": query_string}
        if time:
            params["time"] = time.timestamp()
        
        try:
            response = requests.get(
                f"{self.api_url}/query",
                params=params,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }
    
    def query_range(self, 
                    query_string: str,
                    start: datetime,
                    end: datetime,
                    step: str = "15s") -> Dict:
        """Execute a range query"""
        
        params = {
            "query": query_string,
            "start": start.timestamp(),
            "end": end.timestamp(),
            "step": step
        }
        
        try:
            response = requests.get(
                f"{self.api_url}/query_range",
                params=params,
                timeout=60
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }
    
    def get_series(self, match: List[str], 
                   start: datetime = None,
                   end: datetime = None) -> Dict:
        """Get time series that match label selectors"""
        
        params = {"match[]": match}
        if start:
            params["start"] = start.timestamp()
        if end:
            params["end"] = end.timestamp()
        
        try:
            response = requests.get(
                f"{self.api_url}/series",
                params=params,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }
    
    def get_labels(self) -> Dict:
        """Get all label names"""
        
        try:
            response = requests.get(
                f"{self.api_url}/labels",
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }


async def query_metrics(service_name: str,
                       metric_name: str = None,
                       duration: str = "1h") -> Dict:
    """Query Prometheus metrics for a specific service
    
    Args:
        service_name: Name of the service
        metric_name: Specific metric to query (e.g., 'cpu_usage', 'memory_usage')
        duration: Time range (e.g., '1h', '30m', '24h')
    """
    
    client = PrometheusClient()
    
    # Parse duration
    duration_map = {
        "1h": timedelta(hours=1),
        "30m": timedelta(minutes=30),
        "15m": timedelta(minutes=15),
        "5m": timedelta(minutes=5),
        "24h": timedelta(hours=24),
        "7d": timedelta(days=7)
    }
    
    time_delta = duration_map.get(duration, timedelta(hours=1))
    end_time = datetime.now()
    start_time = end_time - time_delta
    
    # Map metric names to Prometheus queries
    metric_queries = {
        "cpu_usage": f'rate(container_cpu_usage_seconds_total{{pod=~"{service_name}.*"}}[5m]) * 100',
        "memory_usage": f'container_memory_usage_bytes{{pod=~"{service_name}.*"}} / 1024 / 1024',
        "request_rate": f'rate(http_requests_total{{service="{service_name}"}}[5m])',
        "error_rate": f'rate(http_requests_total{{service="{service_name}",status=~"5.."}}[5m])',
        "latency_p50": f'histogram_quantile(0.5, rate(http_request_duration_seconds_bucket{{service="{service_name}"}}[5m]))',
        "latency_p99": f'histogram_quantile(0.99, rate(http_request_duration_seconds_bucket{{service="{service_name}"}}[5m]))',
        "restart_count": f'kube_pod_container_status_restarts_total{{pod=~"{service_name}.*"}}',
        "disk_usage": f'container_fs_usage_bytes{{pod=~"{service_name}.*"}} / container_fs_limit_bytes{{pod=~"{service_name}.*"}} * 100',
        "network_rx": f'rate(container_network_receive_bytes_total{{pod=~"{service_name}.*"}}[5m])',
        "network_tx": f'rate(container_network_transmit_bytes_total{{pod=~"{service_name}.*"}}[5m])'
    }
    
    if metric_name and metric_name in metric_queries:
        query_string = metric_queries[metric_name]
    else:
        # Generic query for all metrics related to the service
        query_string = f'{{pod=~"{service_name}.*"}}'
    
    result = client.query_range(query_string, start_time, end_time)
    
    # Process results
    processed_data = {
        "service": service_name,
        "metric": metric_name or "all",
        "duration": duration,
        "data": [],
        "summary": {}
    }
    
    if result.get("status") == "success" and "data" in result:
        data = result["data"]
        
        if data.get("resultType") == "matrix":
            for series in data.get("result", []):
                metric_labels = series.get("metric", {})
                values = series.get("values", [])
                
                if values:
                    numeric_values = [v[1] for v in values if isinstance(v[1], (int, float, str))]
                    if numeric_values:
                        try:
                            numeric_values = [float(v) for v in numeric_values]
                            processed_data["summary"] = {
                                "current": numeric_values[-1] if numeric_values else None,
                                "min": min(numeric_values) if numeric_values else None,
                                "max": max(numeric_values) if numeric_values else None,
                                "avg": sum(numeric_values) / len(numeric_values) if numeric_values else None
                            }
                        except (ValueError, TypeError):
                            pass
                
                processed_data["data"].append({
                    "labels": metric_labels,
                    "values": values
                })
    else:
        processed_data["error"] = result.get("error", "Unknown error")
    
    return processed_data


async def get_service_metrics_summary(service_name: str,
                                      namespace: str = "default") -> Dict:
    """Get a summary of all key metrics for a service"""
    
    metrics_to_query = [
        "cpu_usage",
        "memory_usage",
        "request_rate",
        "error_rate",
        "latency_p99",
        "restart_count"
    ]
    
    summary = {
        "service": service_name,
        "namespace": namespace,
        "timestamp": datetime.now().isoformat(),
        "metrics": {}
    }
    
    for metric in metrics_to_query:
        result = await query_metrics(service_name, metric, duration="5m")
        if "summary" in result and result["summary"]:
            summary["metrics"][metric] = result["summary"].get("current")
    
    # Calculate health score
    health_score = 100
    alerts = []
    
    if summary["metrics"].get("cpu_usage", 0) > 80:
        health_score -= 20
        alerts.append("High CPU usage")
    
    if summary["metrics"].get("memory_usage", 0) > 80:
        health_score -= 20
        alerts.append("High memory usage")
    
    if summary["metrics"].get("error_rate", 0) > 0.01:  # 1% error rate
        health_score -= 30
        alerts.append("Elevated error rate")
    
    if summary["metrics"].get("restart_count", 0) > 5:
        health_score -= 15
        alerts.append("Multiple pod restarts")
    
    summary["health_score"] = max(0, health_score)
    summary["alerts"] = alerts
    summary["status"] = "healthy" if health_score >= 80 else "degraded" if health_score >= 50 else "critical"
    
    return summary


class LokiClient:
    """Client for querying Loki logs"""
    
    def __init__(self, base_url: str = None):
        self.base_url = base_url or settings.loki_url
    
    def query(self, 
              query: str,
              limit: int = 100,
              start: datetime = None,
              end: datetime = None) -> Dict:
        """Query Loki logs"""
        
        params = {
            "query": query,
            "limit": limit
        }
        
        if start:
            params["start"] = int(start.timestamp() * 1e9)  # Nanoseconds
        if end:
            params["end"] = int(end.timestamp() * 1e9)
        
        try:
            response = requests.get(
                f"{self.base_url}/loki/api/v1/query_range",
                params=params,
                timeout=60
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }


async def query_logs(service_name: str,
                    namespace: str = "default",
                    level: str = None,
                    limit: int = 100,
                    duration: str = "1h") -> Dict:
    """Query Loki logs for a service
    
    Args:
        service_name: Name of the service
        namespace: Kubernetes namespace
        level: Log level filter (e.g., 'error', 'warn', 'info')
        limit: Maximum number of log lines
        duration: Time range (e.g., '1h', '30m', '24h')
    """
    
    client = LokiClient()
    
    # Parse duration
    duration_map = {
        "1h": timedelta(hours=1),
        "30m": timedelta(minutes=30),
        "15m": timedelta(minutes=15),
        "5m": timedelta(minutes=5),
        "24h": timedelta(hours=24),
        "7d": timedelta(days=7)
    }
    
    time_delta = duration_map.get(duration, timedelta(hours=1))
    end_time = datetime.now()
    start_time = end_time - time_delta
    
    # Build LogQL query
    query_parts = [
        f'{{app="{service_name}"}}',
        f'{{namespace="{namespace}"}}'
    ]
    
    if level:
        query_parts.append(f'{{level="{level}"}}')
    
    query = " |= \"\" ".join(query_parts) if query_parts else '{job="default"}'
    
    result = client.query(query, limit=limit, start=start_time, end=end_time)
    
    # Process results
    processed_data = {
        "service": service_name,
        "namespace": namespace,
        "level_filter": level,
        "duration": duration,
        "logs": [],
        "count": 0,
        "error_patterns": []
    }
    
    if result.get("status") == "success" and "data" in result:
        data = result["data"]
        
        if "result" in data:
            for stream in data["result"]:
                labels = stream.get("stream", {})
                values = stream.get("values", [])
                
                for timestamp, log_line in values:
                    processed_data["logs"].append({
                        "timestamp": datetime.fromtimestamp(int(timestamp) / 1e9).isoformat(),
                        "level": labels.get("level", "unknown"),
                        "message": log_line,
                        "pod": labels.get("pod", "unknown")
                    })
            
            processed_data["count"] = len(processed_data["logs"])
            
            # Extract error patterns
            error_logs = [log for log in processed_data["logs"] 
                         if log["level"] in ["error", "ERROR", "Error"]]
            
            if error_logs:
                # Simple error pattern extraction
                patterns = {}
                for log in error_logs:
                    msg = log["message"]
                    # Extract first 50 chars as pattern key
                    pattern_key = msg[:50]
                    if pattern_key in patterns:
                        patterns[pattern_key]["count"] += 1
                    else:
                        patterns[pattern_key] = {
                            "pattern": pattern_key,
                            "count": 1,
                            "example": msg[:200]
                        }
                
                processed_data["error_patterns"] = sorted(
                    patterns.values(),
                    key=lambda x: x["count"],
                    reverse=True
                )[:5]  # Top 5 error patterns
    else:
        processed_data["error"] = result.get("error", "Unknown error")
    
    return processed_data


async def analyze_logs(service_name: str,
                       namespace: str = "default",
                       duration: str = "1h") -> Dict:
    """Analyze logs for patterns and anomalies"""
    
    # Get error logs
    error_logs = await query_logs(
        service_name=service_name,
        namespace=namespace,
        level="error",
        limit=500,
        duration=duration
    )
    
    # Get warn logs
    warn_logs = await query_logs(
        service_name=service_name,
        namespace=namespace,
        level="warn",
        limit=500,
        duration=duration
    )
    
    analysis = {
        "service": service_name,
        "namespace": namespace,
        "duration": duration,
        "summary": {
            "total_logs": 0,
            "error_count": error_logs.get("count", 0),
            "warn_count": warn_logs.get("count", 0),
            "error_rate": 0
        },
        "error_patterns": error_logs.get("error_patterns", []),
        "recommendations": []
    }
    
    analysis["summary"]["total_logs"] = (
        analysis["summary"]["error_count"] + 
        analysis["summary"]["warn_count"]
    )
    
    # Generate recommendations
    if analysis["summary"]["error_count"] > 100:
        analysis["recommendations"].append({
            "severity": "high",
            "message": f"High error count ({analysis['summary']['error_count']}) - investigate immediately"
        })
    
    if analysis["error_patterns"]:
        top_error = analysis["error_patterns"][0]
        analysis["recommendations"].append({
            "severity": "medium",
            "message": f"Most frequent error ({top_error['count']} occurrences): {top_error['pattern']}"
        })
    
    return analysis
