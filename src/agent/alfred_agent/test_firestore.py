"""
Smoke test for Firestore integration.

Usage:
  # Against the emulator (safe, no prod impact):
  export FIRESTORE_EMULATOR_HOST=localhost:8080
  python test_firestore.py

  # Against real Firestore (uses your gcloud ADC):
  unset FIRESTORE_EMULATOR_HOST
  python test_firestore.py
"""
import os
from google.cloud import firestore
from datetime import datetime, timezone

PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "alfred-492407")
db = firestore.Client(project=PROJECT)


def test_write_agent_action():
    """Test writing to agentActions collection."""
    ref = db.collection("agentActions").add({
        "action": "test_action",
        "agent": "test_agent",
        "intent": "smoke test",
        "timestamp": datetime.now(timezone.utc),
    })
    doc_id = ref[1].id
    print(f"[PASS] Written agentActions doc: {doc_id}")
    # Clean up
    db.collection("agentActions").document(doc_id).delete()
    print(f"[PASS] Cleaned up doc: {doc_id}")


def test_read_household():
    """Test reading household context."""
    doc = db.collection("households").document("default").get()
    if doc.exists:
        print(f"[PASS] Household 'default' exists: {doc.to_dict()}")
    else:
        print("[INFO] Household 'default' does not exist yet — creating seed data...")
        db.collection("households").document("default").set({
            "name": "Wayne Household",
            "created": datetime.now(timezone.utc),
        })
        print("[PASS] Seed household created.")


def test_read_members():
    """Test reading household members subcollection."""
    members = db.collection("households").document("default").collection("members").stream()
    member_list = list(members)
    if member_list:
        for m in member_list:
            print(f"  - {m.id}: {m.to_dict()}")
        print(f"[PASS] Found {len(member_list)} members")
    else:
        print("[INFO] No members yet. That's OK for a fresh setup.")


if __name__ == "__main__":
    env = os.getenv("FIRESTORE_EMULATOR_HOST")
    print(f"Project: {PROJECT}")
    print(f"Emulator: {env or 'NOT SET (using real Firestore)'}\n")

    test_write_agent_action()
    print()
    test_read_household()
    print()
    test_read_members()
    print("\nDone.")
