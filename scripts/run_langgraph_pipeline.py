#!/usr/bin/env python3
"""
LangGraph orchestration wrapper for the Indian regime/factor dashboard.

The quantitative work remains in run_pipeline.py. This file turns those
functions into explicit graph nodes with shared state, validation/review,
approval flags, and optional Groq explanation generation.
"""

from __future__ import annotations

import json
import os
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

import run_pipeline as rp


class PipelineState(TypedDict, total=False):
    conn: sqlite3.Connection
    validation_report: dict[str, Any]
    symbols: list[str]
    news_articles: list[dict[str, Any]]
    news_features: list[dict[str, Any]]
    regime_preds: list[dict[str, Any]]
    baskets: list[dict[str, Any]]
    factor_names: list[str]
    factor_returns: list[dict[str, Any]]
    diagnostics: list[dict[str, Any]]
    allocations: list[dict[str, Any]]
    decisions: list[dict[str, Any]]
    portfolio_targets: list[dict[str, Any]]
    rebalance_trades: list[dict[str, Any]]
    bt_portfolio: list[dict[str, Any]]
    bt_summary: list[dict[str, Any]]
    signal_events: list[dict[str, Any]]
    warnings: list[str]
    human_approval_required: bool
    llm_explanation: str
    route: str


def read_env_file() -> dict[str, str]:
    env_path = rp.PROJECT_DIR / ".env"
    values: dict[str, str] = {}
    if not env_path.exists():
        return values
    for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def compact_latest_snapshot(state: PipelineState) -> dict[str, Any]:
    latest_regime = (state.get("regime_preds") or [{}])[-1]
    latest_alloc = (state.get("allocations") or [{}])[-1]
    latest_decision = (state.get("decisions") or [{}])[-1]
    latest_news = (state.get("news_features") or [{}])[-1]
    return {
        "latest_regime": latest_regime,
        "latest_allocation": latest_alloc,
        "latest_decision": latest_decision,
        "latest_news_features": latest_news,
        "warnings": state.get("warnings", []),
        "human_approval_required": state.get("human_approval_required", False),
    }


def groq_explanation(state: PipelineState) -> str:
    key = os.environ.get("GROQ_API_KEY") or read_env_file().get("GROQ_API_KEY")
    snapshot = compact_latest_snapshot(state)
    if not key:
        return "Groq explanation skipped because GROQ_API_KEY is not configured."

    prompt = (
        "Explain this monthly Indian Nifty 200 regime/factor decision in concise technical language. "
        "Mention regime, news evidence, decision gate, factor allocation, and whether human approval is needed. "
        f"Data snapshot:\n{json.dumps(snapshot, default=str)[:7000]}"
    )
    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {"role": "system", "content": "You are a financial ML pipeline explanation agent. Do not give investment advice."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 450,
    }
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"].strip()
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, IndexError, json.JSONDecodeError) as exc:
        return f"Groq explanation fallback: API call failed, so deterministic report is used. Error: {exc}"


def open_database_node(state: PipelineState) -> PipelineState:
    if not rp.INPUT_DB.exists():
        return {"warnings": [f"Input database missing: {rp.INPUT_DB}"], "route": "data_failed"}
    return {"conn": sqlite3.connect(str(rp.INPUT_DB)), "warnings": [], "route": "ok"}


def rss_news_node(state: PipelineState) -> PipelineState:
    news_articles, news_features = rp.rss_news_agent()
    return {"news_articles": news_articles, "news_features": news_features}


def data_validation_node(state: PipelineState) -> PipelineState:
    validation_report, symbols = rp.data_validation_agent(state["conn"])
    warnings = list(state.get("warnings", []))
    if not symbols:
        warnings.append("No tradable symbols were detected after validation.")
        return {"validation_report": validation_report, "symbols": symbols, "warnings": warnings, "route": "data_failed"}
    return {"validation_report": validation_report, "symbols": symbols, "warnings": warnings, "route": "ok"}


def regime_node(state: PipelineState) -> PipelineState:
    return {"regime_preds": rp.regime_detection_agent(state["conn"], state.get("news_features"))}


def factor_node(state: PipelineState) -> PipelineState:
    baskets, factor_names = rp.factor_scoring_agent(state["conn"], state["regime_preds"])
    return {"baskets": baskets, "factor_names": factor_names}


def factor_forecast_node(state: PipelineState) -> PipelineState:
    factor_returns, diagnostics = rp.factor_forecast_agent(state["conn"], state["baskets"], state["regime_preds"])
    return {"factor_returns": factor_returns, "diagnostics": diagnostics}


def allocation_node(state: PipelineState) -> PipelineState:
    allocations, decisions = rp.allocation_optimizer_agent(
        state["factor_returns"],
        state["diagnostics"],
        state["regime_preds"],
        state.get("news_features"),
        state.get("news_articles"),
    )
    return {"allocations": allocations, "decisions": decisions}


def review_node(state: PipelineState) -> PipelineState:
    warnings = list(state.get("warnings", []))
    latest_decision = (state.get("decisions") or [{}])[-1]
    latest_alloc = (state.get("allocations") or [{}])[-1]
    approval_required = False

    if latest_decision.get("decision") in {"REBALANCE", "DEFENSIVE"}:
        approval_required = True
    if float(latest_alloc.get("turnover", 0) or 0) > 0.4:
        approval_required = True
        warnings.append("Latest turnover is above 40%; human approval should review rebalance size.")
    if float(latest_decision.get("news_stress_score", 0) or 0) > 0.45:
        approval_required = True
        warnings.append("High news stress detected; decision requires review before live rebalance.")

    return {"warnings": warnings, "human_approval_required": approval_required}


def portfolio_node(state: PipelineState) -> PipelineState:
    targets, trades = rp.portfolio_transition_agent(state["conn"], state["baskets"], state["allocations"], state["regime_preds"])
    return {"portfolio_targets": targets, "rebalance_trades": trades}


def diagnostics_node(state: PipelineState) -> PipelineState:
    rp.risk_diagnostics_agent(state["diagnostics"], state["regime_preds"])
    return {}


def backtest_node(state: PipelineState) -> PipelineState:
    bt_portfolio, bt_summary = rp.backtest_agent(state["conn"], state["allocations"], state["rebalance_trades"], state["regime_preds"])
    return {"bt_portfolio": bt_portfolio, "bt_summary": bt_summary}


def chart_signal_node(state: PipelineState) -> PipelineState:
    return {"signal_events": rp.chart_signal_agent(state["conn"], state["rebalance_trades"], state["baskets"])}


def explanation_node(state: PipelineState) -> PipelineState:
    rp.explanation_agent(
        state["validation_report"],
        state["regime_preds"],
        state["baskets"],
        state["factor_returns"],
        state["diagnostics"],
        state["allocations"],
        state["decisions"],
        state["portfolio_targets"],
        state["rebalance_trades"],
        state["bt_portfolio"],
        state["bt_summary"],
        state["signal_events"],
    )
    llm_text = groq_explanation(state)
    report = {
        "orchestration": "LangGraph StateGraph",
        "nodes": [
            "OpenDatabase", "RSSNewsAgent", "DataValidationAgent", "RegimeDetectionAgent",
            "FactorScoringAgent", "FactorForecastAgent", "AllocationOptimizerAgent",
            "ReviewApprovalAgent", "PortfolioTransitionAgent", "RiskDiagnosticsAgent",
            "BacktestAgent", "ChartSignalAgent", "ExplanationAgent",
        ],
        "conditional_routes": ["data_failed -> End", "ok -> downstream nodes"],
        "human_approval_required": state.get("human_approval_required", False),
        "warnings": state.get("warnings", []),
        "llm_explanation": llm_text,
        "latest_snapshot": compact_latest_snapshot(state),
    }
    rp.write_json("langgraph_run_report", report)
    (rp.PROJECT_DIR / "langgraph_run_report.md").write_text(
        "# LangGraph Run Report\n\n"
        f"- Human approval required: {report['human_approval_required']}\n"
        f"- Warnings: {len(report['warnings'])}\n\n"
        "## LLM Explanation\n\n"
        f"{llm_text}\n",
        encoding="utf-8",
    )
    return {"llm_explanation": llm_text}


def close_node(state: PipelineState) -> PipelineState:
    conn = state.get("conn")
    if conn:
        conn.close()
    return {}


def route_after_validation(state: PipelineState) -> str:
    return "stop" if state.get("route") == "data_failed" else "continue"


def build_graph():
    graph = StateGraph(PipelineState)
    graph.add_node("open_database", open_database_node)
    graph.add_node("rss_news", rss_news_node)
    graph.add_node("data_validation", data_validation_node)
    graph.add_node("regime_detection", regime_node)
    graph.add_node("factor_scoring", factor_node)
    graph.add_node("factor_forecast", factor_forecast_node)
    graph.add_node("allocation_optimizer", allocation_node)
    graph.add_node("review_approval", review_node)
    graph.add_node("portfolio_transition", portfolio_node)
    graph.add_node("risk_diagnostics", diagnostics_node)
    graph.add_node("backtest", backtest_node)
    graph.add_node("chart_signals", chart_signal_node)
    graph.add_node("explanation", explanation_node)
    graph.add_node("close", close_node)

    graph.set_entry_point("open_database")
    graph.add_edge("open_database", "rss_news")
    graph.add_edge("rss_news", "data_validation")
    graph.add_conditional_edges("data_validation", route_after_validation, {"continue": "regime_detection", "stop": "close"})
    graph.add_edge("regime_detection", "factor_scoring")
    graph.add_edge("factor_scoring", "factor_forecast")
    graph.add_edge("factor_forecast", "allocation_optimizer")
    graph.add_edge("allocation_optimizer", "review_approval")
    graph.add_edge("review_approval", "portfolio_transition")
    graph.add_edge("portfolio_transition", "risk_diagnostics")
    graph.add_edge("risk_diagnostics", "backtest")
    graph.add_edge("backtest", "chart_signals")
    graph.add_edge("chart_signals", "explanation")
    graph.add_edge("explanation", "close")
    graph.add_edge("close", END)
    return graph.compile()


def main():
    print("=" * 60)
    print("Indian Regime/Factor/Portfolio LangGraph Orchestration")
    print("=" * 60)
    app = build_graph()
    app.invoke({})
    print("=" * 60)
    print("LangGraph pipeline complete.")
    print(f"  JSON outputs: {rp.JSON_DIR}")
    print(f"  Report: {rp.PROJECT_DIR / 'langgraph_run_report.md'}")
    print("=" * 60)


if __name__ == "__main__":
    main()
