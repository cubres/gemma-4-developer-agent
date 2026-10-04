# SPDX-License-Identifier: MIT
# Copyright (c) 2026 cubres
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
"""Reproduce a real organizer-compiled ADK sequence with scripted local text.

Requires Python 3.12 on POSIX and an existing dependency environment containing
Google ADK 1.36.1, Google GenAI 2.11.0 and the organizer SDK's dependencies.
The caller supplies a licensed organizer source tree; this program includes no
organizer source, model assets, real tasks or submission bundle. No installation
or download is performed. Do not use Python -O, which disables mechanics checks.

Run from any working directory, with a NEW output directory:

    PYTHONDONTWRITEBYTECODE=1 python check_sequential_portable.py \
        --sdk-root /licensed/organizer/src \
        --output-dir /new/local/sequential-check

--sdk-root must contain adk_submission/adk_submission and swegemma/swegemma.
If ADK is not installed in the current Python environment, additionally supply
--adk-site-packages /dependency/environment/lib/python3.12/site-packages.
This inserts that directory before version/source validation; it does not create
or change an environment. Exact seven source pins are required, so drift fails.
All output is confined to the caller's new output directory; SDK inputs are read
only. Receipt/protocol JSON and original synthetic YAML fixtures are written.
A repeat run must use a different NEW output directory; existing output is never
overwritten. The process has a POSIX 90-second alarm and a 50-second async bound.

Real components: closed registry, organizer compiler, ADK SequentialAgent,
LlmAgent, Runner, state injection, SDK EvalConfig and budget APIs. Fixture
components: scripted BaseLlm responses, synthetic text and empty ToolRegistry.
The full evaluator, real model, sandbox, shell commands and repair quality are
not exercised. Manual budget API charges do not prove evaluator enforcement.
The public notebook attribution is an architectural idea, not a copied agent or
a claim that this fixture attains its score. See sibling provenance.json.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import signal
import socket
import sys
import time
from typing import ClassVar

SDK_PINS = {
    "adk_submission/adk_submission/compiler.py": "39cc4884699faf147ca1b326664e888c1861f750fe36525b840b5f812d593eed",
    "adk_submission/adk_submission/resolvers/generation.py": "ba8bf237261220d46843c8d71118faa387fc07f876f072756dff44d641dd1c14",
    "adk_submission/adk_submission/builders/workflows.py": "d8d7ccf9a51d57daec58c7231e2a62621a3ecca269e71ee64c57062cadadf980",
    "swegemma/swegemma/context.py": "97f06280c50df3132d1af7ef6126884b66b48887a1cf94b293af01e5907dc2a7",
    "swegemma/swegemma/config.py": "f035916218f895796c4d39f1f9ec25284152a6df57cf6de1fea4931165d2349f",
}
ADK_PINS = {
    "agents/sequential_agent.py": "10fb38007cd8f5ecea23df9311ef1fedbc72b9511ad3040c1b571785a6aad769",
    "agents/llm_agent.py": "7d0a8b71724536898ca7f347038dbbc1cf0eeb38d1d6f9e1077b8cfeb9461c0b",
}
PLAN = 'Synthetic source synthetic_module.py: preserve accepted input; check boundary "λ".\nNo repository execution.'
LIMITS = {"timeout_seconds": 60, "max_time_minutes": 5, "max_tool_calls": 60, "max_turns": 100}
NETWORK_ATTEMPTS: list[str] = []


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(text)


def stop_network() -> None:
    """Fail any attempted IP connection; Unix socketpair remains available."""
    original_connect = socket.socket.connect

    def guarded_connect(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            NETWORK_ATTEMPTS.append(repr(address))
            raise RuntimeError("Network connections are prohibited in this CPU fixture")
        return original_connect(sock, address)

    def guarded_create_connection(*args, **kwargs):
        NETWORK_ATTEMPTS.append(repr(args))
        raise RuntimeError("Network connections are prohibited in this CPU fixture")

    socket.socket.connect = guarded_connect
    socket.create_connection = guarded_create_connection


def main() -> None:
    started = time.perf_counter()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sdk-root", required=True, type=Path)
    parser.add_argument("--adk-site-packages", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    if not sys.dont_write_bytecode:
        raise RuntimeError("PYTHONDONTWRITEBYTECODE=1 is required")
    if sys.flags.optimize:
        raise RuntimeError("Python optimization disables mechanics assertions; use normal Python")
    if sys.version_info[:2] != (3, 12) or not hasattr(signal, "SIGALRM"):
        raise RuntimeError("This bounded fixture requires Python 3.12 on POSIX")
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError("90-second CPU bound")))
    signal.alarm(90)
    SDK = args.sdk_root.resolve(strict=True)
    RUN = args.output_dir.absolute()
    if RUN.exists():
        raise FileExistsError("Output directory already exists; provide a NEW directory")
    if args.adk_site_packages is not None:
        site_packages = args.adk_site_packages.resolve(strict=True)
        if not site_packages.is_dir():
            raise ValueError("--adk-site-packages must be a directory")
        sys.path.insert(0, str(site_packages))
    stop_network()
    os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
    os.environ["OTEL_SDK_DISABLED"] = "true"
    spec = importlib.util.find_spec("google.adk")
    if spec is None or not spec.submodule_search_locations:
        raise RuntimeError("Google ADK is unavailable in the selected environment")
    ADK = Path(next(iter(spec.submodule_search_locations))).resolve(strict=True)
    PINS = {SDK / path: value for path, value in SDK_PINS.items()}
    PINS.update({ADK / path: value for path, value in ADK_PINS.items()})
    assert len(PINS) == 7
    assert all(sha(path) == value for path, value in PINS.items()), "Pinned SDK/ADK source drift"
    assert importlib.metadata.version("google-adk") == "1.36.1"
    assert importlib.metadata.version("google-genai") == "2.11.0"
    if RUN.resolve().is_relative_to(SDK) or RUN.resolve().is_relative_to(ADK):
        raise ValueError("Output directory must be outside SDK/ADK source inputs")
    RUN.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(SDK / "adk_submission"))
    sys.path.insert(0, str(SDK / "swegemma"))

    import adk_submission
    import adk_submission.compiler as compiler
    import swegemma
    from adk_submission.registry import ModelRegistry, ToolRegistry
    from google.adk.agents import LlmAgent, SequentialAgent
    from google.adk.models.base_llm import BaseLlm
    from google.adk.models.llm_response import LlmResponse
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.adk.tools.agent_tool import AgentTool
    from google.genai import types
    from swegemma.budget import EvaluationBudget
    from swegemma.config import EvalConfig
    from swegemma.context import SwegemmaContext

    assert adk_submission.__version__ == "0.2.12"
    assert swegemma.__version__ == "0.2.7"
    module_paths = {
        "adk_submission.compiler": SDK / "adk_submission/adk_submission/compiler.py",
        "adk_submission.resolvers.generation": SDK / "adk_submission/adk_submission/resolvers/generation.py",
        "adk_submission.builders.workflows": SDK / "adk_submission/adk_submission/builders/workflows.py",
        "swegemma.context": SDK / "swegemma/swegemma/context.py",
        "swegemma.config": SDK / "swegemma/swegemma/config.py",
        "google.adk.agents.sequential_agent": ADK / "agents/sequential_agent.py",
        "google.adk.agents.llm_agent": ADK / "agents/llm_agent.py",
    }
    assert all(Path(sys.modules[name].__file__).resolve() == path for name, path in module_paths.items()), "Imported source differs from validated pins"

    class ScriptedLlm(BaseLlm):
        case: str
        stage: str
        response: str
        captures: ClassVar[dict[str, list[dict]]] = {}

        async def generate_content_async(self, llm_request, stream=False):
            assert stream is False
            config = llm_request.config
            instruction = config.system_instruction
            if not isinstance(instruction, str):
                instruction = "".join(part.text or "" for part in instruction.parts)
            self.captures.setdefault(self.case, []).append({
                "stage": self.stage, "system_instruction": instruction,
                "request": llm_request.model_dump(mode="json", exclude_none=True),
            })
            yield LlmResponse(content=types.Content(
                role="model", parts=[types.Part.from_text(text=self.response)],
            ), partial=False, turn_complete=True)

    specifications = [
        ("present_state", True, True),
        ("optional_absent_state", False, True),
        ("required_absent_state", False, False),
    ]
    fixtures = {}
    for case, store_plan, optional in specifications:
        directory = RUN / "synthetic_configuration" / case
        config = {
            "name": "synthetic_sequence", "agent_class": "SequentialAgent",
            "description": "Original local synthetic state-transfer fixture.",
            "sub_agents": [
                {"name": "synthetic_explorer", "model": "scripted_explorer",
                 "instruction": "Emit the fixed synthetic plan without tools.",
                 **({"output_key": "repair_plan"} if store_plan else {})},
                {"name": "synthetic_coder", "model": "scripted_coder",
                 "instruction": "Synthetic coder. STATE_BEGIN[{repair_plan" + ("?" if optional else "") + "}]STATE_END"},
            ],
        }
        explorer, coder = config["sub_agents"]
        config["sub_agents"] = [{"config_path": "explorer.yaml"}, {"config_path": "coder.yaml"}]
        write_new(directory / "explorer.yaml", json.dumps(explorer, indent=2) + "\n")
        write_new(directory / "coder.yaml", json.dumps(coder, indent=2) + "\n")
        write_new(directory / "agent.yaml", json.dumps(config, indent=2) + "\n")
        write_new(directory / "eval_config.yaml", json.dumps(LIMITS, indent=2) + "\n")
        fixtures[case] = {name: sha(directory / name) for name in ("agent.yaml", "explorer.yaml", "coder.yaml", "eval_config.yaml")}

    protocol = {
        "frozen_utc": datetime.now(timezone.utc).isoformat(),
        "prior_attempt": {"status": "COMPILER_SCHEMA_REJECTED_BEFORE_SCRIPTED_MODELS",
                          "reason": "Subagents require config_path references, not inline configuration",
                          "source_sha256": "16c5289663dfefee66f49734160142c121462fba6915901d6219bc8aee8ca0b9",
                          "protocol_sha256": "67896f8f9a35cb6f23054aeda2ceac1939b25434587bdd53eb453cffdaf2dc24"},
        "script_sha256": sha(Path(__file__)), "sdk_pins": {str(p): h for p, h in PINS.items()},
        "cases": [list(row) for row in specifications], "fixture_sha256": fixtures,
        "synthetic_plan": PLAN, "limits": LIMITS,
        "real": "Pinned organizer compiler, ADK SequentialAgent/LlmAgent/Runner/state injection, SDK budget APIs",
        "fixture": "Scripted BaseLlm, empty closed ToolRegistry, synthetic text, no organizer evaluator or tools",
        "hard_wall_seconds": 90, "real_model_calls": 0, "gpu": False,
        "native_tool_execution": False, "quality_evaluation": False,
    }
    write_new(RUN / "protocol.json", json.dumps(protocol, indent=2, sort_keys=True) + "\n")

    async def run_case(case, store_plan, optional):
        directory = RUN / "synthetic_configuration" / case
        models = ModelRegistry()
        models.register("scripted_explorer", ScriptedLlm(
            model="local_scripted_explorer", case=case, stage="explorer", response=PLAN))
        models.register("scripted_coder", ScriptedLlm(
            model="local_scripted_coder", case=case, stage="coder", response="SYNTHETIC_CODER_FINISHED"))
        config = EvalConfig(tasks_path=RUN / "unused_synthetic_tasks", snapshots_dir=RUN / "unused_snapshots",
                            results_dir=RUN / "unused_results", submission_dir=directory, models=models, **LIMITS)
        assert asdict(config.budget) == asdict(EvaluationBudget(time_minutes=5, tool_calls=60, turns=100))
        assert config.harness.command_timeout_seconds == 60
        agent = compiler.compile_submission(directory, ToolRegistry(), models,
                                            limits=config.limits, generation_constraints=config.generation_constraints)
        assert type(agent) is SequentialAgent
        assert [child.name for child in agent.sub_agents] == ["synthetic_explorer", "synthetic_coder"]
        assert all(type(child) is LlmAgent and child.tools == [] for child in agent.sub_agents)
        assert not any(isinstance(tool, AgentTool) for child in agent.sub_agents for tool in child.tools)
        sessions = InMemorySessionService()
        session = await sessions.create_session(app_name="synthetic_app", user_id="synthetic_user")
        runner = Runner(app_name="synthetic_app", agent=agent, session_service=sessions)
        context = SwegemmaContext(problem_statement="synthetic only", budget=config.budget, harness=config.harness)
        events, failure = [], None
        try:
            async for event in runner.run_async(user_id=session.user_id, session_id=session.id,
                                              new_message=types.Content(role="user", parts=[types.Part.from_text(text="Synthetic boundary repair.")])):
                context.handle_adk_event(event)
                events.append({"author": event.author, "state_delta": dict(event.actions.state_delta),
                               "is_final": event.is_final_response()})
        except KeyError as exc:
            failure = {"type": type(exc).__name__, "message": str(exc)}
        finally:
            await runner.close()
        final_session = await sessions.get_session(app_name="synthetic_app", user_id=session.user_id, session_id=session.id)
        captures = ScriptedLlm.captures[case]
        if store_plan:
            assert failure is None and final_session.state["repair_plan"] == PLAN
            assert "STATE_BEGIN[" + PLAN + "]STATE_END" in captures[1]["system_instruction"]
            assert events[0]["state_delta"] == {"repair_plan": PLAN}
        elif optional:
            assert failure is None and "repair_plan" not in final_session.state
            assert "STATE_BEGIN[]STATE_END" in captures[1]["system_instruction"]
        else:
            assert failure is not None and "repair_plan" in failure["message"]
            assert [row["stage"] for row in captures] == ["explorer"]
        expected_stages = ["explorer", "coder"] if optional else ["explorer"]
        assert [row["stage"] for row in captures] == expected_stages
        assert context.llm_calls_used == len(expected_stages) and context.tool_calls_used == 0
        assert context.sandbox is None
        return {"status": "PASS", "case": case, "state": final_session.state,
                "events": events, "scripted_requests": captures, "expected_failure": failure,
                "sdk_shared_context_model_events": context.llm_calls_used,
                "actual_native_tool_calls": 0, "no_parent_summary_model_call": True,
                "mapped_budget": asdict(config.budget), "mapped_harness": asdict(config.harness)}

    async def run_all():
        return [await run_case(*row) for row in specifications]

    results = asyncio.run(asyncio.wait_for(run_all(), timeout=50))
    # These are actual public SDK budget APIs, not a full evaluator run.
    shared_tool = SwegemmaContext(budget=EvaluationBudget(time_minutes=5, tool_calls=1, turns=100))
    assert shared_tool.check_budget() is None
    tool_rejection = json.loads(shared_tool.check_budget())
    assert tool_rejection["error_type"] == "BudgetExceeded" and shared_tool.tool_calls_used == 1
    shared_turn = SwegemmaContext(budget=EvaluationBudget(time_minutes=5, tool_calls=60, turns=2))
    for _ in range(2):
        shared_turn.record_llm_call()
    turn_rejection = json.loads(shared_turn.check_budget())
    assert turn_rejection["error_type"] == "BudgetExceeded" and "Turn" in turn_rejection["error_message"]
    no_time = SwegemmaContext(budget=EvaluationBudget(time_minutes=0, tool_calls=60, turns=100))
    time_rejection = json.loads(no_time.check_budget(count_tool_call=False))
    assert time_rejection["error_type"] == "TimeoutExceeded"
    assert all(sha(path) == value for path, value in PINS.items()), "SDK bytes changed"
    assert all(sha(RUN / "synthetic_configuration" / case / name) == value
               for case, members in fixtures.items() for name, value in members.items()), "Fixture bytes changed"
    assert not NETWORK_ATTEMPTS
    receipt = {
        "status": "PASS", "finished_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": time.perf_counter() - started, "script_sha256": sha(Path(__file__)),
        "protocol_sha256": sha(RUN / "protocol.json"), "case_count": len(results), "cases": results,
        "versions": {"google-adk": importlib.metadata.version("google-adk"),
                     "google-genai": importlib.metadata.version("google-genai"),
                     "adk-submission": adk_submission.__version__, "swegemma": swegemma.__version__},
        "python": sys.version, "sdk_pins": {str(p): h for p, h in PINS.items()},
        "budget_api_checks": {"one_tool_charge_then_reject": tool_rejection, "two_turn_charges_then_reject": turn_rejection,
                              "zero_time_reject": time_rejection, "native_tools_executed": False,
                              "fixture_charges_only": True, "full_evaluator_enforcement_exercised": False},
        "source_inputs_preserved": True, "fixture_inputs_preserved": True,
        "network_attempts": NETWORK_ATTEMPTS, "real_model_calls": 0, "scripted_model_calls": 5,
        "native_tool_calls": 0, "sandbox_commands": 0, "gpu": False, "notebook_changes": False,
        "hidden_runtime_attested": False, "solve_rate_or_score_claim": False,
    }
    write_new(RUN / "receipt.json", json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    signal.alarm(0)
    print(json.dumps({"status": receipt["status"], "elapsed_seconds": receipt["elapsed_seconds"],
                      "cases": [row["case"] for row in results], "receipt": str(RUN / "receipt.json")}, indent=2))


if __name__ == "__main__":
    main()
