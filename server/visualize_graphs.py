
import sys
import os

# Add the src directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from agent.graph import build_fishing_planner_graph
from agent.call_graph.graph import build_call_graph
from agent.services import AgentServices
from sqlalchemy.orm import Session


def main():
    """
    Generates visualizations of the LangGraph graphs.
    """
    # Visualize the fishing planner graph
    planner_graph = build_fishing_planner_graph()
    planner_graph_viz = planner_graph.get_graph()
    planner_graph_viz.draw_png('fishing_planner_graph.png')
    print("Generated fishing_planner_graph.png")

    # Visualize the call graph
    # The call graph needs a services object, so we'll create a mock one.
    class MockServices(AgentServices):
        def __init__(self):
            pass
        def start_reservation_call(self, details, preferred_name):
            return type('obj', (object,), {'success': True, 'sid': '123'})
        def peek_call_status(self, sid):
            return "in-progress"
        def drain_transcript_buffer(self, sid):
            return []
        def call_completed(self, sid):
            return True
        def extract_slots_from_transcript(self, transcript):
            return {}
        def now_iso(self):
            return ""
        def pick_business(self, details, preferred_name):
            return type('obj', (object,), {'business': type('obj', (object,), {'phone': '123-456-7890'})})


    services = MockServices()
    call_graph = build_call_graph(services)
    call_graph_viz = call_graph.get_graph()
    call_graph_viz.draw_png('call_graph.png')
    print("Generated call_graph.png")


if __name__ == "__main__":
    main()
