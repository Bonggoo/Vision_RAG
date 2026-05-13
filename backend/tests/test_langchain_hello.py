import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from dotenv import load_dotenv

load_dotenv()

try:
    llm = ChatGoogleGenerativeAI(
        model=os.environ.get("GEMINI_MODEL_NAME", "gemini-3.1-pro-preview"),
        temperature=0,
        api_key=os.environ.get("GEMINI_API_KEY")
    )
    
    print("Sending text to Gemini...")
    msg = HumanMessage(content="Hello! Are you there?")
    res = llm.invoke([msg])
    print("Response:", res.content)
    
except Exception as e:
    print(f"Error: {e}")
