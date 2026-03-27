from langchain.chat_models import init_chat_model
import sqlite3

llm = init_chat_model("openai:gpt-4o")

def update_user_skill_profile(user_id, problem_id, is_correct, pattern):
    """
    LLM analyzes the result to decide how much to increase/decrease 
    the skill score for a specific pattern.
    """
    # Simple logic for now, but GPT-4o can analyze 'why' they failed 
    # if you pass the user's wrong reasoning.
    score_change = 10 if is_correct else -15
    
    conn = sqlite3.connect('data/leetcode.db')
    # SQL to update user_stats set skill_score = skill_score + score_change
    # ...
    conn.close()
