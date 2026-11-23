"""The deployable care chatbot. langgraph.json serves `agent`.

The LangGraph server supplies the checkpointer and Store itself, so `agent` is built without them.
Scripts and tests call build_agent(checkpointer=..., store=...) to get their own.
"""
from langchain.agents import create_agent

from app import tools as t
from app.context import MODEL, CareContext
from app.middleware import build_middleware
from app.rag import search_documents

TOOLS = [t.get_care_plan, t.log_reading, t.log_symptom, t.get_recent_readings, t.escalate_to_nurse,
         search_documents, t.verify_identity, t.list_free_slots, t.book_appointment,
         t.patients_needing_attention, t.remember, t.export_my_memories, t.forget_me]


def build_agent(checkpointer=None, store=None):
    return create_agent(MODEL, tools=TOOLS, context_schema=CareContext, middleware=build_middleware(),
                        checkpointer=checkpointer, store=store)


agent = build_agent()
