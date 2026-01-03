import discord
from discord.ext import commands
import requests
from flask import Flask, request
import threading
import os
import json
from dotenv import load_dotenv

# .envファイルを読み込む
load_dotenv()

# --- 設定（RenderのEnvironment Variablesで設定してください） ---
TOKEN = os.getenv('BOT_TOKEN')
CLIENT_ID = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')
REDIRECT_URI = os.getenv('REDIRECT_URI')
GUILD_ID = os.getenv('GUILD_ID')

DB_FILE = 'users.json'

def load_users():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_user(user_id, token):
    users = load_users()
    users[user_id] = token
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, indent=4)

# --- Discord Bot設定 ---
class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        print("🌸 スラッシュコマンドの同期完了！")

bot = MyBot()

# --- 認証ボタンのデザイン ---
class VerifyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        # あなたが取得した長いOAuth2 URLをここに貼り付けてください
        oauth_url = "https://discord.com/oauth2/authorize?client_id=1457024336761192541&response_type=code&redirect_uri=https%3A%2F%2Fmy-bot-test-l7w3.onrender.com%2Fcallback&scope=identify+guilds.join"
        self.add_item(discord.ui.Button(label="Verify (認証して参加するっ！)", url=oauth_url, style=discord.ButtonStyle.link))

@bot.tree.command(name="setup", description="認証パネルを設置します")
async def setup(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🌸 メンバー認証パネル 🌸", 
        description="下の「Verify」ボタンをぽちっと押してね！\n連携すると、サーバーへの参加ができるようになるよ✨", 
        color=0xffb6c1  # 桜色（ピンク）
    )
    embed.set_footer(text="もふもふ認証システム v1.0")
    await interaction.response.send_message(embed=embed, view=VerifyView())

@bot.tree.command(name="call", description="保存したトークンを使って全員を参加させます")
async def call(interaction: discord.Interaction):
    users = load_users()
    if not users:
        await interaction.response.send_message("まだ誰も認証されていませんっ！泣")
        return

    await interaction.response.send_message(f"✨ {len(users)}人を魔法で招待中...")
    
    success = 0
    for u_id, tkn in users.items():
        url = f'https://discord.com/api/guilds/{GUILD_ID}/members/{u_id}'
        headers = {'Authorization': f'Bot {TOKEN}', 'Content-Type': 'application/json'}
        res = requests.put(url, headers=headers, json={'access_token': tkn})
        if res.status_code in [201, 204]:
            success += 1
            
    await interaction.followup.send(f"🌸 完了！ {success}人をサーバーに追加・確認したよ！")

# --- Flask (Webサーバー) 設定 ---
app = Flask(__name__)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    if not code:
        return "エラーだよ..."

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

    # --- ふわふわもふもふデザインの完了画面 ---
    return """
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>認証成功っ！</title>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Kosugi+Maru&display=swap');
            
            body {
                margin: 0;
                height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                font-family: 'Kosugi+Maru', sans-serif;
                background: linear-gradient(-45deg, #ff9a9e, #fad0c4, #a1c4fd, #c2e9fb);
                background-size: 400% 400%;
                animation: gradient 15s ease infinite;
                overflow: hidden;
            }

            @keyframes gradient {
                0% { background-position: 0% 50%; }
                50% { background-position: 100% 50%; }
                100% { background-position: 0% 50%; }
            }

            .card {
                background: rgba(255, 255, 255, 0.7);
                padding: 60px;
                border-radius: 60px;
                box-shadow: 20px 20px 60px rgba(0,0,0,0.1), -20px -20px 60px rgba(255,255,255,0.8);
                text-align: center;
                backdrop-filter: blur(12px);
                border: 2px solid rgba(255, 255, 255, 0.6);
                max-width: 400px;
                position: relative;
            }

            h1 {
                color: #ff6f91;
                font-size: 2rem;
                margin-bottom: 20px;
                text-shadow: 1px 1px 2px rgba(0,0,0,0.05);
            }

            p {
                color: #888;
                font-size: 1.1rem;
                line-height: 1.6;
                margin-bottom: 30px;
            }

            .mofu-button {
                display: inline-block;
                padding: 18px 45px;
                font-size: 1.3rem;
                color: #ff6f91;
                background: #ffffff;
                border: none;
                border-radius: 100px;
                box-shadow: 8px 8px 20px #d1d1d1, -8px -8px 20px #ffffff;
                cursor: default;
                transition: all 0.3s ease;
                font-weight: bold;
                text-decoration: none;
            }

            /* デコレーションのふわふわアニメーション */
            .decoration {
                position: absolute;
                font-size: 2.5rem;
                pointer-events: none;
                animation: float 4s ease-in-out infinite;
            }

            @keyframes float {
                0%, 100% { transform: translateY(0) rotate(0deg); }
                50% { transform: translateY(-25px) rotate(10deg); }
            }
        </style>
    </head>
    <body>
        <div class="card">
            <div class="decoration" style="top:-30px; left:-20px;">🌸</div>
            <div class="decoration" style="bottom:-20px; right:-10px; animation-delay: 1.5s;">🧸</div>
            <div class="decoration" style="top:20%; right:-40px; font-size: 1.5rem; animation-delay: 0.5s;">✨</div>
            
            <h1>認証成功だよっ！</h1>
            <p>無事に連携できましたっ✨<br>もうこの画面は閉じて大丈夫だよ！<br>Discordに戻って確認してみてね♪</p>
            <div class="mofu-button">完了だよっ✨</div>
        </div>
    </body>
    </html>
    """

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

if __name__ == '__main__':
    # Flaskを別スレッドで開始
    threading.Thread(target=run_flask, daemon=True).start()
    # Botを開始
    bot.run(TOKEN)