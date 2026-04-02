# AgentOS — AI Agent Operating System
### HackWithChicago 3.0 | Neo4j + Groq AI

## Setup in 5 minutes

### 1. Get Neo4j Free (2 min)
- Go to: https://aura.neo4j.io
- Sign up → Create free instance
- Copy: Connection URI, Username (neo4j), Password

### 2. Get Groq Free API Key (1 min)
- Go to: https://console.groq.com
- Sign up → API Keys → Create new key
- Copy the key (starts with gsk_)

### 3. Run Backend
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your credentials
python server.py
```

### 4. Run Frontend
```bash
cd frontend
npm install
npm start
```

### 5. Demo Flow
1. Click "Initialize AgentOS" — loads Neo4j graph
2. Simulate → Normal (approved), Attack (blocked), Escalation (CFO needed)
3. Watch 4 agents respond in real time
4. Check Audit Trail — every action in Neo4j

## The Problem We Solve
Microsoft's AI agents operate from different versions of reality and answer to nobody.
AgentOS gives every agent an identity, shared ground truth, graph-encoded rules,
and a society of agents watching each other in real time.

## Pitch
"Microsoft's own security team proved their agents can be weaponized.
AgentOS is the operating system that makes AI agents safe enough to trust."
