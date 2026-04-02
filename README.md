# AgentOS — AI Agent Operating System
### HackWithChicago 3.0 | Neo4j + Groq + RocketRide

AgentOS is a governance-first operating system for AI agents.  
It enforces shared truth, identity, and real-time oversight across autonomous agents using a graph + pipeline architecture.

---

## Core Idea

Modern AI agents operate in isolation, without shared context or accountability.  
AgentOS introduces:

- Shared Ground Truth via Neo4j graph
- Structured Agent Identity and Roles
- Real-time Multi-Agent Oversight
- Pipeline-based execution using RocketRide

This transforms agents from isolated tools into a coordinated, governed system.

---

## Architecture

Frontend → React dashboard (Command Center, Pipeline View, Audit)

Backend → Python service layer  
- Neo4j graph storage  
- RocketRide pipeline execution  
- Governance + audit logic  

Execution Engine → RocketRide  
- Multi-agent pipeline (.pipe)  
- Worker, Checker, Watcher, Explainer  

Database → Neo4j  
- Rules  
- Agent identities  
- Audit trails  
- Decision graph  

---

## Setup

### 1. Neo4j (Required)

Create a free instance:
https://aura.neo4j.io

Copy:
- URI
- Username
- Password

---

### 2. Groq API Key

Get a free key:
https://console.groq.com

---

### 3. Backend Setup

```bash
cd backend

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
