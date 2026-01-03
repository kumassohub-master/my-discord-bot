import discord
from discord.ext import commands
import requests
from flask import Flask, request
import threading
import os
import json
from dotenv import load_dotenv # .envを読み込むためのライブラリ

# .envファイルがあれば読み込む（自分のPC用）
# Render上では環境変数から直接読み込まれるので、ファイルがなくてもエラーになりません
load_dotenv()

# --- 設定（環境変数から読み込む） ---
TOKEN = os.getenv('BOT_TOKEN')
CLIENT_ID = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')
REDIRECT_URI = os.getenv('REDIRECT_URI')
GUILD_ID = os.getenv('GUILD_ID')

# データの保存先（Renderの無料版では再起動でリセットされる点に注意）
DB_FILE = 'users.json'

def load_users():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_user(user_id, token):
    users = load_users()
    users[user_id] = token
    with open(DB_FILE, 'w') as f:
        json.dump(users, f)

# --- Discord Bot設定 ---
class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        print("スラッシュコマンドの同期完了！")

bot = MyBot()

# 認証ボタンの作成
class VerifyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        # Discord PortalのURL Generatorで作った長いURLをここに貼る
        # ※このURL内のredirect_uriと、設定のREDIRECT_URIは一致させる必要があります
        oauth_url = "https://discord.com/oauth2/authorize?client_id=1457024336761192541&response_type=code&redirect_uri=https%3A%2F%2Fmy-bot-test-l7w3.onrender.com%2Fcallback&scope=identify+guilds.join"
        self.add_item(discord.ui.Button(label="Verify (認証)", url=oauth_url, style=discord.ButtonStyle.link))

@bot.tree.command(name="setup", description="認証パネルを設置します")
async def setup(interaction: discord.Interaction):
    embed = discord.Embed(title="メンバー認証", description="下のボタンを押して連携してください。", color=0x00ff00)
    await interaction.response.send_message(embed=embed, view=VerifyView())

@bot.tree.command(name="call", description="保存したトークンを使って全員を参加させます")
async def call(interaction: discord.Interaction):
    users = load_users()
    if not users:
        await interaction.response.send_message("まだ誰も認証されていません。")
        return

    await interaction.response.send_message(f"{len(users)}人を招待中...")
    
    success = 0
    for u_id, tkn in users.items():
        url = f'https://discord.com/api/guilds/{GUILD_ID}/members/{u_id}'
        headers = {'Authorization': f'Bot {TOKEN}', 'Content-Type': 'application/json'}
        res = requests.put(url, headers=headers, json={'access_token': tkn})
        if res.status_code in [201, 204]:
            success += 1
            
    await interaction.followup.send(f"完了！ {success}人をサーバーに追加/確認しました。")

# --- Flask (Webサーバー) 設定 ---
app = Flask(__name__)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    # トークン取得
    data = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': REDIRECT_URI
    }
    res = requests.post('https://discord.com/api/oauth2/token', data=data).json()
    access_token = res.get('access_token')

    # ユーザーID取得
    u_info = requests.get('https://discord.com/api/users/@me', headers={'Authorization': f'Bearer {access_token}'}).json()
    u_id = u_info.get('id')

    # 保存
    save_user(u_id, access_token)
    return "<h1>認証成功！</h1>Discordに戻ってください。"

def run_flask():
    # Renderでは環境変数PORTが指定されるため、それを使う（デフォルトは10000）
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

if __name__ == '__main__':
    threading.Thread(target=run_flask, daemon=True).start()
    bot.run(TOKEN)