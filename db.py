# db.py
# =========================
# 알고리즘 스터디 데이터베이스 관리
# - 스터디원 관리
# - 문제 등록/조회
# - 벌금 부과/정산
# - 출제자 로테이션 관리
# =========================

import sqlite3
from datetime import date, datetime

import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "study.db")


# SQLite 연결 (멀티스레드 허용)
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cur = conn.cursor()


def init_db():
    """
    데이터베이스 테이블 초기화
    - 기존 테이블이 없으면 생성
    - 마이그레이션 필요시 여기서 처리
    """
    
    # 스터디 멤버 테이블
    cur.execute("""
    CREATE TABLE IF NOT EXISTS study_members (
        user_id INTEGER PRIMARY KEY,
        joined_at TEXT
    )
    """)

    # 사용자 포인트/랭킹 테이블
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        points INTEGER DEFAULT 0,
        solved_count INTEGER DEFAULT 0
    )
    """)

    # 문제 테이블 (v2)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS problems_v2 (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        url TEXT UNIQUE,
        target_date TEXT,
        proposer_id INTEGER,
        created_at TEXT
    )
    """)

    # 문제 풀이 기록 테이블
    cur.execute("""
    CREATE TABLE IF NOT EXISTS solves (
        user_id INTEGER,
        problem_id INTEGER,
        solved_at TEXT,
        UNIQUE(user_id, problem_id)
    )
    """)
    
    # 벌금 테이블 (새로운 구조)
    # - 개별 부과 내역을 기록
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
    
    # 설정 테이블 (로테이션 인덱스 등)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)
    
    # 로테이션 인덱스 초기값 설정 (없으면)
    cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('rotation_index', '0')")

    conn.commit()


# =========================
# 스터디원 관리
# =========================

def register_member(user_id: int) -> bool:
    """
    스터디 멤버 등록
    
    Args:
        user_id: Discord 사용자 ID
        
    Returns:
        성공 여부 (이미 등록된 경우 False)
    """
    try:
        cur.execute(
            "INSERT INTO study_members (user_id, joined_at) VALUES (?, ?)",
            (user_id, str(datetime.now()))
        )
        # users 테이블에도 등록 (포인트/랭킹용)
        cur.execute(
            "INSERT OR IGNORE INTO users (user_id) VALUES (?)",
            (user_id,)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def get_all_members() -> list[int]:
    """
    전체 스터디 멤버 목록 조회
    - 가입 순서대로 정렬 (라운드 로빈용)
    
    Returns:
        user_id 리스트
    """
    cur.execute(
        "SELECT user_id FROM study_members ORDER BY joined_at ASC, rowid ASC"
    )
    return [row[0] for row in cur.fetchall()]


def remove_member(user_id: int) -> bool:
    """
    스터디 멤버 제거
    
    Args:
        user_id: Discord 사용자 ID
        
    Returns:
        성공 여부
    """
    cur.execute("DELETE FROM study_members WHERE user_id=?", (user_id,))
    affected = cur.rowcount
    conn.commit()
    return affected > 0


# =========================
# 출제자 로테이션 관리
# =========================

def get_rotation_index() -> int:
    """
    현재 로테이션 인덱스 조회
    - 이 인덱스가 가리키는 멤버가 현재 출제 차례
    
    Returns:
        현재 인덱스 (0부터 시작)
    """
    cur.execute("SELECT value FROM settings WHERE key='rotation_index'")
    row = cur.fetchone()
    return int(row[0]) if row else 0


def set_rotation_index(index: int):
    """
    로테이션 인덱스 설정
    
    Args:
        index: 새로운 인덱스 값
    """
    cur.execute(
        "UPDATE settings SET value=? WHERE key='rotation_index'",
        (str(index),)
    )
    conn.commit()


def advance_rotation():
    """
    로테이션 인덱스를 1 증가
    - 문제 등록 완료 시 호출
    """
    members = get_all_members()
    if not members:
        return
    
    current = get_rotation_index()
    new_index = (current + 1) % len(members)
    set_rotation_index(new_index)


from typing import Optional, Tuple

def get_last_problem_info() -> Optional[Tuple]:
    """
    가장 마지막으로 등록된 문제의 정보 조회
    
    Returns:
        (target_date, proposer_id) 또는 None
    """
    cur.execute(
        "SELECT target_date, proposer_id FROM problems_v2 ORDER BY target_date DESC LIMIT 1"
    )
    return cur.fetchone()


# =========================
# 문제 관리
# =========================

def get_problems_by_date(target_date_str: str) -> list[tuple]:
    """
    특정 날짜의 등록된 문제 조회
    
    Args:
        target_date_str: 날짜 문자열 (YYYY-MM-DD)
        
    Returns:
        [(id, url, proposer_id), ...] 리스트
    """
    cur.execute(
        "SELECT id, url, proposer_id FROM problems_v2 WHERE target_date=?",
        (target_date_str,)
    )
    return cur.fetchall()


def is_url_registered(url: str) -> bool:
    """
    URL이 이미 등록되어 있는지 확인
    
    Args:
        url: 문제 URL
        
    Returns:
        등록 여부
    """
    cur.execute("SELECT 1 FROM problems_v2 WHERE url=?", (url,))
    return cur.fetchone() is not None


def register_problem_v2(url: str, proposer_id: int, target_date_str: str) -> tuple[bool, str]:
    """
    새 문제 등록
    
    Args:
        url: 문제 URL
        proposer_id: 출제자 Discord ID
        target_date_str: 문제를 풀 날짜 (YYYY-MM-DD)
        
    Returns:
        (성공 여부, 메시지)
    """
    # 중복 URL 체크
    if is_url_registered(url):
        return False, "이미 등록된 적 있는 문제입니다."

    # 해당 날짜에 이미 2문제가 등록되어 있는지 확인
    cur.execute(
        "SELECT COUNT(*) FROM problems_v2 WHERE target_date=?",
        (target_date_str,)
    )
    count = cur.fetchone()[0]
    if count >= 2:
        return False, f"{target_date_str}일자 문제는 이미 2개가 모두 등록되었습니다."

    # 문제 등록
    cur.execute(
        "INSERT INTO problems_v2 (url, target_date, proposer_id, created_at) VALUES (?, ?, ?, ?)",
        (url, target_date_str, proposer_id, str(datetime.now()))
    )
    conn.commit()
    
    # 2번째 문제가 등록되면 로테이션 인덱스 증가
    cur.execute(
        "SELECT COUNT(*) FROM problems_v2 WHERE target_date=?",
        (target_date_str,)
    )
    new_count = cur.fetchone()[0]
    if new_count == 2:
        advance_rotation()
    
    return True, "등록 성공"


from typing import Optional, Tuple

def get_problem_by_id(problem_id: int) -> Optional[Tuple]:
    """
    문제 ID로 문제 정보 조회
    
    Args:
        problem_id: 문제 ID
        
    Returns:
        (id, url, target_date, proposer_id, created_at) 또는 None
    """
    cur.execute(
        "SELECT id, url, target_date, proposer_id, created_at FROM problems_v2 WHERE id=?",
        (problem_id,)
    )
    return cur.fetchone()


# =========================
# 벌금 관리 (새로운 구조)
# =========================

def add_fine(user_id: int, amount: int, reason: str):
    """
    벌금 부과
    
    Args:
        user_id: Discord 사용자 ID
        amount: 벌금 금액
        reason: 부과 사유
    """
    cur.execute(
        "INSERT INTO fines (user_id, amount, reason, created_at, is_settled) VALUES (?, ?, ?, ?, 0)",
        (user_id, amount, reason, str(datetime.now()))
    )
    conn.commit()


def get_user_fine(user_id: int) -> int:
    """
    특정 사용자의 미정산 벌금 총액 조회
    
    Args:
        user_id: Discord 사용자 ID
        
    Returns:
        총 벌금액
    """
    cur.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM fines WHERE user_id=? AND is_settled=0",
        (user_id,)
    )
    return cur.fetchone()[0]


def get_fine_history(user_id: int, limit: int = 20) -> list[tuple]:
    """
    특정 사용자의 벌금 부과 내역 조회
    
    Args:
        user_id: Discord 사용자 ID
        limit: 최대 조회 개수
        
    Returns:
        [(amount, reason, created_at), ...] 리스트
    """
    cur.execute(
        """
        SELECT amount, reason, created_at 
        FROM fines 
        WHERE user_id=? AND is_settled=0
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (user_id, limit)
    )
    return cur.fetchall()


def get_all_fines() -> list[tuple]:
    """
    전체 사용자의 미정산 벌금 현황 조회
    
    Returns:
        [(user_id, total_amount), ...] 리스트
    """
    cur.execute(
        """
        SELECT user_id, SUM(amount) as total
        FROM fines
        WHERE is_settled=0
        GROUP BY user_id
        HAVING total > 0
        ORDER BY total DESC
        """
    )
    return cur.fetchall()


def reset_all_fines():
    """
    모든 벌금을 정산 완료 처리
    - is_settled를 1로 변경하여 기록은 유지
    """
    cur.execute("UPDATE fines SET is_settled=1 WHERE is_settled=0")
    conn.commit()


def reset_user_fine(user_id: int):
    """
    특정 사용자의 벌금만 정산 완료 처리
    
    Args:
        user_id: Discord 사용자 ID
    """
    cur.execute(
        "UPDATE fines SET is_settled=1 WHERE user_id=? AND is_settled=0",
        (user_id,)
    )
    conn.commit()


# =========================
# 랭킹 조회
# =========================

def get_ranking(limit: int = 10) -> list[tuple]:
    """
    포인트 기준 랭킹 조회
    
    Args:
        limit: 최대 조회 인원
        
    Returns:
        [(user_id, points, solved_count), ...] 리스트
    """
    cur.execute(
        "SELECT user_id, points, solved_count FROM users ORDER BY points DESC LIMIT ?",
        (limit,)
    )
    return cur.fetchall()


# =========================
# 레거시 함수 (하위 호환성)
# - 기존 코드와의 호환을 위해 유지
# - 새 코드에서는 사용하지 않음
# =========================

def get_monthly_fine() -> list[tuple]:
    """
    [레거시] 월간 벌금 조회 - get_all_fines()로 대체
    """
    return get_all_fines()
