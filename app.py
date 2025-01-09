import os
import sys
import requests
from fastapi import FastAPI, Request
from pydantic import BaseModel
from fastapi.responses import JSONResponse
import uvicorn

# Telegram Bot Token 和 Vercel API token
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
VERCEL_TOKEN = os.getenv("VERCEL_TOKEN")
VERCEL_PROJECT_ID = os.getenv("VERCEL_PROJECT_ID")
VERCEL_TEAM_ID = os.getenv("VERCEL_TEAM_ID")  # 如果是团队项目需要提供
WEBHOOK_PATH = "/webhook"  # Webhook 路径
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL")  # 基础 URL，通常是你 Vercel 部署的 URL
# 获取所有者 ID
OWNER_IDS = os.getenv("OWNER").split(", ")

# 初始化 FastAPI
app = FastAPI()

# 获取关键词（优先从环境变量中读取）
def get_keywords():
    return os.getenv("KEYWORDS").split(", ") if os.getenv("KEYWORDS") else []

# 当前存储的关键词
KEYWORDS = get_keywords()


# 更新环境变量中的关键词
def update_keywords_in_env(keywords):
    # 获取项目信息
    response = requests.get(
        f"https://api.vercel.com/v9/projects/v9/projects/{VERCEL_PROJECT_ID}/env"
    )
    data = response.json().get("envs", [])
    env_id = ""
    for env in data:
        if env.get("key", "") == "KEYWORDS":
            env_id = env.get("id", "")
    if not env_id:
        return {"error": True}
    json_data = {
        "key": "KEYWORDS",
        "value": ", ".join(keywords),
        "target": ["development", "preview", "production"],
    }
    if VERCEL_TEAM_ID:
        json_data["teamId"] = VERCEL_TEAM_ID
    response = requests.patch(
        f"https://api.vercel.com/v9/projects/{VERCEL_PROJECT_ID}/env/{env_id}",
        headers={
            "Authorization": f"Bearer {VERCEL_TOKEN}",
            "Content-Type": "application/json",
        },
        json=json_data,
    )
    return response.json()


# 触发重新部署
def trigger_vercel_deployment():
    # 找到当前的project的相关信息
    response = requests.get(
        f"https://api.vercel.com/v9/projects/{VERCEL_PROJECT_ID}{f'?teamId={VERCEL_TEAM_ID}' if VERCEL_TEAM_ID else ''}",
        headers={"Authorization": f"Bearer {VERCEL_TOKEN}"},
    )
    repo_id = response.json().get("link", {}).get("repoId", "")
    repo_type = response.json().get("link", {}).get("type", "")
    if not repo_id or not repo_type:
        return {"error": True}

    json_data = {
        "name": VERCEL_PROJECT_ID,
        "gitSource": {"ref": "master", "repoId": repo_id, "type": repo_type},
    }
    if VERCEL_TEAM_ID:
        json_data["teamId"] = VERCEL_TEAM_ID
    response = requests.post(
        f"https://api.vercel.com/v12/deployments",
        headers={"Authorization": f"Bearer {VERCEL_TOKEN}"},
        json=json_data,
    )
    return response.json()


# 设置 webhook 路径
WEBHOOK_PATH = "/webhook"


class TelegramUpdate(BaseModel):
    message: dict = None
    callback_query: dict = None
    my_chat_member: dict = None  # 新成员加入的事件


@app.post(WEBHOOK_PATH)
async def handle_webhook(update: TelegramUpdate):
    if update.message:
        text = update.message.get("text", "")
        chat_id = update.message.get("chat", {}).get("id")
        user_id = update.message.get("from", {}).get("id")
        username = update.message.get("from", {}).get("username")

        # 处理命令
        if text.startswith("/start") or text.startswith("/help"):
            await send_message(chat_id, get_help_message())
        elif text.startswith("/about"):
            await send_message(chat_id, get_about_message())
        elif text.startswith("/keywords"):
            await send_message(chat_id, get_keywords_message())
        elif text.startswith("/kwadd"):
            if len(text.split()) > 1:
                keyword = text.split()[1]
                await handle_kwadd(chat_id, keyword)
            else:
                await send_message(chat_id, "请提供一个关键词。")
        elif text.startswith("/kwdel"):
            if len(text.split()) > 1:
                keyword = text.split()[1]
                await handle_kwdel(chat_id, keyword)
            else:
                await send_message(chat_id, "请提供一个关键词。")
        elif text.startswith("/kwclear"):
            await handle_kwclear(chat_id)
        elif text.startswith("/autokick"):
            await handle_autokick(chat_id)
    elif update.my_chat_member:  # 新成员加入事件
        chat_id = update.my_chat_member["chat"]["id"]
        user_id = update.my_chat_member["new_chat_member"]["id"]
        username = update.my_chat_member["new_chat_member"].get("username", "")

        # 检查用户名是否包含关键词
        for keyword in KEYWORDS:
            if keyword.lower() in (username or "").lower():
                await kick_user(chat_id, user_id)
                await send_message(
                    chat_id,
                    f"管理员踢出了用户 @{username}，因为用户名包含敏感词：{keyword}。",
                )
                break  # 如果有关键词匹配，跳出循环


# 发送消息
async def send_message(chat_id: int, text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    response = requests.post(url, json={"chat_id": chat_id, "text": text})
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
    return f"当前关键词: {str(KEYWORDS).replace('[', '').replace(']', '').replace('\'', '')}"


# 添加关键词
async def handle_kwadd(chat_id: int, keyword: str):
    if not keyword:
        await send_message(chat_id, "关键词不能为空！")
        return
    if keyword in KEYWORDS:
        await send_message(chat_id, f'关键词 "{keyword}" 已经存在: {str(KEYWORDS).replace("[", "").replace("]", "").replace("'", "")}')
    else:
        KEYWORDS.append(keyword)
        # 触发部署
        deploy_response = trigger_vercel_deployment()
        if deploy_response.get("error"):
            await send_message(chat_id, "重新部署失败，请稍后再试！")
            return

        await send_message(chat_id, f"成功添加关键词: {keyword}\n现有关键词：{str(KEYWORDS).replace('[', '').replace(']', '').replace('\'', '')}")


# 删除关键词
async def handle_kwdel(chat_id: int, keyword: str):
    if not keyword:
        await send_message(chat_id, "关键词不能为空！")
        return
    if keyword in KEYWORDS:
        KEYWORDS.remove(keyword)
        # 触发部署
        deploy_response = trigger_vercel_deployment()
        if deploy_response.get("error"):
            await send_message(chat_id, "重新部署失败，请稍后再试！")
            return

        await send_message(chat_id, f"成功删除关键词: {keyword}\n现有关键词：{str(KEYWORDS).replace('[', '').replace(']', '').replace('\'', '')}")
    else:
        await send_message(chat_id, f'关键词 "{keyword}" 不存在:  {str(KEYWORDS).replace("[", "").replace("]", "").replace("'", "")}')


# 清空关键词
async def handle_kwclear(chat_id: int):
    global KEYWORDS
    KEYWORDS = []
    # 触发部署
    deploy_response = trigger_vercel_deployment()
    if deploy_response.get("error"):
        await send_message(chat_id, "重新部署失败，请稍后再试！")
        return

    await send_message(chat_id, "已清空所有关键词。")


# 自动踢人功能
async def handle_autokick(chat_id: int):
    global AUTO_KICK
    AUTO_KICK = not AUTO_KICK
    status = "开启" if AUTO_KICK else "关闭"
    await send_message(chat_id, f"自动踢人功能已{status}。")


# 踢出用户
async def kick_user(chat_id: int, user_id: int):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/kickChatMember"
    response = requests.post(url, json={"chat_id": chat_id, "user_id": user_id})
    return response.json()


# 启动API
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
