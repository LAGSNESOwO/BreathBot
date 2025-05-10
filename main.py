import os
import logging
import json
import time
import requests
import threading
import concurrent.futures
from collections import defaultdict, deque
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables from .env file (if present)
load_dotenv()

# Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "Your_Key_In_Here")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
# 可使用免费的 BreathAI API
AI_API_URL = os.getenv("AI_API_URL", "https://chat.breathai.top/v1/chat/completions")
AI_API_KEY = os.getenv("AI_API_KEY", "Your_Key_In_Here")
AI_MODEL = os.getenv("AI_MODEL", "grok-3-mini-beta")

# 消息速率限制配置
RATE_LIMIT_10S = 5    # 10秒内最多5条消息
RATE_LIMIT_1MIN = 30  # 1分钟内最多30条消息
RATE_LIMIT_1HOUR = 100 # 1小时内最多100条消息

# System prompt that instructs the AI how to respond
SYSTEM_PROMPT = """你是 BreathAI Bot，一个友善的 AI 助手"""

# Setup logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# 全局变量
conversation_history = {}  # 存储用户对话历史
user_message_timestamps = defaultdict(lambda: {"10s": deque(), "1min": deque(), "1hour": deque()})  # 存储用户消息时间戳
message_lock = threading.Lock()  # 用于线程安全地访问全局变量

def send_message(chat_id, text, reply_to_message_id=None, parse_mode=None):
    """Send a message to a Telegram chat."""
    url = f"{TELEGRAM_API_URL}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": text
    }
    
    if reply_to_message_id:
        data["reply_to_message_id"] = reply_to_message_id
        
    if parse_mode:
        data["parse_mode"] = parse_mode
        
    logger.info(f"发送消息到用户 {chat_id}: {text[:30]}...")
    response = requests.post(url, data=data)
    return response.json()

def edit_message(chat_id, message_id, text, parse_mode=None):
    """Edit a message in a Telegram chat."""
    url = f"{TELEGRAM_API_URL}/editMessageText"
    data = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text
    }
    
    if parse_mode:
        data["parse_mode"] = parse_mode
    
    logger.info(f"更新消息 {message_id} 到用户 {chat_id}: {text[:30]}...")    
    response = requests.post(url, data=data)
    return response.json()

def send_chat_action(chat_id, action="typing"):
    """Send a chat action to a Telegram chat."""
    url = f"{TELEGRAM_API_URL}/sendChatAction"
    data = {
        "chat_id": chat_id,
        "action": action
    }
    
    logger.info(f"发送动作 '{action}' 到用户 {chat_id}")
    response = requests.post(url, data=data)
    return response.json()

def check_rate_limit(user_id):
    """检查用户是否超过消息速率限制，并清理过期时间戳"""
    now = datetime.now()
    timestamps = user_message_timestamps[user_id]
    
    # 清理过期的时间戳
    while timestamps["10s"] and (now - timestamps["10s"][0]).total_seconds() > 10:
        timestamps["10s"].popleft()
    while timestamps["1min"] and (now - timestamps["1min"][0]).total_seconds() > 60:
        timestamps["1min"].popleft()
    while timestamps["1hour"] and (now - timestamps["1hour"][0]).total_seconds() > 3600:
        timestamps["1hour"].popleft()
    
    # 检查是否超过限制
    if len(timestamps["10s"]) >= RATE_LIMIT_10S:
        wait_time = 10 - (now - timestamps["10s"][0]).total_seconds()
        return False, f"你他妈发的这么快！休息一下，{int(wait_time)}秒后再发！"
    
    if len(timestamps["1min"]) >= RATE_LIMIT_1MIN:
        wait_time = 60 - (now - timestamps["1min"][0]).total_seconds()
        return False, f"你他妈发的这么快！休息一下，{int(wait_time)}秒后再发！"
    
    if len(timestamps["1hour"]) >= RATE_LIMIT_1HOUR:
        wait_time = 3600 - (now - timestamps["1hour"][0]).total_seconds()
        minutes = int(wait_time // 60)
        seconds = int(wait_time % 60)
        return False, f"你他妈发的太多了！休息一下，{minutes}分{seconds}秒后再发！"
    
    # 记录新的时间戳
    timestamps["10s"].append(now)
    timestamps["1min"].append(now)
    timestamps["1hour"].append(now)
    
    return True, ""

def handle_start_command(chat_id, user_id, username):
    """Handle /start command."""
    message = f"你好 {username}！我是由 Grok 驱动的 AI 助手。有什么我可以帮助你的吗？"
    with message_lock:
        conversation_history[user_id] = []
    logger.info(f"用户 {user_id} ({username}) 启动了机器人")
    send_message(chat_id, message)

def handle_clear_command(chat_id, user_id, username):
    """Handle /clear command."""
    with message_lock:
        conversation_history[user_id] = []
    logger.info(f"用户 {user_id} ({username}) 清除了对话历史")
    send_message(chat_id, "你的对话历史已被清除。")

def handle_message(chat_id, user_id, username, text):
    """Handle regular messages."""
    logger.info(f"收到来自用户 {user_id} ({username}) 的消息: {text}")
    
    # 检查消息速率限制
    with message_lock:
        allowed, error_message = check_rate_limit(user_id)
    
    if not allowed:
        logger.warning(f"用户 {user_id} 超过消息速率限制: {error_message}")
        send_message(chat_id, error_message)
        return
    
    # 立即发送"正在思考..."消息，不等待API响应
    response = send_message(chat_id, "正在思考...")
    response_message_id = response["result"]["message_id"]
    
    # Initialize conversation history for new users
    with message_lock:
        if user_id not in conversation_history:
            conversation_history[user_id] = []
        
        # Add user message to history
        conversation_history[user_id].append({"role": "user", "content": text})
        
        # Create messages array with system prompt and conversation history
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(conversation_history[user_id])
    
    try:
        # Send typing action
        send_chat_action(chat_id)
        
        # Make API request with stream=True
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {AI_API_KEY}"
        }
        
        payload = {
            "model": AI_MODEL,
            "messages": messages,
            "stream": True
        }
        
        logger.info(f"向 BreathAI API 发送请求，模型: {AI_MODEL}, 用户: {user_id}")
        logger.info(f"请求内容: {json.dumps(messages)[:200]}...")
        
        # Use requests to make a streaming request
        with requests.post(AI_API_URL, json=payload, headers=headers, stream=True) as response:
            if response.status_code != 200:
                error_msg = f"错误: API 返回状态码 {response.status_code}"
                logger.error(f"API请求失败: {error_msg}")
                edit_message(
                    chat_id,
                    response_message_id,
                    error_msg
                )
                return
                
            logger.info(f"开始接收来自 BreathAI API 的流式响应")
            
            # Process the streaming response
            collected_content = ""
            update_counter = 0
            
            # Read the stream line by line
            for line in response.iter_lines():
                if line:
                    line = line.decode('utf-8')
                    
                    # Skip empty lines and data: prefix
                    if line.startswith("data: "):
                        data = line[6:]
                        
                        # Check for [DONE] signal
                        if data == "[DONE]":
                            logger.info("收到API响应结束信号 [DONE]")
                            break
                            
                        try:
                            json_data = json.loads(data)
                            if 'choices' in json_data and len(json_data['choices']) > 0:
                                delta = json_data['choices'][0].get('delta', {})
                                content = delta.get('content', '')
                                if content:
                                    collected_content += content
                                    update_counter += 1
                                    
                                    # Update the message periodically to show progress
                                    if update_counter % 10 == 0 and collected_content:
                                        try:
                                            edit_message(
                                                chat_id,
                                                response_message_id,
                                                collected_content
                                            )
                                        except Exception as e:
                                            logger.error(f"更新消息时出错: {e}")
                        except json.JSONDecodeError:
                            logger.error(f"解析JSON失败: {data}")
            
            # Send the final response
            if collected_content:
                logger.info(f"完整响应接收完毕，长度: {len(collected_content)} 字符")
                try:
                    edit_message(
                        chat_id,
                        response_message_id,
                        collected_content,
                        parse_mode="HTML"
                    )
                    
                    # Add the assistant's response to the conversation history
                    with message_lock:
                        conversation_history[user_id].append({
                            "role": "assistant", 
                            "content": collected_content
                        })
                    logger.info(f"已将响应添加到用户 {user_id} 的对话历史中")
                except Exception as e:
                    logger.error(f"更新最终消息时出错: {e}")
            else:
                logger.warning(f"未从API收到任何内容")
                edit_message(
                    chat_id,
                    response_message_id,
                    "抱歉，我无法生成回复。"
                )
                
    except Exception as e:
        logger.error(f"处理消息时出错: {e}")
        send_message(
            chat_id,
            "抱歉，处理您的请求时出现了问题。请稍后再试。"
        )

def process_update(update):
    """处理单个更新，用于并发执行"""
    try:
        if "message" not in update:
            return
            
        message = update["message"]
        
        # Skip messages without text
        if "text" not in message:
            return
            
        chat_id = message["chat"]["id"]
        user_id = message["from"]["id"]
        username = message["from"].get("first_name", "用户")
        text = message["text"]
        
        # Handle commands
        if text.startswith("/start"):
            handle_start_command(chat_id, user_id, username)
        elif text.startswith("/clear"):
            handle_clear_command(chat_id, user_id, username)
        else:
            handle_message(chat_id, user_id, username, text)
    except Exception as e:
        logger.error(f"处理更新时出错: {e}")

def get_updates(offset=None):
    """Get updates from Telegram."""
    url = f"{TELEGRAM_API_URL}/getUpdates"
    data = {"timeout": 30}
    if offset:
        data["offset"] = offset
    response = requests.post(url, data=data)
    return response.json()

def main():
    """Run the bot."""
    logger.info("启动机器人，支持并发处理和消息速率限制...")
    offset = None
    
    # 创建一个线程池用于并发处理消息
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        while True:
            try:
                updates = get_updates(offset)
                
                if "result" in updates and updates["result"]:
                    # 获取最新的update_id用于下次轮询
                    offset = max(update["update_id"] for update in updates["result"]) + 1
                    
                    # 并发处理所有更新
                    futures = [executor.submit(process_update, update) for update in updates["result"]]
                    # 等待所有任务完成（可选，取决于是否需要确保顺序处理）
                    # concurrent.futures.wait(futures)
                    
            except Exception as e:
                logger.error(f"获取更新时出错: {e}")
                time.sleep(5)
                continue

if __name__ == "__main__":
    main() 