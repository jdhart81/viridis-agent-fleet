"""A2A 1.0 commerce facade over the existing HTTP x402 v2 seller lane.

The adapter adds discovery and task semantics; it does not add a payment
rail. Every paid task reuses ``x402_v2.verify_and_settle`` and the same
per-agent durable ``consumed_x402`` ledger as the HTTP surface.

AC1 discovery is a standards-shaped Agent Card at the well-known URL.
AC2 x402 is required and activated through the A2A extension header.
AC3 a payment-required task persists its original request and requirements.
AC4 settlement succeeds before the ungated core can execute.
AC5 payment/task replays are idempotent and never execute twice.
AC6 every error path fails closed; neither private keys nor signing occur here.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from x402_http import (
    INTRO_PAYER_HEADER, INTRO_SCHEDULE, INTRO_SEEN_KEY, X402_HTTP_METADATA,
    X402_HTTP_TOOLS, _classified_settlement, _payer_seen, _payer_wallet,
    intro_enabled,
)

logger = logging.getLogger("viridis.a2a_commerce")

EXTENSION_URI = "https://github.com/google-a2a/a2a-x402/v0.1"
A2A_VERSION = "1.0"
TASKS_KEY = "a2a_x402_tasks"
MEDIA_TYPE = "application/a2a+json"
MAX_TASKS_PER_AGENT = 500


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _skill_id(agent: str, tool: str) -> str:
    return f"{agent}.{tool}"


def _skill_map() -> Dict[str, tuple[str, str]]:
    return {_skill_id(agent, tool): (agent, tool)
            for agent, tool in X402_HTTP_TOOLS}


def agent_card(public_base: str) -> dict:
    from payment_gate import DEFAULT_PRICE_MINOR, PRICE_MINOR
    import x402_rail

    base = public_base.rstrip("/")
    skills = []
    for agent, tool in X402_HTTP_TOOLS:
        meta = X402_HTTP_METADATA[(agent, tool)]
        price_minor = PRICE_MINOR.get(agent, DEFAULT_PRICE_MINOR)
        skills.append({
            "id": _skill_id(agent, tool),
            "name": f"{agent}: {tool}",
            "description": meta["description"],
            "tags": ["x402", "Base", "USDC", "climate", "compliance"],
            "examples": [json.dumps(meta["input_example"],
                                    separators=(",", ":"))],
            "inputModes": ["application/json"],
            "outputModes": ["application/json"],
            "metadata": {
                "priceMinorUsd": price_minor,
                "amountAtomicUsdc": x402_rail.price_atomic(price_minor),
                "httpX402Endpoint": f"{base}/x402/{agent}/{tool}",
                "inputSchema": meta["input_schema"],
            },
        })
    return {
        "name": "Viridis Carbon and Compliance Commerce Agent",
        "description": ("Five deterministic paid skills that chain measure, "
                        "account, disclose, claim, and scan for autonomous "
                        "agent buyers."),
        "supportedInterfaces": [{
            "url": f"{base}/a2a",
            "protocolBinding": "HTTP+JSON",
            "protocolVersion": A2A_VERSION,
        }],
        "provider": {"organization": "Viridis Conservation",
                     "url": base},
        "version": "1.0.0",
        "documentationUrl": f"{base}/quickstart",
        "capabilities": {
            "streaming": False,
            "pushNotifications": False,
            "extendedAgentCard": False,
            "extensions": [{
                "uri": EXTENSION_URI,
                "description": ("x402 v2 exact settlement on Base mainnet "
                                "USDC; settle before serve."),
                "required": True,
                "params": {"x402Version": 2},
            }],
        },
        "defaultInputModes": ["application/json"],
        "defaultOutputModes": ["application/json"],
        "skills": skills,
    }


def status(cores: Dict[str, Any], public_base: str) -> dict:
    from payment_gate import GATE_ATTR
    counts = {"input_required": 0, "working": 0,
              "completed": 0, "failed": 0}
    for core in cores.values():
        gate = getattr(core, GATE_ATTR, {})
        for task in gate.get(TASKS_KEY, {}).values() if isinstance(gate, dict) else ():
            state = str((task.get("status") or {}).get("state", ""))
            key = {"TASK_STATE_INPUT_REQUIRED": "input_required",
                   "TASK_STATE_WORKING": "working",
                   "TASK_STATE_COMPLETED": "completed",
                   "TASK_STATE_FAILED": "failed"}.get(state)
            if key:
                counts[key] += 1
    return {
        "enabled": True,
        "protocol_version": A2A_VERSION,
        "x402_extension": EXTENSION_URI,
        "agent_card": public_base.rstrip("/") + "/.well-known/agent-card.json",
        "message_endpoint": public_base.rstrip("/") + "/a2a/message:send",
        "skills": len(X402_HTTP_TOOLS),
        "tasks": counts,
        "signing_posture": "caller-supplied payment payload; no private keys",
    }


def _headers() -> dict:
    return {"A2A-Version": A2A_VERSION,
            "A2A-Extensions": EXTENSION_URI,
            "X-A2A-Extensions": EXTENSION_URI}


def _response(payload: dict, status_code: int = 200):
    from starlette.responses import JSONResponse
    return JSONResponse(payload, status_code=status_code,
                        media_type=MEDIA_TYPE, headers=_headers())


def _problem(status_code: int, title: str, detail: str):
    from starlette.responses import JSONResponse
    return JSONResponse({"type": "about:blank", "title": title,
                         "status": status_code, "detail": detail},
                        status_code=status_code,
                        media_type="application/problem+json",
                        headers=_headers())


def _extension_active(headers: Any) -> bool:
    raw = str(headers.get("a2a-extensions", "") or
              headers.get("x-a2a-extensions", ""))
    return EXTENSION_URI in {part.strip() for part in raw.split(",")}


def _extract_initial(message: dict):
    if not isinstance(message, dict) or message.get("role") != "ROLE_USER":
        return None, None, "message.role must be ROLE_USER"
    if not isinstance(message.get("messageId"), str) or not message["messageId"]:
        return None, None, "message.messageId is required"
    for part in message.get("parts") or []:
        data = part.get("data") if isinstance(part, dict) else None
        if isinstance(data, dict) and isinstance(data.get("skillId"), str):
            args = data.get("input")
            if not isinstance(args, dict):
                return None, None, "structured part input must be an object"
            return data["skillId"], args, ""
    return None, None, "one data part with skillId and input is required"


def _task_message(task_id: str, context_id: str, status_name: str,
                  text: str, metadata: dict) -> dict:
    return {
        "messageId": str(uuid.uuid4()), "taskId": task_id,
        "contextId": context_id, "role": "ROLE_AGENT",
        "parts": [{"text": text}], "metadata": metadata,
        "extensions": [EXTENSION_URI],
    }


def _payment_task(task_id: str, context_id: str, message: dict,
                  agent: str, tool: str, args: dict,
                  requirement: dict) -> dict:
    status_message = _task_message(
        task_id, context_id, "payment-required",
        "Payment is required before this deterministic skill executes.",
        {"x402.payment.status": "payment-required",
         "x402.payment.required": requirement})
    return {
        "id": task_id, "contextId": context_id,
        "status": {"state": "TASK_STATE_INPUT_REQUIRED",
                   "message": status_message, "timestamp": _now()},
        "history": [message, status_message],
        "metadata": {"viridis.agent": agent, "viridis.tool": tool,
                     "viridis.input": args,
                     "x402.payment.required": requirement},
    }


def _find_task(cores: Dict[str, Any], task_id: str):
    from payment_gate import GATE_ATTR
    for agent, core in cores.items():
        gate = getattr(core, GATE_ATTR, None)
        tasks = gate.get(TASKS_KEY, {}) if isinstance(gate, dict) else {}
        if task_id in tasks:
            return agent, core, gate, tasks, tasks[task_id]
    return None


def make_a2a_handlers(cores, store, public_base):
    import x402_rail
    import x402_v2
    from payment_gate import DEFAULT_PRICE_MINOR, GATE_ATTR, PRICE_MINOR

    async def card(_request):
        return _response(agent_card(public_base))

    async def get_task(request):
        found = _find_task(cores, str(request.path_params.get("id", "")))
        if not found:
            return _problem(404, "Task not found", "Unknown A2A task id")
        return _response({"task": found[-1]})

    async def send_message(request):
        if not x402_rail.is_enabled() or not x402_v2.is_enabled():
            return _problem(503, "Commerce unavailable",
                            "x402 master and v2 switches must both be enabled")
        if not _extension_active(request.headers):
            return _problem(400, "Required extension missing",
                            f"Activate {EXTENSION_URI} with A2A-Extensions")
        try:
            body = await request.json()
        except Exception:
            return _problem(400, "Invalid JSON", "A2A request must be JSON")
        message = body.get("message") if isinstance(body, dict) else None
        if not isinstance(message, dict):
            return _problem(400, "Invalid request", "message is required")

        task_id = str(message.get("taskId") or "")
        if task_id:
            found = _find_task(cores, task_id)
            if not found:
                return _problem(404, "Task not found", "Unknown A2A task id")
            agent, core, gate, tasks, task = found
            if task["status"]["state"] == "TASK_STATE_COMPLETED":
                return _response({"task": task})
            metadata = message.get("metadata")
            payment_status = (metadata.get("x402.payment.status")
                              if isinstance(metadata, dict) else None)
            payload = (metadata.get("x402.payment.payload")
                       if isinstance(metadata, dict) else None)
            if payment_status != "payment-submitted" or not isinstance(payload, dict):
                return _problem(400, "Payment payload required",
                                "Submit x402.payment.payload for this task")
            tool = str(task["metadata"]["viridis.tool"])
            requirement = task["metadata"]["x402.payment.required"]
            header_value = json.dumps(payload, sort_keys=True,
                                      separators=(",", ":"))
            payer = _payer_wallet(payload)
            list_price = PRICE_MINOR.get(agent, DEFAULT_PRICE_MINOR)
            expected_price = (INTRO_SCHEDULE["price_minor"]
                              if intro_enabled() and not _payer_seen(cores, payer)
                              else list_price)
            if str(requirement["accepts"][0]["amount"]) != str(
                    x402_rail.price_atomic(expected_price)):
                refreshed = x402_v2.build_payment_required(
                    agent, tool, expected_price,
                    f"{public_base}/x402/{agent}/{tool}", "POST",
                    X402_HTTP_METADATA[(agent, tool)])
                task = _payment_task(task_id, task["contextId"],
                                     task["history"][0], agent, tool,
                                     task["metadata"]["viridis.input"], refreshed)
                tasks[task_id] = task
                store.save(agent, core)
                return _response({"task": task})
            identifier = x402_v2.payment_identifier(payload, header_value)
            key = "v2:" + hashlib.sha256(identifier.encode()).hexdigest()
            consumed = gate.setdefault("consumed_x402", {})
            if key in consumed:
                if task["status"]["state"] in {
                        "TASK_STATE_WORKING", "TASK_STATE_COMPLETED",
                        "TASK_STATE_FAILED"}:
                    return _response({"task": task})
                return _problem(409, "Payment already consumed",
                                "This authorization belongs to another call")
            result = x402_v2.verify_and_settle(
                payload, requirement, agent, tool)
            if not result.get("settled"):
                return _problem(402, "Settlement failed",
                                str(result.get("reason") or "unknown"))
            prior_task = task
            consumed[key] = _classified_settlement(
                payload, agent, tool, result, identifier,
                intro_applied=(intro_enabled() and
                               expected_price == INTRO_SCHEDULE["price_minor"]),
                list_price_minor=list_price,
                surface="a2a-x402-v2")
            if intro_enabled() and payer:
                gate.setdefault(INTRO_SEEN_KEY, {})[payer.lower()] = {
                    "at": _now(), "route": f"{agent}/{tool}",
                    "tx_hash": result["tx_hash"],
                    "pricing_schedule_version": INTRO_SCHEDULE["version"],
                }
            receipt_meta = {
                "x402.payment.status": "payment-completed",
                "x402.payment.receipts": [{
                    "transaction": result["tx_hash"],
                    "network": result["network"],
                    "amount": result["amount_atomic"],
                }],
            }
            working_message = _task_message(
                task_id, task["contextId"], "payment-completed",
                "Payment settled; executing the requested skill.", receipt_meta)
            task = dict(task)
            task["status"] = {"state": "TASK_STATE_WORKING",
                              "message": working_message, "timestamp": _now()}
            task["history"] = [*task.get("history", []), message,
                               working_message]
            tasks[task_id] = task
            if not store.save(agent, core):
                consumed.pop(key, None)
                tasks[task_id] = prior_task
                return _problem(500, "Persistence failed",
                                "Payment settled; tool was not executed")
            if not result.get("serve", True):
                task["status"] = {"state": "TASK_STATE_FAILED",
                                  "message": _task_message(
                                      task_id, task["contextId"],
                                      "payment-failed", str(result.get("reason")),
                                      receipt_meta), "timestamp": _now()}
                tasks[task_id] = task
                store.save(agent, core)
                return _response({"task": task})
            inner = getattr(core, "_gate_inner", None)
            if inner is None:
                return _problem(500, "Agent unavailable", "Gated core missing")
            try:
                out = inner({"action": X402_HTTP_TOOLS[(agent, tool)],
                             **task["metadata"]["viridis.input"]})
                if asyncio.iscoroutine(out):
                    out = await out
                final_state = "TASK_STATE_COMPLETED"
            except Exception as exc:
                logger.exception("A2A paid tool failed after settle")
                out = {"status": "error", "error_type": "tool_error",
                       "message": type(exc).__name__,
                       "tx_hash": result["tx_hash"]}
                final_state = "TASK_STATE_FAILED"
            final_message = _task_message(
                task_id, task["contextId"], "payment-completed",
                "Paid skill completed." if final_state.endswith("COMPLETED")
                else "Paid skill failed after settlement.", receipt_meta)
            task["status"] = {"state": final_state, "message": final_message,
                              "timestamp": _now()}
            task["artifacts"] = [{
                "artifactId": str(uuid.uuid4()), "name": f"{agent}.{tool}.result",
                "parts": [{"data": out}],
            }]
            task["history"] = [*task.get("history", []), final_message]
            tasks[task_id] = task
            if not store.save(agent, core):
                return _problem(500, "Persistence failed",
                                "Tool ran after settlement but final task save failed")
            return _response({"task": task})

        skill_id, args, error = _extract_initial(message)
        mapping = _skill_map().get(str(skill_id))
        if not mapping:
            return _problem(400, "Unknown skill", error or str(skill_id))
        agent, tool = mapping
        core = cores.get(agent)
        gate = getattr(core, GATE_ATTR, None) if core is not None else None
        if not isinstance(gate, dict) or getattr(core, "_gate_inner", None) is None:
            return _problem(500, "Agent unavailable", "Gated core missing")
        if not x402_v2._matches_schema(args,
                                       X402_HTTP_METADATA[(agent, tool)]["input_schema"]):
            return _problem(400, "Invalid skill input",
                            "input does not match the advertised JSON schema")
        list_price = PRICE_MINOR.get(agent, DEFAULT_PRICE_MINOR)
        payer_hint = str(request.headers.get(INTRO_PAYER_HEADER, "")).strip()
        price = (INTRO_SCHEDULE["price_minor"]
                 if intro_enabled() and not _payer_seen(cores, payer_hint)
                 else list_price)
        requirement = x402_v2.build_payment_required(
            agent, tool, price, f"{public_base}/x402/{agent}/{tool}",
            "POST", X402_HTTP_METADATA[(agent, tool)])
        task_id = str(uuid.uuid4())
        context_id = str(message.get("contextId") or uuid.uuid4())
        task = _payment_task(task_id, context_id, message,
                             agent, tool, args, requirement)
        tasks = gate.setdefault(TASKS_KEY, {})
        if len(tasks) >= MAX_TASKS_PER_AGENT:
            terminal = [key for key, value in tasks.items()
                        if str((value.get("status") or {}).get("state", ""))
                        in {"TASK_STATE_COMPLETED", "TASK_STATE_FAILED",
                            "TASK_STATE_REJECTED", "TASK_STATE_CANCELED"}]
            if terminal:
                tasks.pop(terminal[0], None)
            else:
                return _problem(429, "Task capacity reached", "Retry later")
        tasks[task_id] = task
        if not store.save(agent, core):
            tasks.pop(task_id, None)
            return _problem(503, "Persistence unavailable",
                            "Payment task was not accepted")
        return _response({"task": task})

    return card, send_message, get_task
