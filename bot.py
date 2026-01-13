# bot.py
# =========================
# 알고리즘 스터디 디스코드 봇
# - 평일 문제 출제 및 관리
# - 벌금 부과/정산 시스템
# - 라운드 로빈 출제자 순환
# =========================

from __future__ import annotations  # Python 3.9 이하 호환성

import os
import discord
from discord.ext import commands, tasks
from discord import app_commands
from dotenv import load_dotenv
from datetime import date, datetime, timedelta
import db

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# .env에 GUILD_ID=123456789012345678 넣어두면 즉시 반영됨
GUILD_ID = int(os.getenv("GUILD_ID", "0"))

# 채널 이름 설정
PROBLEM_CHANNEL_NAME = "문제공지"  # 문제 공지 채널 이름

# =========================
# 2026년 한국 공휴일 목록
# 평일이더라도 이 날짜에는 문제 출제를 하지 않음
# =========================
HOLIDAYS_2026 = {
    # 신정
    "2026-01-01",
    # 설날 연휴 (2/14 토, 2/15 일 포함하여 실제 평일은 16~18)
    "2026-02-16", "2026-02-17", "2026-02-18",
    # 삼일절 및 대체휴일
    "2026-03-01", "2026-03-02",
    # 어린이날
    "2026-05-05",
    # 부처님오신날 및 대체휴일
    "2026-05-24", "2026-05-25",
    # 현충일
    "2026-06-06",
    # 지방선거일
    "2026-06-03",
    # 광복절 및 대체휴일
    "2026-08-15", "2026-08-17",
    # 추석 연휴
    "2026-09-24", "2026-09-25", "2026-09-26",
    # 개천절 및 대체휴일
    "2026-10-03", "2026-10-05",
    # 한글날
    "2026-10-09",
    # 크리스마스
    "2026-12-25",
}

# Discord Intents 설정
intents = discord.Intents.default()
intents.members = True
intents.message_content = True


class AlgoBot(commands.Bot):
    """알고리즘 스터디 봇 클래스"""
    
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        """봇 시작 시 초기화 작업"""
        # 개발 단계: 길드 싱크로 즉시 반영
        if GUILD_ID:
            guild_obj = discord.Object(id=GUILD_ID)
            self.tree.copy_global_to(guild=guild_obj)
            synced = await self.tree.sync(guild=guild_obj)
            print(f"✅ Guild Sync 완료 (GUILD_ID={GUILD_ID}) - {len(synced)} commands")

        else:
            # 운영 단계: 전역 sync (반영이 느릴 수 있음)
            await self.tree.sync()
            print("✅ Global Sync 완료")

        # 스케줄 태스크 시작
        study_reminder.start()
        daily_problem_announcement.start()


bot = AlgoBot()


@bot.event
async def on_ready():
    """봇 준비 완료 이벤트"""
    db.init_db()
    print(f"🤖 봇 로그인 완료: {bot.user}")
    print(f"📦 로드된 슬래시 명령어: {[cmd.name for cmd in bot.tree.get_commands()]}")

    # 멤버 캐시 로드 (멘션 등에 필요)
    for g in bot.guilds:
        try:
            await g.chunk(cache=True)
        except Exception:
            pass


# =========================
# 유틸리티 함수
# =========================

def is_study_day(target_date: date) -> bool:
    """
    스터디 진행일인지 확인
    - 평일(월~금)이면서
    - 공휴일이 아닌 날
    """
    # 주말 체크 (토=5, 일=6)
    if target_date.weekday() > 4:
        return False
    
    # 공휴일 체크
    date_str = target_date.strftime("%Y-%m-%d")
    if date_str in HOLIDAYS_2026:
        return False
    
    return True


def get_next_study_day(from_date: date) -> date:
    """
    주어진 날짜 이후의 다음 스터디 진행일을 반환
    (주말 및 공휴일 제외)
    """
    next_day = from_date + timedelta(days=1)
    while not is_study_day(next_day):
        next_day += timedelta(days=1)
    return next_day


def parse_date_input(date_str: str) -> tuple[bool, date | str]:
    """
    YY-MM-DD 또는 YYYY-MM-DD 형식의 날짜 문자열을 파싱
    
    Returns:
        (성공 여부, date 객체 또는 에러 메시지)
    """
    try:
        # YY-MM-DD 형식 (예: 26-01-15)
        if len(date_str) == 8 and date_str[2] == '-' and date_str[5] == '-':
            parsed = datetime.strptime(date_str, "%y-%m-%d").date()
            return True, parsed
        # YYYY-MM-DD 형식 (예: 2026-01-15)
        elif len(date_str) == 10 and date_str[4] == '-' and date_str[7] == '-':
            parsed = datetime.strptime(date_str, "%Y-%m-%d").date()
            return True, parsed
        else:
            return False, "날짜 형식이 올바르지 않습니다. (예: 26-01-15 또는 2026-01-15)"
    except ValueError:
        return False, "유효하지 않은 날짜입니다. (예: 26-01-15 또는 2026-01-15)"


# =========================
# 슬래시 명령 에러 핸들러
# =========================

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    """슬래시 명령 실행 중 발생한 에러 처리"""
    print("❌ AppCommandError:", repr(error))

    if isinstance(error, app_commands.MissingPermissions):
        msg = "❌ 권한이 없습니다. (관리자 전용 명령어입니다)"
    else:
        msg = f"❌ 오류 발생: {type(error).__name__}"

    if interaction.response.is_done():
        await interaction.followup.send(msg, ephemeral=True)
    else:
        await interaction.response.send_message(msg, ephemeral=True)


# =========================
# /sync (개발용)
# =========================

@bot.tree.command(name="sync", description="(개발용) 이 서버에 슬래시 명령을 동기화합니다")
@app_commands.checks.has_permissions(administrator=True)
async def sync_slash(interaction: discord.Interaction):
    """관리자 전용: 슬래시 명령어 수동 동기화"""
    guild_obj = discord.Object(id=interaction.guild.id)
    synced = await bot.tree.sync(guild=guild_obj)
    await interaction.response.send_message(
        f"✅ 이 서버에 {len(synced)}개 명령 동기화 완료", 
        ephemeral=True
    )


# =========================
# /스터디가입
# =========================

@bot.tree.command(name="스터디가입", description="스터디 멤버로 등록합니다 (문제 출제 로테이션에 참여)")
async def register_study(interaction: discord.Interaction):
    """스터디 멤버 등록"""
    success = db.register_member(interaction.user.id)
    if success:
        await interaction.response.send_message(
            f"🎉 {interaction.user.mention}님, 스터디 멤버로 등록되었습니다!\n"
            f"이제 문제 출제 로테이션에 참여하게 됩니다."
        )
    else:
        await interaction.response.send_message(
            "이미 등록된 멤버입니다.", 
            ephemeral=True
        )


# =========================
# /문제등록
# =========================

@bot.tree.command(name="문제등록", description="특정 날짜에 풀 문제 2개를 등록합니다")
@app_commands.describe(
    target_date="문제를 풀 날짜 (YY-MM-DD 형식, 예: 26-01-15)",
    url1="첫 번째 문제 URL",
    url2="두 번째 문제 URL"
)
async def register_daily_problem(
    interaction: discord.Interaction, 
    target_date: str, 
    url1: str, 
    url2: str
):
    """
    지정된 날짜에 풀 문제 2개를 등록
    - 날짜는 YY-MM-DD 또는 YYYY-MM-DD 형식
    - 공휴일/주말에는 등록 불가
    """
    # 날짜 파싱
    success, result = parse_date_input(target_date)
    if not success:
        await interaction.response.send_message(f"❌ {result}", ephemeral=True)
        return
    
    parsed_date = result
    
    # 스터디 진행일인지 확인
    if not is_study_day(parsed_date):
        date_str = parsed_date.strftime("%Y-%m-%d")
        weekday_name = ["월", "화", "수", "목", "금", "토", "일"][parsed_date.weekday()]
        
        if parsed_date.weekday() > 4:
            reason = "주말"
        else:
            reason = "공휴일"
            
        await interaction.response.send_message(
            f"❌ {date_str}({weekday_name})은 {reason}이므로 문제를 등록할 수 없습니다.",
            ephemeral=True
        )
        return
    
    # 과거 날짜 체크
    if parsed_date < date.today():
        await interaction.response.send_message(
            "❌ 과거 날짜에는 문제를 등록할 수 없습니다.",
            ephemeral=True
        )
        return
    
    target_date_str = str(parsed_date)
    
    # 문제 등록
    success1, msg1 = db.register_problem_v2(url1, interaction.user.id, target_date_str)
    if not success1:
        await interaction.response.send_message(
            f"❌ 1번 문제 등록 실패: {msg1}", 
            ephemeral=True
        )
        return

    success2, msg2 = db.register_problem_v2(url2, interaction.user.id, target_date_str)
    if not success2:
        await interaction.response.send_message(
            f"⚠️ 1번 문제는 등록되었으나, 2번 문제 등록 실패: {msg2}\n"
            f"다른 문제를 등록해주세요.",
            ephemeral=True
        )
        return

    weekday_name = ["월", "화", "수", "목", "금", "토", "일"][parsed_date.weekday()]
    await interaction.response.send_message(
        f"✅ **{target_date_str}({weekday_name})** 문제 등록 완료!\n"
        f"1️⃣ {url1}\n"
        f"2️⃣ {url2}"
    )


# =========================
# /출제자 (순차 로테이션)
# =========================

@bot.tree.command(name="출제자", description="오늘과 앞으로의 문제 출제자 순서를 확인합니다")
async def show_proposer(interaction: discord.Interaction):
    # ✅ 1) 먼저 ACK (3초 제한 회피)
    await interaction.response.defer(thinking=True)  # thinking=True면 "생각중..." 표시

    members = db.get_all_members()
    if not members:
        await interaction.followup.send(
            "❌ 등록된 스터디 멤버가 없습니다.\n`/스터디가입`으로 먼저 등록해주세요!",
            ephemeral=True
        )
        return

    today = date.today()
    current_index = db.get_rotation_index()

    async def get_mention(uid):
        try:
            u = await bot.fetch_user(uid)
            return u.mention
        except Exception:
            return f"알 수 없음(ID: {uid})"

    async def get_name(uid):
        try:
            u = await bot.fetch_user(uid)
            return u.display_name
        except Exception:
            return "알 수 없음"

    embed = discord.Embed(
        title="📅 문제 출제 순서 (라운드 로빈)",
        description="스터디원들이 순서대로 돌아가며 출제합니다",
        color=0x3498db
    )

    shown_days = 0
    check_date = today
    temp_index = current_index
    schedule_text = ""

    while shown_days < 7:
        if is_study_day(check_date):
            date_str = check_date.strftime("%Y-%m-%d")
            weekday_name = ["월", "화", "수", "목", "금", "토", "일"][check_date.weekday()]
            registered = db.get_problems_by_date(date_str)

            proposer_uid = members[temp_index % len(members)]

            if registered:
                proposers = {pid for _, _, pid in registered}
                names = [await get_name(pid) for pid in proposers]
                status = f"✅ {', '.join(names)} (등록완료)"
            else:
                status = f"⏳ {await get_mention(proposer_uid)} (예정)"

            day_label = ""
            if check_date == today:
                day_label = " **[오늘]**"
            elif check_date == today + timedelta(days=1):
                day_label = " **[내일]**"

            schedule_text += f"📌 {date_str}({weekday_name}){day_label}\n   └ {status}\n\n"

            temp_index += 1
            shown_days += 1

        check_date += timedelta(days=1)

    embed.add_field(name="향후 출제 일정", value=schedule_text, inline=False)

    rotation_text = ""
    for i, uid in enumerate(members):
        marker = "👉 " if i == (current_index % len(members)) else "   "
        rotation_text += f"{marker}{i+1}. {await get_name(uid)}\n"

    embed.add_field(name="📋 전체 출제 순서", value=rotation_text, inline=False)
    embed.set_footer(text="💡 /문제등록 으로 문제를 등록하면 자동으로 다음 사람에게 넘어갑니다")

    # ✅ 2) defer를 했으니 followup으로 보내야 함
    await interaction.followup.send(embed=embed)



# =========================
# /벌금부과 (관리자 전용)
# =========================

@bot.tree.command(name="벌금부과", description="(관리자) 스터디원에게 벌금을 부과합니다")
@app_commands.describe(
    member="벌금을 부과할 멤버",
    reason="부과 사유 (예: 문제 미풀이, 음성채널 불참 등)",
    amount="벌금 금액 (기본값: 1000원)"
)
@app_commands.checks.has_permissions(administrator=True)
async def impose_fine(
    interaction: discord.Interaction, 
    member: discord.Member, 
    reason: str,
    amount: int = 1000
):
    """
    관리자가 특정 멤버에게 벌금을 부과
    - 문제 미풀이: 1문제당 1000원
    - 음성채널 무단 불참: 1000원
    - 부과 시 해당 멤버에게 DM 발송
    """
    if amount <= 0:
        await interaction.response.send_message(
            "❌ 벌금 금액은 0보다 커야 합니다.", 
            ephemeral=True
        )
        return
    
    # DB에 벌금 기록
    db.add_fine(member.id, amount, reason)
    
    # 현재 총 벌금 조회
    total = db.get_user_fine(member.id)
    
    # DM으로 알림
    try:
        dm_embed = discord.Embed(
            title="💰 벌금이 부과되었습니다",
            color=0xff6b6b
        )
        dm_embed.add_field(name="부과 사유", value=reason, inline=False)
        dm_embed.add_field(name="부과 금액", value=f"{amount:,}원", inline=True)
        dm_embed.add_field(name="누적 벌금", value=f"{total:,}원", inline=True)
        dm_embed.set_footer(text=f"부과자: {interaction.user.display_name}")
        
        await member.send(embed=dm_embed)
        dm_sent = True
    except discord.Forbidden:
        dm_sent = False
    
    # 응답
    response_msg = (
        f"✅ **{member.display_name}**님에게 벌금 부과 완료\n"
        f"📝 사유: {reason}\n"
        f"💵 금액: {amount:,}원\n"
        f"📊 누적 벌금: {total:,}원"
    )
    
    if not dm_sent:
        response_msg += "\n\n⚠️ DM 전송 실패 (DM이 차단되어 있을 수 있습니다)"
    
    await interaction.response.send_message(response_msg)


# =========================
# /나의벌금
# =========================

@bot.tree.command(name="나의벌금", description="나의 현재 벌금 내역을 확인합니다")
async def my_fine(interaction: discord.Interaction):
    """본인의 벌금 내역 및 총액 조회"""
    total = db.get_user_fine(interaction.user.id)
    history = db.get_fine_history(interaction.user.id)
    
    embed = discord.Embed(
        title="💰 나의 벌금 현황",
        color=0xf39c12 if total > 0 else 0x2ecc71
    )
    
    embed.add_field(
        name="💵 현재 누적 벌금",
        value=f"**{total:,}원**",
        inline=False
    )
    
    if history:
        history_text = ""
        for i, (amount, reason, created_at) in enumerate(history[-10:], 1):  # 최근 10건
            # 날짜 포맷팅
            date_part = created_at.split()[0] if created_at else "날짜없음"
            history_text += f"{i}. {date_part} | {amount:,}원 | {reason}\n"
        
        embed.add_field(
            name="📋 최근 부과 내역",
            value=f"```\n{history_text}```" if history_text else "내역 없음",
            inline=False
        )
    else:
        embed.add_field(
            name="📋 부과 내역",
            value="🎉 벌금 내역이 없습니다!",
            inline=False
        )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)


# =========================
# /월정산 (관리자 전용)
# =========================

@bot.tree.command(name="월정산", description="(관리자) 전체 스터디원의 벌금 현황을 확인합니다")
@app_commands.checks.has_permissions(administrator=True)
async def monthly_summary(interaction: discord.Interaction):
    """전체 스터디원의 벌금 현황 조회"""
    results = db.get_all_fines()
    
    if not results:
        await interaction.response.send_message("이번 정산 기간의 벌금 내역이 없습니다.")
        return

    embed = discord.Embed(
        title="📊 벌금 정산 현황",
        description="스터디원별 누적 벌금 내역입니다",
        color=0xFFD700
    )
    
    total_sum = 0
    for user_id, total in results:
        try:
            user = await bot.fetch_user(user_id)
            name = user.display_name
        except Exception:
            name = f"Unknown({user_id})"
        
        embed.add_field(
            name=name,
            value=f"💵 {total:,}원",
            inline=True
        )
        total_sum += total
    
    embed.add_field(
        name="━━━━━━━━━━━━━━",
        value=f"**총 합계: {total_sum:,}원**",
        inline=False
    )
    
    embed.set_footer(text="💡 /정산완료 명령어로 벌금을 초기화할 수 있습니다")
    
    await interaction.response.send_message(embed=embed)


# =========================
# /정산완료 (관리자 전용)
# =========================

@bot.tree.command(name="정산완료", description="(관리자) 모든 벌금을 정산 완료 처리하고 초기화합니다")
@app_commands.checks.has_permissions(administrator=True)
async def reset_fines(interaction: discord.Interaction):
    """
    모든 벌금을 초기화
    - 확인 메시지 후 실행
    """
    # 현재 총 벌금 확인
    results = db.get_all_fines()
    if not results:
        await interaction.response.send_message(
            "정산할 벌금 내역이 없습니다.",
            ephemeral=True
        )
        return
    
    total_sum = sum(total for _, total in results)
    member_count = len(results)
    
    # 정산 실행
    db.reset_all_fines()
    
    embed = discord.Embed(
        title="✅ 정산 완료",
        description="모든 벌금이 초기화되었습니다",
        color=0x2ecc71
    )
    embed.add_field(name="정산 금액", value=f"{total_sum:,}원", inline=True)
    embed.add_field(name="정산 인원", value=f"{member_count}명", inline=True)
    embed.set_footer(text=f"처리자: {interaction.user.display_name}")
    
    await interaction.response.send_message(embed=embed)


# =========================
# /랭킹
# =========================

@bot.tree.command(name="랭킹", description="현재 스터디 랭킹을 확인합니다")
async def show_ranking(interaction: discord.Interaction):
    """문제 풀이 포인트 기준 랭킹 표시"""
    ranking = db.get_ranking()
    
    if not ranking:
        await interaction.response.send_message("아직 랭킹 데이터가 없습니다.")
        return

    embed = discord.Embed(title="🏆 스터디 랭킹", color=0xFFD700)
    
    medals = ["🥇", "🥈", "🥉"]
    
    for idx, (user_id, points, count) in enumerate(ranking, 1):
        try:
            user = await bot.fetch_user(user_id)
            name = user.display_name
        except Exception:
            name = "Unknown"

        medal = medals[idx-1] if idx <= 3 else f"{idx}위"
        
        embed.add_field(
            name=f"{medal} {name}",
            value=f"💎 {points}점 ({count}문제 해결)",
            inline=False
        )
    
    await interaction.response.send_message(embed=embed)


# =========================
# /로테이션설정 (관리자 전용)
# =========================

@bot.tree.command(name="로테이션설정", description="(관리자) 현재 출제자 순번을 설정합니다")
@app_commands.describe(
    member="현재 출제 순번으로 설정할 멤버"
)
@app_commands.checks.has_permissions(administrator=True)
async def set_rotation(interaction: discord.Interaction, member: discord.Member):
    """
    라운드 로빈 출제 순번을 특정 멤버로 설정
    - 해당 멤버부터 다음 출제가 시작됨
    """
    members = db.get_all_members()
    
    if member.id not in members:
        await interaction.response.send_message(
            f"❌ {member.display_name}님은 스터디 멤버로 등록되어 있지 않습니다.",
            ephemeral=True
        )
        return
    
    new_index = members.index(member.id)
    db.set_rotation_index(new_index)
    
    await interaction.response.send_message(
        f"✅ 출제 순번이 **{member.display_name}**님으로 설정되었습니다.\n"
        f"다음 출제부터 이 순서로 진행됩니다."
    )


# =========================
# /다음출제자 (관리자 전용)
# =========================

@bot.tree.command(name="다음출제자", description="(관리자) 출제 순번을 다음 사람으로 넘깁니다")
@app_commands.checks.has_permissions(administrator=True)
async def next_proposer(interaction: discord.Interaction):
    """수동으로 출제 순번을 다음 사람으로 이동"""
    members = db.get_all_members()
    
    if not members:
        await interaction.response.send_message(
            "❌ 등록된 스터디 멤버가 없습니다.",
            ephemeral=True
        )
        return
    
    current_index = db.get_rotation_index()
    new_index = (current_index + 1) % len(members)
    db.set_rotation_index(new_index)
    
    try:
        prev_user = await bot.fetch_user(members[current_index % len(members)])
        next_user = await bot.fetch_user(members[new_index])
        
        await interaction.response.send_message(
            f"✅ 출제 순번이 넘어갔습니다.\n"
            f"{prev_user.display_name} ➡️ **{next_user.display_name}**"
        )
    except Exception:
        await interaction.response.send_message(
            f"✅ 출제 순번이 인덱스 {new_index}로 변경되었습니다."
        )


# =========================
# 스터디 10분 전 알림 (22:00)
# =========================

@tasks.loop(minutes=1)
async def study_reminder():
    """
    매일 22:00에 @everyone 멘션으로 스터디 시작 10분 전 알림
    - 스터디 진행일에만 발송
    """
    now = datetime.now()
    
    # 22:00 체크
    if now.hour != 21 or now.minute != 50:
        return
    
    # 오늘이 스터디 진행일인지 확인
    if not is_study_day(now.date()):
        return
    
    for guild in bot.guilds:
        channel = discord.utils.get(guild.text_channels, name=PROBLEM_CHANNEL_NAME)
        if not channel:
            print(f"⚠️ [{guild.name}] '{PROBLEM_CHANNEL_NAME}' 채널을 찾을 수 없습니다.")
            continue
        
        embed = discord.Embed(
            title="⏰ 정기 스터디 10분 전!",
            description="곧 스터디가 시작됩니다. 음성 채널에 입장해주세요!",
            color=0xe74c3c
        )
        embed.set_footer(text="22:00 스터디 시작")
        
        await channel.send(content="@everyone", embed=embed)


# =========================
# 일일 문제 공지 (23:00)
# =========================

@tasks.loop(minutes=1)
async def daily_problem_announcement():
    """
    매일 23:00에 다음날 문제 공지
    - 금, 토요일 저녁에는 스킵 (다음날이 토, 일이므로)
    - 내일이 공휴일이면 스킵
    - 채널 공지 + 멤버 DM 발송
    """
    now = datetime.now()
    
    # 23:00 체크
    if now.hour != 23 or now.minute != 0:
        return

    # 내일 날짜 계산
    tomorrow = now.date() + timedelta(days=1)
    
    # 내일이 스터디 진행일인지 확인
    if not is_study_day(tomorrow):
        return

    target_date_str = str(tomorrow)
    problems = db.get_problems_by_date(target_date_str)
    weekday_name = ["월", "화", "수", "목", "금", "토", "일"][tomorrow.weekday()]

    for guild in bot.guilds:
        channel = discord.utils.get(guild.text_channels, name=PROBLEM_CHANNEL_NAME)
        if not channel:
            print(f"⚠️ [{guild.name}] '{PROBLEM_CHANNEL_NAME}' 채널을 찾을 수 없습니다.")
            continue

        if not problems:
            await channel.send(
                f"⚠️ **{target_date_str}({weekday_name})** 문제가 아직 등록되지 않았습니다! 😭\n"
                f"출제자분은 `/문제등록` 명령어로 문제를 등록해주세요!"
            )
            continue

        # 채널 공지용 Embed
        embed = discord.Embed(
            title=f"📅 {target_date_str}({weekday_name}) 오늘의 알고리즘",
            description="내일 22:00 스터디 전까지 풀어오세요!",
            color=0x00ff00
        )

        for pid, url, proposer_id in problems:
            try:
                proposer = await bot.fetch_user(proposer_id)
                proposer_name = proposer.display_name
            except Exception:
                proposer_name = "알 수 없음"

            embed.add_field(
                name=f"📝 문제 #{pid}",
                value=f"🔗 [문제 보러가기]({url})\n👤 출제자: {proposer_name}",
                inline=False
            )

        # 채널에 공지
        members = db.get_all_members()
        mentions = " ".join([f"<@{uid}>" for uid in members]) if members else ""
        await channel.send(content=mentions, embed=embed)
        
        # 각 멤버에게 DM 발송
        for uid in members:
            try:
                user = await bot.fetch_user(uid)
                await user.send(embed=embed)
            except discord.Forbidden:
                print(f"⚠️ {uid}에게 DM 발송 실패 (DM 차단)")
            except Exception as e:
                print(f"⚠️ {uid}에게 DM 발송 중 오류: {e}")


# =========================
# 봇 실행
# =========================

bot.run(TOKEN)
