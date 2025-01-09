import os
import sys
import requests
from fastapi import FastAPI, Request
from pydantic import BaseModel
from fastapi.responses import JSONResponse

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
    if os.path.exists("keywords.txt"):
        with open("keywords.txt") as f:
            return f.read().split(", ")
    return os.getenv("KEYWORDS").split(", ") if os.getenv("KEYWORDS") else []

def save_keywords_to_file():
    with open("keywords.txt", "w") as f:
        f.write(str(KEYWORDS).replace("[", "").replace("]", ""))

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
        elif text.startswith("/savekeywords"):
            await save_keywords(chat_id, user_id)
        elif text.startswith("/readfile"):
            with open("keywords.txt", "r") as f:
                await send_message(chat_id, f.read())
    return JSONResponse({"status": "ok"})


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
    return f"当前关键词: {str(KEYWORDS).replace('[', '').replace(']', '')}"


# 添加关键词
async def handle_kwadd(chat_id: int, keyword: str):
    if not keyword:
        await send_message(chat_id, "关键词不能为空！")
        return
    if keyword in KEYWORDS:
        await send_message(chat_id, f'关键词 "{keyword}" 已经存在: {KEYWORDS}')
    else:
        KEYWORDS.append(keyword)
        save_keywords_to_file()
        await send_message(chat_id, f"成功添加关键词: {keyword}\n现有关键词：{KEYWORDS}")


# 删除关键词
async def handle_kwdel(chat_id: int, keyword: str):
    if not keyword:
        await send_message(chat_id, "关键词不能为空！")
        return
    if keyword in KEYWORDS:
        KEYWORDS.remove(keyword)
        save_keywords_to_file()
        await send_message(chat_id, f"成功删除关键词: {keyword}\n现有关键词：{KEYWORDS}")
    else:
        await send_message(chat_id, f'关键词 "{keyword}" 不存在: {KEYWORDS}')



# 清空关键词
async def handle_kwclear(chat_id: int):
    global KEYWORDS
    KEYWORDS = []
    save_keywords_to_file()
    await send_message(chat_id, "已清空所有关键词。")


# 自动踢人功能
async def handle_autokick(chat_id: int):
    autokick_enabled = os.getenv("AUTOKICK", "true") == "true"
    new_status = "false" if autokick_enabled else "true"
    os.environ["AUTOKICK"] = new_status
    await send_message(
        chat_id, f"自动踢人功能已{'启用' if new_status == 'true' else '禁用'}。"
    )


# 保存当前关键词到环境变量并触发 Vercel 部署
async def save_keywords(chat_id: int, user_id: int):
    # 检查用户是否是所有者
    if str(user_id) not in OWNER_IDS:
        await send_message(chat_id, "你没有权限执行此操作！")
        return

    update_response = update_keywords_in_env(KEYWORDS)

    if update_response.get("error"):
        await send_message(chat_id, "保存关键词失败，请稍后再试！")
        return

    # 触发重新部署
    deploy_response = trigger_vercel_deployment()

    if deploy_response.get("error"):
        await send_message(chat_id, "重新部署失败，请稍后再试！")
        return

    await send_message(
        chat_id,
        f"关键词已成功保存，并触发了 Vercel 重新部署！ 当前关键词: {', '.join(KEYWORDS)}",
    )


# 设置 Webhook 路由
@app.post("/setWebhook")
@app.get("/setWebhook")
async def set_webhook():
    if not WEBHOOK_BASE_URL:
        return JSONResponse(
            {"status": "error", "message": "未设置 WEBHOOK_BASE_URL 环境变量。"}
        )

    webhook_url = f"{WEBHOOK_BASE_URL}{WEBHOOK_PATH}"

    # 设置 Telegram Webhook
    set_webhook_url = (
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook?url={webhook_url}"
    )

    try:
        response = requests.get(set_webhook_url)
        result = response.json()

        if result.get("ok"):
            return JSONResponse({"status": "success", "message": "Webhook 设置成功！"})
        else:
            return JSONResponse(
                {
                    "status": "error",
                    "message": f"Webhook 设置失败: {result.get('description')}",
                }
            )
    except requests.exceptions.RequestException as e:
        return JSONResponse(
            {"status": "error", "message": f"设置 Webhook 时发生错误: {str(e)}"}
        )


# 启动 FastAPI 应用
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
