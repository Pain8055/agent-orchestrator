import streamlit as st
import requests
import re
from supabase import create_client

st.set_page_config(page_title="My Agent Team", page_icon="🤖")
st.title("🤖 My Agent Team")

GROQ_KEY = st.secrets["GROQ_API_KEY"]
TAVILY_KEY = st.secrets["TAVILY_API_KEY"]
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
TAVILY_URL = "https://api.tavily.com/search"

# --- Agent roster: role -> (model, system prompt) ---
AGENTS = {
    "head": {
        "model": "openai/gpt-oss-120b",
        "system": "You are the lead orchestrator of an AI agent team. You plan, delegate, and give clear final answers."
    },
    "code": {
        "model": "qwen/qwen3.6-27b",
        "system": "You are a senior software engineer. Write correct, clean, working code. Briefly explain key decisions. No fluff."
    },
    "debug": {
        "model": "qwen/qwen3.6-27b",
        "system": "You are a debugging specialist. Given broken code or an error, find the root cause precisely and give the exact fix. Explain WHY it broke."
    },
    "reasoning": {
        "model": "openai/gpt-oss-120b",
        "system": "You are a reasoning and math specialist. Solve problems step by step, show your work, double-check your final answer."
    },
    "writing": {
        "model": "openai/gpt-oss-120b",
        "system": "You are a professional writing assistant. Write clear, well-structured, natural text for the requested purpose."
    },
    "design": {
        "model": "openai/gpt-oss-120b",
        "system": "You are a UI/UX design specialist. Give concrete, specific design decisions (colors, layout, spacing, typography) — never vague advice."
    },
    "review": {
        "model": "openai/gpt-oss-120b",
        "system": "You are a strict quality reviewer. Given a task and a draft answer, find any mistakes, gaps, or weaknesses. If it's good, say so briefly. If not, give the corrected version."
    },
}

def call_agent(role, prompt, max_tokens=800):
    agent = AGENTS[role]
    headers = {"Authorization": f"Bearer {GROQ_KEY}"}
    payload = {
        "model": agent["model"],
        "messages": [
            {"role": "system", "content": agent["system"]},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": max_tokens
    }
    r = requests.post(GROQ_URL, headers=headers, json=payload)
    if r.status_code != 200:
        return f"[Error {r.status_code}] {r.text}"
    return r.json()["choices"][0]["message"]["content"]

def web_search(query):
    payload = {"api_key": TAVILY_KEY, "query": query, "max_results": 5}
    r = requests.post(TAVILY_URL, json=payload)
    if r.status_code != 200:
        return f"[Search error] {r.text}"
    results = r.json().get("results", [])
    return "\n\n".join(f"- {x['title']}: {x['content'][:200]}" for x in results)

# --- Routing ---
TAGS = {
    "code:": "code", "debug:": "debug", "math:": "reasoning", "reason:": "reasoning",
    "writing:": "writing", "design:": "design", "search:": "search", "review:": "review",
}

def detect_role(task):
    lower = task.lower()
    for tag, role in TAGS.items():
        if lower.startswith(tag):
            return role, task[len(tag):].strip()
    if any(w in lower for w in ["traceback", "error", "bug", "not working", "crash", "fails"]):
        return "debug", task
    if any(w in lower for w in ["function", "script", "code", "html", "css", "javascript", "python", "api"]):
        return "code", task
    if any(w in lower for w in ["calculate", "solve", "equation", "how many", "logic"]):
        return "reasoning", task
    if any(w in lower for w in ["essay", "article", "blog", "write a", "letter", "email"]):
        return "writing", task
    if any(w in lower for w in ["color", "layout", "ui", "design", "style", "theme"]):
        return "design", task
    if any(w in lower for w in ["latest", "current", "news", "who is", "search"]):
        return "search", task
    return "head", task

def is_complex(task):
    lower = task.lower()
    if lower.startswith("plan:"):
        return True
    complex_signals = ["and then", " and ", "full", "entire", "complete", "end to end", "build a", "create a", "step by step"]
    hits = sum(1 for s in complex_signals if s in lower)
    return len(task.split()) > 25 or hits >= 2

def run_simple(task):
    role, clean_task = detect_role(task)
    if role == "search":
        results = web_search(clean_task)
        return call_agent("head", f"Summarize these search results for: {clean_task}\n\n{results}"), role
    return call_agent(role, clean_task), role

def run_multistep(task):
    clean_task = task[5:].strip() if task.lower().startswith("plan:") else task

    plan_prompt = f"""Break this task into 2-5 ordered steps. For each step pick exactly one agent from: code, debug, reasoning, writing, design, search.
Format EXACTLY like this, one per line, nothing else:
STEP | agent | short description of what to do

Task: {clean_task}"""

    plan_raw = call_agent("head", plan_prompt, max_tokens=400)

    steps = []
    for line in plan_raw.strip().split("\n"):
        parts = [p.strip() for p in line.split("|")]
        if len(parts) == 3 and parts[1] in ["code", "debug", "reasoning", "writing", "design", "search"]:
            steps.append((parts[1], parts[2]))

    if not steps:
        return call_agent("head", clean_task), "head", plan_raw

    step_results = []
    for role, desc in steps:
        if role == "search":
            results = web_search(desc)
            result = call_agent("head", f"Summarize for: {desc}\n\n{results}")
        else:
            result = call_agent(role, desc)
        step_results.append((role, desc, result))

    combined = "\n\n".join(f"[{r.upper()}] {d}\n{res}" for r, d, res in step_results)
    final = call_agent("head", f"Combine these sub-task results into one clear final answer for: {clean_task}\n\n{combined}", max_tokens=1000)
    return final, "multi-step", step_results

def run_task(task):
    if is_complex(task):
        result, mode, detail = run_multistep(task)
        return result, mode, detail
    result, role = run_simple(task)
    return result, role, None

def save_message(user_id, role, content):
    supabase.table("chat_history").insert({
        "user_id": user_id,
        "role": role,
        "content": content
    }).execute()

def load_history(user_id):
    res = supabase.table("chat_history").select("*").eq("user_id", user_id).order("created_at").execute()
    return res.data

# --- User ID entry ---
if "user_id" not in st.session_state:
    st.session_state.user_id = ""

with st.sidebar:
    st.subheader("Your ID")
    uid_input = st.text_input("Enter your ID (same ID = same history, any device)", value=st.session_state.user_id)
    if st.button("Load / Switch"):
        st.session_state.user_id = uid_input.strip()
        st.session_state.messages = load_history(st.session_state.user_id)
        st.rerun()
    st.divider()
    st.caption("Agents: code, debug, reasoning, writing, design, search, review")
    st.caption("Force a specific agent: 'code: ...', 'debug: ...' etc")
    st.caption("Force multi-step: 'plan: ...'")

if not st.session_state.user_id:
    st.info("👈 Enter an ID in the sidebar to start (e.g. 'anuj'). Use the same ID on any device to keep your history.")
    st.stop()

st.caption(f"Logged in as: **{st.session_state.user_id}**")

if "messages" not in st.session_state:
    st.session_state.messages = load_history(st.session_state.user_id)

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

if prompt := st.chat_input("Type a task..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    save_message(st.session_state.user_id, "user", prompt)
    with st.chat_message("user"):
        st.write(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Working..."):
            result, mode, detail = run_task(prompt)
            if mode == "multi-step" and detail:
                st.caption("Multi-step: " + " → ".join(r for r, d, res in detail))
                with st.expander("See individual agent steps"):
                    for r, d, res in detail:
                        st.markdown(f"**[{r}]** {d}")
                        st.write(res)
                        st.divider()
            else:
                st.caption(f"Routed to: {mode}")
            st.write(result)

    st.session_state.messages.append({"role": "assistant", "content": result})
    save_message(st.session_state.user_id, "assistant", result)
