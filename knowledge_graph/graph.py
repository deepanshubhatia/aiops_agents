"""
Knowledge Graph Module for Project Aether
Manages Neo4j database for system topology and dependency mapping
"""
from neo4j import GraphDatabase, Driver, Session
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime
import json
from config.settings import settings


@dataclass
class Service:
    """Represents a microservice in the knowledge graph"""
    name: str
    namespace: str
    service_type: str  # e.g., 'frontend', 'backend', 'database'
    labels: Dict[str, str]
    status: str = "unknown"
    created_at: Optional[datetime] = None


@dataclass
class Dependency:
    """Represents a dependency relationship between services"""
    source: str
    target: str
    dependency_type: str  # e.g., 'calls', 'uses', 'depends_on'
    protocol: str = "http"
    port: int = 80
    metrics: Optional[Dict[str, float]] = None


@dataclass
class Metric:
    """Represents a metric associated with a service"""
    service_name: str
    metric_name: str
    value: float
    timestamp: datetime
    labels: Optional[Dict[str, str]] = None


class KnowledgeGraph:
    """Neo4j-based knowledge graph for AIOps"""
    
    def __init__(self, 
                 uri: str = None,
                 user: str = None,
                 password: str = None):
        self.uri = uri or settings.neo4j_uri
        self.user = user or settings.neo4j_user
        self.password = password or settings.neo4j_password
        self.driver: Optional[Driver] = None
        
    def connect(self) -> bool:
        """Establish connection to Neo4j"""
        try:
            self.driver = GraphDatabase.driver(
                self.uri, 
                auth=(self.user, self.password)
            )
            # Verify connection
            self.driver.verify_connectivity()
            return True
        except Exception as e:
            print(f"Failed to connect to Neo4j: {e}")
            return False
    
    def close(self):
        """Close Neo4j connection"""
        if self.driver:
            self.driver.close()
            self.driver = None
    
    def init_schema(self):
        """Initialize database schema with constraints and indexes"""
        with self.driver.session() as session:
            # Create constraints for unique nodes
            session.run("""
                CREATE CONSTRAINT service_name IF NOT EXISTS
                FOR (s:Service) REQUIRE s.name IS UNIQUE
            """)
            
            session.run("""
                CREATE CONSTRAINT service_namespace IF NOT EXISTS
                FOR (s:Service) REQUIRE (s.name, s.namespace) IS UNIQUE
            """)
            
            # Create indexes
            session.run("""
                CREATE INDEX service_type_idx IF NOT EXISTS
                FOR (s:Service) ON (s.service_type)
            """)
            
            session.run("""
                CREATE INDEX service_status_idx IF NOT EXISTS
                FOR (s:Service) ON (s.status)
            """)
            
            session.run("""
                CREATE INDEX metric_timestamp_idx IF NOT EXISTS
                FOR (m:Metric) ON (m.timestamp)
            """)
    
    def add_service(self, service: Service) -> bool:
        """Add or update a service node"""
        with self.driver.session() as session:
            try:
                session.run("""
                    MERGE (s:Service {name: $name, namespace: $namespace})
                    SET s.service_type = $service_type,
                        s.labels = $labels,
                        s.status = $status,
                        s.updated_at = datetime()
                    RETURN s
                """, {
                    "name": service.name,
                    "namespace": service.namespace,
                    "service_type": service.service_type,
                    "labels": json.dumps(service.labels),
                    "status": service.status
                })
                return True
            except Exception as e:
                print(f"Failed to add service {service.name}: {e}")
                return False
    
    def add_dependency(self, dependency: Dependency) -> bool:
        """Add a dependency relationship between services"""
        with self.driver.session() as session:
            try:
                session.run("""
                    MATCH (source:Service {name: $source})
                    MATCH (target:Service {name: $target})
                    MERGE (source)-[r:DEPENDS_ON]->(target)
                    SET r.dependency_type = $dependency_type,
                        r.protocol = $protocol,
                        r.port = $port,
                        r.updated_at = datetime()
                    RETURN r
                """, {
                    "source": dependency.source,
                    "target": dependency.target,
                    "dependency_type": dependency.dependency_type,
                    "protocol": dependency.protocol,
                    "port": dependency.port
                })
                return True
            except Exception as e:
                print(f"Failed to add dependency: {e}")
                return False
    
    def add_metric(self, metric: Metric) -> bool:
        """Add a metric to a service"""
        with self.driver.session() as session:
            try:
                session.run("""
                    MATCH (s:Service {name: $service_name})
                    CREATE (m:Metric {
                        name: $metric_name,
                        value: $value,
                        timestamp: $timestamp,
                        labels: $labels
                    })
                    MERGE (s)-[r:HAS_METRIC]->(m)
                    SET r.timestamp = datetime()
                """, {
                    "service_name": metric.service_name,
                    "metric_name": metric.metric_name,
                    "value": metric.value,
                    "timestamp": metric.timestamp.isoformat(),
                    "labels": json.dumps(metric.labels) if metric.labels else "{}"
                })
                return True
            except Exception as e:
                print(f"Failed to add metric: {e}")
                return False
    
    def get_service(self, name: str, namespace: str = "default") -> Optional[Dict]:
        """Retrieve a service by name and namespace"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (s:Service {name: $name, namespace: $namespace})
                RETURN s
            """, {"name": name, "namespace": namespace})
            
            record = result.single()
            if record:
                return dict(record["s"])
            return None
    
    def get_dependencies(self, service_name: str, 
                        direction: str = "both") -> List[Dict]:
        """Get dependencies for a service
        
        Args:
            service_name: Name of the service
            direction: 'upstream', 'downstream', or 'both'
        """
        with self.driver.session() as session:
            if direction == "upstream":
                # Services that this service depends on
                result = session.run("""
                    MATCH (s:Service {name: $name})-[r:DEPENDS_ON]->(target:Service)
                    RETURN target.name as name, target.namespace as namespace,
                           r.dependency_type as type, r.protocol as protocol
                """, {"name": service_name})
            elif direction == "downstream":
                # Services that depend on this service
                result = session.run("""
                    MATCH (source:Service)-[r:DEPENDS_ON]->(s:Service {name: $name})
                    RETURN source.name as name, source.namespace as namespace,
                           r.dependency_type as type, r.protocol as protocol
                """, {"name": service_name})
            else:  # both
                result = session.run("""
                    MATCH (s:Service {name: $name})
                    OPTIONAL MATCH (s)-[r1:DEPENDS_ON]->(upstream:Service)
                    OPTIONAL MATCH (downstream:Service)-[r2:DEPENDS_ON]->(s)
                    RETURN upstream.name as upstream_name, 
                           downstream.name as downstream_name,
                           r1.dependency_type as upstream_type,
                           r2.dependency_type as downstream_type
                """, {"name": service_name})
            
            return [dict(record) for record in result]
    
    def multi_hop_analysis(self, start_service: str, 
                          max_hops: int = 3,
                          min_impact_score: float = 0.5) -> List[Dict]:
        """Perform multi-hop root cause analysis
        
        Finds potential root causes for issues affecting the start_service
        by traversing the dependency graph and analyzing impact scores.
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH path = (start:Service {name: $start_service})
                             -[:DEPENDS_ON*1..$max_hops]->(root:Service)
                WHERE ALL(n IN nodes(path) WHERE n.status <> 'healthy')
                WITH start, root, path,
                     length(path) as hops,
                     reduce(score = 1.0, r IN relationships(path) | 
                            score * (CASE WHEN r.metrics IS NOT NULL 
                                    THEN 0.8 ELSE 0.9 END)) as impact_score
                WHERE impact_score >= $min_score
                RETURN root.name as service,
                       root.namespace as namespace,
                       root.status as status,
                       hops,
                       impact_score,
                       [n IN nodes(path) | n.name] as path_services
                ORDER BY impact_score DESC, hops ASC
            """, {
                "start_service": start_service,
                "max_hops": max_hops,
                "min_score": min_impact_score
            })
            
            return [dict(record) for record in result]
    
    def get_critical_path(self, source: str, target: str) -> List[str]:
        """Find the critical path between two services"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH path = shortestPath(
                    (source:Service {name: $source})
                    -[:DEPENDS_ON*]->
                    (target:Service {name: $target})
                )
                RETURN [n IN nodes(path) | n.name] as path
            """, {"source": source, "target": target})
            
            record = result.single()
            if record:
                return record["path"]
            return []
    
    def get_service_topology(self, namespace: Optional[str] = None) -> Dict:
        """Get complete service topology for visualization"""
        with self.driver.session() as session:
            # Get all services
            if namespace:
                services_result = session.run("""
                    MATCH (s:Service {namespace: $namespace})
                    RETURN s.name as name, s.namespace as namespace,
                           s.service_type as type, s.status as status
                """, {"namespace": namespace})
            else:
                services_result = session.run("""
                    MATCH (s:Service)
                    RETURN s.name as name, s.namespace as namespace,
                           s.service_type as type, s.status as status
                """)
            
            services = [dict(record) for record in services_result]
            
            # Get all dependencies
            deps_result = session.run("""
                MATCH (s:Service)-[r:DEPENDS_ON]->(t:Service)
                RETURN s.name as source, t.name as target,
                       r.dependency_type as type
            """)
            
            dependencies = [dict(record) for record in deps_result]
            
            return {
                "services": services,
                "dependencies": dependencies
            }
    
    def update_service_status(self, name: str, 
                             namespace: str, 
                             status: str,
                             metrics: Optional[Dict] = None) -> bool:
        """Update service status and metrics"""
        with self.driver.session() as session:
            try:
                session.run("""
                    MATCH (s:Service {name: $name, namespace: $namespace})
                    SET s.status = $status,
                        s.last_updated = datetime()
                """, {
                    "name": name,
                    "namespace": namespace,
                    "status": status
                })
                
                # Add metrics if provided
                if metrics:
                    for metric_name, value in metrics.items():
                        self.add_metric(Metric(
                            service_name=name,
                            metric_name=metric_name,
                            value=value,
                            timestamp=datetime.now()
                        ))
                
                return True
            except Exception as e:
                print(f"Failed to update service status: {e}")
                return False
    
    def clear_database(self) -> bool:
        """Clear all data from the database (use with caution!)"""
        with self.driver.session() as session:
            try:
                session.run("MATCH (n) DETACH DELETE n")
                return True
            except Exception as e:
                print(f"Failed to clear database: {e}")
                return False
    
    def sync_from_kubernetes(self, k8s_data: List[Dict]):
        """Sync service topology from Kubernetes data"""
        for service_data in k8s_data:
            service = Service(
                name=service_data["name"],
                namespace=service_data.get("namespace", "default"),
                service_type=service_data.get("type", "unknown"),
                labels=service_data.get("labels", {}),
                status=service_data.get("status", "unknown")
            )
            self.add_service(service)
            
            # Add dependencies
            for dep in service_data.get("dependencies", []):
                dependency = Dependency(
                    source=service.name,
                    target=dep["target"],
                    dependency_type=dep.get("type", "depends_on"),
                    protocol=dep.get("protocol", "http"),
                    port=dep.get("port", 80)
                )
                self.add_dependency(dependency)


# Singleton instance
knowledge_graph = KnowledgeGraph()
