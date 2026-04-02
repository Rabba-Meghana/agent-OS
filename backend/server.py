from flask import Flask, jsonify, request
from flask_cors import CORS
from neo4j import GraphDatabase
import os
import json
import time
import requests
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
CORS(app)

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

def run_query(query, params={}):
    with driver.session() as session:
        result = session.run(query, params)
        return [record.data() for record in result]

def call_groq(system, user):
    """Call Groq API - fast and free"""
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    body = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ],
        "max_tokens": 200,
        "temperature": 0.3
    }
    r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=body)
    return r.json()["choices"][0]["message"]["content"]

@app.route("/api/setup", methods=["POST"])
def setup():
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
    nodes = run_query("MATCH (n) RETURN id(n) as id, labels(n) as labels, properties(n) as props")
    edges = run_query("MATCH (a)-[r]->(b) RETURN id(a) as source, id(b) as target, type(r) as type, id(r) as id")
    return jsonify({"nodes": nodes, "edges": edges})

@app.route("/api/simulate", methods=["POST"])
def simulate():
    data = request.json
    action_type = data.get("type", "normal")
    description = data.get("description", "")
    amount = data.get("amount", 1000)
    source_verified = data.get("source_verified", True)
    timestamp = datetime.now().isoformat()
    action_id = f"action-{int(time.time())}"

    # WORKER AGENT
    worker_reasoning = call_groq(
        "You are WorkerAgent, an AI that processes enterprise requests. Be concise. Max 2 sentences.",
        f"Request: {description}. Amount: ${amount}. Source verified: {source_verified}. What action do you want to take?"
    )

    # CHECKER AGENT - queries rules from graph
    rules = run_query("MATCH (r:Rule) RETURN r.name as name, r.description as desc, r.severity as severity, r.action as action")
    rules_text = "\n".join([f"- {r['name']}: {r['desc']} ({r['severity']}, {r['action']})" for r in rules])
    checker_raw = call_groq(
        "You are CheckerAgent. Enforce rules strictly. Respond ONLY with valid JSON: {\"allowed\": true or false, \"rule_violated\": \"rule name or null\", \"reason\": \"one sentence\"}",
        f"Worker wants to: {worker_reasoning}\nRules:\n{rules_text}\nSource verified: {source_verified}\nAmount: ${amount}\nAllowed?"
    )
    try:
        checker_result = json.loads(checker_raw)
    except:
        checker_result = {"allowed": source_verified and amount <= 50000, "rule_violated": None, "reason": checker_raw[:100]}

    # Determine final status
    if not source_verified or action_type == "attack":
        status = "BLOCKED"
        checker_result["rule_violated"] = checker_result.get("rule_violated") or "Unverified Source Block"
    elif amount > 50000:
        status = "ESCALATED"
        checker_result["rule_violated"] = checker_result.get("rule_violated") or "CFO Approval Required"
    elif not checker_result.get("allowed", True):
        status = "BLOCKED"
    else:
        status = "APPROVED"

    # WATCHER AGENT
    watcher_alert = call_groq(
        "You are WatcherAgent. Detect anomalies. ONE sentence only.",
        f"Action: {description}. Status: {status}. Source verified: {source_verified}. Amount: ${amount}. Anomaly?"
    )

    # EXPLAINER AGENT
    explanation = call_groq(
        "You are ExplainerAgent. Explain to a non-technical executive in 2 sentences max.",
        f"Worker tried: {description}. Result: {status}. Rule: {checker_result.get('rule_violated')}. Watcher: {watcher_alert}. Summarize."
    )

    # Write to Neo4j audit trail
    run_query("""
        MATCH (w:Agent {type:'worker'}), (c:Agent {type:'checker'})
        CREATE (act:Action {
            id: $action_id, description: $description, status: $status,
            amount: $amount, source_verified: $source_verified,
            rule_violated: $rule_violated, timestamp: $timestamp, type: $action_type
        })
        CREATE (w)-[:PERFORMED]->(act)
        CREATE (c)-[:EVALUATED]->(act)
    """, {
        "action_id": action_id, "description": description, "status": status,
        "amount": amount, "source_verified": source_verified,
        "rule_violated": checker_result.get("rule_violated") or "",
        "timestamp": timestamp, "action_type": action_type
    })

    if action_type == "attack":
        run_query("MATCH (a:Agent {type:'worker'}) SET a.risk_score = a.risk_score + 25")

    return jsonify({
        "action_id": action_id, "status": status,
        "worker": worker_reasoning,
        "checker": checker_result,
        "watcher": watcher_alert,
        "explanation": explanation,
        "rule_violated": checker_result.get("rule_violated"),
        "timestamp": timestamp
    })

@app.route("/api/audit", methods=["GET"])
def audit():
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
    agents = run_query("MATCH (a:Agent) RETURN properties(a) as agent")
    return jsonify({"agents": [r['agent'] for r in agents]})

@app.route("/api/rules", methods=["GET"])
def get_rules():
    rules = run_query("MATCH (r:Rule) RETURN properties(r) as rule")
    return jsonify({"rules": [r['rule'] for r in rules]})

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(debug=True, port=5000)
