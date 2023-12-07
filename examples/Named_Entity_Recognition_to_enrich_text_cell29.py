def enrich_entities(text: str, label_entities: dict) -> str:
    """
    Enriches text with knowledge base links.
    """
    entity_link_dict = find_all_links(label_entities)
    logging.info(f"entity_link_dict: {entity_link_dict}")
    
    for entity, link in entity_link_dict.items():
        text = text.replace(entity, f"[{entity}]({link})")

    return text