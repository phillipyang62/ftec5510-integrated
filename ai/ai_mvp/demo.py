"""Seed fake market data and run two profiles through the HTTP API."""

import argparse
import json
import os
from datetime import datetime, timezone
from http.client import HTTPConnection


def run(port, require_model):
    token = os.getenv("AI_MVP_API_TOKEN")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    def request(method, path, data=None):
        connection = HTTPConnection("127.0.0.1", port, timeout=330)
        try:
            body = json.dumps(data).encode() if data is not None else None
            connection.request(method, path, body, headers)
            response = connection.getresponse()
            payload = json.load(response)
            if response.status != 200:
                raise RuntimeError(f"{method} {path}: {response.status} {payload}")
            return payload
        finally:
            connection.close()

    now = datetime.now(timezone.utc).isoformat()
    request("POST", "/v1/market/quotes", {"quotes": [
        {"symbol": "BTC/USDT", "price": "68000.50", "as_of": now,
         "source": "demo", "name": "Bitcoin", "aliases": ["比特币"]},
        {"symbol": "ETH/USDT", "price": "3200.25", "as_of": now,
         "source": "demo", "name": "Ethereum", "aliases": ["以太坊"]},
    ]})
    for user_id, scores, rai, risk_level, product_cap, mode, simulation_state in (
        ("demo-learner", [38, 50, 28, 60, 48], 43, "C2", "R2", "education", "not_applicable"),
        ("demo-experienced", [62, 65, 75, 60, 55], 63, "C3", "R3", "advisory", "available"),
    ):
        profile = request("PUT", f"/v1/profiles/{user_id}", {
            "questionnaire_version": "1.0.0", "source": "demo",
            "assessment": {"dimensions": dict(zip(("FC", "RA", "KE", "BD", "OC"), scores)),
                           "rai": rai, "risk_level": risk_level, "product_cap": product_cap,
                           "flags": [], "prohibitions": []},
        })
        result = request("POST", "/v1/chat", {
            "user_id": user_id, "message": "比特币和以太坊现在多少钱？这些报价该怎么理解？",
        })
        print(json.dumps({"user_id": user_id, "mode": result["mode"], "risk_ceiling": result["risk_ceiling"],
                          "generation": result["generation"], "trace_id": result["trace_id"],
                          "reply": result["reply"]}, ensure_ascii=False), flush=True)
        if result["mode"] != mode or result["risk_ceiling"] != profile["risk_ceiling"]:
            raise RuntimeError("unexpected profile route or risk ceiling")
        if {item["matches"][0]["symbol"] for item in result["market"]} != {"BTC/USDT", "ETH/USDT"}:
            raise RuntimeError("expected both market pairs to resolve")
        if result["reply"].count("模拟报价 ·") != 2:
            raise RuntimeError("expected two clearly marked simulated quotes")
        result = request("POST", "/v1/chat", {
            "user_id": user_id, "message": "可以给我一个模拟方案吗？", "include_simulation": True,
        })
        print(json.dumps({"user_id": user_id, "product_cap": result["product_cap"],
                          "simulation": result["simulation"]}, ensure_ascii=False), flush=True)
        if result["product_cap"] != product_cap or result["simulation"]["state"] != simulation_state:
            raise RuntimeError("unexpected simulation gate")
    if require_model:
        result = request("POST", "/v1/chat", {"user_id": "demo-learner", "message": "什么是流动性？请用一句话解释。"})
        print(json.dumps({"generation": result["generation"], "reply": result["reply"]}, ensure_ascii=False), flush=True)
        if result["generation"] != "remote_model":
            raise RuntimeError("expected a provider API reply")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--require-api-model", action="store_true")
    args = parser.parse_args()
    run(args.port, args.require_api_model)


if __name__ == "__main__":
    main()
