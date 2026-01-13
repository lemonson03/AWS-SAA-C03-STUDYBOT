# db.py (일부 발췌 및 수정)

def init_db():
    # ... 기존 테이블 생성 코드 유지 ...
    
    # users 테이블에 진도 정보(progress) 추가
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        progress TEXT DEFAULT '섹션 1',  -- 현재 어디까지 했는지 (예: '섹션 5', '문제 100')
        points INTEGER DEFAULT 0         -- 정렬용 점수 (내부 계산)
    )
    """)
    
    # 주간 목표 저장용 설정
    cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('weekly_goal', '섹션 1 시작')")
    conn.commit()

def update_progress(user_id: int, progress_str: str):
    """사용자의 진도를 업데이트하고 정렬용 점수를 계산하여 저장"""
    # 점수 계산 로직: '섹션 1' -> 1점, '문제 1' -> 1001점 (섹션 30 이후가 문제이므로)
    score = 0
    try:
        if "섹션" in progress_str:
            num = int(progress_str.replace("섹션", "").strip())
            score = num
        elif "문제" in progress_str:
            num = int(progress_str.replace("문제", "").strip())
            score = 1000 + num  # 섹션보다 무조건 높게
    except:
        score = 0 # 형식에 안 맞으면 0점

    cur.execute(
        "UPDATE users SET progress=?, points=? WHERE user_id=?",
        (progress_str, score, user_id)
    )
    conn.commit()

def get_saa_ranking():
    """진도 점수(points) 기준 내림차순 정렬"""
    cur.execute("SELECT user_id, progress FROM users ORDER BY points DESC")
    return cur.fetchall()

def set_weekly_goal(goal_str: str):
    cur.execute("UPDATE settings SET value=? WHERE key='weekly_goal'", (goal_str,))
    conn.commit()

def get_weekly_goal():
    cur.execute("SELECT value FROM settings WHERE key='weekly_goal'")
    return cur.fetchone()[0]
