import os
import sys
import uuid
import json
from datetime import datetime
from typing import List, Dict, Optional
import redis
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

# =====================================================================
# 1. API KEY VERIFICATION & CLIENT INITIALIZATION
# =====================================================================

# Explicitly pull the Gemini API key from the environment
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    print("❌ ERROR: GEMINI_API_KEY environment variable not found!")
    print("Please set it in your PowerShell terminal by running:")
    print('   $env:GEMINI_API_KEY="your-actual-api-key-here"')
    print("\nThen run this script again.")
    sys.exit(1)

# Initialize the Gemini Language Model Client using the environment key
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",  
    temperature=0.7,
    google_api_key=GEMINI_API_KEY
)

# Connect to the local Redis instance running inside your Docker container
try:
    r = redis.Redis(host="localhost", port=6379, decode_responses=True)
    # Perform a quick ping test to ensure Redis is awake
    r.ping()
except redis.exceptions.ConnectionError:
    print("❌ ERROR: Could not connect to Redis!")
    print("Make sure Docker Desktop is open and your Redis container is running.")
    print("Run this command in a separate PowerShell window to fix it:")
    print("   docker start chat-redis")
    sys.exit(1)

# =====================================================================
# 2. THE REDIS MEMORY ENGINE
# =====================================================================
class RedisConversationManager:
    """Manages chat messages directly in Redis using structured lists and strings."""
    
    @staticmethod
    def get_conversation_list_key(conversation_id: str) -> str:
        return f"conversation:{conversation_id}:messages"

    @staticmethod
    def get_message_key(message_id: str) -> str:
        return f"message:{message_id}"

    def save_message(self, conversation_id: str, role: str, content: str, parent_id: Optional[str] = None) -> str:
        """Saves a single message object into Redis and appends its ID to the conversation list."""
        message_id = f"msg_{uuid.uuid4().hex[:8]}"
        
        # Structure the individual message data object
        message_data = {
            "message_id": message_id,
            "conversation_id": conversation_id,
            "parent_id": parent_id or "",
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # 1. Store the individual message object as a stringified JSON key
        r.set(self.get_message_key(message_id), json.dumps(message_data))
        
        # 2. Push this unique message ID to the tracking list for this conversation
        r.rpush(self.get_conversation_list_key(conversation_id), message_id)
        
        return message_id

    def get_context_window(self, conversation_id: str) -> List[Dict]:
        """Retrieves every individual message object linked to this conversation in order."""
        list_key = self.get_conversation_list_key(conversation_id)
        message_ids = r.lrange(list_key, 0, -1)
        
        context_messages = []
        for msg_id in message_ids:
            raw_msg = r.get(self.get_message_key(msg_id))
            if raw_msg:
                context_messages.append(json.loads(raw_msg))
                
        return context_messages

# Initialize our Redis Manager
memory_manager = RedisConversationManager()

# =====================================================================
# 3. CONSOLE INTERACTION LOOP
# =====================================================================
def run_console_chat():
    print("🤖 Welcome to the Gemini + Redis Live Chat Console!")
    print("--------------------------------------------------")
    
    # Generate a single active conversation session ID
    conversation_id = f"conv_{uuid.uuid4().hex[:6]}"
    print(f"Active Session Started. ID: {conversation_id}")
    print("Type 'exit', 'quit', or 'stop' to end the session.\n")
    
    # The system prompt sets Gemini's core behavioral rules
    system_instruction = (
        "You are a sharp, analytical AI assistant. Start the chat by saying 'Hey, what's going on?'. "
        "Keep track of everything the user says. Ask deep follow-up questions to keep them talking."
    )
    
    # Prime the context window by generating the first greeting
    print(f"AI: Hey, what's going on?\n")
    last_message_id = memory_manager.save_message(
        conversation_id=conversation_id,
        role="assistant",
        content="Hey, what's going on?",
        parent_id=None
    )

    while True:
        try:
            user_input = input("You: ")
            if user_input.lower() in ['exit', 'quit', 'stop']:
                print("Ending active chat session. Goodbye!")
                break
                
            if not user_input.strip():
                continue
                
            # 1. Save user's message as an individual record in Redis
            user_msg_id = memory_manager.save_message(
                conversation_id=conversation_id,
                role="user",
                content=user_input,
                parent_id=last_message_id
            )
            
            # 2. Fetch the entire active history array from Redis
            history = memory_manager.get_context_window(conversation_id)
            
            # 3. Format the text items into native LangChain structures for Gemini
            llm_payload = [SystemMessage(content=system_instruction)]
            for msg in history:
                if msg["role"] == "user":
                    llm_payload.append(HumanMessage(content=msg["content"]))
                elif msg["role"] == "assistant":
                    llm_payload.append(AIMessage(content=msg["content"]))
            
            # 4. Invoke Gemini with complete contextual memory
            print("\nGemini is thinking...")
            ai_response = llm.invoke(llm_payload)
            print(f"AI: {ai_response.content}\n")
            
            # 5. Save Gemini's response back to Redis
            last_message_id = memory_manager.save_message(
                conversation_id=conversation_id,
                role="assistant",
                content=ai_response.content,
                parent_id=user_msg_id
            )
            
        except KeyboardInterrupt:
            print("\nSession stopped.")
            break

if __name__ == "__main__":
    run_console_chat()
