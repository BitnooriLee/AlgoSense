from dotenv import load_dotenv
from langgraph.graph import END, START, MessagesState, StateGraph

from agents.classification_agent import classification_agent

load_dotenv()


class TutorState(MessagesState):
    pass


graph_builder = StateGraph(TutorState)
graph_builder.add_node("classification_agent", classification_agent)
graph_builder.add_edge(START, "classification_agent")
graph_builder.add_edge("classification_agent", END)
graph = graph_builder.compile()
