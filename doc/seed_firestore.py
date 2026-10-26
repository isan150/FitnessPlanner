"""Seed script for Doc's exercise and nutrition catalog in Firestore."""

from google.cloud import firestore

FIRESTORE_PROJECT = "qwiklabs-gcp-04-98d762769735"

exercises = [
    {
        "id": "goblet-squat",
        "name": "Goblet Squat",
        "muscle_group": "legs",
        "equipment": "dumbbell",
        "difficulty": "beginner",
        "description": "Hold a dumbbell or kettlebell against your chest. Squat until thighs are parallel to the floor.",
        "recommended_sets": "3-4",
        "recommended_reps": "10-12",
    },
    {
        "id": "push-up",
        "name": "Standard Push-Up",
        "muscle_group": "chest",
        "equipment": "bodyweight",
        "difficulty": "beginner",
        "description": "Keep body in a straight plank line. Lower chest to just above floor and press up.",
        "recommended_sets": "3",
        "recommended_reps": "12-15",
    },
    {
        "id": "dumbbell-row",
        "name": "Single-Arm Dumbbell Row",
        "muscle_group": "back",
        "equipment": "dumbbell",
        "difficulty": "beginner",
        "description": "Hinge at the hips with flat back. Pull dumbbell towards your hip, squeezing the lat.",
        "recommended_sets": "3-4",
        "recommended_reps": "8-12",
    },
    {
        "id": "plank",
        "name": "Forearm Plank",
        "muscle_group": "core",
        "equipment": "bodyweight",
        "difficulty": "beginner",
        "description": "Rest on forearms and toes. Maintain a neutral spine and brace core tight.",
        "recommended_sets": "3",
        "recommended_reps": "30-60 sec hold",
    },
    {
        "id": "romanian-deadlift",
        "name": "Dumbbell Romanian Deadlift (RDL)",
        "muscle_group": "legs",
        "equipment": "dumbbell",
        "difficulty": "intermediate",
        "description": "Hinge at hips with slight knee bend. Lower weights until feeling stretch in hamstrings, then squeeze glutes to stand.",
        "recommended_sets": "3",
        "recommended_reps": "10-12",
    },
]

def seed():
    print(f"Connecting to Firestore with project: {FIRESTORE_PROJECT}...")
    db = firestore.Client(project=FIRESTORE_PROJECT)
    collection = db.collection("exercises")
    
    for ex in exercises:
        doc_id = ex["id"]
        data = {k: v for k, v in ex.items() if k != "id"}
        collection.document(doc_id).set(data)
        print(f"✓ Seeded exercise: {ex['name']} ({doc_id})")

    print("\nAll exercises seeded successfully!")

if __name__ == "__main__":
    seed()
