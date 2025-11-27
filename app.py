from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from social_media_extractor import SocialMediaExtractor

app = Flask(__name__)
CORS(app)

# Initialize extractor
extractor = SocialMediaExtractor()

@app.route('/')
def home():
    return jsonify({
        "message": "Social Media Engagement API",
        "version": "1.0",
        "endpoints": {
            "/health": "Check API health",
            "/extract": "Extract engagement metrics from social media links (POST)", 
            "/platforms": "Get supported platforms"
        }
    })

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "service": "social-media-api"})

@app.route('/platforms')
def platforms():
    return jsonify({
        "supported_platforms": [
            "X/Twitter",
            "YouTube",
            "TikTok", 
            "Stockbit",
            "Instagram",
            "LinkedIn"
        ]
    })

@app.route('/extract', methods=['POST'])
def extract_engagement():
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
        
        links = data.get('links', [])
        
        if not links:
            return jsonify({"error": "No links provided"}), 400
        
        if not isinstance(links, list):
            return jsonify({"error": "Links must be a list"}), 400
        
        # Validate links
        valid_links = []
        for link in links:
            if isinstance(link, str) and link.strip():
                valid_links.append(link.strip())
        
        if not valid_links:
            return jsonify({"error": "No valid links provided"}), 400
        
        # Process links
        print(f"📥 Processing {len(valid_links)} links...")
        result = extractor.process_links(valid_links)
        print(f"✅ Processing complete")
        
        return jsonify(result)
        
    except Exception as e:
        print(f"❌ API Error: {str(e)}")
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500

@app.route('/extract-single', methods=['POST'])
def extract_single():
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
        
        url = data.get('url', '').strip()
        
        if not url:
            return jsonify({"error": "No URL provided"}), 400
        
        print(f"📥 Processing single URL: {url}")
        
        # Process single URL
        platform = extractor.detect_platform(url)
        
        processors = {
            'x': extractor.fetch_x_metrics,
            'youtube': extractor.fetch_youtube_metrics,
            'tiktok': extractor.fetch_tiktok_metrics,
            'stockbit': extractor.fetch_stockbit_metrics, 
            'instagram': extractor.fetch_instagram_metrics,
            'linkedin': extractor.fetch_linkedin_metrics
        }
        
        if platform in processors:
            result = processors[platform](url)
        else:
            result = {
                "date": None, "url": url, "author": None, "content": None,
                "followers": None, "views": None, "likes": None, "comments": None,
                "saves": None, "shares": None, "reposts": None, "platform": "unknown",
                "error": "Unsupported platform"
            }
        
        print(f" Single URL processing complete")
        return jsonify({"result": result})
        
    except Exception as e:
        print(f" Single URL Error: {str(e)}")
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"Starting Social Media API Server on port {port}...")
    app.run(host='0.0.0.0', port=port, debug=False)
