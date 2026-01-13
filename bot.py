# bot.py (주요 기능 위주)
import os
import discord
from discord.ext import commands, tasks  # ⬅️ 이 줄이 빠져있을 확률이 99%입니다!
from discord import app_commands
from dotenv import load_dotenv
from datetime import date, datetime, timedelta
import db
ALLOWED_CHANNEL = "aws-saa-c03"

class AlgoBot(commands.Bot):
    # ... 기존 setup_hook 유지 ...

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """지정된 채널에서만 명령어 작동"""
        if interaction.channel.name != ALLOWED_CHANNEL:
            await interaction.response.send_message(f"❌ `{ALLOWED_CHANNEL}` 채널에서만 가능합니다.", ephemeral=True)
            return False
        return True

bot = AlgoBot()

# =========================
# /진도입력 (String으로 받음)
# =========================
@bot.tree.command(name="진도입력", description="현재 공부한 진도를 입력하세요 (예: 섹션 5, 문제 120)")
@app_commands.describe(progress="현재 어디까지 하셨나요?")
async def set_progress(interaction: discord.Interaction, progress: str):
    db.update_progress(interaction.user.id, progress)
    await interaction.response.send_message(f"✅ {interaction.user.mention}님의 진도가 `{progress}`(으)로 기록되었습니다!")

# =========================
# /랭킹 (SAA 버전)
# =========================
@bot.tree.command(name="랭킹", description="SAA 공부 진도 순위를 확인합니다")
async def show_saa_ranking(interaction: discord.Interaction):
    ranking = db.get_saa_ranking()
    goal = db.get_weekly_goal()
    
    embed = discord.Embed(title="🏆 SAA 스터디 진도 랭킹", color=0x3498db)
    embed.add_field(name="🚩 이번 주 목표", value=f"**{goal}**", inline=False)
    
    medals = ["🥇", "🥈", "🥉"]
    for idx, (uid, progress) in enumerate(ranking, 1):
        try:
            user = await bot.fetch_user(uid)
            name = user.display_name
        except:
            name = "Unknown"
        
        medal = medals[idx-1] if idx <= 3 else f"{idx}위"
        embed.add_field(name=f"{medal} {name}", value=f"현재: `{progress}`", inline=False)
    
    await interaction.response.send_message(embed=embed)

# =========================
# /목표설정 (관리자용)
# =========================
@bot.tree.command(name="목표설정", description="(관리자) 이번 주 달성해야 할 목표 분량을 설정합니다")
@app_commands.checks.has_permissions(administrator=True)
async def set_goal(interaction: discord.Interaction, goal: str):
    db.set_weekly_goal(goal)
    await interaction.response.send_message(f"📢 이번 주 목표가 **{goal}** (으)로 설정되었습니다!\n미달성 시 벌금 1,000원이 부과됩니다.")

# =========================
# /벌금부과 (미달성자 일괄 부과 기능 예시)
# =========================
@bot.tree.command(name="미달성벌금", description="(관리자) 목표 미달성자들에게 벌금을 1,000원씩 부과합니다")
@app_commands.checks.has_permissions(administrator=True)
async def penalty_check(interaction: discord.Interaction):
    # 이 부분은 수동으로 체크하거나, 로직을 짜서 일괄 처리할 수 있습니다.
    # 여기서는 간단히 대상자를 선택해서 부과하는 기존 방식을 SAA용으로 설명만 드립니다.
    await interaction.response.send_message("미달성 인원을 확인하여 `/벌금부과` 명령어를 사용해주세요.")
