import streamlit as st
import requests
import speech_recognition as sr
import pyttsx3
import threading
import queue
import time
from datetime import datetime

API_URL = "http://127.0.0.1:5000/chat"

# Initialize speech queue
if "speech_queue" not in st.session_state:
    st.session_state.speech_queue = queue.Queue()

# Text-to-Speech (TTS) worker function
def tts_worker(q):
    while True:
        text = q.get()
        if text is None:
            break
        try:
            engine = pyttsx3.init()
            voices = engine.getProperty('voices')
            for voice in voices:
                if "female" in voice.name.lower() or "zira" in voice.name.lower() or "samantha" in voice.name.lower():
                    engine.setProperty('voice', voice.id)
                    break
            engine.setProperty('rate', 180)
            engine.say(text)
            while True:
                try:
                    engine.runAndWait()
                    break
                except RuntimeError as e:
                    if "run loop already started" in str(e):
                        engine.stop()
                        time.sleep(0.2)
                    else:
                        raise e
            engine.stop()
        except Exception as e:
            print("TTS run error:", e)

# Start the TTS thread
if "tts_thread" not in st.session_state:
    st.session_state.tts_thread = threading.Thread(
        target=tts_worker, 
        args=(st.session_state.speech_queue,), 
        daemon=True
    )
    st.session_state.tts_thread.start()

def speak(text):
    st.session_state.speech_queue.put(text)

# Voice recognition function
def listen():
    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        st.info("Listening... Speak now 🎙️")
        try:
            audio = recognizer.listen(source, timeout=5)
            text = recognizer.recognize_google(audio)
            return text
        except sr.UnknownValueError:
            return "Sorry, I couldn't understand. Try speaking more clearly."
        except sr.RequestError:
            return "Microphone error. Please check your device settings."

# App title
st.title("😎 Serene")
st.write("Chat with Serene, your virtual buddy! 😊")

# Initialize session state variables
if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = []

if "expand_history" not in st.session_state:
    st.session_state["expand_history"] = False

# Reset chat button
if st.button("🗑️ Reset Chat"):
    st.session_state["chat_history"] = []
    response = requests.post("http://127.0.0.1:5000/reset", json={"user_id": "user1"})
    if response.status_code == 200:
        st.success("Chat history reset successfully!")
    else:
        st.error("Failed to reset chat history.")

# Input fields
col1, col2 = st.columns([4, 1])

with col1:
    user_input = st.text_input("Ask Serene something...", "")

with col2:
    if st.button("🎙️", help="Voice Input"):
        user_voice = listen()
        if user_voice:
            st.write(f"**You (Voice):** {user_voice}")
            response = requests.post(API_URL, json={"user_id": "user1", "message": user_voice}).json()
            timestamp = datetime.now().strftime("%H:%M")
            st.session_state["chat_history"].append(("You", user_voice, timestamp))
            st.session_state["chat_history"].append(("Serene", response["response"], timestamp))
            speak(response["response"])
            st.session_state["expand_history"] = False  # Auto-collapse history

if st.button("Send", key="send"):
    if user_input:
        timestamp = datetime.now().strftime("%H:%M")
        
        # Show typing indicator
        with st.spinner("Serene is typing..."):
            response = requests.post(API_URL, json={"user_id": "user1", "message": user_input}).json()
        
        # Store messages with timestamps
        st.session_state["chat_history"].append(("You", user_input, timestamp))
        st.session_state["chat_history"].append(("Serene", response["response"], timestamp))
        
        speak(response["response"])
        st.session_state["expand_history"] = False  # Auto-collapse history

# Custom CSS for better UI
st.markdown("""
<style>
body {
    background-color: #121212;
    color: white;
    font-family: 'Arial', sans-serif;
}

.chat-container {
    width: 100%;
    padding: 10px;
}

.chat-box {
    padding: 12px;
    margin: 10px 0;
    border-radius: 18px;
    max-width: 80%;
    box-shadow: 2px 2px 8px rgba(255, 255, 255, 0.1);
}

.you {
    background: linear-gradient(to right, #80ff72, #7ee8fa);
    color: black;
    text-align: left;
    float: left;
    clear: both;
    border: 1px solid #4CAF50;
}

.serene {
    background: linear-gradient(to right, #6a11cb, #2575fc);
    color: white;
    text-align: left;
    float: right;
    clear: both;
    border: 1px solid #1e3c72;
}

.timestamp {
    font-size: 0.8em;
    color: #ccc;
    margin-top: 5px;
    text-align: right;
}
</style>
""", unsafe_allow_html=True)

# Display chat history with beautified bubbles
with st.expander("📜 Previous Conversations", expanded=st.session_state["expand_history"]):
    st.markdown('<div class="chat-container">', unsafe_allow_html=True)

    for i, (sender, msg, timestamp) in enumerate(st.session_state["chat_history"]):
        bubble_class = "you" if sender == "You" else "serene"

        st.markdown(f"""
        <div class="chat-box {bubble_class}">
          <div><strong>{sender}</strong></div>
          <div>{msg}</div>
          <div class="timestamp">{timestamp}</div>
        </div>
        """, unsafe_allow_html=True)

        if sender == "Serene":
            if st.button("🔊", key=f"play_{i}", help="Play Audio"):
                speak(msg)

    st.markdown('</div>', unsafe_allow_html=True)
