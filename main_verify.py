import streamlit as st
import sqlite3
import json

# Force mobile-friendly layout
st.set_page_config(page_title="AlgoSense Verify", layout="centered")

def load_data(pid):
    conn = sqlite3.connect('data/leetcode.db')
    conn.row_factory = sqlite3.Row
    res = conn.cursor().execute("SELECT * FROM problems WHERE id=?", (pid,)).fetchone()
    conn.close()
    return res

def get_all_ids():
    conn = sqlite3.connect('data/leetcode.db')
    # Fetch all IDs to populate the dropdown
    rows = conn.cursor().execute("SELECT id FROM problems ORDER BY CAST(id AS INTEGER)").fetchall()
    conn.close()
    return [row[0] for row in rows]

st.title("📱 AlgoSense Mobile View")

# Sidebar for Problem Selection
all_ids = get_all_ids()

if not all_ids:
    st.error("No data found in leetcode.db. Please run your data_loader first.")
else:
    pid = st.sidebar.selectbox("Select Problem ID", all_ids)
    data = load_data(pid)

    if data:
        # Convert SQLite Row to Dictionary for easier access
        data_dict = dict(data)
        
        st.subheader(f"{data_dict.get('id')}. {data_dict.get('title')}")
        
        # Tabs for Mobile UX
        tab1, tab2, tab3 = st.tabs(["📝 Problem", "📊 Details", "⚡ Quiz"])
        
        with tab1:
            st.markdown("### Description")
            # Using .get() ensures it doesn't crash if a key is missing
            st.markdown(data_dict.get('content', 'No content available'))
            
        with tab2:
            st.markdown("### Examples")
            st.info(data_dict.get('examples', 'No examples provided'))
            
            st.markdown("### Constraints")
            st.warning(data_dict.get('constraints', 'No constraints provided'))
            
        with tab3:
            st.write("### What is the optimal approach?")
            
            # Parse MCQ options from JSON string
            try:
                options = json.loads(data_dict.get('mcq_options', '[]'))
            except:
                options = []
                
            if options:
                # radio index=None means no option is selected by default
                choice = st.radio("Choose one:", options, index=None)
                
                if st.button("Submit Answer"):
                    if choice is None:
                        st.warning("Please select an option.")
                    else:
                        correct_idx = data_dict.get('correct_idx')
                        if options.index(choice) == correct_idx:
                            # Use 'pattern' (confirmed by your DB schema)
                            logic_pattern = data_dict.get('pattern', 'Correct!')
                            st.success(f"✅ Correct! Logic: {logic_pattern}")
                            
                            # Show Solution Code (using 'snippet' from your DB schema)
                            st.markdown("---")
                            st.markdown("### Optimal Solution")
                            solution = data_dict.get('snippet')
                            if solution:
                                st.code(solution, language='python')
                            else:
                                st.write("No solution snippet found.")
                        else:
                            st.error("❌ Incorrect. Think about the time complexity or constraints.")
            else:
                st.write("No quiz options available for this problem.")

# Debugging helper in Sidebar - toggle this to see all keys in your DB
if st.sidebar.checkbox("Show DB Column Names"):
    if 'data_dict' in locals():
        st.sidebar.write("Available Keys in DB:", list(data_dict.keys()))
        st.sidebar.json(data_dict)
