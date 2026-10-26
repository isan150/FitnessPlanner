# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import re
from typing import Any, Dict, List, Optional
from a2ui.schema.manager import A2uiSchemaManager
from a2ui.basic_catalog.provider import BasicCatalog
from app.a2ui_utils import a2ui_callback
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.code_executors.agent_engine_sandbox_code_executor import AgentEngineSandboxCodeExecutor
from google.adk.tools import ToolContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.cloud import firestore, storage
from google import genai
from google.genai import types

MODEL = "gemini-3.8-flash"
FIRESTORE_PROJECT = "qwiklabs-gcp-04-98d762769735"
GCS_BUCKET_NAME = "doc-fitness-assets-98d762769735"
AGENT_ENGINE_RESOURCE_NAME = "projects/611495102745/locations/us-east1/reasoningEngines/1697741610797760512"


def _get_db() -> firestore.Client:
    return firestore.Client(project=FIRESTORE_PROJECT)


def search_exercises(
    muscle_group: Optional[str] = None,
    equipment: Optional[str] = None,
    difficulty: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Search for exercises in the exercise catalog by muscle group, equipment, or difficulty.

    Args:
        muscle_group: Optional muscle group to filter by (e.g., 'legs', 'chest', 'back', 'core').
        equipment: Optional equipment to filter by (e.g., 'dumbbell', 'bodyweight').
        difficulty: Optional difficulty level (e.g., 'beginner', 'intermediate', 'advanced').

    Returns:
        A list of matching exercise items with their details.
    """
    db = _get_db()
    docs = db.collection("exercises").stream()
    results = []

    for doc in docs:
        item = doc.to_dict()
        item["id"] = doc.id

        if muscle_group and item.get("muscle_group", "").lower() != muscle_group.lower():
            continue
        if equipment and item.get("equipment", "").lower() != equipment.lower():
            continue
        if difficulty and item.get("difficulty", "").lower() != difficulty.lower():
            continue

        results.append(item)

    return results


def get_exercise_details(exercise_id: str) -> Dict[str, Any]:
    """Retrieve full details for a specific exercise by its identifier.

    Args:
        exercise_id: The unique identifier or slug of the exercise (e.g., 'goblet-squat', 'push-up').

    Returns:
        The exercise details dictionary, or an error message if not found.
    """
    db = _get_db()
    doc_ref = db.collection("exercises").document(exercise_id.strip().lower())
    doc = doc_ref.get()
    if not doc.exists:
        return {"error": f"Exercise '{exercise_id}' not found."}
    data = doc.to_dict()
    data["id"] = doc.id
    return data


def add_exercise(
    name: str,
    muscle_group: str,
    equipment: str,
    difficulty: str,
    description: str,
    recommended_sets: str = "3",
    recommended_reps: str = "10-12",
) -> Dict[str, Any]:
    """Add a new exercise to the exercise catalog.

    Args:
        name: Name of the exercise (e.g., 'Overhead Shoulder Press').
        muscle_group: Target muscle group (e.g., 'shoulders', 'legs', 'back', 'chest', 'arms', 'core').
        equipment: Equipment needed (e.g., 'dumbbell', 'barbell', 'bodyweight', 'kettlebell').
        difficulty: Difficulty level ('beginner', 'intermediate', 'advanced').
        description: Brief description of proper execution form and cues.
        recommended_sets: Recommended number of sets (e.g. '3-4').
        recommended_reps: Recommended rep range (e.g. '8-12').

    Returns:
        Confirmation dictionary with the created exercise ID.
    """
    db = _get_db()
    doc_id = re.sub(r"[^a-zA-Z0-9]+", "-", name.lower()).strip("-")
    data = {
        "name": name,
        "muscle_group": muscle_group.lower(),
        "equipment": equipment.lower(),
        "difficulty": difficulty.lower(),
        "description": description,
        "recommended_sets": recommended_sets,
        "recommended_reps": recommended_reps,
    }
    db.collection("exercises").document(doc_id).set(data)
    data["id"] = doc_id
    return {"status": "success", "message": f"Added exercise '{name}'", "exercise": data}


def log_workout(
    user_id: str,
    routine_name: str,
    exercises_completed: List[str],
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """Log a completed workout for a user in the workout_logs collection.

    Args:
        user_id: Identifier of the user (e.g. 'default_user' or username).
        routine_name: Name or description of the routine (e.g. 'Leg Day', 'Full Body Circuit').
        exercises_completed: List of exercise names or IDs performed.
        notes: Optional subjective notes (e.g. 'felt strong', 'used 35 lb dumbbells').

    Returns:
        Confirmation dictionary with the logged workout ID.
    """
    db = _get_db()
    log_data = {
        "user_id": user_id,
        "routine_name": routine_name,
        "exercises_completed": exercises_completed,
        "notes": notes or "",
        "timestamp": firestore.SERVER_TIMESTAMP,
    }
    update_time, doc_ref = db.collection("workout_logs").add(log_data)
    return {"status": "success", "workout_log_id": doc_ref.id, "routine_name": routine_name}


def calculate_macro_targets(
    weight_lbs: float,
    height_inches: float,
    age: int,
    gender: str,
    activity_level: str = "moderate",
    goal: str = "maintenance",
) -> Dict[str, Any]:
    """Calculate daily calorie and macronutrient targets using the Mifflin-St Jeor equation.

    Args:
        weight_lbs: Body weight in pounds.
        height_inches: Height in total inches (e.g. 70 for 5ft 10in).
        age: Age in years.
        gender: Biological sex ('male' or 'female').
        activity_level: Activity multiplier ('sedentary', 'light', 'moderate', 'active', 'very_active').
        goal: Target fitness goal ('fat_loss', 'maintenance', 'muscle_gain').

    Returns:
        A dictionary with BMR, TDEE, target daily calories, and macro breakdown (protein, carbs, fat in grams).
    """
    weight_kg = weight_lbs * 0.453592
    height_cm = height_inches * 2.54

    # Mifflin-St Jeor formula
    if gender.lower() == "male":
        bmr = (10 * weight_kg) + (6.25 * height_cm) - (5 * age) + 5
    else:
        bmr = (10 * weight_kg) + (6.25 * height_cm) - (5 * age) - 161

    multipliers = {
        "sedentary": 1.2,
        "light": 1.375,
        "moderate": 1.55,
        "active": 1.725,
        "very_active": 1.9,
    }
    tdee = bmr * multipliers.get(activity_level.lower(), 1.55)

    if goal.lower() == "fat_loss":
        target_calories = round(tdee - 500)
    elif goal.lower() == "muscle_gain":
        target_calories = round(tdee + 300)
    else:
        target_calories = round(tdee)

    # 1g protein per lb of body weight (4 kcal/g)
    protein_g = round(weight_lbs * 1.0)
    # 25% of calories from fat (9 kcal/g)
    fat_g = round((target_calories * 0.25) / 9)
    # Remaining calories from carbohydrates (4 kcal/g)
    remaining_cals = max(0, target_calories - (protein_g * 4 + fat_g * 9))
    carbs_g = round(remaining_cals / 4)

    return {
        "bmr": round(bmr),
        "tdee": round(tdee),
        "target_calories": target_calories,
        "protein_g": protein_g,
        "carbs_g": carbs_g,
        "fat_g": fat_g,
        "goal": goal,
    }


def get_fruit_nutrition(fruit_name: str) -> Dict[str, Any]:
    """Fetch real nutritional and macronutrient data for a fruit using the public Fruityvice API.

    Args:
        fruit_name: The name of the fruit to look up (e.g., 'banana', 'apple', 'strawberry', 'orange', 'blueberry').

    Returns:
        A dictionary with real calories, carbohydrates, protein, fat, and sugar per 100g.
    """
    import urllib.request
    import json

    cleaned_name = fruit_name.strip().lower()
    url = f"https://www.fruityvice.com/api/fruit/{cleaned_name}"
    req = urllib.request.Request(url, headers={"User-Agent": "DocFitnessAgent/1.0"})

    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
            nutritions = data.get("nutritions", {})
            return {
                "name": data.get("name", fruit_name.capitalize()),
                "family": data.get("family"),
                "calories": nutritions.get("calories"),
                "carbohydrates_g": nutritions.get("carbohydrates"),
                "protein_g": nutritions.get("protein"),
                "fat_g": nutritions.get("fat"),
                "sugar_g": nutritions.get("sugar"),
                "serving_size": "per 100 grams",
            }
    except Exception as e:
        return {"error": f"Could not retrieve nutrition for '{fruit_name}': {str(e)}"}


async def generate_fitness_image(
    prompt: str,
    tool_context: ToolContext,
) -> Dict[str, Any]:
    """Generate a photo or visual representation for a meal, smoothie, exercise, or milestone badge.

    Args:
        prompt: Detailed description of what to visualize (e.g. 'high protein berry smoothie in a tall glass garnished with mint', 'overhead dumbbell shoulder press in a modern gym').
        tool_context: Context supplied by ADK runtime used to save artifacts to the session.

    Returns:
        A dictionary containing the saved artifact filename, the public Cloud Storage image URL, and status.
    """
    import uuid

    # 1. Call gemini-3.1-flash-lite-image model in global region via Vertex AI
    client = genai.Client(
        vertexai=True,
        project=FIRESTORE_PROJECT,
        location="global",
    )

    enhanced_prompt = f"High quality photo in fitness & nutrition domain: {prompt}"
    response = client.models.generate_content(
        model="gemini-3.1-flash-lite-image",
        contents=enhanced_prompt,
    )

    image_bytes = None
    mime_type = "image/jpeg"
    for candidate in response.candidates:
        if candidate.content and candidate.content.parts:
            for part in candidate.content.parts:
                if part.inline_data and part.inline_data.data:
                    image_bytes = part.inline_data.data
                    mime_type = part.inline_data.mime_type or "image/jpeg"
                    break
        if image_bytes:
            break

    if not image_bytes:
        return {"error": "Failed to generate image bytes from model."}

    ext = "jpg" if "jpeg" in mime_type else "png"
    unique_id = str(uuid.uuid4())[:8]
    filename = f"image_{unique_id}.{ext}"

    # 2. Save artifact to ADK session so it appears in Playground's Artifacts panel
    artifact_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
    artifact_version = await tool_context.save_artifact(
        filename=filename,
        artifact=artifact_part,
    )

    # 3. Upload bytes directly to Cloud Storage public bucket without local file
    gcs_client = storage.Client(project=FIRESTORE_PROJECT)
    bucket = gcs_client.bucket(GCS_BUCKET_NAME)
    blob = bucket.blob(filename)
    blob.upload_from_string(image_bytes, content_type=mime_type)
    public_url = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{filename}"

    return {
        "status": "success",
        "filename": filename,
        "artifact_version": artifact_version,
        "public_image_url": public_url,
        "markdown_embed": f"![{prompt}]({public_url})",
    }


# WRITE: after each turn, send the session to Memory Bank for extraction.
async def generate_memories_callback(callback_context: CallbackContext):
    await callback_context.add_session_to_memory()
    return None


# A2UI Schema Manager setup (v0.8 with Basic Catalog)
schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

a2ui_instruction = schema_manager.generate_system_prompt(
    role_description=(
        "You are Doc, an adaptive and knowledgeable fitness, workout, and nutrition coach. "
        "Your mission is to help users reach their fitness goals through safe, structured exercise plans "
        "and sound nutritional principles. You remember the user's stated preferences, past workouts, injuries, "
        "dietary restrictions, and fitness goals from previous conversations and use them to personalize your coaching. "
        "You have access to a secure code execution sandbox, a Firestore-backed catalog of exercises, a workout logger, "
        "a calorie/macro calculator, real fruit nutrition lookup, and an image generator: "
        "- You have an isolated Python code execution sandbox. Write and execute Python code when you need to perform "
        "complex custom data analysis, calculate progression percentages, project volume loads, or evaluate custom mathematical formulas. "
        "- Use search_exercises to find exercises targeting specific muscle groups, equipment, or difficulty levels. "
        "- Use get_exercise_details to retrieve specific technique cues, recommended sets, and reps. "
        "- Use add_exercise if the user wants to add a custom movement to their library. "
        "- Use log_workout when a user shares that they completed a session. "
        "- Use calculate_macro_targets when the user asks for nutrition, calorie, or macro recommendations based on stats and goals. "
        "- Use get_fruit_nutrition to fetch real nutritional data (calories, carbs, sugar, protein, fats per 100g). "
        "- Use generate_fitness_image whenever the user requests an image, photo, or visual idea. The tool returns a public https URL. "
        "Always be encouraging, prioritize proper form, and adapt recommendations to the user's goals and equipment access."
    ),
    workflow_description="Analyze the request and return structured UI when appropriate.",
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        '{"Image": {"url": {"literalString": "https://..."}}}. Never point an '
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    code_executor=AgentEngineSandboxCodeExecutor(
        agent_engine_resource_name=AGENT_ENGINE_RESOURCE_NAME,
    ),
    instruction=a2ui_instruction,
    tools=[
        PreloadMemoryTool(),
        search_exercises,
        get_exercise_details,
        add_exercise,
        log_workout,
        calculate_macro_targets,
        get_fruit_nutrition,
        generate_fitness_image,
    ],
    after_model_callback=a2ui_callback,
    after_agent_callback=generate_memories_callback,
)

app = App(
    root_agent=root_agent,
    name="app",
)

