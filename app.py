import streamlit as st
import requests
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

MODELS = {
    "head":   "openai/gpt-oss-120b",
    "code":   "qwen/qwen3.6-27b",
    "design": "openai/gpt-oss-120b",
}

def call_model(model_key, prompt, system=""):
    headers = {"Authorization": f"Bearer {GROQ_KEY}"}
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload = {
        "model": MODELS[model_key],
        "messages": messages,
        "max_tokens": 800
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

def detect_task_type(task):
    lower = task.lower()
    if lower.startswith("code:"):
        return "code", task[5:].strip()
    if lower.startswith("design:"):
        return "design", task[7:].strip()
    if lower.startswith("search:"):
        return "search", task[7:].strip()
    if any(w in lower for w in ["bug", "function", "script", "error", "code", "html", "css", "js"]):
        return "code", task
    if any(w in lower for w in ["color", "layout", "ui", "design", "style", "theme"]):
        return "design", task
    if any(w in lower for w in ["latest", "current", "news", "who is", "search"]):
        return "search", task
    return "head", task

def run_task(task):
    task_type, clean_task = detect_task_type(task)
    if task_type == "search":
        results = web_search(clean_task)
        return call_model("head", f"Summarize these search results for: {clean_task}\n\n{results}"), task_type
    if task_type == "code":
        return call_model("code", clean_task, system="You are a precise coding assistant. Give working code with brief explanation."), task_type
    if task_type == "design":
        return call_model("design", clean_task, system="You are a UI/UX design assistant. Give concrete design decisions, not vague advice."), task_type
    return call_model("head", clean_task), task_type

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

if not st.session_state.user_id:
    st.info("👈 Enter an ID in the sidebar to start (e.g. 'anuj'). Use the same ID on any device to keep your history.")
    st.stop()

st.caption(f"Logged in as: **{st.session_state.user_id}**")

if "messages" not in st.session_state:
    st.session_state.messages = load_history(st.session_state.user_id)

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

if prompt := st.chat_input("Type a task... (e.g. 'code: sort a list in python')"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    save_message(st.session_state.user_id, "user", prompt)
    with st.chat_message("user"):
        st.write(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Working..."):
            result, task_type = run_task(prompt)
            st.caption(f"Routed to: {task_type}")
            st.write(result)

    st.session_state.messages.append({"role": "assistant", "content": result})
    save_message(st.session_state.user_id, "assistant", result)
