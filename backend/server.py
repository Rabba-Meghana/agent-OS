from flask import Flask, jsonify, request
from flask_cors import CORS
from neo4j import GraphDatabase
import anthropic
import os
import json
import time
from datetime import datetime
import threading

app = Flask(__name__)
CORS(app)

NEO4J_URI = os.getenv("NEO4J_URI", "neo4j+s://your-instance.databases.neo4j.io")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "your-password")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "your-key")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
ai_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

def run_query(query, params={}):
    with driver.session() as session:
        result = session.run(query, params)
        return [record.data() for record in result]

def call_ai(system, user):
    msg = ai_client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=300,
        system=system,
        messages=[{"role": "user", "content": user}]
    )
    return msg.content[0].text

@app.route("/api/setup", methods=["POST"])
def setup():
    """Initialize the Neo4j graph with agents, rules, definitions"""
    queries = [
        "MATCH (n) DETACH DELETE n",
        """CREATE (a1:Agent {id:'worker-001', name:'WorkerAgent', type:'worker', status:'active', risk_score:0})
           CREATE (a2:Agent {id:'checker-001', name:'CheckerAgent', type:'checker', status:'active', risk_score:0})
           CREATE (a3:Agent {id:'watcher-001', name:'WatcherAgent', type:'watcher', status:'active', risk_score:0})
           CREATE (a4:Agent {id:'explainer-001', name:'ExplainerAgent', type:'explainer', status:'active', risk_score:0})""",
        """CREATE (d1:Definition {id:'def-risk', concept:'HIGH_RISK_CUSTOMER', value:'credit_score < 600 OR missed_payments >= 3', verified:true})
           CREATE (d2:Definition {id:'def-txn', concept:'APPROVED_TRANSACTION', value:'amount <= 50000 AND customer_verified = true', verified:true})
           CREATE (d3:Definition {id:'def-cust', concept:'CUSTOMER', value:'active_account = true AND kyc_complete = true', verified:true})""",
        """CREATE (r1:Rule {id:'rule-001', name:'No External Forward', description:'Agents cannot forward data externally', severity:'CRITICAL', action:'BLOCK'})
           CREATE (r2:Rule {id:'rule-002', name:'CFO Approval Required', description:'Transactions over $50k need CFO approval', severity:'HIGH', action:'ESCALATE'})
           CREATE (r3:Rule {id:'rule-003', name:'Customer Data Protection', description:'Customer PII cannot leave system boundary', severity:'CRITICAL', action:'BLOCK'})
           CREATE (r4:Rule {id:'rule-004', name:'Unverified Source Block', description:'Actions from unverified sources are blocked', severity:'HIGH', action:'BLOCK'})""",
        """MATCH (w:Agent {type:'worker'}), (c:Agent {type:'checker'}) CREATE (w)-[:CHECKED_BY]->(c)""",
        """MATCH (w:Agent {type:'worker'}), (wa:Agent {type:'watcher'}) CREATE (w)-[:MONITORED_BY]->(wa)""",
        """MATCH (wa:Agent {type:'watcher'}), (e:Agent {type:'explainer'}) CREATE (wa)-[:REPORTS_TO]->(e)""",
        """MATCH (a:Agent {type:'worker'}), (r:Rule) CREATE (a)-[:GOVERNED_BY]->(r)""",
        """MATCH (a:Agent), (d:Definition) CREATE (a)-[:USES_DEFINITION]->(d)""",
    ]
    for q in queries:
        run_query(q)
    return jsonify({"status": "Graph initialized", "message": "AgentOS is ready"})

@app.route("/api/graph", methods=["GET"])
def get_graph():
    """Return full graph for visualization"""
    nodes = run_query("MATCH (n) RETURN id(n) as id, labels(n) as labels, properties(n) as props")
    edges = run_query("MATCH (a)-[r]->(b) RETURN id(a) as source, id(b) as target, type(r) as type, id(r) as id")
    return jsonify({"nodes": nodes, "edges": edges})

@app.route("/api/simulate", methods=["POST"])
def simulate():
    """Simulate an action — normal or attack"""
    data = request.json
    action_type = data.get("type", "normal")
    description = data.get("description", "")
    amount = data.get("amount", 1000)
    source_verified = data.get("source_verified", True)

    timestamp = datetime.now().isoformat()
    action_id = f"action-{int(time.time())}"

    # WORKER AGENT — decides what to do
    worker_reasoning = call_ai(
        "You are WorkerAgent, an AI that processes enterprise requests. Be concise. Respond in 2 sentences.",
        f"You received this request: {description}. Amount: ${amount}. Source verified: {source_verified}. What action do you want to take?"
    )

    # CHECKER AGENT — checks rules in graph
    rules = run_query("MATCH (r:Rule) RETURN r.name as name, r.description as desc, r.severity as severity, r.action as action")
    rules_text = "\n".join([f"- {r['name']}: {r['desc']} (Severity: {r['severity']}, Action: {r['action']})" for r in rules])

    checker_reasoning = call_ai(
        "You are CheckerAgent. You enforce rules strictly. Respond with JSON only: {allowed: true/false, rule_violated: 'rule name or null', reason: 'short reason'}",
        f"Worker wants to: {worker_reasoning}\nRules:\n{rules_text}\nSource verified: {source_verified}\nAmount: ${amount}\nIs this allowed?"
    )

    try:
        checker_result = json.loads(checker_reasoning)
    except:
        checker_result = {"allowed": not (not source_verified or amount > 50000), "rule_violated": None, "reason": checker_reasoning}

    allowed = checker_result.get("allowed", True)
    rule_violated = checker_result.get("rule_violated")
    
    # Determine status
    if action_type == "attack" or not source_verified:
        status = "BLOCKED"
        allowed = False
        rule_violated = rule_violated or "No External Forward"
    elif amount > 50000:
        status = "ESCALATED"
        allowed = False
        rule_violated = rule_violated or "CFO Approval Required"
    else:
        status = "APPROVED" if allowed else "BLOCKED"

    # WATCHER AGENT — detects anomalies
    watcher_alert = call_ai(
        "You are WatcherAgent. You detect anomalies. Be very concise — 1 sentence only.",
        f"Action: {description}. Status: {status}. Source verified: {source_verified}. Amount: ${amount}. Any anomaly detected?"
    )

    # EXPLAINER AGENT — plain English summary
    explanation = call_ai(
        "You are ExplainerAgent. Explain what happened in plain English for a non-technical executive. 2-3 sentences max.",
        f"Worker tried: {description}. Checker result: {status}. Rule violated: {rule_violated}. Watcher says: {watcher_alert}. Explain this incident."
    )

    # Write action to graph
    run_query("""
        MATCH (w:Agent {type:'worker'}), (c:Agent {type:'checker'})
        CREATE (act:Action {
            id: $action_id,
            description: $description,
            status: $status,
            amount: $amount,
            source_verified: $source_verified,
            rule_violated: $rule_violated,
            timestamp: $timestamp,
            type: $action_type
        })
        CREATE (w)-[:PERFORMED]->(act)
        CREATE (c)-[:EVALUATED]->(act)
    """, {
        "action_id": action_id,
        "description": description,
        "status": status,
        "amount": amount,
        "source_verified": source_verified,
        "rule_violated": rule_violated or "",
        "timestamp": timestamp,
        "action_type": action_type
    })

    # Update agent risk score if attack
    if action_type == "attack":
        run_query("MATCH (a:Agent {type:'worker'}) SET a.risk_score = a.risk_score + 25")

    return jsonify({
        "action_id": action_id,
        "status": status,
        "worker": worker_reasoning,
        "checker": checker_result,
        "watcher": watcher_alert,
        "explanation": explanation,
        "rule_violated": rule_violated,
        "timestamp": timestamp
    })

@app.route("/api/audit", methods=["GET"])
def audit():
    """Return full audit trail"""
    actions = run_query("""
        MATCH (a:Agent)-[:PERFORMED]->(act:Action)
        RETURN a.name as agent, act.description as description, 
               act.status as status, act.timestamp as timestamp,
               act.rule_violated as rule_violated, act.amount as amount
        ORDER BY act.timestamp DESC LIMIT 20
    """)
    return jsonify({"audit_trail": actions})

@app.route("/api/agents", methods=["GET"])
def get_agents():
    agents = run_query("MATCH (a:Agent) RETURN a")
    return jsonify({"agents": [r['a'] for r in agents]})

@app.route("/api/rules", methods=["GET"])
def get_rules():
    rules = run_query("MATCH (r:Rule) RETURN r")
    return jsonify({"rules": [r['r'] for r in rules]})

if __name__ == "__main__":
    app.run(debug=True, port=5000)
