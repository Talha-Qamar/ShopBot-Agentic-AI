"""CareCompanion: a Streamlit front end for the care agent.

Run the agent server first, then the UI (from the repo root):
    langgraph dev
    streamlit run ui/streamlit_app.py

Patients chat with the agent. When a reading is too high, the run pauses and shows up in
the doctor's nurse inbox. The doctor's decision resumes the patient's chat.
Learning mode shows what happens inside each turn.
"""
import html
import json
import sys
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

import backend as api                                   # noqa: E402  (the only way we talk to the agent)
from steps import KIND_COLOR, text_of, to_steps         # noqa: E402
from app.agent import TOOLS                             # noqa: E402  (only to SHOW the access policy)
from app.middleware import DOCTOR_ONLY, NEEDS_IDENTITY  # noqa: E402

st.set_page_config(page_title="CareCompanion", page_icon="🩺", layout="wide")
st.html((Path(__file__).parent / "style.css").read_text().join(["<style>", "</style>"]))

PATIENTS = json.loads((ROOT / "data" / "patients.json").read_text())   # synthetic
ASSISTANT_AVATAR = "🩺"

# In a real app these come from login. Here you pick who you are in the sidebar.
PEOPLE = {
    "sara": {"name": "Sara", "avatar": "👩", "role": "Patient", "about": "Hypertension",
             "context": {"user_id": "sara", "role": "patient", "patient_token": "p-001"},
             "try": ["What's my blood pressure target?", "My BP is 128/82 this morning", "My BP is 190/120",
                     "How do I measure my blood pressure?", "Should I double my dose?",
                     "Book me an appointment", "1970-03-14", "My knee hurts when I walk"]},
    "omar": {"name": "Omar", "avatar": "👨", "role": "Patient", "about": "Type 2 diabetes",
             "context": {"user_id": "omar", "role": "patient", "patient_token": "p-002"},
             "try": ["Show my recent readings", "My sugar is 145 today", "My glucose is 350",
                     "What should I do if my sugar is low?", "What did the doctor note last time?",
                     "Book me an appointment", "1962-11-02", "What do you remember about me?"]},
    "dr_lee": {"name": "Dr. Lee", "avatar": "🧑‍⚕️", "role": "Clinician", "about": "Nurse inbox · patients",
               "context": {"user_id": "dr_lee", "role": "doctor", "patient_token": "p-001"},
               "try": ["Who needs attention today?", "Show recent readings", "What is in the care plan?"]},
}


# ───────────────────────── small helpers ─────────────────────────

def dob(person):
    """Synthetic date of birth, shown so you can pass verify_identity in the demo."""
    token = person["context"]["patient_token"] if person["role"] == "Patient" else None
    return f"  \nDOB {PATIENTS[token]['date_of_birth']}" if token else ""


def chips(names, css=""):
    return "".join(f'<span class="chip {css}">{html.escape(n)}</span>' for n in names)


def visible_tools(role: str, verified: bool):
    """Mirrors pick_tools_and_model in app/middleware.py, so students can SEE the policy."""
    shown, hidden = [], []
    for t in TOOLS:
        blocked = (t.name in DOCTOR_ONLY and role != "doctor") or (t.name in NEEDS_IDENTITY and not verified)
        (hidden if blocked else shown).append(t.name)
    return shown, hidden


def context_for(person: dict) -> dict:
    return {**person["context"], "language": st.session_state.get("language", "English")}


def thread_for(key: str, person: dict) -> str:
    """One saved conversation per user. Reuses the latest one, so a page reload keeps the chat."""
    slot = f"thread:{key}"
    if slot not in st.session_state:
        ctx = context_for(person)
        st.session_state[slot] = api.latest_thread(ctx["user_id"]) or api.new_thread(ctx, person["name"])
    return st.session_state[slot]


def run_and_record(thread_id: str, stream, label="Thinking…", show=True):
    """Consume a streamed run, showing each step live, and keep the steps for the learning panel."""
    steps = []
    with st.status(label, expanded=show and st.session_state.learning) as status:
        for node, update in stream:
            for step in to_steps(node, update):
                steps.append(step)
                if step["kind"] != "middleware":
                    status.write(f"{step['icon']} {step['title']}")
                    status.update(label=f"{step['icon']} {step['title']}")
        paused = any(s["kind"] == "pause" for s in steps)
        status.update(label="⏸️ Paused for a human" if paused else "✅ Done", state="complete", expanded=False)
    st.session_state.setdefault("turns", {})[thread_id] = steps


# ───────────────────────── chat pieces ─────────────────────────

def render_messages(messages: list, person: dict):
    learning = st.session_state.learning
    results = {m.get("tool_call_id"): m for m in messages if m["type"] == "tool"}
    for m in messages:
        if m["type"] == "human":
            with st.chat_message("user", avatar=person["avatar"]):
                st.markdown(text_of(m))
        elif m["type"] == "ai":
            calls = m.get("tool_calls") or []
            if not text_of(m) and not (learning and calls):
                continue
            with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
                if learning:
                    for call in calls:
                        result = results.get(call["id"])
                        with st.expander(f"🔧 **{call['name']}**  ·  tool call", expanded=False):
                            st.caption("Arguments the model chose")
                            st.json(call["args"])
                            st.caption("What the tool returned")
                            st.code(text_of(result) if result else "⏸️ waiting…", language=None, wrap_lines=True)
                if text_of(m):
                    st.markdown(text_of(m))


def empty_state(person: dict):
    st.markdown(
        f'<div class="hero"><div class="hero-emoji">{person["avatar"]}</div>'
        f'<div><div class="hero-title">Hi {html.escape(person["name"])}, how can I help today?</div>'
        f'<div class="hero-sub">Log a reading, ask about your care plan, or book an appointment.</div></div></div>',
        unsafe_allow_html=True)


def suggestions(person: dict, key: str, disabled: bool):
    def pick():   # queue the clicked suggestion as the next message, then clear the pill
        st.session_state[f"queued:{key}"] = st.session_state[f"pills:{key}"]
        st.session_state[f"pills:{key}"] = None
    st.pills("Try", person["try"], key=f"pills:{key}", on_change=pick, disabled=disabled,
             label_visibility="collapsed")


@st.fragment(run_every="3s")
def wait_for_nurse(thread_id: str):
    """Poll until the nurse resumes the run (from the doctor view, maybe in another tab)."""
    if api.thread_status(thread_id) != "interrupted":
        st.rerun(scope="app")
    st.caption("🔄 Checking for the nurse's reply every few seconds…")


def paused_card(thread_id: str, intr: dict, person: dict, ctx: dict, key: str):
    info = api.describe_interrupt(intr["value"])
    if info["kind"] == "approval" and info["tool"] == "forget_me":
        with st.container(border=True):
            st.markdown("**🗑️ Delete everything I remember about you?**")
            st.caption("This can't be undone. The agent paused here because `forget_me` needs your approval.")
            yes, no, _ = st.columns([1, 1, 2])
            if yes.button("Yes, delete", type="primary", key=f"fy-{key}"):
                run_and_record(thread_id, api.stream_resume(thread_id, api.decisions(True, info["count"]), ctx))
                st.rerun()
            if no.button("Keep my memories", key=f"fn-{key}"):
                run_and_record(thread_id, api.stream_resume(
                    thread_id, api.decisions(False, info["count"], "The patient changed their mind."), ctx))
                st.rerun()
        return
    if info["kind"] == "reading":
        what = f"Your reading <b>{html.escape(info['value'])}</b> is above the safe limit your doctor set."
    else:
        what = f"I've asked a nurse to look at this: <i>{html.escape(info['args'].get('reason', ''))}</i>."
    st.markdown(f'<div class="paused"><b>⏸️ Waiting for a nurse</b><br>{what} '
                f"I'll continue as soon as they reply.<br><span class=\"muted\">"
                f'If you feel unwell right now, call emergency services.</span></div>', unsafe_allow_html=True)
    wait_for_nurse(thread_id)


def chat_view(key: str, person: dict):
    """The chat column, used by patients and by the doctor's clinical assistant."""
    ctx = context_for(person)
    thread_id = thread_for(key, person)
    state = api.get_state(thread_id)
    messages = (state.get("values") or {}).get("messages", [])
    interrupts = api.pending_interrupts(state)

    box = st.container(height=560, border=True)
    with box:
        if not messages:
            empty_state(person)
        render_messages(messages, person)
        if interrupts:
            paused_card(thread_id, interrupts[0], person, ctx, key)

    suggestions(person, key, disabled=bool(interrupts))
    typed = st.chat_input("Paused for a nurse…" if interrupts else f"Message as {person['name']}…",
                          disabled=bool(interrupts), key=f"input-{key}")
    text = typed or st.session_state.pop(f"queued:{key}", None)
    if text and not interrupts:
        with box:
            with st.chat_message("user", avatar=person["avatar"]):
                st.markdown(text)
            with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
                run_and_record(thread_id, api.stream_message(thread_id, text, ctx))
        st.rerun()
    return thread_id, state, ctx


# ───────────────────────── learning panel ─────────────────────────

def timeline(steps: list):
    if not steps:
        st.caption("Send a message to see each step: middleware → model → tools → reply.")
        return
    out, pending_mw = [], []

    def flush():
        if pending_mw:
            out.append(f'<div class="step" style="--c:{KIND_COLOR["middleware"]}"><div class="t">🧱 Middleware hooks</div>'
                       f'<div class="mw-row">{chips(pending_mw, "mw")}</div></div>')
            pending_mw.clear()

    for s in steps:
        if s["kind"] == "middleware":
            pending_mw.append(s["label"])
            continue
        flush()
        sub = f'<div class="s">{html.escape(s["sub"])}</div>' if s.get("sub") else ""
        detail = f'<div class="d">{html.escape(s["detail"])}</div>' if s.get("detail") else ""
        out.append(f'<div class="step" style="--c:{KIND_COLOR[s["kind"]]}">'
                   f'<div class="t">{s["icon"]} {html.escape(s["title"])}</div>{sub}{detail}</div>')
    flush()
    st.markdown("".join(out), unsafe_allow_html=True)


def learning_panel(thread_id: str, state: dict, ctx: dict):
    values = state.get("values") or {}
    st.markdown("##### 🎓 Under the hood")
    steps_tab, ctx_tab, state_tab, mem_tab = st.tabs(["Last turn", "Context & tools", "State", "Memory"])

    with steps_tab:
        with st.container(height=520, border=False):
            timeline(st.session_state.get("turns", {}).get(thread_id, []))

    with ctx_tab:
        st.caption("**Runtime context**, sent with every run. It comes from login, never from the chat. "
                   "Tools read it through `ToolRuntime`, and the model never sees it.")
        st.code(json.dumps(ctx, indent=2), language="json")
        shown, hidden = visible_tools(ctx["role"], bool(values.get("identity_verified")))
        st.caption("**Tools the model can see.** `pick_tools_and_model` filters them by role and identity.")
        st.markdown(chips(shown) + chips(hidden, "off"), unsafe_allow_html=True)

    with state_tab:
        status = "interrupted" if state.get("interrupts") else "idle"
        c1, c2 = st.columns(2)
        c1.metric("Messages", len(values.get("messages", [])))
        c2.metric("Status", status)
        st.markdown(f"**identity_verified:** `{values.get('identity_verified', False)}`  \n"
                    f"**thread_id:** `{thread_id[:18]}…`")
        st.caption("The checkpointer saves this after every step, which is why a run can pause and resume later.")
        st.link_button("Open in LangSmith Studio ↗", api.STUDIO_URL, use_container_width=True)

    with mem_tab:
        st.caption(f"**Long-term memory** in the Store, namespace `(\"memories\", \"{ctx['patient_token']}\")`. "
                   "It is shared across every conversation.")
        facts = api.memories(ctx["patient_token"])
        if facts:
            for fact in facts:
                st.markdown(f"- {fact}")
        else:
            st.caption("Nothing yet. Try *\"My knee hurts when I walk\"*.")


def with_panel(key: str, person: dict):
    if st.session_state.learning:
        left, right = st.columns([3, 2], gap="large")
        with left:
            thread_id, state, ctx = chat_view(key, person)
        with right:
            learning_panel(thread_id, state, ctx)
    else:
        _, mid, _ = st.columns([1, 4, 1])
        with mid:
            chat_view(key, person)


# ───────────────────────── doctor view ─────────────────────────

def resume_context(meta: dict) -> dict:
    return {k: meta[k] for k in ("user_id", "role", "patient_token", "language") if k in meta}


def inbox_card(item: dict, i: int):
    meta, info, thread = item["meta"], item["info"], item["thread"]
    patient = PATIENTS.get(meta.get("patient_token"), {})
    tid = thread["thread_id"]
    last_said = next((text_of(m) for m in reversed(item["messages"]) if m["type"] == "human"), "")
    with st.container(border=True):
        top, badge = st.columns([4, 1.4])
        top.markdown(f"#### {html.escape(patient.get('name', meta.get('name', 'Patient')))}")
        top.caption(f"{patient.get('condition', '').capitalize()} · {meta.get('patient_token')} · "
                    f"{thread['updated_at'][11:16]} UTC")
        if info["kind"] == "reading":
            badge.badge("Reading over limit", color="red", icon="🚨")
            limits = patient.get("thresholds", {})
            a, b = st.columns(2)
            a.metric(info["reading"].replace("_", " ").title(), info["value"])
            b.metric("Their limit", " / ".join(str(v) for v in limits.values()))
        else:
            badge.badge("Symptom alert", color="orange", icon="⚠️")
            st.markdown(f"**Agent wants to call `{info['tool']}`:** {html.escape(info['args'].get('reason', ''))}")
        if last_said:
            st.markdown(f'<div class="quote">“{html.escape(last_said)}”</div>', unsafe_allow_html=True)

        note = st.text_area("Note to the patient", key=f"note-{tid}-{i}", height=80,
                            value="Please sit down, rest for 5 minutes and measure again. "
                                  "If you have chest pain or feel faint, call emergency services.")
        ctx = resume_context(meta)
        go, no, _ = st.columns([1.3, 1, 1.5])
        if info["kind"] == "reading":
            # interrupt() inside log_reading: whatever we resume with becomes the tool's "nurse_reply"
            if go.button("✅ Send note & continue", key=f"go-{tid}-{i}", type="primary"):
                with st.spinner("Resuming the patient's chat…"):
                    run_and_record(tid, api.stream_resume(tid, note, ctx), show=False)
                st.toast(f"Sent to {patient.get('name', 'patient')}", icon="✅")
                st.rerun()
        else:
            # HumanInTheLoopMiddleware: resume with a decision
            if go.button("✅ Acknowledge alert", key=f"go-{tid}-{i}", type="primary"):
                run_and_record(tid, api.stream_resume(tid, api.decisions(True, info["count"]), ctx), show=False)
                st.rerun()
            if no.button("↩️ Not needed", key=f"no-{tid}-{i}"):
                run_and_record(tid, api.stream_resume(tid, api.decisions(False, info["count"], note), ctx), show=False)
                st.rerun()


@st.fragment(run_every="5s")
def inbox():
    items = api.nurse_inbox()
    if not items:
        st.markdown('<div class="empty">🎉 No patients are waiting. New alerts appear here automatically.</div>',
                    unsafe_allow_html=True)
        return
    st.caption("These patient chats are **paused** mid-run. Your answer resumes them exactly where they stopped.")
    for i, item in enumerate(items):
        inbox_card(item, i)


def patients_tab():
    cols = st.columns(len(PATIENTS))
    for col, (token, p) in zip(cols, PATIENTS.items()):
        with col.container(border=True):
            st.markdown(f"#### {p['name']}")
            st.caption(f"{token} · {p['condition']} · MRN hidden")
            st.markdown(f"**Target:** {p['target']}  \n**Medicines:** {', '.join(p['medications'])}")
            st.markdown("**Alert thresholds**<br>" + chips(f"{k.replace('_', ' ')} {v}" for k, v in p["thresholds"].items()),
                        unsafe_allow_html=True)
            facts = api.memories(token)
            st.markdown("**Remembered**<br>" + (chips(facts, "mw") if facts else '<span class="muted">nothing yet</span>'),
                        unsafe_allow_html=True)


def doctor_view(key: str, person: dict):
    waiting = len(api.nurse_inbox())
    t1, t2, t3 = st.tabs([f"🔔 Nurse inbox ({waiting})", "💬 Clinical assistant", "👥 Patients"])
    with t1:
        inbox()
    with t2:
        with_panel(key, person)
    with t3:
        patients_tab()


# ───────────────────────── page ─────────────────────────

with st.sidebar:
    st.markdown('<div class="brand">🩺 CareCompanion</div>'
                '<div class="muted">LangChain v1 · LangGraph workshop demo</div>', unsafe_allow_html=True)
    st.divider()
    who = st.radio("Signed in as", list(PEOPLE), key="who",
                   format_func=lambda k: f"{PEOPLE[k]['avatar']}  {PEOPLE[k]['name']}",
                   captions=[f"{p['role']} · {p['about']}" + dob(p) for p in PEOPLE.values()])
    st.selectbox("Language", ["English", "Urdu", "Spanish", "Arabic"], key="language",
                 help="Part of the runtime context. The prompt tells the model to reply in it.")
    st.toggle("🎓 Learning mode", value=True, key="learning",
              help="Show tool calls, middleware and state next to the chat.")
    if st.button("＋ New conversation", use_container_width=True):
        person = PEOPLE[who]
        st.session_state[f"thread:{who}"] = api.new_thread(context_for(person), person["name"])
        st.rerun()
    st.divider()
    online = api.server_ok()
    st.markdown(f'<span class="dot {"on" if online else "off"}"></span> Agent server '
                f'{"connected" if online else "offline"}<br><span class="muted">{api.SERVER_URL}</span>',
                unsafe_allow_html=True)
    st.link_button("LangSmith Studio ↗", api.STUDIO_URL, use_container_width=True)
    st.caption("All data is synthetic. This is a teaching demo, not a medical device.")

if not online:
    st.error("Can't reach the agent server. Start it from the repo root with `langgraph dev`, then refresh.")
    st.stop()

person = PEOPLE[who]
st.markdown(f'<div class="page-title">{person["avatar"]} {html.escape(person["name"])}'
            f'<span class="role-pill">{person["role"]}</span></div>', unsafe_allow_html=True)

if person["context"]["role"] == "doctor":
    doctor_view(who, person)
else:
    with_panel(who, person)
