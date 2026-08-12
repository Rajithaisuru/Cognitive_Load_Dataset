def map_paas_to_cognitive_load(paas_rating: int) -> tuple[int, str]:
    if paas_rating in (1, 2):
        return 1, "Very Low"
    if paas_rating in (3, 4):
        return 2, "Low"
    if paas_rating == 5:
        return 3, "Medium"
    if paas_rating in (6, 7):
        return 4, "High"
    if paas_rating in (8, 9):
        return 5, "Very High"

    raise ValueError("Paas rating must be between 1 and 9.")

