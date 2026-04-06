from flask import Flask, jsonify, request
from flask_cors import CORS
from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError, ServiceUnavailable
import asyncio
import os
import json
import time
import requests
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
CORS(app)

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
ROCKETRIDE_ENABLED = os.getenv("ROCKETRIDE_ENABLED", "true").lower() == "true"
ROCKETRIDE_PIPELINE = Path(__file__).resolve().parent / "pipelines" / "agentos_simulate.pipe"

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

def run_query(query, params={}):
    with driver.session() as session:
        result = session.run(query, params)
        return [record.data() for record in result]


def _extract_rocketride_answer(response):
    answers = response.get("answers")
    if isinstance(answers, list) and answers:
        payload = answers[0]
    else:
        payload = response

    if isinstance(payload, dict):
        if isinstance(payload.get("text"), str):
            return payload["text"]
        if isinstance(payload.get("answer"), str):
            return payload["answer"]
        return json.dumps(payload)
    return str(payload)


def _parse_json_maybe_fenced(raw_text):
    text = raw_text.strip()
    if text.startswith("```"):
        text = text[3:].strip()
        if text.startswith("json"):
            text = text[4:].strip()
        if text.endswith("```"):
            text = text[:-3].strip()
    return json.loads(text)


async def _simulate_with_rocketride(description, amount, source_verified, rules):
    from rocketride import RocketRideClient
    from rocketride.schema import Question

    if not ROCKETRIDE_PIPELINE.exists():
        raise RuntimeError(f"RocketRide pipeline not found: {ROCKETRIDE_PIPELINE}")

    with open(ROCKETRIDE_PIPELINE, "r", encoding="utf-8") as f:
        pipeline = json.load(f)

    question = Question(expectJson=True)
    question.addInstruction(
        "Output format",
        "Return ONLY JSON with keys worker, checker, watcher, explanation. "
        "checker must contain allowed (boolean), rule_violated (string or null), reason (string)."
    )
    question.addContext({
        "task": "Evaluate an enterprise action through a 4-agent governance model",
        "input": {
            "description": description,
            "amount": amount,
            "source_verified": source_verified
        },
        "rules": rules
    })
    question.addQuestion("Simulate WorkerAgent, CheckerAgent, WatcherAgent, and ExplainerAgent outputs.")

    async with RocketRideClient() as client:
        result = await client.use(pipeline=pipeline, source="chat_1", use_existing=True)
        token = result["token"]
        response = await client.chat(token=token, question=question)

    parsed = _parse_json_maybe_fenced(_extract_rocketride_answer(response))
    checker = parsed.get("checker") if isinstance(parsed, dict) else {}
    if not isinstance(checker, dict):
        checker = {}

    return {
        "worker": str(parsed.get("worker", "")) if isinstance(parsed, dict) else "",
        "checker": {
            "allowed": bool(checker.get("allowed", True)),
            "rule_violated": checker.get("rule_violated"),
            "reason": str(checker.get("reason", ""))
        },
        "watcher": str(parsed.get("watcher", "")) if isinstance(parsed, dict) else "",
        "explanation": str(parsed.get("explanation", "")) if isinstance(parsed, dict) else ""
    }

@app.route("/", methods=["GET"])
def root():
    return jsonify({
        "name": "AgentOS Backend",
        "status": "running",
        "endpoints": [
            "/api/health",
            "/api/setup",
            "/api/graph",
            "/api/simulate",
            "/api/audit",
            "/api/agents",
            "/api/rules",
            "/api/rocketride/check"
        ]
    })

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
    try:
        for q in queries:
            run_query(q)
        return jsonify({"status": "Graph initialized", "message": "AgentOS is ready"})
    except ServiceUnavailable as exc:
        return jsonify({
            "status": "error",
            "message": "Cannot connect to Neo4j. Verify NEO4J_URI, NEO4J_USER, and NEO4J_PASSWORD in backend/.env.",
            "details": str(exc)
        }), 503
    except Neo4jError as exc:
        return jsonify({
            "status": "error",
            "message": "Neo4j returned an error while initializing the graph.",
            "details": str(exc)
        }), 500

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

    # CHECKER AGENT - queries rules from graph
    rules = run_query("MATCH (r:Rule) RETURN r.name as name, r.description as desc, r.severity as severity, r.action as action")
    ai_provider = "groq"
    rocketride_error = None

    if ROCKETRIDE_ENABLED:
        try:
            rr_result = asyncio.run(_simulate_with_rocketride(description, amount, source_verified, rules))
            worker_reasoning = rr_result["worker"]
            checker_result = rr_result["checker"]
            watcher_alert = rr_result["watcher"]
            explanation = rr_result["explanation"]
            ai_provider = "rocketride"
        except Exception as exc:
            rocketride_error = str(exc)

    if ai_provider != "rocketride":
        worker_reasoning = call_groq(
            "You are WorkerAgent, an AI that processes enterprise requests. Be concise. Max 2 sentences.",
            f"Request: {description}. Amount: ${amount}. Source verified: {source_verified}. What action do you want to take?"
        )

        rules_text = "\n".join([f"- {r['name']}: {r['desc']} ({r['severity']}, {r['action']})" for r in rules])
        checker_raw = call_groq(
            "You are CheckerAgent. Enforce rules strictly. Respond ONLY with valid JSON: {\"allowed\": true or false, \"rule_violated\": \"rule name or null\", \"reason\": \"one sentence\"}",
            f"Worker wants to: {worker_reasoning}\nRules:\n{rules_text}\nSource verified: {source_verified}\nAmount: ${amount}\nAllowed?"
        )
        try:
            checker_result = json.loads(checker_raw)
        except Exception:
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

    if ai_provider != "rocketride":
        watcher_alert = call_groq(
            "You are WatcherAgent. Detect anomalies. ONE sentence only.",
            f"Action: {description}. Status: {status}. Source verified: {source_verified}. Amount: ${amount}. Anomaly?"
        )

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
        "timestamp": timestamp,
        "ai_provider": ai_provider,
        "rocketride_error": rocketride_error
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


@app.route("/api/rocketride/check", methods=["GET"])
def rocketride_check():
    result = {
        "enabled": ROCKETRIDE_ENABLED,
        "pipeline": str(ROCKETRIDE_PIPELINE),
        "pipeline_exists": ROCKETRIDE_PIPELINE.exists()
    }

    try:
        from rocketride import RocketRideClient
        result["client_installed"] = True
    except Exception as exc:
        result["client_installed"] = False
        result["status"] = "error"
        result["error"] = str(exc)
        return jsonify(result), 500

    if not ROCKETRIDE_ENABLED or not ROCKETRIDE_PIPELINE.exists():
        result["status"] = "disabled"
        return jsonify(result)

    async def _check_connection():
        async with RocketRideClient() as client:
            await client.ping()

    try:
        asyncio.run(_check_connection())
        result["status"] = "ok"
    except Exception as exc:
        result["status"] = "error"
        result["error"] = str(exc)
        return jsonify(result), 500

    return jsonify(result)

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "rocketride_enabled": ROCKETRIDE_ENABLED,
        "rocketride_pipeline_exists": ROCKETRIDE_PIPELINE.exists()
    })

if __name__ == "__main__":
    app.run(debug=True, port=5000)
