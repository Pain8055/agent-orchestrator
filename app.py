import streamlit as st
import requests

st.set_page_config(page_title="My Agent Team", page_icon="🤖")
st.title("🤖 My Agent Team")

GROQ_KEY = st.secrets["GROQ_API_KEY"]
TAVILY_KEY = st.secrets["TAVILY_API_KEY"]

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
    payload = {"model": MODELS[model_key], "messages": messages}
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

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

if prompt := st.chat_input("Type a task... (e.g. 'code: sort a list in python')"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Working..."):
            result, task_type = run_task(prompt)
            st.caption(f"Routed to: {task_type}")
            st.write(result)

    st.session_state.messages.append({"role": "assistant", "content": result})
