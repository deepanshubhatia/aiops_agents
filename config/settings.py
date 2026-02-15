"""
Project Aether - Configuration Module
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional
from pathlib import Path


class Settings(BaseSettings):
    """Application settings"""
    
    # Ollama Configuration
    ollama_host: str = Field(default="http://localhost:11434", alias="OLLAMA_HOST")
    ollama_model: str = Field(default="glm-4.6:cloud", alias="OLLAMA_MODEL")
    
    # Neo4j Configuration
    neo4j_uri: str = Field(default="bolt://localhost:7687", alias="NEO4J_URI")
    neo4j_user: str = Field(default="neo4j", alias="NEO4J_USER")
    neo4j_password: str = Field(default="password", alias="NEO4J_PASSWORD")
    
    # Kubernetes Configuration
    kubeconfig_path: str = Field(default="~/.kube/config", alias="KUBECONFIG")
    
    # Prometheus Configuration
    prometheus_url: str = Field(default="http://localhost:9090", alias="PROMETHEUS_URL")
    
    # Loki Configuration
    loki_url: str = Field(default="http://localhost:3100", alias="LOKI_URL")
    
    # Chaos Mesh Configuration
    chaos_mesh_namespace: str = Field(default="chaos-testing", alias="CHAOS_MESH_NAMESPACE")
    
    # Application Configuration
    app_name: str = Field(default="project-aether", alias="APP_NAME")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
