import os
import requests
from fastapi import FastAPI, Request
from pydantic import BaseModel
from fastapi.responses import JSONResponse

# Telegram Bot Token 和 Vercel API token
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
VERCEL_TOKEN = os.getenv('VERCEL_TOKEN')
VERCEL_PROJECT_ID = os.getenv('VERCEL_PROJECT_ID')
VERCEL_TEAM_ID = os.getenv('VERCEL_TEAM_ID')  # 如果是团队项目需要提供
WEBHOOK_PATH = '/webhook'  # Webhook 路径
WEBHOOK_BASE_URL = os.getenv('WEBHOOK_BASE_URL')  # 基础 URL，通常是你 Vercel 部署的 URL
OWNER_ID = os.getenv('OWNER')  # 所有者的 Telegram 用户 ID

# 初始化 FastAPI
app = FastAPI()

# 获取 KEYWORDS 环境变量并初始化
initial_keywords = os.getenv('KEYWORDS', '').split(',')
current_keywords = initial_keywords if initial_keywords else []

# 获取 Vercel环境变量 API URL
def get_vercel_env_url():
    return f"https://api.vercel.com/v6/projects/{VERCEL_PROJECT_ID}/env"

# 更新环境变量中的关键词
def update_keywords_in_env(keywords):
    response = requests.post(
        get_vercel_env_url(),
        headers={
            'Authorization': f"Bearer {VERCEL_TOKEN}",
            'Content-Type': 'application/json'
        },
        json={
            'key': 'KEYWORDS',
            'value': ','.join(keywords),
            'target': ['production'],
            'teamId': VERCEL_TEAM_ID
        }
    )
    return response.json()

# 触发重新部署
def trigger_vercel_deployment():
    response = requests.post(
        f"https://api.vercel.com/v12/deployments",
        headers={'Authorization': f"Bearer {VERCEL_TOKEN}"},
        json={
            'name': VERCEL_PROJECT_ID,
            'teamId': VERCEL_TEAM_ID,
            'gitSource': {
                'branch': 'main'  # 确保是你要部署的分支
            }
        }
    )
    return response.json()

# 获取当前的关键词
def get_keywords():
    return current_keywords

# 设置 webhook 路径
WEBHOOK_PATH = "/webhook"

class TelegramUpdate(BaseModel):
    message: dict = None
    callback_query: dict = None

@app.post(WEBHOOK_PATH)
async def handle_webhook(update: TelegramUpdate):
    if update.message:
        text = update.message.get("text", "")
        chat_id = update.message.get("chat", {}).get("id")
        user_id = update.message.get("from", {}).get("id")
        username = update.message.get("from", {}).get("username")

        # 只有所有者才有权限修改关键词等操作
        if user_id != int(OWNER_ID):
            await send_message(chat_id, "您没有权限执行此操作！")
            return JSONResponse({"status": "forbidden"})

        # 处理命令
        if text.startswith('/start') or text.startswith('/help'):
            await send_message(chat_id, get_help_message())
        elif text.startswith('/about'):
            await send_message(chat_id, get_about_message())
        elif text.startswith('/keywords'):
            await send_message(chat_id, get_keywords_message())
        elif text.startswith('/kwadd'):
            keyword = text[len('/kwadd '):].strip()
            if keyword:
                await handle_kwadd(chat_id, keyword)
            else:
                await send_message(chat_id, "请提供一个关键词。")
        elif text.startswith('/kwdel'):
            keyword = text[len('/kwdel '):].strip()
            if keyword:
                await handle_kwdel(chat_id, keyword)
            else:
                await send_message(chat_id, "请提供一个要删除的关键词。")
        elif text.startswith('/kwclear'):
            await handle_kwclear(chat_id)
        elif text.startswith('/autokick'):
            await handle_autokick(chat_id)
        elif text.startswith('/savekeywords'):
            await save_keywords(chat_id)

    return JSONResponse({"status": "ok"})

# 发送消息
async def send_message(chat_id: int, text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    response = requests.post(
        url,
        json={"chat_id": chat_id, "text": text}
    )
    return response.json()

# 获取帮助信息
def get_help_message():
    return """
/help - 显示帮助信息
/about - 显示机器人信息
/keywords - 显示关键词
/kwadd <关键词> - 添加关键词
/kwdel <关键词> - 删除关键词
/kwclear - 清空关键词
/autokick - 切换自动踢人功能状态
/savekeywords - 保存当前关键词到环境变量并触发 Vercel 部署
"""

# 获取关于信息
def get_about_message():
    return """
这是一个基于 FastAPI 和 Webhook 的群组管理机器人。
功能：
- 自动踢出用户名包含特定关键词的新成员。
- 管理员可以管理关键词。
- 监听特定群组的消息。

开发者: GamerNoTitle
"""

# 获取当前存储的关键词
def get_keywords_message():
    keywords = get_keywords()
    return f"当前关键词: {', '.join(keywords) if keywords else '无'}"

# 添加关键词
async def handle_kwadd(chat_id: int, keyword: str):
    keywords = get_keywords()
    if keyword in keywords:
        await send_message(chat_id, f"关键词 \"{keyword}\" 已经存在。")
    else:
        keywords.append(keyword)
        global current_keywords
        current_keywords = keywords
        await send_message(chat_id, f"成功添加关键词: {keyword}")

# 删除关键词
async def handle_kwdel(chat_id: int, keyword: str):
    keywords = get_keywords()
    if keyword in keywords:
        keywords.remove(keyword)
        global current_keywords
        current_keywords = keywords
        await send_message(chat_id, f"成功删除关键词: {keyword}")
    else:
        await send_message(chat_id, f"关键词 \"{keyword}\" 不存在。")

# 清空关键词
async def handle_kwclear(chat_id: int):
    global current_keywords
    current_keywords = []
    await send_message(chat_id, "已清空所有关键词。")

# 自动踢人功能
async def handle_autokick(chat_id: int):
    autokick_enabled = os.getenv('AUTOKICK', 'false') == 'true'
    new_status = 'false' if autokick_enabled else 'true'
    os.environ['AUTOKICK'] = new_status
    await send_message(chat_id, f"自动踢人功能已{'启用' if new_status == 'true' else '禁用'}。")

# 保存当前关键词到环境变量并触发 Vercel 部署
async def save_keywords(chat_id: int):
    update_response = update_keywords_in_env(current_keywords)
    
    if update_response.get('error'):
        await send_message(chat_id, '保存关键词失败，请稍后再试！')
        return
    
    deploy_response = trigger_vercel_deployment()
    
    if deploy_response.get('error'):
        await send_message(chat_id, '重新部署失败，请稍后再试！')
        return
    
    await send_message(chat_id, f"关键词已成功保存，并触发了 Vercel 重新部署！ 当前关键词: {', '.join(current_keywords)}")

# 更新关键词到环境变量
def update_keywords_in_env(keywords):
    response = requests.post(
        get_vercel_env_url(),
        headers={
            'Authorization': f"Bearer {VERCEL_TOKEN}",
            'Content-Type': 'application/json'
        },
        json={
            'key': 'KEYWORDS',
            'value': ','.join(keywords),
            'target': ['production'],
            'teamId': VERCEL_TEAM_ID
        }
    )
    return response.json()

# 触发重新部署
def trigger_vercel_deployment():
    response = requests.post(
        f"https://api.vercel.com/v12/deployments",
        headers={'Authorization': f"Bearer {VERCEL_TOKEN}"},
        json={
            'name': VERCEL_PROJECT_ID,
            'teamId': VERCEL_TEAM_ID,
            'gitSource': {
                'branch': 'master'
            }
        }
    )
    return response.json()

# 设置 Webhook 路由
@app.post("/setWebhook")
@app.get("/setWebhook")
async def set_webhook():
    if not WEBHOOK_BASE_URL:
        return JSONResponse({"status": "error", "message": "未设置 WEBHOOK_BASE_URL 环境变量。"})

    webhook_url = f"{WEBHOOK_BASE_URL}{WEBHOOK_PATH}"
    
    set_webhook_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook?url={webhook_url}"

    try:
        response = requests.get(set_webhook_url)
        result = response.json()

        if result.get("ok"):
            return JSONResponse({"status": "success", "message": "Webhook 设置成功！"})
        else:
            return JSONResponse({"status": "error", "message": f"Webhook 设置失败: {result.get('description')}"})
    except requests.exceptions.RequestException as e:
        return JSONResponse({"status": "error", "message": f"设置 Webhook 时发生错误: {str(e)}"})

# 启动 FastAPI 应用
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
