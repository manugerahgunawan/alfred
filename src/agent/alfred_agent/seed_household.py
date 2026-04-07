import os
import google.cloud.firestore
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

def seed_household():
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "alfred-492407")
    db = google.cloud.firestore.Client(project=project_id)
    
    # 1. Seed Household Rules
    household_ref = db.collection("households").document("default")
    household_data = {
        "family_members": ["Bruce", "Damian", "Dick", "Tim", "Cassandra", "Barbara"],
        "rules": [
            {"name": "Family Dinner", "time": "19:00", "mandatory": True, "description": "Daily family gathering. Professional conflicts should be avoided."},
            {"name": "Damian Training", "days": ["Monday", "Wednesday"], "time": "18:00", "description": "Training evaluation for the Young Master."}
        ],
        "shopping_list": ["Milk", "Premium Tea Leaves", "Gotham Gazelle (Morning Edition)"],
        "chores": [
            {"task": "Inventory Batcave supplies", "assigned_to": "Alfred", "status": "In Progress"},
            {"task": "Service the Tumbler", "assigned_to": "Bruce", "status": "Pending"}
        ],
        "last_updated": datetime.now(timezone.utc)
    }
    
    household_ref.set(household_data)
    print(f"--- Seeded 'households/default' for project {project_id} ---")

if __name__ == "__main__":
    seed_household()
