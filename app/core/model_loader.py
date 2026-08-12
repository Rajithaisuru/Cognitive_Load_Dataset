import os

import joblib


model_path = os.path.join(os.path.dirname(__file__), "..", "..", "model", "cognitive_load_model.pkl")

model = joblib.load(model_path)

print("New Model loaded successfully")
