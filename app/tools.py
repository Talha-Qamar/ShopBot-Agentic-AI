"""Every tool reads the patient from runtime.context, never from a model argument."""
import re
from datetime import datetime
from uuid import uuid4

from langchain.messages import ToolMessage
from langchain.tools import ToolRuntime, tool
from langgraph.types import Command, interrupt

from app.context import PATIENTS, CareContext

# In-memory fake database (a real app would use its EHR / database here)
READINGS = [
    {"patient": "p-001", "kind": "blood_pressure", "value": "142/90", "time": "2026-11-18 08:00"},
    {"patient": "p-001", "kind": "blood_pressure", "value": "136/86", "time": "2026-11-20 08:00"},
    {"patient": "p-002", "kind": "glucose", "value": "138", "time": "2026-11-20 07:30"},
    {"patient": "p-002", "kind": "glucose", "value": "320", "time": "2026-11-21 07:30"},
]
SYMPTOMS = []
APPOINTMENTS = []
FREE_SLOTS = ["2026-11-25 09:00", "2026-11-25 14:30", "2026-11-27 11:00"]


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def is_urgent(patient_token: str, kind: str, value: str) -> bool:
    # CUSTOM: clinical thresholds are policy, set per patient by a doctor
    limits = PATIENTS[patient_token]["thresholds"]
    numbers = [int(n) for n in re.findall(r"\d+", value)]
    if kind == "blood_pressure" and len(numbers) >= 2:
        return numbers[0] >= limits.get("systolic", 999) or numbers[1] >= limits.get("diastolic", 999)
    if kind == "glucose" and numbers:
        return numbers[0] >= limits.get("glucose_high", 9999) or numbers[0] <= limits.get("glucose_low", 0)
    return False


# ── care (notebooks 01 and 03) ──

@tool
def get_care_plan(runtime: ToolRuntime[CareContext]) -> str:
    """Get the patient's care plan: condition, target and medicines."""
    p = PATIENTS[runtime.context.patient_token]
    return f"Condition: {p['condition']}. Target: {p['target']}. Medicines: {', '.join(p['medications'])}."


@tool
def log_reading(kind: str, value: str, runtime: ToolRuntime[CareContext]) -> str:
    """Log a home reading. kind is 'blood_pressure' (value like '128/82') or 'glucose' (value in mg/dL like '140')."""
    patient = runtime.context.patient_token
    note = ""
    if is_urgent(patient, kind, value):
        nurse_reply = interrupt({"alert": "reading above threshold", "patient": patient, "kind": kind, "value": value})
        note = f" URGENT, reviewed by nurse: {nurse_reply}"
    READINGS.append({"patient": patient, "kind": kind, "value": value, "time": now()})
    return f"Logged {kind} {value}.{note}"


@tool
def log_symptom(symptom: str, runtime: ToolRuntime[CareContext]) -> str:
    """Log a symptom the patient reports, e.g. 'headache since this morning'."""
    SYMPTOMS.append({"patient": runtime.context.patient_token, "symptom": symptom, "time": now()})
    return f"Logged symptom: {symptom}"


@tool
def get_recent_readings(runtime: ToolRuntime[CareContext], limit: int = 5) -> str:
    """Get the patient's most recent home readings."""
    mine = [r for r in READINGS if r["patient"] == runtime.context.patient_token][-limit:]
    return "\n".join(f"{r['time']}  {r['kind']}: {r['value']}" for r in mine) or "No readings yet."


@tool
def escalate_to_nurse(reason: str, runtime: ToolRuntime[CareContext]) -> str:
    """Alert the nurse about a worrying SYMPTOM. Never use this for readings: log_reading alerts the nurse itself."""
    return f"Nurse alerted about {runtime.context.patient_token}: {reason}"


# ── identity, booking, doctors (notebook 02) ──

@tool
def verify_identity(date_of_birth: str, runtime: ToolRuntime[CareContext]) -> Command:
    """Verify the patient's identity with their date of birth (YYYY-MM-DD). Required before booking."""
    ok = PATIENTS[runtime.context.patient_token]["date_of_birth"] == date_of_birth
    reply = "Identity verified." if ok else "That date of birth doesn't match our records."
    return Command(update={"identity_verified": ok,
                           "messages": [ToolMessage(reply, tool_call_id=runtime.tool_call_id)]})


@tool
def list_free_slots() -> str:
    """List free appointment slots with the patient's doctor."""
    return "\n".join(FREE_SLOTS)


@tool
def book_appointment(slot: str, runtime: ToolRuntime[CareContext]) -> str:
    """Book one of the free slots (exact text from list_free_slots)."""
    if slot not in FREE_SLOTS:
        return f"{slot} is not free. Free slots: {', '.join(FREE_SLOTS)}"
    FREE_SLOTS.remove(slot)
    APPOINTMENTS.append({"patient": runtime.context.patient_token, "slot": slot})
    return f"Booked {slot}."


@tool
def patients_needing_attention() -> str:
    """For doctors: list patients whose latest reading breached their threshold."""
    latest = {r["patient"]: r for r in READINGS}
    flagged = [f"{pid} ({PATIENTS[pid]['condition']}): {r['kind']} {r['value']} at {r['time']}"
               for pid, r in latest.items() if is_urgent(pid, r["kind"], r["value"])]
    return "\n".join(flagged) or "No patients above threshold right now."


# ── long-term memory (notebook 06) ──

def memory_namespace(patient_token: str):
    return ("memories", patient_token)


@tool
def remember(fact: str, runtime: ToolRuntime[CareContext]) -> str:
    """Save a lasting fact about the patient worth following up next time, e.g. 'knee pain when walking'."""
    runtime.store.put(memory_namespace(runtime.context.patient_token), str(uuid4()), {"fact": fact})
    return f"Remembered: {fact}"


@tool
def export_my_memories(runtime: ToolRuntime[CareContext]) -> str:
    """Show the patient everything remembered about them."""
    items = runtime.store.search(memory_namespace(runtime.context.patient_token), limit=100)
    return "\n".join(f"- {i.value['fact']}" for i in items) or "Nothing remembered."


@tool
def forget_me(runtime: ToolRuntime[CareContext]) -> str:
    """Delete everything remembered about the patient. Only when they explicitly ask."""
    items = runtime.store.search(memory_namespace(runtime.context.patient_token), limit=1000)
    for item in items:
        runtime.store.delete(item.namespace, item.key)
    return f"Deleted {len(items)} memories."
