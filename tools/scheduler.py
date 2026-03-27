import sqlite3
from datetime import datetime, timedelta
from langchain_openai import ChatOpenAI # or your init_chat_model

def get_next_review_cards(user_id, mode="Pattern", limit=5):
    conn = sqlite3.connect('data/leetcode.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    now = datetime.now().isoformat()
    one_week_ago = (datetime.now() - timedelta(days=7)).isoformat()
    
    # 1. PRIORITY: Cards failed yesterday/recently
    # (Assuming we have a 'last_result' column in user_progress)
    failed_cards = cursor.execute("""
        SELECT p.* FROM problems p
        JOIN user_progress up ON p.id = up.problem_id
        WHERE up.user_id = ? AND up.last_result = 'fail'
        ORDER BY up.last_reviewed DESC LIMIT ?
    """, (user_id, limit)).fetchall()
    
    # 2. STALE: Cards not seen in 1 week
    stale_cards = cursor.execute("""
        SELECT p.* FROM problems p
        JOIN user_progress up ON p.id = up.problem_id
        WHERE up.user_id = ? AND up.last_reviewed < ?
        ORDER BY up.last_reviewed ASC LIMIT ?
    """, (user_id, one_week_ago, limit)).fetchall()
    
    # 3. NEW/WEAK: AI-driven based on weak patterns
    # We get the user's lowest skill categories first
    weak_patterns = cursor.execute("""
        SELECT tag FROM user_stats 
        WHERE user_id = ? 
        ORDER BY skill_score ASC LIMIT 3
    """, (user_id,)).fetchall()
    
    weak_tags = [row['tag'] for row in weak_patterns]
    
    # Fetch problems from those weak tags that haven't been solved yet
    new_weak_cards = []
    if weak_tags:
        placeholder = ', '.join(['?'] * len(weak_tags))
        new_weak_cards = cursor.execute(f"""
            SELECT * FROM problems 
            WHERE primary_pattern IN ({placeholder})
            AND id NOT IN (SELECT problem_id FROM user_progress WHERE user_id = ?)
            LIMIT ?
        """, (*weak_tags, user_id, limit)).fetchall()

    conn.close()
    
    # Combine and return (Prioritize Failed > Stale > Weak)
    combined = (list(failed_cards) + list(stale_cards) + list(new_weak_cards))[:limit]
    return [dict(row) for row in combined]
