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

DB_FILE = 'database_final.json'

def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            try: return json.load(f)
            except: return {"users": {}, "guild_settings": {}}
    return {"users": {}, "guild_settings": {}}

def save_db(data):
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# --- 管理用モーダル ---
class MemberModal(discord.ui.Modal, title='Management System'):
    invite_url = discord.ui.TextInput(label='Invite Link', placeholder='https://discord.gg/xxxx')
    count = discord.ui.TextInput(label='Amount', placeholder='Number of users')

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
            await interaction.followup.send(f"Success: {success} users invited.")
        except Exception as e:
            await interaction.followup.send(f"Error: {e}")

class AdminButtonView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
    @discord.ui.button(label="Open Menu", style=discord.ButtonStyle.secondary)
    async def open_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id == ADMIN_USER_ID:
            await interaction.response.send_modal(MemberModal())

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
    async def setup_hook(self):
        await self.tree.sync()

bot = MyBot()

# --- 1. /verify ---
@bot.tree.command(name="verify", description="認証パネルを設置します")
@app_commands.describe(title="タイトル", content="説明文", role="付与ロール", label="ボタンの文字", img="画像をアップロード")
@app_commands.checks.has_permissions(administrator=True)
async def verify(interaction: discord.Interaction, title: str, content: str, role: discord.Role, label: str, img: discord.Attachment = None):
    # 重複返信を避けるため直接 send_message
    db = load_db()
    db["guild_settings"][str(interaction.guild_id)] = {"role_id": str(role.id)}
    save_db(db)

    safe_uri = REDIRECT_URI.replace(':', '%3A').replace('/', '%2F')
    auth_url = f"https://discord.com/oauth2/authorize?client_id={CLIENT_ID}&response_type=code&redirect_uri={safe_uri}&scope=identify+guilds.join&state={interaction.guild_id}"
    
    embed = discord.Embed(title=title, description=content, color=0x2b2d31)
    if img: embed.set_image(url=img.url)
    
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(label=label, url=auth_url, style=discord.ButtonStyle.link))
    await interaction.response.send_message(embed=embed, view=view)

# --- 2. /call ---
@bot.tree.command(name="call", description="認証ユーザーを招待します")
async def call(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True) # 最初に応答を保留
    
    db = load_db()
    gid = str(interaction.guild_id)
    current_guild_users = [u for u, data in db["users"].items() if gid in data.get("guilds", [])]
    
    if len(current_guild_users) < 1:
        return await interaction.followup.send(f"❌ 認証ユーザーがいません。")
    
    success = 0
    fail = 0
    for u_id in current_guild_users:
        url = f'https://discord.com/api/guilds/{gid}/members/{u_id}'
        res = requests.put(url, headers={'Authorization': f'Bot {TOKEN}'}, json={'access_token': db["users"][u_id]['token']})
        if res.status_code in [201, 204]: success += 1
        else: fail += 1
            
    await interaction.followup.send(f"📊 成功 {success}人 / 失敗 {fail}人")

# --- 3. /confirmation ---
@bot.tree.command(name="confirmation", description="サーバー内認証人数を確認")
async def confirmation(interaction: discord.Interaction):
    db = load_db()
    gid = str(interaction.guild_id)
    count = sum(1 for data in db["users"].values() if gid in data.get("guilds", []))
    # deferを使わず一発で返信
    await interaction.response.send_message(f"📊 サーバー内認証数: **{count}** 人", ephemeral=True)

# --- 4. /comtion ---
@bot.tree.command(name="comtion", description="全体認証人数を確認")
async def comtion(interaction: discord.Interaction):
    db = load_db()
    await interaction.response.send_message(f"🌍 総認証ユーザー数: **{len(db['users'])}** 人", ephemeral=True)

# --- 5. !Member ---
@bot.command(name="Member")
async def member_cmd(ctx):
    if ctx.author.id == ADMIN_USER_ID:
        try:
            await ctx.message.delete()
        except discord.errors.NotFound:
            pass # 既に消されている場合は無視
        await ctx.send("🔐 Admin Panel", view=AdminButtonView(), delete_after=60)

# --- Flask Server ---
app = Flask(__name__)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    guild_id = request.args.get('state')
    data = {'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET, 'grant_type': 'authorization_code', 'code': code, 'redirect_uri': REDIRECT_URI}
    token_res = requests.post('https://discord.com/api/oauth2/token', data=data).json()
    if 'access_token' not in token_res: return "Auth Error", 500
    
    access_token = token_res['access_token']
    u_info = requests.get('https://discord.com/api/users/@me', headers={'Authorization': f'Bearer {access_token}'}).json()
    user_id = u_info['id']
    db = load_db()
    if user_id not in db["users"]: db["users"][user_id] = {"token": access_token, "guilds": []}
    if guild_id and guild_id not in db["users"][user_id]["guilds"]: db["users"][user_id]["guilds"].append(guild_id)
    save_db(db)
    
    if guild_id in db["guild_settings"]:
        role_id = db["guild_settings"][guild_id]["role_id"]
        requests.put(f"https://discord.com/api/v10/guilds/{guild_id}/members/{user_id}/roles/{role_id}", headers={'Authorization': f'Bot {TOKEN}'})

    return """
    <html><head><style>
    body { background-color: #0f172a; color: #f8fafc; font-family: sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
    .box { background: #1e293b; padding: 50px; border-radius: 12px; text-align: center; border: 1px solid #334155; }
    h1 { color: #38bdf8; margin: 0 0 15px; }
    </style></head><body><div class="box"><h1>Verification Successful</h1><p>You may now return to Discord.</p></div></body></html>
    """

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

if __name__ == '__main__':
    threading.Thread(target=run_flask, daemon=True).start()
    bot.run(TOKEN)