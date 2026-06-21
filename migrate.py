import json
import os
import re
import time

def clean_and_split_date_range(date_str):
    """
    Analyse une chaîne de date pour détecter s'il s'agit d'une plage.
    Si c'est le cas, sépare et nettoie la date de début et la date de fin.
    Prend en compte l'absence d'espaces autour du tiret et les mois textuels (ex: Juillet 1942-Février 1943).
    """
    if not date_str:
        return None, None
        
    # Normalisation de tous les types de tirets (tiret long, en-dash, em-dash) vers le tiret standard
    normalized = date_str.replace("–", "-").replace("—", "-")
    
    # 1. Cas simple : Séparateur déjà propre avec espaces " - "
    if " - " in normalized:
        parts = normalized.split(" - ")
        if len(parts) == 2:
            return parts[0].strip(), parts[1].strip()
            
    # 2. Recherche d'un tiret de plage (deux années à 4 chiffres de part et d'autre d'un tiret)
    # Ex: "1914-1918" ou "18-06-1940-19-06-1940" (sépare au milieu)
    hyphen_indices = [i for i, char in enumerate(normalized) if char == '-']
    for idx in hyphen_indices:
        left = normalized[:idx].strip()
        right = normalized[idx+1:].strip()
        # Si les deux côtés contiennent une année à 4 chiffres, c'est le bon séparateur de plage
        if re.search(r'\b\d{4}\b', left) and re.search(r'\b\d{4}\b', right):
            return left, right
            
    # 3. Cas de repli : S'il y a un seul et unique tiret dans toute la chaîne (sans espaces)
    # Ex: "Juillet 1942-Février 1943"
    if normalized.count('-') == 1:
        idx = normalized.index('-')
        left = normalized[:idx].strip()
        right = normalized[idx+1:].strip()
        if left and right:
            return left, right
            
    return None, None

def migrate_old_database(old_filepath="dates.json", new_filepath="revis-brevet.json"):
    """
    Migre une base de données intermédiaire ou ancienne vers la structure multi-matières finale.
    Associe les thèmes/chapitres existants à la matière par défaut 'Histoire'.
    Met en relation les fiches 'dates' avec leur 'chapterId' stable et ajoute un ID unique.
    Prend en compte, nettoie et standardise automatiquement les plages de dates.
    """
    if not os.path.exists(old_filepath):
        print(f"Erreur : Le fichier d'origine {old_filepath} n'existe pas dans ce dossier.")
        return

    try:
        with open(old_filepath, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
    except Exception as e:
        print(f"Erreur lors de la lecture du fichier : {e}")
        return

    # Extraction ou initialisation des composants
    old_settings = {}
    old_dates = []

    if isinstance(raw_data, dict):
        old_settings = raw_data.get("settings", {})
        old_dates = raw_data.get("dates", [])
    elif isinstance(raw_data, list):
        old_dates = raw_data
        old_settings = {"themes": [], "chapters": []}
    else:
        print("Format de fichier non reconnu.")
        return

    # Vérification si la migration est requise
    needs_migration = False
    
    if "subjects" not in old_settings:
        needs_migration = True

    if not needs_migration:
        for card in old_dates:
            old_date_val = card.get("date", "")
            start, end = clean_and_split_date_range(old_date_val)
            is_range = (start is not None and end is not None)
            card_type = card.get("type", "date")
            
            # 1. Vérification des champs de base
            if "chapterId" not in card or "id" not in card or "type" not in card:
                needs_migration = True
                break
            
            # 2. Vérification si c'est une plage de dates mais typée comme simple "date"
            if is_range and card_type == "date":
                needs_migration = True
                break
                
            # 3. Vérification si la plage n'est pas proprement formatée avec les espaces " - "
            if is_range and " - " not in old_date_val:
                needs_migration = True
                break

    if not needs_migration:
        print("La base de données semble déjà parfaitement à jour avec les ID stables, types de fiches et la structure multi-matières.")
        return

    print(f"Détection de {len(old_dates)} fiches à migrer ou à enrichir. Début de la conversion...")

    # 1. Traitement de la matière par défaut
    subject_id = "sub_histoire"
    subjects_list = [{"id": subject_id, "name": "Histoire"}]

    # 2. Conversion et sécurisation des Thèmes existants
    themes_list = old_settings.get("themes", [])
    themes_map_by_name = {}
    
    for theme in themes_list:
        if "subjectId" not in theme:
            theme["subjectId"] = subject_id
        themes_map_by_name[theme["name"].strip().lower()] = theme["id"]

    # 3. Conversion et sécurisation des Chapitres existants
    chapters_list = old_settings.get("chapters", [])
    chapters_map_by_name = {}
    
    for chapter in chapters_list:
        if "subjectId" not in chapter:
            chapter["subjectId"] = subject_id
        chapters_map_by_name[chapter["name"].strip().lower()] = chapter["id"]

    # 4. Conversion et association des Fiches de révisions
    new_cards = []
    timestamp = int(time.time())

    for index, old_card in enumerate(old_dates):
        card_id = old_card.get("id", f"card_{index + 1}_{timestamp}")
        
        # Détection automatique du type de fiche (plage de dates ou date simple)
        old_date_val = old_card.get("date", "").strip()
        start, end = clean_and_split_date_range(old_date_val)
        
        detected_type = "date"
        if old_card.get("type"):
            detected_type = old_card["type"]
        elif start and end:
            detected_type = "plage"

        theme_name = old_card.get("theme", "").strip()
        chapter_name = old_card.get("chapter", "").strip()
        chapter_id = old_card.get("chapterId", None)

        # Si pas de chapterId, on tente de le résoudre via le nom du chapitre
        if not chapter_id and chapter_name:
            chap_key = chapter_name.lower()
            if chap_key in chapters_map_by_name:
                chapter_id = chapters_map_by_name[chap_key]
            else:
                # Création dynamique du chapitre s'il n'existe pas dans settings
                chapter_id = f"c_auto_{len(chapters_list) + 1}_{timestamp}"
                
                # Résolution ou création du thème parent lié
                theme_id = None
                if theme_name:
                    theme_key = theme_name.lower()
                    if theme_key in themes_map_by_name:
                        theme_id = themes_map_by_name[theme_key]
                    else:
                        theme_id = f"t_auto_{len(themes_list) + 1}_{timestamp}"
                        themes_list.append({
                            "id": theme_id,
                            "subjectId": subject_id,
                            "name": theme_name
                        })
                        themes_map_by_name[theme_key] = theme_id

                chapters_list.append({
                    "id": chapter_id,
                    "themeId": theme_id,
                    "subjectId": subject_id,
                    "name": chapter_name
                })
                chapters_map_by_name[chap_key] = chapter_id

        # Reconstruction de la fiche nettoyée et enrichie
        migrated_card = {
            "id": card_id,
            "type": detected_type,
            "level": int(old_card.get("level", 0)),
            "chapterId": chapter_id
        }

        # Distribution des attributs selon le type de carte
        if detected_type == "definition":
            migrated_card["term"] = old_card.get("term", "").strip()
            migrated_card["definition"] = old_card.get("definition", "").strip()
        elif detected_type == "formula":
            migrated_card["formulaName"] = old_card.get("formulaName", "").strip()
            migrated_card["formula"] = old_card.get("formula", "").strip()
        else:
            # Type date simple ou plage de dates
            if start and end:
                # Écrit la plage sous son format standardisé "Début - Fin"
                migrated_card["date"] = f"{start} - {end}"
            else:
                migrated_card["date"] = old_date_val
                
            migrated_card["dateFormat"] = old_card.get("dateFormat", "Année").strip()
            migrated_card["event"] = old_card.get("event", "").strip()

        # Conserver l'explication si elle existe
        if "explanation" in old_card and old_card["explanation"]:
            migrated_card["explanation"] = old_card["explanation"].strip()

        new_cards.append(migrated_card)

    # Assemblage final de la nouvelle structure
    new_db = {
        "settings": {
            "subjects": subjects_list,
            "themes": themes_list,
            "chapters": chapters_list
        },
        "dates": new_cards
    }

    try:
        with open(new_filepath, "w", encoding="utf-8") as f:
            json.dump(new_db, f, indent=2, ensure_ascii=False)
        print(f"\nMigration réussie avec succès !")
        print(f"Structure finale exportée dans '{new_filepath}' :")
        print(f" - Matières : {len(subjects_list)}")
        print(f" - Thèmes : {len(themes_list)}")
        print(f" - Chapitres : {len(chapters_list)}")
        print(f" - Fiches de révisions liées : {len(new_cards)} (dont {sum(1 for c in new_cards if c['type'] == 'plage')} plages proprement séparées)")
    except Exception as e:
        print(f"Erreur lors de l'écriture du fichier de sortie : {e}")

if __name__ == "__main__":
    migrate_old_database()