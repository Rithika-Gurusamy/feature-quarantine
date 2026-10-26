import os
import sys
import uuid
import json
from datetime import datetime, UTC
from typing import List, Dict, Optional
import redis
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

# Pull the Gemini API key from the system environment
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    print("ERROR: GEMINI_API_KEY environment variable not found!")
    print("Please set it in your PowerShell terminal by running:")
    print('   $env:GEMINI_API_KEY="your-actual-api-key-here"')
    print("\nThen run this script again.")
    sys.exit(1)

# Initialize the Gemini Language Model client
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",  
    temperature=0.7,
    google_api_key=GEMINI_API_KEY
)

# Connect to the local Redis instance running inside Docker
try:
    r = redis.Redis(host="localhost", port=6379, decode_responses=True)
    r.ping()
except redis.exceptions.ConnectionError:
    print(" ERROR: Could not connect to Redis!")
    print("Make sure Docker Desktop is open and your Redis container is running.")
    print("Run this command in a separate PowerShell window to fix it:")
    print("   docker start chat-redis")
    sys.exit(1)

# The conversation manager class handling message objects and lists in Redis
class RedisConversationManager:
    """Manages chat messages directly in Redis using structured lists and strings."""
    
    @staticmethod
    def get_conversation_list_key(conversation_id: str) -> str:
        return f"conversation:{conversation_id}:messages"

    @staticmethod
    def get_message_key(message_id: str) -> str:
        return f"message:{message_id}"

    def save_message(self, conversation_id: str, role: str, content: str, parent_id: Optional[str] = None) -> str:
        message_id = f"msg_{uuid.uuid4().hex[:8]}"
        
        # Uses modern timezone-aware UTC datetime to fix the console deprecation warning
        message_data = {
            "message_id": message_id,
            "conversation_id": conversation_id,
            "parent_id": parent_id or "",
            "role": role,
            "content": content,
            "timestamp": datetime.now(UTC).isoformat()
        }
        
        # Save individual message string and append its reference to the conversation timeline list
        r.set(self.get_message_key(message_id), json.dumps(message_data))
        r.rpush(self.get_conversation_list_key(conversation_id), message_id)
        
        return message_id

    def get_context_window(self, conversation_id: str) -> List[Dict]:
        list_key = self.get_conversation_list_key(conversation_id)
        message_ids = r.lrange(list_key, 0, -1)
        
        context_messages = []
        for msg_id in message_ids:
            raw_msg = r.get(self.get_message_key(msg_id))
            if raw_msg:
                context_messages.append(json.loads(raw_msg))
                
        return context_messages

# Initialize the manager object instance
memory_manager = RedisConversationManager()

# The operational loop managing user text input, database caching, and AI logic
def run_console_chat():
    print("🤖 Welcome to the Gemini + Redis Live Chat Console!")
    print("--------------------------------------------------")
    
    conversation_id = f"conv_{uuid.uuid4().hex[:6]}"
    print(f"Active Session Started. ID: {conversation_id}")
    print("Type 'exit', 'quit', or 'stop' to end the session.\n")
    
    system_instruction = (
        "You are a sharp, analytical AI assistant. Start the chat by saying 'Hey, what's going on?'. "
        "Keep track of everything the user says. Ask deep follow-up questions to keep them talking."
    )
    
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
                
            # Step 1: Save the incoming prompt into the Redis key-value store
            user_msg_id = memory_manager.save_message(
                conversation_id=conversation_id,
                role="user",
                content=user_input,
                parent_id=last_message_id
            )
            
            # Step 2: Extract historical dialog logs out of Redis
            history = memory_manager.get_context_window(conversation_id)
            
            # Step 3: Build the prompt template object payload for the LangChain client
            llm_payload = [SystemMessage(content=system_instruction)]
            for msg in history:
                if msg["role"] == "user":
                    llm_payload.append(HumanMessage(content=msg["content"]))
                elif msg["role"] == "assistant":
                    llm_payload.append(AIMessage(content=msg["content"]))
            
            # Step 4: Fire request payload to Gemini API over network interface
            print("\nGemini is thinking...")
            ai_response = llm.invoke(llm_payload)
            print(f"AI: {ai_response.content}\n")
            
            # Step 5: Update tracking variables and log final answer text block inside Redis
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
