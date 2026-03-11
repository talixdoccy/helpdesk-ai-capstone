import os
import requests
import streamlit as st
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_TABLE_TICKETS = os.getenv("SUPABASE_TABLE_TICKETS")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

st.set_page_config(page_title="HelpDesk AI", page_icon="🛠️", layout="wide")


# ---------- Helper functions ----------
def classify_ticket(text: str):
    text_lower = text.lower()

    if "email" in text_lower or "outlook" in text_lower:
        return "Email", "Medium", "Reset email profile and re-add account."
    elif "password" in text_lower or "login" in text_lower:
        return "Account Access", "High", "Verify username and reset password."
    elif "vpn" in text_lower:
        return "VPN", "High", "Check VPN credentials and network connection."
    elif "wifi" in text_lower or "internet" in text_lower:
        return "Network", "High", "Check connection status and restart router."
    else:
        return "General Support", "Normal", "Review issue and escalate if needed."


def save_ticket_to_supabase(ticket_text, category, priority, suggested_action):
    endpoint = f"{SUPABASE_URL}/rest/v1/tickets"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    payload = {
        "ticket_text": ticket_text,
        "category": category,
        "priority": priority,
        "suggested_action": suggested_action
    }

    response = requests.post(endpoint, headers=headers, json=payload)
    return response


def save_qa_log_to_supabase(question, answer, retrieved_chunk):
    endpoint = f"{SUPABASE_URL}/rest/v1/qa_logs"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    payload = {
        "question": question,
        "answer": answer,
        "retrieved_chunk": retrieved_chunk
    }

    response = requests.post(endpoint, headers=headers, json=payload)
    return response


def load_docs(folder="docs"):
    documents = []
    if os.path.exists(folder):
        for filename in os.listdir(folder):
            if filename.endswith(".md"):
                filepath = os.path.join(folder, filename)
                with open(filepath, "r", encoding="utf-8") as file:
                    content = file.read()
                    documents.append({"filename": filename, "content": content})
    return documents


def search_docs(question, docs):
    stop_words = {
        "what", "should", "i", "do", "if", "my", "is", "the", "a", "an",
        "to", "for", "of", "and", "on", "in", "it", "not", "can", "how"
    }

    question_words = [
        word.strip("?,.!").lower()
        for word in question.split()
        if word.strip("?,.!").lower() not in stop_words
    ]

    best_doc = None
    best_score = 0

    for doc in docs:
        content_lower = doc["content"].lower()
        score = sum(1 for word in question_words if word in content_lower)

        if score > best_score:
            best_score = score
            best_doc = doc

    return best_doc, best_score


def generate_helpdesk_answer(question, context):
    prompt = f"""
You are a helpful IT support assistant.

Answer the user's question using only the helpdesk context below.
If the context does not contain enough information, say:
"I'm not sure about this one — please contact support."

Keep the answer clear, practical, and short.

Helpdesk context:
{context}

User question:
{question}
"""

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt
    )
    return response.output_text


# ---------- UI ----------
st.title("🛠️ HelpDesk AI")
st.markdown("**Knowledge Base + Ticket Triage Assistant**")
st.write("This app helps classify support tickets and answer technical questions from helpdesk documentation.")

tab1, tab2 = st.tabs(["🎫 Ticket Triage", "📚 Knowledge Base"])

# ---------- Tab 1: Ticket Triage ----------
with tab1:
    st.subheader("Analyze a Support Ticket")

    ticket_text = st.text_area(
        "Describe the support issue:",
        placeholder="Example: My Outlook email is not syncing on my phone.",
        height=150
    )

    if st.button("Analyze Ticket"):
        if not ticket_text.strip():
            st.warning("Please enter a support ticket.")
        else:
            category, priority, suggested_action = classify_ticket(ticket_text)

            st.success("Ticket analyzed successfully.")
            st.write(f"**Category:** {category}")
            st.write(f"**Priority:** {priority}")
            st.write(f"**Suggested Action:** {suggested_action}")

            response = save_ticket_to_supabase(
                ticket_text,
                category,
                priority,
                suggested_action
            )

            if response.status_code == 201:
                st.info("Ticket saved to Supabase successfully.")
            else:
                st.error(f"Failed to save ticket. Status code: {response.status_code}")
                try:
                    st.json(response.json())
                except Exception:
                    st.write(response.text)

# ---------- Tab 2: Knowledge Base ----------
with tab2:
    st.subheader("HelpDesk Knowledge Base")

    docs = load_docs()
    st.write(f"Loaded documents: {len(docs)}")

    question = st.text_input(
        "Ask a technical support question:",
        placeholder="Example: What should I do if I forgot my password?"
    )

    if st.button("Get AI Answer"):
        if not question.strip():
            st.warning("Please enter a question.")
        else:
            best_doc, score = search_docs(question, docs)

            if best_doc and score > 0:
                st.success("Relevant document found.")
                st.write(f"**Best Match:** {best_doc['filename']}")
                st.write(f"**Match Score:** {score}")

                try:
                    answer = generate_helpdesk_answer(question, best_doc["content"])
                    st.markdown("### AI Answer")
                    st.write(answer)

                    log_response = save_qa_log_to_supabase(
                        question,
                        answer,
                        best_doc["content"]
                    )

                    if log_response.status_code == 201:
                        st.info("Q&A log saved to Supabase successfully.")
                    else:
                        st.error(f"Failed to save Q&A log. Status code: {log_response.status_code}")
                        try:
                            st.json(log_response.json())
                        except Exception:
                            st.write(log_response.text)

                    with st.expander("Show retrieved context"):
                        st.text_area(
                            "Relevant Content",
                            best_doc["content"],
                            height=300
                        )

                except Exception as e:
                    st.error("OpenAI answer generation failed.")
                    st.write(str(e))
            else:
                st.warning("No relevant document found. Please try a different question.")