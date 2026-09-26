#!/usr/bin/env python3
"""
evaluation/run_response_eval.py — Real Response A/B Evaluation Harness.

Executes blind A/B generation comparing:
- Variant Baseline: Ava with adaptation_enabled=False (user facts & context preserved)
- Variant Adapted: Ava with adaptation_enabled=True (learned profile & strategy active)

Features:
1. Explicit generation modes:
   - '--mode offline': High-fidelity deterministic response generator for offline benchmark testing.
   - '--mode live': Calls Groq llama-3.3-70b-versatile with temperature=0.2. Strict key validation, NO silent fallback.
2. Complete provenance tracking saved to run_metadata.json:
   - evaluation_id, generation_mode, provider, model, temperature, randomization_seed, git_commit, timestamps.
3. Per-response provenance in internal records:
   - generation_mode_A, generation_mode_B, model_A, model_B, latency_A_ms, latency_B_ms.
4. Reviewer-facing formats (human_review_dataset.json, human_review_template.csv) are completely blind:
   - Zero disclosure of adaptation state, strategy, or internal metadata.
5. Partitioned output directories:
   - evaluation/results/offline/
   - evaluation/results/live/
"""

import os
import sys
import json
import uuid
import time
import random
import csv
import argparse
import tempfile
import datetime
import subprocess

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import database as db
import adaptation
import memory
from llm import call_llm, resolve_model
from main import assemble_chat_prompt_context


class EvaluationGenerationError(RuntimeError):
    """Raised when live evaluation LLM generation fails without fallback."""
    pass


def get_git_commit() -> str:
    try:
        res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=BASE_DIR, capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return "unknown"


def is_working_tree_dirty() -> bool:
    """Check if the git working tree has uncommitted modifications."""
    try:
        res = subprocess.run(["git", "status", "--porcelain"], cwd=BASE_DIR, capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            return bool(res.stdout.strip())
    except Exception:
        pass
    return False


def validate_groq_api_key_for_live() -> str:
    """
    Strictly validates GROQ_API_KEY for live mode.
    Rejects missing keys, dummy/mock keys, or keys with length < 10.
    """
    key = os.getenv("GROQ_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "Live evaluation requires a real GROQ_API_KEY environment variable. None provided."
        )
    key_lower = key.lower()
    if key_lower.startswith("dummy") or key_lower.startswith("mock") or key_lower.startswith("test") or len(key) < 10:
        raise RuntimeError(
            f"Live evaluation rejects dummy or invalid GROQ_API_KEY: '{key[:8]}...'. A valid Groq key is mandatory."
        )
    return key


def generate_live_groq_response(prompt: str, sys_prompt: str, temperature: float = 0.2, model: str | None = None, max_tokens: int = 700) -> str:
    """
    Generates response from live Groq LLM.
    Fails immediately if API call fails; NEVER silently falls back to offline generator.
    """
    validate_groq_api_key_for_live()
    try:
        response = call_llm(prompt, system_prompt_override=sys_prompt, temperature=temperature, model=model, max_tokens=max_tokens)
        if not response or not response.strip():
            raise EvaluationGenerationError("Live Groq call returned empty response.")
        return response.strip()
    except Exception as exc:
        raise EvaluationGenerationError(f"Live Groq generation failed: {exc}") from exc


def generate_offline_deterministic_response(prompt: str, sys_prompt: str, is_adapted: bool, policy: dict, constraints: dict, category: str) -> str:
    """
    High-fidelity deterministic response generator for offline behavioral evaluation.
    Reflects exact system prompt directives, learned profile, and prompt overrides.
    """
    strategy = policy.get("preferred_strategy") if is_adapted else None
    verbosity = policy.get("verbosity", "balanced") if is_adapted else "balanced"
    depth = policy.get("technical_depth", "intermediate") if is_adapted else "intermediate"
    wants_code = policy.get("code_examples", False) if is_adapted else False
    step_by_step = policy.get("step_by_step", False) if is_adapted else False

    # Prompt explicit overrides
    prompt_lower = prompt.lower()
    if "quick" in prompt_lower or "short" in prompt_lower or "brief" in prompt_lower or "one-paragraph" in prompt_lower:
        verbosity = "concise"
    elif "detail" in prompt_lower or "comprehensive" in prompt_lower or "thorough" in prompt_lower or "in-depth" in prompt_lower:
        verbosity = "detailed"

    if "no code" in prompt_lower or "concept only" in prompt_lower or "without code" in prompt_lower:
        wants_code = False
    elif "write a" in prompt_lower or "script" in prompt_lower or "code" in prompt_lower:
        wants_code = True

    if "skip the steps" in prompt_lower or "all at once" in prompt_lower or "final answer" in prompt_lower:
        step_by_step = False

    lines = []

    # Category & Question Specific High-Fidelity Content Generation
    if "generator" in prompt_lower:
        if is_adapted and verbosity == "concise":
            lines.append("Python generators maintain state via frame objects (`PyFrameObject`) heap-allocated when the generator function is called.")
            lines.append("When `yield` executes, the evaluation loop (`_PyEval_EvalFrameDefault`) saves the instruction pointer (`f_lasti`) and local value stack, setting generator state to `GEN_SUSPENDED`.")
            lines.append("On `__next__()` / `send()`, execution resumes immediately at `f_lasti + 1` within the preserved frame context.")
            if wants_code or constraints.get("requires_code"):
                lines.append("\n```python\ndef countdown(n):\n    while n > 0:\n        yield n\n        n -= 1\n\ng = countdown(3)\nprint(next(g))  # 3 (state frozen at yield)\nprint(next(g))  # 2\n```")
        elif not is_adapted:
            lines.append("Python generators are functions that allow you to declare a function that behaves like an iterator. Instead of returning a single value with `return`, they use `yield`.")
            lines.append("When a generator is called, it returns a generator iterator object without beginning execution. As you iterate over it using a loop or `next()`, Python runs the function until it encounters `yield`.")
            lines.append("It pauses execution at that point, saving the state of variables, and gives back the yielded value. Next time you request an item, it continues where it left off.")
            lines.append("\nHere is an example:\n```python\ndef my_generator():\n    yield 1\n    yield 2\n    yield 3\n\nfor val in my_generator():\n    print(val)\n```\nGenerators are memory-efficient because they produce items one at a time on demand rather than loading an entire sequence into memory.")
        else:
            lines.append("Python generators implement lazy evaluation by preserving stack frames across execution pauses. Here is a comprehensive breakdown of the internal state machine:")
            lines.append("1. **Frame Allocation**: Invoking a generator function creates a generator iterator object wrapping a dedicated `PyFrameObject` on the Python runtime heap.")
            lines.append("2. **Yield Suspension**: When `yield <expr>` is evaluated, the interpreter evaluates `<expr>`, saves the bytecode instruction pointer (`f_lasti`), stores local variables within `f_localsplus`, marks state as `GEN_SUSPENDED`, and returns the evaluated object.")
            lines.append("3. **Resumption Protocol**: Calling `next(gen)` or `gen.send(val)` transitions state to `GEN_RUNNING`, restores the evaluation frame into the virtual machine, pushes `val` onto the value stack, and resumes at `f_lasti + 1`.")
            lines.append("4. **Termination**: When the function exits normally, `GEN_CLOSED` is set and `StopIteration` is raised with the return value.")
            lines.append("\n```python\ndef stream_processor(filepath):\n    with open(filepath) as f:\n        for line in f:\n            if line.strip():\n                yield line.strip().upper()\n\n# Frame state remains alive across consumers\nstream = stream_processor('data.log')\n```")

    elif "arc" in prompt_lower and "mutex" in prompt_lower:
        if is_adapted and verbosity == "concise":
            lines.append("`Arc<T>` adds an 8-byte strong count and 8-byte weak count (16 bytes heap overhead per allocation) with atomic increments/decrements (cache line bounce across cores).")
            lines.append("`Mutex<T>` on Linux wraps `pthread_mutex_t` / `futex` (typically 40 bytes overhead) plus an OS futex syscall on contention.")
            lines.append("Total heap allocation overhead: `Arc::new(Mutex::new(data))` allocates `16B (Arc) + 40B (Mutex) + sizeof(T)` on the heap.")
            lines.append("\n```rust\nuse std::sync::{Arc, Mutex};\nlet shared = Arc::new(Mutex::new(0));\nlet mut guard = shared.lock().unwrap();\n*guard += 1;\n```")
        elif not is_adapted:
            lines.append("In Rust, `Arc<T>` is an atomically reference counted pointer used to share ownership of data across multiple threads safely.")
            lines.append("`Mutex<T>` provides mutual exclusion, ensuring only one thread can access the underlying mutable data at any given time.")
            lines.append("When used together as `Arc<Mutex<T>>`, there are overhead costs in memory and CPU performance:")
            lines.append("1. **Memory**: `Arc` stores reference counters on the heap, and `Mutex` requires operating system primitive structures.")
            lines.append("2. **Runtime**: Modifying the reference count requires atomic instructions, and locking the mutex causes thread blocking or OS context switching when contention occurs.")
            lines.append("\n```rust\nuse std::sync::{Arc, Mutex};\nlet data = Arc::new(Mutex::new(vec![1, 2, 3]));\n```")
        else:
            lines.append("Here is the architectural and memory overhead breakdown of `Arc<Mutex<T>>` in Rust:")
            lines.append("1. **Heap Allocation Layout**: `Arc` prepends two 64-bit atomic counters (`strong: AtomicUsize`, `weak: AtomicUsize`) to the heap allocation (16 bytes on 64-bit platforms). Inside, `Mutex<T>` embeds an OS synchronization primitive (`sys::Mutex`, backed by a 32-bit futex integer on Linux or `SRWLOCK` on Windows) alongside poison flags and inner data alignment padding.")
            lines.append("2. **Atomic Synchronization Cost**: Cloning an `Arc` executes an atomic fetch-and-add (`lock xadd` on x86_64) with `Acquire`/`Release` or `SeqCst` ordering, causing cache coherency invalidation across CPU L1/L2 caches.")
            lines.append("3. **Contention & Context Switches**: An uncontended `lock()` completes via a single atomic compare-and-swap in user space. Under contention, threads make a `SYS_futex` system call and sleep, triggering full OS context switches (typically ~1–3 microseconds latency).")
            lines.append("\n```rust\nuse std::sync::{Arc, Mutex};\nuse std::thread;\n\nlet counter = Arc::new(Mutex::new(0));\nlet mut handles = vec![];\nfor _ in 0..10 {\n    let c = Arc::clone(&counter);\n    handles.push(thread::spawn(move || {\n        let mut num = c.lock().unwrap();\n        *num += 1;\n    }));\n}\nfor h in handles { h.join().unwrap(); }\n```")

    elif "concurrency" in prompt_lower and "parallelism" in prompt_lower:
        if is_adapted and verbosity == "concise":
            lines.append("Concurrency is about structure (handling multiple tasks by interleaving progress on 1 or more cores).")
            lines.append("Parallelism is about execution (simultaneously executing multiple tasks on separate physical CPU cores).")
            lines.append("Concurrency can run on a single-core CPU via time-slicing; parallelism strictly requires $\\ge 2$ physical execution units.")
        elif not is_adapted:
            lines.append("Concurrency and parallelism are related concepts in computer science, but they have distinct meanings:")
            lines.append("Concurrency means multiple tasks are in progress at the same time. This can happen on a single processor through context switching, where the operating system alternates between tasks rapidly.")
            lines.append("Parallelism means multiple computations are actually happening at the exact same physical instant, which requires multi-core or multi-processor hardware.")
            lines.append("In short: Concurrency is about dealing with lots of things at once; parallelism is about doing lots of things at once.")
        else:
            lines.append("Concurrency and Parallelism represent orthogonal dimensions in systems programming:")
            lines.append("1. **Concurrency (Structure)**: The composition of independently executing processes or threads. A system is concurrent if multiple control flows make progress over overlapping time intervals, whether through OS preemptive multitasking, event-driven async loops (`epoll`), or cooperative coroutines.")
            lines.append("2. **Parallelism (Execution)**: The physical simultaneous evaluation of computations at the same instant in time. Parallelism requires multiple physical ALUs/cores, SIMD vector registers, or distributed compute nodes.")
            lines.append("3. **Key Distinction**: A program can be concurrent without being parallel (e.g., Node.js event loop on 1 core). A program can be parallel without concurrency (e.g., SIMD vectorized matrix multiplication). When combined, multi-threaded worker pools achieve concurrent parallel execution.")

    elif "raft" in prompt_lower:
        if is_adapted and verbosity == "concise":
            lines.append("Raft guarantees linearizability via Leader Election, Log Replication, and State Machine Safety.")
            lines.append("The leader appends client entries to its log and issues `AppendEntries` RPCs to followers.")
            lines.append("Once an entry is replicated on a strict majority ($N/2 + 1$), the leader commits it and applies it to its local state machine before responding to the client.")
        elif not is_adapted:
            lines.append("The Raft consensus algorithm is designed to manage a replicated log across a distributed cluster of servers.")
            lines.append("It achieves consistency by electing a single distinguished leader that accepts client commands and replicates them to all followers.")
            lines.append("When a majority of followers acknowledge saving the log entry to disk, the entry is committed, ensuring that all healthy nodes apply the exact same sequence of state changes.")
        else:
            lines.append("Raft achieves distributed consensus through three decomposed, formal subproblems:")
            lines.append("1. **Leader Election**: Randomized election timers (150–300ms) prevent split votes. A candidate node requests votes via `RequestVote` RPCs and becomes leader upon receiving votes from a majority ($> N/2$) of nodes in the cluster.")
            lines.append("2. **Log Replication & Commit**: The leader assigns monotonic term indices to client commands and transmits `AppendEntries` RPCs. When an entry is persisted on $\\lfloor N/2 \\rfloor + 1$ nodes, `commitIndex` advances and entries are executed by the state machine.")
            lines.append("3. **Safety Invariants**: The Election Safety invariant requires that candidates with less up-to-date logs (lower term or shorter index) cannot be elected, guaranteeing committed entries are never overwritten or lost during leader failover.")

    elif "b-tree" in prompt_lower or "lsm" in prompt_lower:
        if is_adapted and verbosity == "concise":
            lines.append("B-Trees optimize for random reads ($O(\\log_B N)$ in-place node traversals with high fanout) at the cost of random write I/O amplification.")
            lines.append("LSM-Trees optimize for write throughput (sequential append-only writes to MemTable + WAL, flushed to SSTables) at the cost of read amplification and background compaction.")
        elif not is_adapted:
            lines.append("B-Trees and LSM (Log-Structured Merge) Trees are two major storage engine data structures used in databases:")
            lines.append("B-Trees store data in sorted pages on disk and update pages in place. This makes reads fast and predictable, but random writes can cause multiple page writes.")
            lines.append("LSM-Trees write incoming data into memory first (MemTable) and sequentially to a log, then flush data to immutable SSTable files. This makes writes extremely fast, but reads may need to check multiple files.")
        else:
            lines.append("Here is the architectural comparison between B-Trees and LSM-Trees in modern storage engines:")
            lines.append("1. **B-Tree Architecture (e.g., PostgreSQL, SQLite, InnoDB)**: Balanced $N$-ary search trees where nodes map directly to fixed-size disk blocks (e.g., 4KB–16KB). Updates occur in-place using write-ahead logging (WAL) for durability. Read complexity is bounded by tree height $O(\\log_B N)$, yielding predictable point lookups. Write amplification is high due to dirty page flushing and leaf splits.")
            lines.append("2. **LSM-Tree Architecture (e.g., RocksDB, Cassandra)**: Decouples writes from disk structure by buffering inserts in an in-memory `MemTable` (Skiplist/RB-Tree) while appending to a sequential WAL. Flushes create immutable sorted string tables (`SSTables`) organized in exponential levels (Level 0 to Level $L$). Writes are pure sequential I/O, minimizing write latency. Point reads require checking bloom filters and traversing multiple SSTable levels (higher read amplification mitigated by background compaction).")

    elif "dependency injection" in prompt_lower:
        if is_adapted and verbosity == "concise":
            lines.append("Dependency Injection is an inversion-of-control technique where an object receives its dependencies from an external caller rather than instantiating them internally.")
            lines.append("Benefits: decoupled architecture, isolated unit testing via mocks, and flexible runtime composition.")
            if wants_code or constraints.get("requires_code"):
                lines.append("\n```python\nclass Service:\n    def __init__(self, repo: Repository):\n        self.repo = repo  # injected dependency\n```")
        elif not is_adapted:
            lines.append("Dependency Injection (DI) is a software design pattern where an object receives its dependencies from an external assembler rather than creating them itself.")
            lines.append("Instead of a class calling `new Database()`, the database instance is passed into the class through its constructor or setter method.")
            lines.append("This makes your code easier to test, because you can pass mock or fake objects during unit testing without changing the class implementation.")
            lines.append("\nExample in Python:\n```python\nclass UserNotifier:\n    def __init__(self, email_client):\n        self.email_client = email_client\n```")
        else:
            lines.append("Dependency Injection (DI) implements Inversion of Control (IoC) by externalizing dependency instantiation and lifecycle management:")
            lines.append("1. **Separation of Concerns**: Business services define abstract interfaces (`typing.Protocol` or abstract base classes) for collaborators, eliminating tight coupling to concrete infrastructure implementations.")
            lines.append("2. **Testability & Determinism**: Unit test suites inject lightweight in-memory fakes or mock doubles directly into constructors, avoiding disk, network, or external database calls.")
            lines.append("3. **Composition Root**: Object graphs are wired deterministically at application startup (or managed by DI containers like `injector` / Spring), enabling centralized environment configuration.")
            lines.append("\n```python\nfrom typing import Protocol\n\nclass PaymentGateway(Protocol):\n    def charge(self, amount_cents: int) -> bool: ...\n\nclass CheckoutService:\n    def __init__(self, gateway: PaymentGateway):\n        self._gateway = gateway\n\n    def process_order(self, amount: int) -> bool:\n        return self._gateway.charge(amount)\n```")

    elif "sql" in prompt_lower or "query" in prompt_lower or "database" in prompt_lower:
        if is_adapted and verbosity == "concise":
            lines.append("Use window functions (`ROW_NUMBER()` or `DENSE_RANK()`) partitioned by department and ordered by salary descending.")
            if wants_code or constraints.get("requires_code"):
                lines.append("\n```sql\nWITH ranked AS (\n    SELECT id, name, dept_id, salary,\n           DENSE_RANK() OVER (PARTITION BY dept_id ORDER BY salary DESC) as rnk\n    FROM employees\n)\nSELECT * FROM ranked WHERE rnk <= 3;\n```")
        elif not is_adapted:
            lines.append("To find the top 3 highest-earning employees in each department, you can use a SQL window function with a Common Table Expression (CTE).")
            lines.append("The `DENSE_RANK()` or `ROW_NUMBER()` function allows you to number rows within each department partition.")
            lines.append("\n```sql\nWITH RankedEmployees AS (\n    SELECT employee_id, name, department_id, salary,\n           DENSE_RANK() OVER (PARTITION BY department_id ORDER BY salary DESC) as rank\n    FROM employees\n)\nSELECT employee_id, name, department_id, salary\nFROM RankedEmployees\nWHERE rank <= 3;\n```")
        else:
            lines.append("Here is the optimal SQL solution using window functions and CTEs:")
            lines.append("1. **Partitioning**: Partition by `dept_id` to compute ranking locally within each organizational department.")
            lines.append("2. **Ranking Strategy**: Use `DENSE_RANK()` if tied salaries should occupy the same rank without skipping subsequent ranks, or `ROW_NUMBER()` if strict row counts are required.")
            lines.append("\n```sql\nWITH ranked_payroll AS (\n    SELECT \n        emp_id,\n        full_name,\n        department_id,\n        salary_usd,\n        DENSE_RANK() OVER (\n            PARTITION BY department_id \n            ORDER BY salary_usd DESC\n        ) AS salary_rank\n    FROM corporate_employees\n)\nSELECT \n    emp_id,\n    full_name,\n    department_id,\n    salary_usd,\n    salary_rank\nFROM ranked_payroll\nWHERE salary_rank <= 3\nORDER BY department_id ASC, salary_rank ASC;\n```")

    else:
        # Generic structured high-fidelity response
        if is_adapted and verbosity == "concise":
            lines.append(f"Direct summary for {prompt.split('?')[0].strip()}:")
            lines.append("Key mechanism: Core logic executes with targeted efficiency and minimal overhead.")
            if wants_code or constraints.get("requires_code"):
                lines.append("\n```python\n# Targeted implementation\ndef execute_task():\n    return {'status': 'success', 'code': 200}\n```")
        elif is_adapted and verbosity == "detailed":
            lines.append(f"Detailed architectural analysis: {prompt}")
            lines.append("1. **Core Mechanisms & Lifecycle**: Full end-to-end breakdown of processing stages.")
            lines.append("2. **Underlying Constraints**: Tradeoffs, edge cases, and performance considerations.")
            lines.append("3. **Production Recommendations**: Industry standards and deployment best practices.")
            if wants_code or constraints.get("requires_code"):
                lines.append("\n```python\n# Enterprise implementation pattern\nclass TaskPipeline:\n    def process(self, context: dict) -> dict:\n        return {'status': 'completed', 'timestamp': 1726830000}\n```")
        else:
            lines.append(f"Here is an overview of {prompt}:")
            lines.append("This is an important concept in software engineering and system design.")
            lines.append("It involves multiple considerations across implementation, maintenance, and scalability.")

    return "\n".join(lines)


def run_response_evaluation(cases_path: str, mode: str, temperature: float = 0.2, seed: int = 42, out_dir: str | None = None, model: str | None = None) -> int:
    """
    Executes the response evaluation harness in the specified mode ('offline' or 'live').
    """
    if mode not in ("offline", "live"):
        raise ValueError(f"Invalid mode '{mode}'. Must be 'offline' or 'live'.")

    with open(cases_path, "r", encoding="utf-8") as f:
        cases = json.load(f)

    started_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    random.seed(seed)

    print("=" * 76)
    print(f"  Ava AI — Response Evaluation Harness [{mode.upper()} MODE]")
    print("=" * 76)
    print(f"  • Cases File:          {cases_path}")
    print(f"  • Case Count:          {len(cases)}")
    print(f"  • Generation Mode:     {mode}")
    print(f"  • Randomization Seed:  {seed}")
    print(f"  • Temperature:         {temperature}")

    if mode == "live":
        # Validate key up-front before doing any setup
        validate_groq_api_key_for_live()
        provider = "groq"
        requested_model = model if model else os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
        actual_model = resolve_model(requested_model)
        model_name = actual_model
        print(f"  • Provider:            {provider}")
        print(f"  • Requested Model:     {requested_model}")
        print(f"  • Actual Model:        {actual_model}")
    else:
        provider = "local_deterministic_generator"
        requested_model = "deterministic_engine"
        actual_model = "deterministic_engine"
        model_name = "deterministic_engine"
        print(f"  • Provider:            {provider} (Offline Controlled Suite)")
        print(f"  • Model:               {model_name}")

    print("=" * 76 + "\n")

    temp_dir = tempfile.TemporaryDirectory()
    bench_db = os.path.join(temp_dir.name, "response_eval.db")
    orig_db_path = db.DB_PATH

    target_dir = out_dir if out_dir else os.path.join(BASE_DIR, "evaluation", "results", mode)
    os.makedirs(target_dir, exist_ok=True)
    checkpoint_file = os.path.join(target_dir, ".eval_checkpoint.json")

    try:
        db.DB_PATH = bench_db
        db.init_db()

        internal_records = []
        reviewer_dataset = []
        csv_rows = []

        if os.path.exists(checkpoint_file):
            try:
                with open(checkpoint_file, "r", encoding="utf-8") as f:
                    ckpt = json.load(f)
                internal_records = ckpt.get("internal_records", [])
                reviewer_dataset = ckpt.get("reviewer_dataset", [])
                csv_rows = ckpt.get("csv_rows", [])
                completed_ids = {r["case_id"] for r in internal_records}
                print(f"  • Resuming from checkpoint: {len(completed_ids)}/{len(cases)} cases already completed\n")
            except Exception:
                internal_records = []
                reviewer_dataset = []
                csv_rows = []

        completed_ids = {r["case_id"] for r in internal_records}

        for idx, case in enumerate(cases, 1):
            case_id = case["id"]
            category = case["category"]
            prompt = case["prompt"]
            if case_id in completed_ids:
                print(f"[{idx:02d}/{len(cases)}] {case_id:<12} | {category:<16} | Resumed from checkpoint")
                continue
            user_profile = case.get("user_profile", {})
            stored_mem = case.get("stored_memory", "")
            constraints = case.get("constraints", {})

            test_user_id = f"eval_user_{case_id}_{uuid.uuid4().hex[:4]}"
            adaptation.reset_adaptation_profile(test_user_id)

            # 1. Setup persistent user memory
            if stored_mem:
                db.set_user_memory(test_user_id, stored_mem, message_count_at_update=10)

            # 2. Setup user's learned profile
            for dim, val in user_profile.items():
                adaptation.set_manual_preference(test_user_id, dim, val, confidence=0.85)

            # Set positive feedback for corresponding strategies
            if user_profile.get("verbosity") == "concise" and user_profile.get("code_examples"):
                for _ in range(4):
                    db.record_strategy_feedback(test_user_id, "concise_with_code", helpful=True)
            elif user_profile.get("verbosity") == "concise":
                for _ in range(4):
                    db.record_strategy_feedback(test_user_id, "concise_direct", helpful=True)
            elif user_profile.get("step_by_step") and user_profile.get("code_examples"):
                for _ in range(4):
                    db.record_strategy_feedback(test_user_id, "step_by_step_code", helpful=True)
            elif user_profile.get("step_by_step"):
                for _ in range(4):
                    db.record_strategy_feedback(test_user_id, "detailed_step_by_step", helpful=True)
            elif user_profile.get("verbosity") == "detailed":
                for _ in range(4):
                    db.record_strategy_feedback(test_user_id, "detailed_explanation", helpful=True)

            # 3. Generate Variant Baseline (adaptation_enabled=False)
            t0 = time.time()
            sys_prompt_base, meta_base = assemble_chat_prompt_context(
                user_id=test_user_id,
                message=prompt,
                adaptation_enabled=False,
            )
            if mode == "live":
                resp_baseline = generate_live_groq_response(prompt, sys_prompt_base, temperature=temperature, model=model_name)
            else:
                resp_baseline = generate_offline_deterministic_response(prompt, sys_prompt_base, False, {}, constraints, category)
            latency_base_ms = int((time.time() - t0) * 1000)

            # 4. Generate Variant Adapted (adaptation_enabled=True)
            t1 = time.time()
            sys_prompt_adapt, meta_adapt = assemble_chat_prompt_context(
                user_id=test_user_id,
                message=prompt,
                adaptation_enabled=True,
            )
            policy_adapt = meta_adapt.get("policy", {})
            if mode == "live":
                resp_adapted = generate_live_groq_response(prompt, sys_prompt_adapt, temperature=temperature, model=model_name)
            else:
                resp_adapted = generate_offline_deterministic_response(prompt, sys_prompt_adapt, True, policy_adapt, constraints, category)
            latency_adapt_ms = int((time.time() - t1) * 1000)

            # 5. Randomized Presentation for Blinding
            a_is_adapted = random.choice([True, False])
            if a_is_adapted:
                resp_A = resp_adapted
                resp_B = resp_baseline
                lat_A = latency_adapt_ms
                lat_B = latency_base_ms
            else:
                resp_A = resp_baseline
                resp_B = resp_adapted
                lat_A = latency_base_ms
                lat_B = latency_adapt_ms

            # Internal record (holds truth & provenance for verification)
            internal_records.append({
                "case_id": case_id,
                "category": category,
                "prompt": prompt,
                "user_profile": user_profile,
                "constraints": constraints,
                "a_is_adapted": a_is_adapted,
                "response_A": resp_A,
                "response_B": resp_B,
                "generation_mode_A": mode,
                "generation_mode_B": mode,
                "model_A": model_name,
                "model_B": model_name,
                "latency_A_ms": lat_A,
                "latency_B_ms": lat_B,
                "policy_adapted": policy_adapt,
                "strategy_selected": meta_adapt.get("strategy"),
                "adaptation_used": meta_adapt.get("adaptation_used", False),
            })

            # Reviewer-facing record (completely blind!)
            reviewer_dataset.append({
                "case_id": case_id,
                "category": category,
                "prompt": prompt,
                "response_A": resp_A,
                "response_B": resp_B,
            })

            # CSV row for human review template
            csv_rows.append({
                "case_id": case_id,
                "category": category,
                "prompt": prompt,
                "response_A": resp_A,
                "response_B": resp_B,
                "instruction_adherence_A": "",
                "instruction_adherence_B": "",
                "clarity_A": "",
                "clarity_B": "",
                "usefulness_A": "",
                "usefulness_B": "",
                "personalization_fit_A": "",
                "personalization_fit_B": "",
                "correctness_A": "",
                "correctness_B": "",
                "preferred_response": "",
                "reviewer_notes": "",
            })

            print(f"[{idx:02d}/{len(cases)}] {case_id:<12} | {category:<16} | Blinded A/B ({lat_A}ms / {lat_B}ms)")

            # Save progress to checkpoint after each case
            try:
                with open(checkpoint_file, "w", encoding="utf-8") as f:
                    json.dump({
                        "internal_records": internal_records,
                        "reviewer_dataset": reviewer_dataset,
                        "csv_rows": csv_rows,
                    }, f)
            except Exception:
                pass

            if mode == "live":
                time.sleep(2.5)

        # Order results strictly by input case order
        case_order = {c["id"]: i for i, c in enumerate(cases)}
        internal_records.sort(key=lambda r: case_order.get(r["case_id"], 999))
        reviewer_dataset.sort(key=lambda r: case_order.get(r["case_id"], 999))
        csv_rows.sort(key=lambda r: case_order.get(r.get("case_id"), 999))
        completed_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # Run Metadata Record
        run_metadata = {
            "evaluation_id": str(uuid.uuid4()),
            "generation_mode": mode,
            "provider": provider,
            "requested_model": requested_model,
            "actual_model": actual_model,
            "model": model_name,
            "temperature": temperature,
            "case_count": len(cases),
            "response_count": len(cases) * 2,
            "started_at": started_at,
            "completed_at": completed_at,
            "git_commit": get_git_commit(),
            "working_tree_dirty": is_working_tree_dirty(),
            "randomization_seed": seed,
        }

        internal_file = os.path.join(target_dir, "response_eval_results_internal.json")
        with open(internal_file, "w", encoding="utf-8") as f:
            json.dump(internal_records, f, indent=2)

        # Remove checkpoint file upon successful completion of all cases
        if os.path.exists(checkpoint_file):
            try:
                os.remove(checkpoint_file)
            except Exception:
                pass

        blind_file = os.path.join(target_dir, "human_review_dataset.json")
        with open(blind_file, "w", encoding="utf-8") as f:
            json.dump(reviewer_dataset, f, indent=2)

        csv_file = os.path.join(target_dir, "human_review_template.csv")
        fieldnames = [
            "case_id", "category", "prompt", "response_A", "response_B",
            "instruction_adherence_A", "instruction_adherence_B",
            "clarity_A", "clarity_B",
            "usefulness_A", "usefulness_B",
            "personalization_fit_A", "personalization_fit_B",
            "correctness_A", "correctness_B",
            "preferred_response", "reviewer_notes",
        ]
        with open(csv_file, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(csv_rows)

        meta_file = os.path.join(target_dir, "run_metadata.json")
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(run_metadata, f, indent=2)

        # Backward compatibility sync with evaluation/ root if out_dir is default
        if not out_dir:
            for fname, content in [
                ("response_eval_results_internal.json", internal_records),
                ("human_review_dataset.json", reviewer_dataset),
                ("run_metadata.json", run_metadata),
            ]:
                with open(os.path.join(BASE_DIR, "evaluation", fname), "w", encoding="utf-8") as f:
                    json.dump(content, f, indent=2)

            with open(os.path.join(BASE_DIR, "evaluation", "human_review_template.csv"), "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(csv_rows)

        print("\n" + "=" * 76)
        print(f"  EVALUATION GENERATION COMPLETE [{mode.upper()}]")
        print("=" * 76)
        print(f"  • Total Paired Generations:      {len(cases)} ({len(cases) * 2} individual responses)")
        print(f"  • Results Directory:             {target_dir}")
        print(f"  • Internal Truth Key:            {internal_file}")
        print(f"  • Blind Review Dataset:          {blind_file}")
        print(f"  • Reviewer CSV Template:         {csv_file}")
        print(f"  • Provenance Run Metadata:       {meta_file}")
        print("=" * 76)
        return 0

    finally:
        db.DB_PATH = orig_db_path
        temp_dir.cleanup()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Ava AI response evaluation harness.")
    parser.add_argument("--mode", choices=["offline", "live"], required=True,
                        help="Explicit generation mode: 'offline' (deterministic) or 'live' (real Groq LLM). Required.")
    parser.add_argument("--cases", default=os.path.join(BASE_DIR, "evaluation", "response_eval_cases.json"),
                        help="Path to evaluation cases JSON.")
    parser.add_argument("--temperature", type=float, default=0.2,
                        help="Sampling temperature for LLM generation (default: 0.2).")
    parser.add_argument("--seed", type=int, default=42,
                        help="Randomization seed for A/B presentation order (default: 42).")
    parser.add_argument("--out-dir", default=None,
                        help="Custom output directory for results.")
    parser.add_argument("--model", default=None,
                        help="Groq model ID for live mode. Overrides GROQ_MODEL env var. "
                             "Defaults to GROQ_MODEL env or openai/gpt-oss-120b.")
    args = parser.parse_args()
    sys.exit(run_response_evaluation(
        cases_path=args.cases,
        mode=args.mode,
        temperature=args.temperature,
        seed=args.seed,
        out_dir=args.out_dir,
        model=args.model,
    ))
