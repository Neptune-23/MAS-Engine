# Company AI Toolkit (MAS-Engine)

> A production-grade, self-evolving autonomous coding agent kernel and MCP toolchain service engineered for enterprise development workflows.

---

## 📌 Architecture & Key Features

Built on top of the **Model Context Protocol (MCP)**, this project combines a deterministic finite state machine (FSM) with an action chunk execution pipeline to achieve both LLM reasoning power and reliable engineering guarantees.

### 1. 🔌 Dedicated Language Adapters
- **Multi-Language AST Support**: Built-in specialized adapters for languages including Python and PHP, with automatic runtime detection.
- **Syntax Validation & Sanitization**: Pre-execution AST syntax verification and automated code cleaning to prevent malformed code from propagating downstream.

### 2. ⚡ Kernel Action Chunk & Runner
- **Atomic Action Pipelines**: Translates high-level LLM outputs into structured `ActionPrimitive` sequences grouped into executable `ActionChunk` units.
- **Continuous Execution with Barriers**: Supports non-blocking continuous execution while intercepting uncertain boundaries via barrier mechanics for automated verification.

### 3. 🛡️ State Machine Governance & Circuit Breakers
- **Explicit Transition Whitelist**: Enforces strict state transitions across task lifecycles to prevent invalid execution paths.
- **TTL Cache & Healing Circuit Breaker**: Features automated cache TTL invalidation and a self-healing retry circuit breaker to prevent infinite repair loops and token exhaustion.
- **Anti-Reward Hacking Detection**: Identifies and blocks degenerate agent behaviors, such as test-suite bypassing, mock passes, or empty implementations.

### 4. ✂️ AST-Guided Code Slicer
- **Precision Context Extraction**: Analyzes dependency graphs via AST to isolate affected classes, functions, and minimal relevant context.
- **Benchmarked Token Reduction**: Drastically shrinks prompt token footprints, improving inference throughput while minimizing LLM hallucination risks.

### 5. 🌱 RSI Recursive Self-Improvement Engine
- **0-Token Fast-Path Self-Healing**: Automatically matches known error signatures against cataloged macro skills (`EvolvedSkillRegistry`) for instant, sub-second remediation without LLM inference overhead.
- **Online Trajectory Mining & Skill Synthesis**: Upon task completion, `TrajectoryMiner` discovers recurring success patterns, and `SkillSynthesizer` compiles them into executable macro skills to dynamically expand the agent's action space at runtime.

### 6. 📊 Telemetry & Data Flywheel
- **End-to-End Session Tracking**: Tracks complete lifecycle events, device fingerprints, per-step latencies, state transitions, and task verdicts.
- **Automated SFT & DPO Dataset Export**: Automatically formats and exports execution trajectories into standard SFT and DPO alignment datasets to power ongoing model fine-tuning.

---

## 📂 Project Structure

```
company-ai-toolkit/
├── mcp-server/              # MCP server entry point and RPC dispatcher
│   └── server.py            # Main dispatch loop, state machine orchestration, and broadcast events
├── kernel/                  # Core scheduling and execution kernel
│   ├── chunk.py             # ActionChunk and ActionPrimitive definitions
│   ├── runner.py            # ActionChunkRunner pipeline engine
│   └── evolution.py         # Skill registry, trajectory miner, and skill synthesizer
├── state_machine/           # Task state machine definitions and transition policies
├── adapters/                # Dedicated language adapters (Python, PHP, etc.)
├── tools/                   # Workspace analysis and AST code slicing utilities
├── telemetry/               # Session metrics, device fingerprinting, and SFT/DPO exporters
└── tests/                   # Comprehensive test suite (16 automated tests)


🚀 Quick Start
1. Prerequisites & Environment Setup
Python 3.11+ (tested on Python 3.13):

Bash
# Create and activate virtual environment
python -m venv venv

# Windows (PowerShell)
.\venv\Scripts\Activate.ps1

# Linux / macOS
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
2. Linting & Testing
Bash
# Run linting with auto-fix
ruff check . --fix

# Run the complete test suite
pytest -v
3. Launching the MCP Server
Bash
python mcp_server/server.py


🧪 Test Suite Overview
The project maintains 100% pass rates across its core modules:

test_adapters.py: Adapter registry, dispatching, and syntax cleaning

test_anti_reward_hacking.py: Anti-reward hacking heuristics and interception

test_code_slicer.py: AST slicing precision and token reduction benchmarks

test_evolution.py: Trajectory pattern mining and RSI 0-Token fast-path fixes

test_kernel_chunk.py: Continuous pipeline execution and barrier interception

test_state_machine.py: Transition whitelisting, cache TTL, and circuit breaking

test_telemetry.py: Device fingerprinting and telemetry session export

test_trajectory.py: Full trajectory recording and SFT/DPO dataset export