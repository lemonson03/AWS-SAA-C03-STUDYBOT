import sqlite3
import os
from datetime import datetime

# 파일 경로 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

# 데이터 전용 폴더가 없으면 생성 (권한 에러 방지)
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

DB_PATH = os.path.join(DATA_DIR, "study.db")

# ✅ DB 연결 및 커서 정의 (이 부분이 정확해야 에러가 안 납니다)
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cur = conn.cursor()

def init_db():
    """데이터베이스 테이블 초기화"""
    # 설정 테이블
    cur.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)

    # 사용자 진도 및 랭킹 테이블
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        progress TEXT DEFAULT '섹션 1',
        points INTEGER DEFAULT 0
    )
    """)

    # 벌금 테이블
    cur.execute("""
    CREATE TABLE IF NOT EXISTS fines (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount INTEGER,
        reason TEXT,
        created_at TEXT,
        is_settled INTEGER DEFAULT 0
    )
    """)

    # 초기 설정값 삽입
    cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('weekly_goal', '섹션 1 시작')")
    
    conn.commit()

# =========================
# 진도 및 랭킹 관리
# =========================

def update_progress(user_id: int, progress_str: str):
    """사용자의 진도를 업데이트하고 정렬용 점수를 계산하여 저장"""
    score = 0
    try:
        if "섹션" in progress_str:
            num = int(progress_str.replace("섹션", "").strip())
            score = num
        elif "문제" in progress_str:
            num = int(progress_str.replace("문제", "").strip())
            score = 1000 + num
    except:
        score = 0

    # 사용자 등록 및 업데이트
    cur.execute(
        "INSERT OR REPLACE INTO users (user_id, progress, points) VALUES (?, ?, ?)",
        (user_id, progress_str, score)
    )
    conn.commit()

def get_saa_ranking():
    """진도 점수(points) 기준 내림차순 정렬"""
    cur.execute("SELECT user_id, progress FROM users ORDER BY points DESC")
    return cur.fetchall()

# =========================
# 목표 관리
# =========================

def set_weekly_goal(goal_str: str):
    cur.execute("UPDATE settings SET value=? WHERE key='weekly_goal'", (goal_str,))
    conn.commit()

def get_weekly_goal():
    cur.execute("SELECT value FROM settings WHERE key='weekly_goal'")
    row = cur.fetchone()
    return row[0] if row else "설정된 목표 없음"

# =========================
# 벌금 관리 (기본 기능)
# =========================

def add_fine(user_id: int, amount: int, reason: str):
    cur.execute(
        "INSERT INTO fines (user_id, amount, reason, created_at) VALUES (?, ?, ?, ?)",
        (user_id, amount, reason, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()

def get_user_fine(user_id: int) -> int:
    cur.execute("SELECT SUM(amount) FROM fines WHERE user_id=? AND is_settled=0", (user_id,))
    row = cur.fetchone()
    return row[0] if row[0] else 0