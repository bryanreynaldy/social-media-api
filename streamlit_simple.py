import streamlit as st
import requests
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="Social Media Engagement", page_icon="📊")
st.title("📊 Social Media Engagement Extractor")

# Configuration
st.sidebar.header("API Configuration")
api_url = st.sidebar.text_input("Backend API URL", "https://your-backend.herokuapp.com")

st.sidebar.markdown("""
**Supported Platforms:**
- YouTube
- TikTok  
- X/Twitter
- Instagram
""")

# Main app
tab1, tab2 = st.tabs(["Single URL", "Batch URLs"])

with tab1:
    st.header("Single URL Extraction")
    url = st.text_input("Enter URL:", placeholder="https://www.youtube.com/watch?v=...")
    
    if st.button("Get Metrics", type="primary") and url:
        with st.spinner("Fetching metrics..."):
            try:
                response = requests.post(
                    f"{api_url}/extract-single",
                    json={"url": url},
                    timeout=30
                )
                
                if response.status_code == 200:
                    result = response.json().get("result", {})
                    
                    # Display metrics
                    cols = st.columns(4)
                    metrics = [
                        ("Platform", result.get("platform", "N/A")),
                        ("Likes", result.get("likes", "N/A")),
                        ("Comments", result.get("comments", "N/A")),
                        ("Views", result.get("views", "N/A"))
                    ]
                    
                    for col, (label, value) in zip(cols, metrics):
                        col.metric(label, value)
                    
                    # Additional info
                    if result.get("author"):
                        st.write(f"**Author:** {result['author']}")
                    if result.get("error"):
                        st.error(f"Error: {result['error']}")
                        
                else:
                    st.error(f"API returned {response.status_code}")
                    
            except Exception as e:
                st.error(f"Failed to connect: {str(e)}")

with tab2:
    st.header("Batch Processing")
    st.info("For batch processing, please use the backend API directly or deploy the full version.")
    
    st.markdown("""
    **Backend API Endpoints:**
    - `POST /extract-single` - Single URL
    - `POST /extract` - Multiple URLs
    - `GET /health` - Health check
    """)

st.markdown("---")
st.markdown("Social Media Engagement API | Streamlit Frontend")
