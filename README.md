# AgentOS — AI Agent Operating System
### HackWithChicago 3.0 | Neo4j + RocketRide AI

## The Problem
Microsoft's enterprise AI agents operate from different versions of reality and answer to nobody. One agent thinks "high risk" means one thing, another thinks something else. Agents can be hijacked, go rogue, and make dangerous decisions with zero accountability.

## What We Built
A graph-powered operating system where every AI agent has an identity, shares ground truth definitions, follows graph-encoded rules, and is watched by other agents in real time.

**4 Specialized Agents:**
- **WorkerAgent** — Processes enterprise requests autonomously
- **CheckerAgent** — Queries Neo4j before every action, enforces rules
- **WatcherAgent** — Detects behavioral anomalies and drift
- **ExplainerAgent** — Generates plain English audit reports

**Neo4j Graph holds:**
- Agent identities and relationships
- Shared ground truth definitions
- Ground rules as graph constraints
- Full immutable audit trail

## Setup

### Backend
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
# Fill in NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, ANTHROPIC_API_KEY
python server.py
```

### Frontend
```bash
cd frontend
npm install
npm start
```

## Demo Flow
1. Click "Initialize AgentOS" — graph schema loads into Neo4j
2. Go to Simulate → try Normal, Attack, and Escalation scenarios
3. Watch all 4 agents respond in real time
4. Check Audit Trail — every action permanently recorded
5. Check Rules — ground truth encoded in graph

## Tech Stack
- **Neo4j Aura** — Graph database (agent relationships, rules, audit trail)
- **RocketRide AI / Anthropic** — Powers all 4 agents
- **Flask** — Backend API
- **React** — Frontend UI

## The Pitch
*"Microsoft's own security team documented that their AI agents can be weaponized with no way to stop them. AgentOS is the graph that gives every agent an identity, every action a rule, and a society of agents that watch each other — so nothing happens in the dark."*
