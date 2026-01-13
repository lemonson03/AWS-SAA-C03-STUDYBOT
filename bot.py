import os
import discord
from discord.ext import commands, tasks
from discord import app_commands
from dotenv import load_dotenv
from datetime import date, datetime, timedelta
import db

# .env 파일 로드
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", "0"))
ALLOWED_CHANNEL = "aws-saa-c03"

# Discord Intents 설정
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

class AlgoBot(commands.Bot):
    def __init__(self):
        # ✅ 여기서 command_prefix를 명시해야 에러가 나지 않습니다.
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        """봇 시작 시 슬래시 명령어 동기화"""
        db.init_db()
        if GUILD_ID:
            guild_obj = discord.Object(id=GUILD_ID)
            self.tree.copy_global_to(guild=guild_obj)
            synced = await self.tree.sync(guild=guild_obj)
            print(f"✅ Guild Sync 완료: {len(synced)}개 명령어")
        else:
            await self.tree.sync()
            print("✅ Global Sync 완료")

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """지정된 채널에서만 명령어 작동"""
        if interaction.channel.name != ALLOWED_CHANNEL:
            await interaction.response.send_message(f"❌ `{ALLOWED_CHANNEL}` 채널에서만 가능합니다.", ephemeral=True)
            return False
        return True

# 봇 객체 생성
bot = AlgoBot()

@bot.event
async def on_ready():
    print(f"🤖 봇 로그인 완료: {bot.user}")

# =========================
# 슬래시 명령어들
# =========================

@bot.tree.command(name="sync", description="(개발용) 명령어를 동기화합니다")
@app_commands.checks.has_permissions(administrator=True)
async def sync_slash(interaction: discord.Interaction):
    guild_obj = discord.Object(id=interaction.guild.id)
    synced = await bot.tree.sync(guild=guild_obj)
    await interaction.response.send_message(f"✅ {len(synced)}개 명령 동기화 완료", ephemeral=True)

@bot.tree.command(name="진도입력", description="현재 공부한 진도를 입력하세요 (예: 섹션 5, 문제 120)")
@app_commands.describe(progress="현재 어디까지 하셨나요?")
async def set_progress(interaction: discord.Interaction, progress: str):
    db.update_progress(interaction.user.id, progress)
    await interaction.response.send_message(f"✅ {interaction.user.mention}님의 진도가 `{progress}`(으)로 기록되었습니다!")

@bot.tree.command(name="랭킹", description="SAA 공부 진도 순위를 확인합니다")
async def show_saa_ranking(interaction: discord.Interaction):
    ranking = db.get_saa_ranking()
    goal = db.get_weekly_goal()
    
    embed = discord.Embed(title="🏆 SAA 스터디 진도 랭킹", color=0x3498db)
    embed.add_field(name="🚩 이번 주 목표", value=f"**{goal}**", inline=False)
    
    medals = ["🥇", "🥈", "🥉"]
    if not ranking:
        embed.description = "아직 등록된 진도가 없습니다."
    else:
        for idx, (uid, progress) in enumerate(ranking, 1):
            try:
                user = await bot.fetch_user(uid)
                name = user.display_name
            except:
                name = f"User({uid})"
            
            medal = medals[idx-1] if idx <= 3 else f"{idx}위"
            embed.add_field(name=f"{medal} {name}", value=f"현재: `{progress}`", inline=False)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="목표설정", description="(관리자) 이번 주 목표 분량을 설정합니다")
@app_commands.checks.has_permissions(administrator=True)
async def set_goal(interaction: discord.Interaction, goal: str):
    db.set_weekly_goal(goal)
    await interaction.response.send_message(f"📢 이번 주 목표가 **{goal}**(으)로 설정되었습니다!")

# 봇 실행
bot.run(TOKEN)