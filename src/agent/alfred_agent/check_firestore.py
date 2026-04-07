import os
import google.cloud.firestore
from dotenv import load_dotenv

load_dotenv()

def check_firestore():
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "alfred-492407")
    db = google.cloud.firestore.Client(project=project_id)
    
    print(f"--- Checking Firestore Project: {project_id} ---")
    
    try:
        collections = db.collections()
        for coll in collections:
            print(f"Collection: {coll.id}")
            docs = coll.stream()
            count = 0
            for doc in docs:
                if count >= 5: break
                print(f"  - Document: {doc.id}")
                data = doc.to_dict()
                print(f"    Data: {data}")
                count += 1
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_firestore()
