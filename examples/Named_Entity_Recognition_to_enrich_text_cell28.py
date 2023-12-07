def find_all_links(label_entities:dict) -> dict:
    """ 
    Finds all Wikipedia links for the dictionary entities in the whitelist label list.
    """
    whitelist = ['event', 'gpe', 'org', 'person', 'product', 'work_of_art']
    
    return {e: find_link(e) for label, entities in label_entities.items() 
                            for e in entities
                            if label in whitelist}