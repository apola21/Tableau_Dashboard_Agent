import streamlit as st
import asyncio
import os
import time
from datetime import datetime
import base64
from TableauDashboardAgent_Clean import TableauDashboardAgent

# Page configuration
st.set_page_config(
    page_title="Tableau Dashboard Agent",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(90deg, #1f77b4, #ff7f0e);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        text-align: center;
        margin-bottom: 2rem;
    }
    .sample-question {
        background-color: #f0f2f6;
        padding: 0.5rem;
        border-radius: 5px;
        margin: 0.5rem 0;
        cursor: pointer;
        transition: background-color 0.3s;
    }
    .sample-question:hover {
        background-color: #e1e5e9;
    }
    .status-box {
        background-color: #e8f5e8;
        border-left: 4px solid #28a745;
        padding: 1rem;
        margin: 1rem 0;
        border-radius: 5px;
    }
    .error-box {
        background-color: #f8d7da;
        border-left: 4px solid #dc3545;
        padding: 1rem;
        margin: 1rem 0;
        border-radius: 5px;
    }
</style>
""", unsafe_allow_html=True)

# Initialize the agent
@st.cache_resource
def get_agent():
    """Initialize and cache the Tableau Dashboard Agent"""
    try:
        return TableauDashboardAgent()
    except Exception as e:
        st.error(f"Failed to initialize agent: {str(e)}")
        return None

def display_sample_questions():
    """Display sample questions in the sidebar"""
    st.sidebar.header("💡 Sample Questions")
    st.sidebar.markdown("Click any question below to try it:")
    
    sample_questions = [
        "Show me data for bachelor's degree programs",
        "What programs are available in STEM category?",
        "Filter by Lehman College and show results",
        "How many master's programs are there?",
        "Compare data across different colleges",
        "Show me trends in the data",
        "What certificate programs are available?",
        "Show me programs by delivery format",
        "Filter by academic plan and show results",
        "What's the enrollment data by college type?"
    ]
    
    for i, question in enumerate(sample_questions):
        if st.sidebar.button(f"📋 {question}", key=f"sample_{i}", use_container_width=True):
            st.session_state.user_question = question
            st.rerun()

def display_chat_history():
    """Display the chat history"""
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            
            # Display screenshot if available
            if message.get("screenshot"):
                st.image(
                    message["screenshot"], 
                    caption="📊 Dashboard Screenshot", 
                    use_column_width=True
                )
            
            # Display metadata if available
            if message.get("metadata"):
                with st.expander("📈 Analysis Details"):
                    st.json(message["metadata"])

def process_user_question(prompt):
    """Process the user's question and return the response"""
    agent = get_agent()
    if not agent:
        return "❌ Agent initialization failed. Please check the logs.", None, None
    
    try:
        # Run the async analysis
        result = asyncio.run(agent.analyze_dashboard(prompt))
        
        if "error" in result:
            error_msg = f"❌ **Error:** {result['error']}"
            return error_msg, None, None
        
        # Analyze the data
        analysis = asyncio.run(agent.analyze_dashboard_data(prompt, result))
        
        # Prepare metadata
        metadata = {
            "dashboard_title": result.get("title", "Unknown"),
            "dashboard_url": result.get("url", ""),
            "timestamp": datetime.now().isoformat(),
            "processing_time": "30-60 seconds"
        }
        
        # Handle screenshot
        screenshot_data = result.get("screenshot_data", {})
        screenshot_path = None
        
        if screenshot_data and not screenshot_data.get("error"):
            screenshot_path = screenshot_data.get("screenshot_path")
            if screenshot_path and os.path.exists(screenshot_path):
                metadata["screenshot_captured"] = True
                metadata["screenshot_path"] = screenshot_path
            else:
                metadata["screenshot_captured"] = False
        else:
            metadata["screenshot_captured"] = False
        
        return analysis, screenshot_path, metadata
        
    except Exception as e:
        error_msg = f"❌ **An error occurred:** {str(e)}"
        return error_msg, None, {"error": str(e)}

def main():
    # Header
    st.markdown("""
    <div class="main-header">
        <h1>📊 Tableau Dashboard Agent</h1>
        <p>Ask questions about CUNY program data and get insights from the dashboard!</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Sidebar
    with st.sidebar:
        st.markdown("### 🎯 About This Agent")
        st.markdown("""
        This agent can:
        - Apply filters to Tableau dashboards
        - Extract insights from charts and data
        - Answer questions about program information
        - Generate visual analysis reports
        """)
        
        st.markdown("### ⚠️ Important Notes")
        st.markdown("""
        - Analysis takes 30-60 seconds per question
        - The agent opens a browser to interact with the dashboard
        - Screenshots are captured for visual analysis
        - Results include both data and visual insights
        """)
        
        # Sample questions
        display_sample_questions()
        
        # Clear chat button
        if st.button("🗑️ Clear Chat History", use_container_width=True):
            st.session_state.messages = []
            st.rerun()
    
    # Initialize session state
    if 'messages' not in st.session_state:
        st.session_state.messages = []
    
    # Main chat interface
    st.header("💬 Chat with the Dashboard Agent")
    
    # Display chat history
    display_chat_history()
    
    # Chat input
    if prompt := st.chat_input("Ask about CUNY program data (e.g., 'Show me bachelor's programs')..."):
        # Add user message to chat history
        st.session_state.messages.append({
            "role": "user", 
            "content": prompt,
            "timestamp": datetime.now().isoformat()
        })
        
        # Display user message
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # Get agent response
        with st.chat_message("assistant"):
            with st.spinner("🔍 Analyzing dashboard... This may take 30-60 seconds."):
                # Show processing status
                status_placeholder = st.empty()
                status_placeholder.markdown("""
                <div class="status-box">
                    <strong>🔄 Processing your request...</strong><br>
                    • Opening dashboard<br>
                    • Applying filters<br>
                    • Capturing screenshot<br>
                    • Analyzing data<br>
                    • Generating insights
                </div>
                """, unsafe_allow_html=True)
                
                # Process the question
                response_content, screenshot_path, metadata = process_user_question(prompt)
                
                # Clear status
                status_placeholder.empty()
                
                # Display response
                if response_content.startswith("❌"):
                    st.markdown(f"""
                    <div class="error-box">
                        {response_content}
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(response_content)
                
                # Display screenshot if available
                if screenshot_path and os.path.exists(screenshot_path):
                    st.image(
                        screenshot_path, 
                        caption="📊 Dashboard Analysis Screenshot", 
                        use_column_width=True
                    )
                
                # Display metadata
                if metadata:
                    with st.expander("📈 Analysis Details"):
                        st.json(metadata)
                
                # Add assistant response to chat history
                assistant_message = {
                    "role": "assistant", 
                    "content": response_content,
                    "timestamp": datetime.now().isoformat(),
                    "metadata": metadata
                }
                
                if screenshot_path and os.path.exists(screenshot_path):
                    assistant_message["screenshot"] = screenshot_path
                
                st.session_state.messages.append(assistant_message)
    
    # Footer
    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("**📊 Dashboard:** [CUNY Programs](https://insights.cuny.edu/t/CUNYGuest/views/CUNYRegisteredProgramsInventory/ProgramCount)")
    
    with col2:
        st.markdown("**🔧 Technology:** Playwright + GPT-4 Vision")
    
    with col3:
        st.markdown("**⏱️ Processing:** 30-60 seconds per query")

if __name__ == "__main__":
    main()

