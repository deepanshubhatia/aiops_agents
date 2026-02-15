# Project Aether

**AIOps Multi-Agent System with Knowledge Graphs and Chaos Engineering**

Project Aether is a comprehensive AIOps platform that combines hierarchical multi-agent orchestration, Neo4j knowledge graphs for system topology, and Chaos Mesh integration for resilience testing. It enables intelligent incident response through automated root cause analysis and remediation.

## Features

- **Multi-Agent Orchestration**: Hierarchical agent system using OpenAI/Google AI SDKs with manual state handoffs
- **Knowledge Graph**: Neo4j-powered system topology mapping with multi-hop root cause analysis
- **Infrastructure Provisioning**: Kind (Kubernetes in Docker) + Helm for cloud-native environments
- **Observability Stack**: Integrated Prometheus, Loki, and Grafana
- **Chaos Engineering**: Automated fault injection using Chaos Mesh
- **Tool Integration**: Specialized tools for metrics, logs, and Kubernetes operations

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    CLI Interface                        │
└────────────────┬────────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────────┐
│              Agent Orchestrator                         │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────────┐   │
│  │ TriageAgent │ │ RootCause   │ │ Remediation     │   │
│  │             │ │  Analyzer   │ │   Advisor       │   │
│  └─────────────┘ └─────────────┘ └─────────────────┘   │
│  ┌─────────────┐                                      │
│  │ Action      │                                      │
│  │ Executor    │                                      │
│  └─────────────┘                                      │
└────────┬──────────────────────────────┬─────────────────┘
         │                            │
┌────────▼────────┐          ┌────────▼────────┐
│   Knowledge     │          │     Tools       │
│    Graph        │          │                 │
│   (Neo4j)       │          │ • k8s_tools     │
│                 │          │ • metrics_tools │
│ • Services      │          │                 │
│ • Dependencies  │          │                 │
│ • Multi-hop     │          │                 │
│   analysis      │          │                 │
└────────┬────────┘          └────────┬────────┘
         │                            │
┌────────▼────────────────────────────▼─────────────┐
│              Infrastructure Layer                   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│  │   Kind   │ │   Helm   │ │Prometheus│          │
│  │ Cluster  │ │  Charts  │ │  + Loki  │          │
│  └──────────┘ └──────────┘ └──────────┘          │
│  ┌──────────┐                                      │
│  │  Chaos   │                                      │
│  │  Mesh    │                                      │
│  └──────────┘                                      │
└─────────────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites

- Python 3.9+
- Docker
- Kind (Kubernetes in Docker)
- Helm
- Neo4j (local or cloud instance)
- OpenAI API key or Google AI API key

### Installation

1. **Clone and setup**:
```bash
git clone <repository>
cd project-aether
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

2. **Configure environment**:
```bash
cp .env.example .env
# Edit .env with your API keys and configurations
```

3. **Create infrastructure**:
```bash
# Create Kind cluster
python main.py infra create-cluster --name aether-cluster --workers 2

# Deploy observability stack
python main.py infra deploy-observability
```

4. **Verify setup**:
```bash
python main.py agents status
```

## Usage

### Infrastructure Management

```bash
# Create a Kind cluster
python main.py infra create-cluster --name my-cluster --workers 3

# Delete cluster
python main.py infra delete-cluster --name my-cluster

# Deploy observability stack (Prometheus, Loki, Grafana)
python main.py infra deploy-observability
```

### Incident Response

```bash
# Run incident response workflow
python main.py agents run-incident \
  --incident-id INC-001 \
  --service frontend-app \
  --namespace production \
  --symptoms "high latency,timeout errors" \
  --provider openai
```

### Knowledge Graph Operations

```bash
# View service dependencies
python main.py knowledge dependencies --service frontend-app --namespace production

# Run root cause analysis
python main.py knowledge root-cause --start-service frontend-app --max-hops 3
```

### Chaos Engineering

```bash
# Inject network partition fault
python main.py chaos inject \
  --target frontend-app \
  --type network-partition \
  --duration 5m \
  --namespace production

# Run resilience benchmark
python main.py chaos benchmark \
  --services "frontend-app,backend-api,database" \
  --namespace production

# List active experiments
python main.py chaos experiments
```

## Project Structure

```
project-aether/
├── agents/
│   ├── orchestrator/
│   │   └── core.py          # Multi-agent orchestration logic
│   └── specialized/
│       └── incident_agents.py  # Specialized AIOps agents
├── config/
│   └── settings.py          # Configuration management
├── infrastructure/
│   ├── kind/
│   │   └── manager.py       # Kind cluster management
│   └── helm_charts/
│       └── manager.py       # Helm deployment management
├── knowledge_graph/
│   └── graph.py             # Neo4j knowledge graph operations
├── resilience/
│   └── chaos_mesh.py        # Chaos Mesh integration
├── tools/
│   ├── k8s_tools.py         # Kubernetes tools
│   └── metrics_tools.py     # Prometheus/Loki tools
├── main.py                  # CLI entry point
├── requirements.txt         # Python dependencies
└── .env.example            # Environment template
```

## Configuration

Create a `.env` file with the following variables:

```env
# AI/LLM Configuration
OPENAI_API_KEY=your-openai-key
OPENAI_MODEL=gpt-4
GOOGLE_API_KEY=your-google-key

# Neo4j Configuration
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-password

# Observability
PROMETHEUS_URL=http://localhost:9090
LOKI_URL=http://localhost:3100

# Chaos Mesh
CHAOS_MESH_NAMESPACE=chaos-testing
```

## Agent System

### Agent Types

1. **TriageAgent**: Classifies incidents and determines severity
2. **RootCauseAnalyzer**: Performs multi-hop analysis using knowledge graph
3. **RemediationAdvisor**: Generates remediation recommendations
4. **ActionExecutor**: Executes approved remediation actions

### Workflow

```
Incident Detection
       ↓
  TriageAgent (Classification)
       ↓
  RootCauseAnalyzer (Multi-hop analysis)
       ↓
  RemediationAdvisor (Generate actions)
       ↓
  ActionExecutor (Execute/Approve)
```

## Knowledge Graph

The Neo4j knowledge graph stores:

- **Service Nodes**: Microservices with metadata
- **Dependency Edges**: Service-to-service relationships
- **Metrics**: Historical performance data
- **Multi-hop Analysis**: Root cause traversal

### Schema

```cypher
(Service)-[:DEPENDS_ON]->(Service)
(Service)-[:HAS_METRIC]->(Metric)
```

## Chaos Engineering

Supported fault injection types:

- **Network Partition**: Simulate network isolation
- **Pod Failure**: Kill pods to test resilience
- **Resource Stress**: CPU/memory exhaustion
- **I/O Delay**: Storage latency injection

## API Keys

### Neo4j
- Local: Install Neo4j Desktop or use Docker
- Cloud: Use Neo4j Aura (https://neo4j.com/cloud/aura/)

## Testing

```bash
# Run tests
pytest tests/

# Run specific test file
pytest tests/test_agents.py

# Run with coverage
pytest --cov=.
```

## Development

```bash
# Install in development mode
pip install -e .

# Run linting
flake8 .
black .

# Run type checking
mypy .
```

## Troubleshooting

### Common Issues

**Kind cluster not creating:**
```bash
# Ensure Docker is running
docker ps

# Check Kind installation
kind version
```

**Neo4j connection issues:**
```bash
# Verify Neo4j is running
docker ps | grep neo4j

# Check connection
curl http://localhost:7474
```

**Helm deployment fails:**
```bash
# Update helm repos
helm repo update

# Check helm version
helm version
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit changes
4. Push to the branch
5. Open a Pull Request

## License

MIT License - see LICENSE file

## Support

- Issues: https://github.com/anomalyco/project-aether/issues
- Documentation: https://project-aether.readthedocs.io

## Roadmap

- [ ] Integration with AWS/GCP/Azure managed Kubernetes
- [ ] Additional LLM providers (Anthropic, Cohere)
- [ ] Web UI for visualization
- [ ] Machine learning for anomaly detection
- [ ] Integration with PagerDuty/Opsgenie
- [ ] Service mesh (Istio/Linkerd) support
