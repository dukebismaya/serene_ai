import os
import requests
import threading
import random
import streamlit as st
import pyttsx3
import speech_recognition as sr
from textblob import TextBlob
from flask import Flask, request, jsonify
from pinecone import Pinecone, ServerlessSpec
from sentence_transformers import SentenceTransformer
import logging, time

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

# Load Groq API key from environment variable

import streamlit as st

GROQ_API_KEY = st.secrets["GROQ_API"]
PINECONE_API_KEY = st.secrets["PINECONE_API"]

app = Flask(__name__)

# Initialize Pinecone client
pc = Pinecone(api_key=PINECONE_API_KEY)
INDEX_NAME = "serene-chat-history"
dimension = 384  # all-MiniLM-L6-v2 dimension

# Create index if not exists
if INDEX_NAME not in pc.list_indexes().names():
    pc.create_index(
        name=INDEX_NAME,
        dimension=dimension,
        metric="cosine",
        spec=ServerlessSpec(
            cloud="aws",
            region="us-east-1"
        )
    )

# Connect to index
index = pc.Index(INDEX_NAME)
embed_model = SentenceTransformer('all-MiniLM-L6-v2')

# Initialize Text-to-Speech engine
engine = pyttsx3.init()

# Suggested quick replies
QUICK_REPLIES = [
    "Tell me more about that. 💙",
    "How has your day been? 😊",
    "Would you like some relaxation techniques? 🌿",
    "I'm here to listen. What's on your mind? 🤗"
]

# # ✅ DATABASE SETUP
# DB_FILE = "serene_chat.db"

# def init_db():
#     """Creates necessary tables if they don't exist."""
#     with sqlite3.connect(DB_FILE) as conn:
#         cursor = conn.cursor()
#         cursor.execute("""
#         CREATE TABLE IF NOT EXISTS users (
#             id INTEGER PRIMARY KEY AUTOINCREMENT,
#             user_id TEXT UNIQUE,
#             name TEXT,
#             mood TEXT
#         )
#         """)
#         cursor.execute("""
#         CREATE TABLE IF NOT EXISTS messages (
#             id INTEGER PRIMARY KEY AUTOINCREMENT,
#             user_id TEXT,
#             message TEXT,
#             sender TEXT,  
#             timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
#         )
#         """)
#         conn.commit()

# init_db()  # Initialize the database
from datetime import datetime, timezone
import uuid

def save_message(user_id, message, sender):
    """Save message to Pinecone with metadata"""
    try:
        embedding = embed_model.encode(message).tolist()
        metadata = {
            "user_id": user_id,
            "sender": sender,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        vector_id = f"{user_id}_{uuid.uuid4()}"
        index.upsert(vectors=[(vector_id, embedding, metadata)])
        return True
    except Exception as e:
        app.logger.error(f"Save error: {str(e)}")
        return False

def get_last_messages(user_id, top_k=5):
    """Retrieve the most relevant past messages for a user."""
    try:
        query_embedding = embed_model.encode(user_id).tolist()  # Encode user ID as vector
        results = index.query(vector=query_embedding, top_k=top_k, include_metadata=True)

        return [
            (match['metadata']['message'], match['metadata']['sender'])
            for match in results.get('matches', [])
        ]
    except Exception as e:
        logging.error(f"Query error: {str(e)}")
        return []




def detect_mood(user_input):
    """Analyzes mood using sentiment analysis."""
    analysis = TextBlob(user_input)
    polarity = analysis.sentiment.polarity  
    
    if polarity < -0.3:
        return "negative"
    elif polarity > 0.3:
        return "positive"
    else:
        return "neutral"

def speak(text):
    """Convert text to speech."""
    engine.say(text)
    engine.runAndWait()

def listen():
    """Recognize speech input from the user."""
    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        st.info("Listening... Speak now 🎙️")
        try:
            audio = recognizer.listen(source, timeout=5)
            text = recognizer.recognize_google(audio)
            return text
        except sr.UnknownValueError:
            return "Sorry, I didn't catch that."
        except sr.RequestError:
            return "Speech recognition service unavailable."

def generate_response(user_id, user_input):
    """Generates AI response with chat memory."""
    last_messages = get_last_messages(user_id)

    # Format past messages for context
    conversation_context = "\n".join([f"{sender}: {msg}" for msg, sender in last_messages])

    # System instructions for AI personality
    serene_behavior = (
        "You are Serene, a virtual friend who chats dynamically with users. "
        "You behave like a real human buddy, not a machine. "
        "You are created by Bismay, Sumit, and Anup. Be friendly but avoid being overly dramatic or romantic. "
        "Your main goal is to be a supportive companion, especially in mental wellness discussions."
        "You should keep your response to the point and be precise. Keep the user enaged like a real friend. "
    )

    # Construct payload for Groq API
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": serene_behavior},
            {"role": "user", "content": conversation_context + f"\nUser: {user_input}"}
        ],
        "temperature": 0.9,
        "max_tokens": 250,
        "top_p": 0.95
    }

    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    for attempt in range(3):  # Retry up to 3 times
        response = requests.post("https://api.groq.com/openai/v1/chat/completions", json=payload, headers=headers)
        
        if response.status_code == 200:
            try:
                response_data = response.json()
                bot_response = response_data.get("choices", [{}])[0].get("message", {}).get("content", "No response.")
                
                # Save messages in Pinecone
                save_message(user_id, user_input, "user")
                save_message(user_id, bot_response, "bot")

                return bot_response
            except Exception as e:
                logging.error(f"Error parsing response: {e}")
                return "Error processing response."

        elif response.status_code in [429, 500]:  # Rate limit or server error
            time.sleep(2 ** attempt)  # Exponential backoff

    return "I'm sorry, I couldn't process that request right now. Please try again later."

@app.route('/chat', methods=['POST'])
def chat():
    """Handles chat requests and returns AI responses."""
    data = request.json
    user_id = data.get("user_id", "default_user")
    user_input = data.get("message")

    if not user_input:
        return jsonify({"error": "Message is required"}), 400

    response = generate_response(user_id, user_input)

    return jsonify({"response": response, "quick_replies": QUICK_REPLIES})

@app.route("/reset", methods=["POST"])
def reset_chat():
    """Clears chat history for a specific user in Pinecone."""
    data = request.json
    user_id = data.get("user_id")

    if not user_id:
        return jsonify({"error": "User ID is required"}), 400

    try:
        # Retrieve all vector IDs associated with the user
        query_embedding = embed_model.encode(user_id).tolist()
        results = index.query(vector=query_embedding, top_k=100, include_metadata=True)

        vector_ids = [match.get('id') for match in results.get('matches', []) if 'id' in match]

        if vector_ids:
            index.delete(vector_ids)  # Corrected deletion method
            return jsonify({"message": "Chat history cleared!"})
        else:
            return jsonify({"message": "No messages found for this user."})
    
    except Exception as e:
        logging.error(f"Failed to reset chat: {str(e)}")
        return jsonify({"error": f"Failed to reset chat: {str(e)}"}), 500

    
@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "ok", "message": "Serene Chat API is running!"})



if __name__ == '__main__':
    app.run(debug=True, threaded=True)

