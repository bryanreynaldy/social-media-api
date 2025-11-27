import streamlit as st
import requests
import json
import pandas as pd
from datetime import datetime

# Judul app
st.set_page_config(page_title="Social Media Engagement API", page_icon="📊")
st.title("📊 Social Media Engagement Extractor")
st.markdown("Extract engagement metrics from various social media platforms")

# Initialize Flask app (akan running di background)
import subprocess
import threading
import time
import os

def start_flask_app():
    """Start Flask app in background"""
    os.system("python app.py")

# Start Flask app in background thread
@st.cache_resource
def start_backend():
    thread = threading.Thread(target=start_flask_app, daemon=True)
    thread.start()
    time.sleep(5)  # Wait for Flask to start
    return True

# Sidebar
st.sidebar.header("Configuration")
api_url = st.sidebar.text_input("API URL", "http://localhost:5000")

# Check if backend is running
try:
    response = requests.get(f"{api_url}/health", timeout=5)
    if response.status_code == 200:
        st.sidebar.success("✅ API is running")
    else:
        st.sidebar.error("❌ API not responding")
except:
    st.sidebar.warning("⚠️ Starting API...")
    start_backend()

# Main tabs
tab1, tab2, tab3 = st.tabs(["Single URL", "Batch URLs", "API Status"])

with tab1:
    st.header("Single URL Extraction")
    
    url = st.text_input("Enter social media URL:", placeholder="https://twitter.com/username/status/123456789")
    
    if st.button("Extract Metrics", type="primary"):
        if url:
            with st.spinner("Extracting engagement metrics..."):
                try:
                    response = requests.post(
                        f"{api_url}/extract-single",
                        json={"url": url},
                        timeout=30
                    )
                    
                    if response.status_code == 200:
                        result = response.json()["result"]
                        
                        # Display results
                        col1, col2, col3 = st.columns(3)
                        
                        with col1:
                            st.metric("Platform", result.get("platform", "Unknown").upper())
                            st.metric("Likes", result.get("likes", "N/A"))
                            
                        with col2:
                            st.metric("Comments", result.get("comments", "N/A"))
                            st.metric("Views", result.get("views", "N/A"))
                            
                        with col3:
                            st.metric("Followers", result.get("followers", "N/A"))
                            st.metric("Shares", result.get("shares", "N/A"))
                        
                        # Additional info
                        st.subheader("Details")
                        st.write(f"**Author:** {result.get('author', 'N/A')}")
                        st.write(f"**Date:** {result.get('date', 'N/A')}")
                        st.write(f"**Content:** {result.get('content', 'N/A')}")
                        
                        if result.get("error"):
                            st.error(f"Error: {result['error']}")
                            
                    else:
                        st.error(f"API Error: {response.status_code}")
                        
                except Exception as e:
                    st.error(f"Request failed: {str(e)}")
        else:
            st.warning("Please enter a URL")

with tab2:
    st.header("Batch URL Extraction")
    
    st.markdown("Enter multiple URLs (one per line):")
    urls_text = st.text_area("URLs:", height=150, placeholder="https://twitter.com/user/status/123\nhttps://www.youtube.com/watch?v=abc123\nhttps://www.instagram.com/p/ABC123/")
    
    if st.button("Process Batch", type="primary"):
        if urls_text:
            urls = [url.strip() for url in urls_text.split('\n') if url.strip()]
            
            with st.spinner(f"Processing {len(urls)} URLs..."):
                try:
                    response = requests.post(
                        f"{api_url}/extract",
                        json={"links": urls},
                        timeout=60
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        
                        # Display summary
                        st.subheader("Summary")
                        summary = result.get("summary", {})
                        st.write(f"**Total Processed:** {summary.get('total_processed', 0)}")
                        
                        # Platform stats
                        platform_stats = summary.get('platform_stats', {})
                        for platform, stats in platform_stats.items():
                            st.write(f"**{platform.upper()}:** {stats.get('success', 0)} success, {stats.get('errors', 0)} errors")
                        
                        # Results table
                        st.subheader("Results")
                        df = pd.DataFrame(result.get("results", []))
                        if not df.empty:
                            st.dataframe(df)
                            
                            # Download button
                            csv = df.to_csv(index=False)
                            st.download_button(
                                label="Download CSV",
                                data=csv,
                                file_name=f"engagement_metrics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                                mime="text/csv"
                            )
                        else:
                            st.info("No results to display")
                            
                    else:
                        st.error(f"API Error: {response.status_code}")
                        
                except Exception as e:
                    st.error(f"Request failed: {str(e)}")
        else:
            st.warning("Please enter at least one URL")

with tab3:
    st.header("API Status & Information")
    
    try:
        # Health check
        health_response = requests.get(f"{api_url}/health", timeout=5)
        if health_response.status_code == 200:
            st.success("✅ API Health: Healthy")
        else:
            st.error("❌ API Health: Unhealthy")
        
        # Platforms info
        platforms_response = requests.get(f"{api_url}/platforms", timeout=5)
        if platforms_response.status_code == 200:
            platforms = platforms_response.json().get("supported_platforms", [])
            st.write("**Supported Platforms:**")
            for platform in platforms:
                st.write(f"- {platform}")
        
        # API info
        info_response = requests.get(f"{api_url}/", timeout=5)
        if info_response.status_code == 200:
            info = info_response.json()
            st.write("**API Information:**")
            st.write(f"Version: {info.get('version', 'N/A')}")
            st.write(f"Message: {info.get('message', 'N/A')}")
            
    except Exception as e:
        st.error(f"Could not connect to API: {str(e)}")

# Footer
st.markdown("---")
st.markdown("Built with Streamlit & Flask | Social Media Engagement API")
